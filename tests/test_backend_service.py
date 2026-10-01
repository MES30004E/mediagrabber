import json
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from morgan_media_downloader.backend.service import BackendService
from morgan_media_downloader.backend.protocol import parse_command
from morgan_media_downloader.yt_runtime import RuntimeSnapshot
from test_backend_protocol import command


class FixtureYDL:
    calls = []
    entered = None
    release = None
    private = False

    def __init__(self, params): self.params = params
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def extract_info(self, target, download=False):
        self.calls.append((target, self.params.copy()))
        if self.entered:
            self.entered.set(); assert self.release.wait(5)
        if self.private and 'cookiesfrombrowser' not in self.params:
            raise RuntimeError('Private playlist: authentication required token=private-value')
        if self.params.get('skip_download'):
            return {'title': 'Collection', 'entries': [{'title': 'Selected video', 'webpage_url': 'https://youtube.test/video', 'playlist_index': 1}]}
        return {'title': 'Selected video', 'ext': 'mp4', 'formats': [
            {'format_id': 'v', 'url': 'internal', 'height': 720, 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'aac'}]}
    def process_ie_result(self, info, download=True):
        for hook in self.params.get('progress_hooks', []):
            hook({'status': 'downloading', 'downloaded_bytes': 32, 'total_bytes': 64})
        output = Path(self.params['outtmpl'].replace('%(title)s', info['title']).replace('%(ext)s', 'mp4'))
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(b'fixture media')
        for hook in self.params.get('post_hooks', []): hook(str(output))
        return {**info, 'filepath': str(output)}
    def prepare_filename(self, info): return ''


@pytest.fixture
def service():
    FixtureYDL.calls = []; FixtureYDL.entered = None; FixtureYDL.release = None; FixtureYDL.private = False
    messages = []
    worker = BackendService(messages.append, runtime_factory=lambda: RuntimeSnapshot('fixture', 'Bundled', FixtureYDL))
    hello = send(worker, 'session.hello', {'supported_versions': ['1.0']}, hello=True)
    assert messages[0]['payload']['status'] == 'completed'
    assert messages[1]['type'] == 'session.ready'
    yield worker, messages
    if FixtureYDL.release: FixtureYDL.release.set()
    worker.close()


def send(worker, kind, payload, hello=False, job_id=None):
    raw = command(kind, payload, None if hello else worker.session_id, job_id)
    worker.handle(parse_command(json.dumps(raw).encode()))
    return raw['request_id']


def events(messages, kind):
    return [m for m in messages if m['type'] == kind and m['kind'] == 'event']


@pytest.mark.parametrize('input,target', [
    ('ordinary text', 'ytsearch10:ordinary text'), (':ytwatchlater', ':ytwatchlater'),
    ('https://www.youtube.com/feed/watch_later', 'https://www.youtube.com/playlist?list=WL'),
    ('https://www.youtube.com/watch?v=fixture', 'https://www.youtube.com/watch?v=fixture'),
])
def test_analysis_uses_existing_parser_and_item_flow(service, input, target):
    worker, messages = service
    request_id = send(worker, 'analysis.start', {'inputs': [input]})
    assert worker.wait_idle(5)
    assert FixtureYDL.calls[0][0] == target
    assert [m['type'] for m in messages if m['request_id'] == request_id] == [
        'analysis.start', 'analysis.started', 'analysis.item', 'analysis.completed']
    item = events(messages, 'analysis.item')[0]
    assert item['payload']['item']['title'] == 'Selected video'
    assert item['payload']['item']['collection_title'] == 'Collection'
    assert item['source_id'] == item['payload']['item']['source_id']
    assert events(messages, 'analysis.completed')[0]['payload']['count'] == 1


def test_private_auth_proxy_provider_preserved_by_real_policy(service):
    worker, messages = service; FixtureYDL.private = True
    send(worker, 'analysis.start', {'inputs': [':ytwatchlater'], 'config': {
        'authentication_mode': 'Auto', 'cookies_browser': 'Firefox', 'browser_profile': 'qa',
        'provider_url': 'http://127.0.0.1:4416',
        'proxy': {'mode': 'Custom SOCKS5 Proxy', 'host': '127.0.0.1', 'port': 1080}}})
    assert worker.wait_idle(5)
    assert len(FixtureYDL.calls) == 2
    options = FixtureYDL.calls[1][1]
    assert options['cookiesfrombrowser'] == ('firefox', 'qa', None, None)
    assert options['proxy'] == 'socks5h://127.0.0.1:1080'
    assert options['extractor_args']['youtubepot-bgutilhttp']['base_url'] == ['http://127.0.0.1:4416']
    assert events(messages, 'auth.required')
    assert events(messages, 'analysis.completed')[0]['payload']['effective_authentication'] == 'Auto -> Browser Cookies'
    assert 'private-value' not in json.dumps(messages)


