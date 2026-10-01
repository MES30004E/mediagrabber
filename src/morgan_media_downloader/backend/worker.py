"""Bounded JSONL transport. stdout is protocol-only; no third-party text relay."""
from __future__ import annotations

import io
import json
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
    except (ValueError, UnicodeError):
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
    def write(self, value): return len(value)
    def flush(self): pass


def main() -> int:
    # Capture the protocol pipe before suppressing library stdout/stderr. Engine
    # diagnostics use the explicit structured callback instead of text scraping.
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = QuietLibraryStream()
    try:
        return run(input_stream, output_stream)
    except BrokenPipeError:
        return 0
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
