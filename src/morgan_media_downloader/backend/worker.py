"""Bounded JSONL transport. stdout is protocol-only; no third-party text relay."""
from __future__ import annotations

import io
import json
import os
import sys
import threading

from .protocol import MAX_FRAME_BYTES, ProtocolError, identifier, parse_command
from .service import BackendService


class JsonLineWriter:
    def __init__(self, stream):
        self.stream = stream
        self.lock = threading.Lock()

    def __call__(self, message):
        frame = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(frame) > MAX_FRAME_BYTES:
            raise ProtocolError('protocol.frame_too_large')
        with self.lock:
            self.stream.write(frame + b'\n')
            self.stream.flush()


def _request_identity(frame):
    try:
        value = json.loads(frame)
        return identifier(value.get('request_id')) if isinstance(value, dict) else None
    except (ValueError, UnicodeError, RecursionError):
        return None


def run(input_stream, output_stream) -> int:
    service = BackendService(JsonLineWriter(output_stream))
    malformed = 0
    try:
        while True:
            frame = input_stream.readline(MAX_FRAME_BYTES + 2)
            if not frame:
                break
            try:
                if len(frame.rstrip(b'\r\n')) > MAX_FRAME_BYTES:
                    while frame and not frame.endswith(b'\n'):
                        frame = input_stream.readline(MAX_FRAME_BYTES + 2)
                    raise ProtocolError('protocol.frame_too_large')
                command = parse_command(frame)
            except ProtocolError as exc:
                service.protocol_error(exc.code, _request_identity(frame))
                malformed += 1
                if malformed >= 3: break
                continue
            malformed = 0
            if not service.handle(command): break
    finally:
        service.close()
    return 0


class QuietLibraryStream(io.TextIOBase):
    """Unstructured dependency output is discarded, not trusted to carry no secrets."""
    def __init__(self, fd):
        self.fd = fd
    def write(self, value): return len(value)
    def flush(self): pass
    def fileno(self): return self.fd


def main() -> int:
    # Capture the protocol pipe before suppressing library stdout/stderr. Engine
    # diagnostics use the explicit structured callback instead of text scraping.
    input_stream = sys.stdin.buffer
    old_stdout, old_stderr = sys.stdout, sys.stderr
    old_stdout.flush(); old_stderr.flush()
    protocol_fd = os.dup(old_stdout.fileno())
    saved_stdout_fd, saved_stderr_fd = os.dup(1), os.dup(2)
    output_stream = os.fdopen(protocol_fd, 'wb', buffering=0)
    # Native libraries and engine children inherit descriptors, not sys.stdout.
    # Keep the protocol on a private non-inheritable duplicate and silence both
    # dependency descriptors as well as Python-level streams.
    with open(os.devnull, 'wb') as sink:
        os.dup2(sink.fileno(), 1); os.dup2(sink.fileno(), 2)
    sys.stdout, sys.stderr = QuietLibraryStream(1), QuietLibraryStream(2)
    try:
        return run(input_stream, output_stream)
    except BrokenPipeError:
        return 0
    finally:
        output_stream.close()
        os.dup2(saved_stdout_fd, 1); os.dup2(saved_stderr_fd, 2)
        os.close(saved_stdout_fd); os.close(saved_stderr_fd)
        sys.stdout, sys.stderr = old_stdout, old_stderr