def test_explicit_private_failure_is_safe_and_never_drops_auth(service, monkeypatch):
    worker, messages = service
    def fail(self, target, download=False):
        FixtureYDL.calls.append((target, self.params.copy()))
        raise RuntimeError('Private playlist: auth required cookie=private-value /private/cookies.txt')
    monkeypatch.setattr(FixtureYDL, 'extract_info', fail)
    send(worker, 'analysis.start', {'inputs': [':ytwatchlater'], 'config': {'authentication_mode': 'Browser Cookies'}})
    assert worker.wait_idle(5)
    assert len(FixtureYDL.calls) == 1
    assert events(messages, 'auth.failed')
    assert events(messages, 'analysis.failed')
    assert 'private-value' not in json.dumps(messages) and '/private/cookies.txt' not in json.dumps(messages)


def test_analysis_cancel_waits_for_legacy_extraction_and_discards_late_items(service):
    worker, messages = service
    FixtureYDL.entered = threading.Event(); FixtureYDL.release = threading.Event()
    request = send(worker, 'analysis.start', {'inputs': ['waiting']})
    assert FixtureYDL.entered.wait(5)
    send(worker, 'analysis.cancel', {'target_request_id': request})
    assert not worker.wait_idle(.01)
    assert not events(messages, 'analysis.cancelled')
    FixtureYDL.release.set(); assert worker.wait_idle(5)
    assert events(messages, 'analysis.cancelled')[0]['request_id'] == request
    assert not events(messages, 'analysis.item') and not events(messages, 'analysis.completed')


def test_download_retains_job_identity_and_uses_existing_hooks(service, tmp_path):
    worker, messages = service
    analysis = send(worker, 'analysis.start', {'inputs': ['https://youtube.test/video']})
    assert worker.wait_idle(5)
    source_id = events(messages, 'analysis.item')[0]['source_id']
    download = send(worker, 'jobs.enqueue', {'analysis_request_id': analysis, 'source_ids': [source_id],
        'options': {'download_dir': str(tmp_path), 'compatibility': 'Original / Best Available', 'verify_postprocessing': False}})
    assert worker.wait_idle(5)
    started = events(messages, 'download.started')[0]
    progress = next(m for m in events(messages, 'download.progress') if m['payload']['downloaded_bytes'] == 32)
    completed = events(messages, 'download.completed')[0]
    assert started['job_id'] == progress['job_id'] == completed['job_id']
    assert started['attempt_id'] == completed['attempt_id']
    assert started['request_id'] == download
    assert progress['payload']['downloaded_bytes'] == 32
    assert completed['payload']['status'] == 'Completed'
    assert (tmp_path / 'Selected video.mp4').exists()


def test_duplicate_request_and_wrong_session_do_not_repeat_engine_work(service):
    worker, messages = service
    raw = command('analysis.start', {'inputs': ['search']}, worker.session_id)
    parsed = parse_command(json.dumps(raw).encode())
    worker.handle(parsed); assert worker.wait_idle(5); worker.handle(parsed)
    assert len(FixtureYDL.calls) == 1
    wrong = command('analysis.start', {'inputs': ['search']}, str(uuid4()))
    worker.handle(parse_command(json.dumps(wrong).encode()))
    assert messages[-1]['payload']['error']['code'] == 'session.mismatch'
    assert len(FixtureYDL.calls) == 1


def test_unknown_cancellation_target_and_shutdown_response(service):
    worker, messages = service
    send(worker, 'analysis.cancel', {'target_request_id': str(uuid4())})
    assert messages[-1]['payload']['status'] == 'rejected'
    shutdown = send(worker, 'session.shutdown', {})
    assert messages[-1]['request_id'] == shutdown and messages[-1]['payload']['status'] == 'completed'
