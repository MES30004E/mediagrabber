"""Phase 1 in-memory operation owner. Does not read/write Qt settings or its DB."""
from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from ..auth import requires_authentication
from ..downloader import analyse_with_authentication, download_job
from ..models import DownloadJob, JobStatus
from ..parsing import split_input
from ..yt_runtime import RuntimeSnapshot
from .adapters import error_payload, media_payload, options_from_payload, progress_payload, safe_text
from .protocol import Command, CommandType, Configuration, EventType, MAX_FRAME_BYTES, VERSION


def bundled_runtime() -> RuntimeSnapshot:
    from yt_dlp import YoutubeDL, version
    return RuntimeSnapshot(version.__version__, 'Bundled', YoutubeDL)


@dataclass
class Operation:
    command: Command
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    job: DownloadJob | None = None
    source_id: str | None = None
    attempt_id: str | None = None
    revision: int = 0
    started: bool = False
    finished: bool = False


class BackendService:
    def __init__(self, emit, runtime_factory=None):
        self.emit = emit
        self.runtime_factory = runtime_factory or bundled_runtime
        self.session_id = str(uuid4())
        self.lock = threading.RLock()
        self.sequence = 0
        self.ready = False
        self.closed = False
        self.operations: dict[str, Operation] = {}
        self.jobs: dict[str, Operation] = {}
        self.sources: dict[str, tuple[str, object, Configuration]] = {}
        self.completed_analyses: set[str] = set()
        self.responses = OrderedDict()
        self.seen: set[str] = set()

    def _send(self, kind, type, command=None, payload=None, operation=None, source_id=None):
        with self.lock:
            self.sequence += 1
            message = {'protocol_version': VERSION, 'kind': kind, 'type': str(type.value if isinstance(type, EventType) else type),
                       'request_id': command.request_id if command else None, 'session_id': self.session_id,
                       'job_id': operation.job.id if operation and operation.job else (command.job_id if command else None),
                       'source_id': source_id or (operation.source_id if operation else None),
                       'timestamp': datetime.now(timezone.utc).isoformat(), 'sequence': self.sequence,
                       'payload': payload or {}}
            if operation and operation.job:
                message.update(job_revision=operation.revision, attempt_id=operation.attempt_id)
            self.emit(message)

    def protocol_error(self, code, request_id=None):
        with self.lock:
            self._send('event', EventType.ERROR, payload={'error': error_payload(code)})

    def _respond(self, command, status, result=None, code=None):
        payload = {'status': status}
        payload['error' if code else 'result'] = error_payload(code) if code else (result or {})
        self.responses[command.request_id] = payload
        self.seen.add(command.request_id)
        while len(self.responses) > 4096:
            self.responses.popitem(last=False)
        self._send('response', command.type.value, command, payload)

    def handle(self, command: Command) -> bool:
        # Shutdown must join without the state lock held: workers need it to finish.
        if command.type == CommandType.SHUTDOWN:
            with self.lock:
                if not self._validate_session(command):
                    return True
            self.close()
            with self.lock:
                self._respond(command, 'completed')
            return False
        with self.lock:
            if not self._validate_session(command):
                return True
            if command.request_id in self.seen:
                payload = self.responses.get(command.request_id)
                if payload is not None:
                    self._send('response', command.type.value, command, payload)
                else:
                    self._send('response', command.type.value, command,
                               {'status': 'rejected', 'error': error_payload('request.expired')})
                return True
            if len(self.seen) >= 65536:
                self._send('response', command.type.value, command,
                           {'status': 'rejected', 'error': error_payload('session.limit')})
                return True
            if command.type == CommandType.HELLO:
                if VERSION not in command.payload.supported_versions:
                    self._respond(command, 'rejected', code='protocol.unsupported_version')
                    return True
                self.ready = True
                result = {'selected_version': VERSION, 'capabilities': [v.value for v in CommandType],
                          'max_frame_bytes': MAX_FRAME_BYTES, 'max_analysis_inputs': 100,
                          'max_concurrent_operations': 4, 'max_session_items': 4096,
                          'durable_jobs': False, 'runtime_source': 'bundled', 'secret_ipc': False}
                self._respond(command, 'completed', result)
                self._send('event', EventType.READY, command, result)
            elif command.type == CommandType.PING:
                self._respond(command, 'completed')
            elif command.type == CommandType.ANALYSE:
                if self._active_count() >= 4 or len(self.operations) >= 4096:
                    self._respond(command, 'rejected', code='worker.capacity')
                else:
                    op = Operation(command)
                    self.operations[command.request_id] = op
                    self._respond(command, 'accepted', {'operation_id': command.request_id})
                    self._start(op, self._analyse)
            elif command.type == CommandType.DOWNLOAD:
                self._enqueue(command)
            elif command.type in (CommandType.CANCEL_ANALYSIS, CommandType.CANCEL_JOB):
                op = (self.operations.get(command.payload.target_request_id) if command.type == CommandType.CANCEL_ANALYSIS
                      else self.jobs.get(command.job_id))
                if not op or op.finished or (command.type == CommandType.CANCEL_ANALYSIS and op.job):
                    self._respond(command, 'rejected', code='operation.not_active')
                else:
                    if op.job and command.payload.expected_job_revision != op.revision:
                        self._respond(command, 'rejected', code='state.conflict')
                    else:
                        op.stop.set()
                        self._respond(command, 'accepted', {'cancellation': 'requested'})
            return True

    def _validate_session(self, command):
        if self.closed:
            self._send('response', command.type.value, command, {'status': 'rejected', 'error': error_payload('session.closed')})
            return False
        if command.type == CommandType.HELLO:
            valid = command.session_id is None or command.session_id == self.session_id
        else:
            valid = self.ready and command.session_id == self.session_id
        if not valid:
            self._send('response', command.type.value, command,
                       {'status': 'rejected', 'error': error_payload('session.mismatch' if self.ready else 'session.hello_required')})
        return valid

    def _active_count(self):
        return sum(not op.finished for op in (*self.operations.values(), *self.jobs.values()))

    def _start(self, op, target):
        op.thread = threading.Thread(target=target, args=(op,), name='morgan-backend-operation')
        op.thread.start()

    def _event(self, op, kind, payload=None, source_id=None):
        self._send('event', kind, op.command, payload, op, source_id)

    def _analyse(self, op):
        count = 0
        effective = ''
        try:
            self._event(op, EventType.ANALYSIS_STARTED, {'operation_id': op.command.request_id})
            config = op.command.payload.config
            runtime = self.runtime_factory()
            for raw in op.command.payload.inputs:
                for value in split_input(raw):
                    if op.stop.is_set(): break
                    def status(message):
                        if 'Authentication required' in message:
                            self._event(op, EventType.AUTH_REQUIRED, {'mode': config.authentication_mode})
                    items, effective = analyse_with_authentication(
                        value, config.proxy_url, config.provider_url, config.provider_home,
                        config.authentication_mode, config.cookies_browser, config.browser_profile,
                        config.cookies_file, runtime, status)
                    for item in items:
                        with self.lock:
                            if op.stop.is_set(): break
                            if len(self.sources) >= 4096: raise RuntimeError('capacity')
                            source_id = str(uuid4())
                            self.sources[source_id] = (op.command.request_id, copy.deepcopy(item), config)
                            count += 1
                            self._event(op, EventType.ANALYSIS_ITEM, {'item': media_payload(item, source_id)}, source_id)
            with self.lock:
                if op.stop.is_set():
                    self._event(op, EventType.ANALYSIS_CANCELLED)
                else:
                    self.completed_analyses.add(op.command.request_id)
                    self._event(op, EventType.ANALYSIS_COMPLETED, {'count': count, 'effective_authentication': safe_text(effective)})
                op.finished = True
        except Exception as exc:
            with self.lock:
                if op.stop.is_set():
                    self._event(op, EventType.ANALYSIS_CANCELLED)
                else:
                    if requires_authentication(exc):
                        self._event(op, EventType.AUTH_FAILED, {'error': error_payload('auth.failed', 'auth', 'analysis', 'Authentication was not accepted.')})
                    self._event(op, EventType.ANALYSIS_FAILED,
                                {'error': error_payload('analysis.failed', 'extraction', 'analysis', 'Analysis failed. Check authentication, connection and provider settings.')})
                op.finished = True

    def _enqueue(self, command):
        payload = command.payload
        entries = [self.sources.get(s) for s in payload.source_ids]
        if (payload.analysis_request_id not in self.completed_analyses or any(
                not entry or entry[0] != payload.analysis_request_id for entry in entries)):
            self._respond(command, 'rejected', code='analysis.selection_invalid')
            return
        if self._active_count() + len(entries) > 4 or len(self.jobs) + len(entries) > 4096:
            self._respond(command, 'rejected', code='worker.capacity')
            return
        options = options_from_payload(payload.options)
        if not options.download_dir.strip():
            self._respond(command, 'rejected', code='download.destination_required')
            return
        ops = []
        for source_id, entry in zip(payload.source_ids, entries):
            _, item, analysis_config = entry
            config = payload.config or analysis_config
            selected_options = copy.deepcopy(options)
            selected_options.authentication_mode = config.authentication_mode
            selected_options.cookies_browser = config.cookies_browser
            selected_options.browser_profile = config.browser_profile
            selected_options.cookies_file = config.cookies_file
            op = Operation(command, job=DownloadJob(copy.deepcopy(item), selected_options),
                           source_id=source_id, attempt_id=str(uuid4()), revision=1)
            self.jobs[op.job.id] = op
            ops.append((op, config))
        self._respond(command, 'accepted', {'jobs': [{'job_id': op.job.id, 'source_id': op.source_id,
                       'attempt_id': op.attempt_id, 'job_revision': op.revision} for op, _ in ops]})
        for op, config in ops:
            self._start(op, lambda current, c=config: self._download(current, c))

    def _download(self, op, config):
        try:
            runtime = self.runtime_factory()
            def progress(job):
                with self.lock:
                    if op.stop.is_set(): return
                    op.revision += 1
                    if job.active_transfer_task and job.formats_playable and not op.started:
                        op.started = True
                        self._event(op, EventType.DOWNLOAD_STARTED, {'runtime_version': runtime.version,
                                                                    'formats_playable': job.formats_playable})
                    kind = EventType.DOWNLOAD_PROCESSING if job.active_postprocess_task or job.status == JobStatus.CONVERTING else EventType.DOWNLOAD_PROGRESS
                    self._event(op, kind, progress_payload(job))
            def diagnostic(category, message, level):
                # Third-party strings stay out of IPC; no paths, headers or exceptions.
                self._event(op, EventType.DIAGNOSTIC, {'category': safe_text(category, 32), 'level': safe_text(level, 16),
                                                     'safe_message': 'Backend engine diagnostic.'})
            result = download_job(op.job, config.proxy_url, config.provider_url, config.provider_home,
                                  progress, op.stop, runtime, diagnostic)
            with self.lock:
                op.revision += 1
                if op.stop.is_set():
                    self._event(op, EventType.JOB_CANCELLED, {'retained_files': True})
                elif result.status == JobStatus.FAILED:
                    if requires_authentication(result.error):
                        self._event(op, EventType.AUTH_FAILED, {'error': error_payload('auth.failed', 'auth', 'download', 'Authentication was not accepted.')})
                    self._event(op, EventType.DOWNLOAD_FAILED, {'error': error_payload('download.failed', 'transfer', 'download', 'Download failed. Check the source and settings.')})
                else:
                    self._event(op, EventType.DOWNLOAD_COMPLETED, {'status': result.status.value,
                        'final_files': [safe_text(v, 8192) for v in result.final_files[:100]],
                        'warnings': [safe_text(v) for v in result.warnings[:100]],
                        'verification_performed': bool(result.verification)})
                op.finished = True
        except Exception:
            with self.lock:
                self._event(op, EventType.JOB_CANCELLED if op.stop.is_set() else EventType.DOWNLOAD_FAILED,
                            {'error': error_payload('download.failed', 'transfer', 'download')})
                op.finished = True

    def wait_idle(self, timeout):
        deadline = time.monotonic() + timeout
        with self.lock:
            threads = [op.thread for op in (*self.operations.values(), *self.jobs.values()) if op.thread]
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        return all(not t.is_alive() for t in threads)

    def close(self):
        with self.lock:
            self.closed = True
            ops = list(self.operations.values()) + list(self.jobs.values())
            for op in ops:
                if not op.finished: op.stop.set()
        for op in ops:
            if op.thread: op.thread.join()
