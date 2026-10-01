import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from morgan_media_downloader.backend.worker import run
from morgan_media_downloader.backend.protocol import MAX_FRAME_BYTES
from test_backend_protocol import command


ROOT = Path(__file__).resolve().parents[1]


def decoded(output):
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [m['sequence'] for m in messages] == list(range(1, len(messages) + 1))
    return messages


def test_stream_hello_then_eof_exits_with_only_json():
    output = io.BytesIO()
    assert run(io.BytesIO(json.dumps(command()).encode() + b'\n'), output) == 0
    messages = decoded(output)
    assert messages[0]['kind'] == 'response' and messages[1]['type'] == 'session.ready'


@pytest.mark.parametrize('frame,code', [
    (b'{bad\n', 'protocol.invalid_json'), (b'\xff\n', 'protocol.invalid_json'),
    (b'a' * (MAX_FRAME_BYTES + 10) + b'\n', 'protocol.frame_too_large'),
])
def test_bad_frame_then_valid_hello_recovers(frame, code):
    output = io.BytesIO()
    assert run(io.BytesIO(frame + json.dumps(command()).encode() + b'\n'), output) == 0
    messages = decoded(output)
    assert messages[0]['payload']['error']['code'] == code
    assert messages[-1]['type'] == 'session.ready'


def test_unknown_command_error_retains_valid_request_identity():
    raw = command('unknown', {})
    output = io.BytesIO(); run(io.BytesIO(json.dumps(raw).encode() + b'\n'), output)
    message = decoded(output)[0]
    assert message['request_id'] == raw['request_id']
    assert message['payload']['error']['code'] == 'protocol.unknown_command'


def test_three_invalid_frames_close_without_consuming_more_input():
    output = io.BytesIO(); run(io.BytesIO(b'{\n{\n{\n' + json.dumps(command()).encode() + b'\n'), output)
    assert len(decoded(output)) == 3


def launch(args=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
    return subprocess.Popen([sys.executable, *(args or ['-m', 'morgan_media_downloader.backend'])],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env, cwd=ROOT)


def write(proc, raw):
    proc.stdin.write(json.dumps(raw) + '\n'); proc.stdin.flush()


def read(proc):
    # A TextIOWrapper may already hold the next line despite an empty OS pipe.
    import queue
    import threading
    result = queue.Queue()
    threading.Thread(target=lambda: result.put(proc.stdout.readline()), daemon=True).start()
    line = result.get(timeout=10)
    assert line, 'Worker exited unexpectedly'
    return json.loads(line)


def test_real_worker_subprocess_has_no_startup_network_or_qt_dependency():
    proc = launch(['-c', "import socket, urllib.request; socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')); urllib.request.urlopen = socket.create_connection; from morgan_media_downloader.backend.worker import main; import sys; assert not any(m.startswith('PySide6') for m in sys.modules); raise SystemExit(main())"])
    try:
        hello = command(); write(proc, hello)
        response = read(proc); ready = read(proc)
        assert response['request_id'] == hello['request_id']
        assert ready['type'] == 'session.ready'
        shutdown = command('session.shutdown', {}, ready['session_id']); write(proc, shutdown)
        final = read(proc)
        assert final['request_id'] == shutdown['request_id']
        stdout, stderr = proc.communicate(timeout=10)
        assert proc.returncode == 0 and stdout == '' and stderr == ''
    finally:
        if proc.poll() is None: proc.kill(); proc.communicate()


def test_real_entry_point_eof_smoke():
    result = subprocess.run([sys.executable, '-m', 'morgan_media_downloader.backend'],
                            input=json.dumps(command()) + '\n', text=True, capture_output=True,
                            cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')), timeout=10)
    assert result.returncode == 0
    assert [json.loads(line)['kind'] for line in result.stdout.splitlines()] == ['response', 'event']
    assert result.stderr == ''


def test_subprocess_fixture_uses_real_analysis_and_suppresses_library_noise():
    proc = launch([str(ROOT / 'tests/backend_subprocess_fixture.py')])
    try:
        write(proc, command()); read(proc); ready = read(proc)
        request = command('analysis.start', {'inputs': [':ytwatchlater']}, ready['session_id']); write(proc, request)
        messages = []
        while not messages or messages[-1]['type'] != 'analysis.completed':
            messages.append(read(proc))
        assert all(m['request_id'] == request['request_id'] for m in messages)
        assert [m['type'] for m in messages] == ['analysis.start', 'analysis.started', 'analysis.item', 'analysis.completed']
        assert 'private-value' not in json.dumps(messages)
        write(proc, command('session.shutdown', {}, ready['session_id'])); read(proc)
        stdout, stderr = proc.communicate(timeout=10)
        assert proc.returncode == 0 and stdout == '' and 'private-value' not in stderr
    finally:
        if proc.poll() is None: proc.kill(); proc.communicate()
