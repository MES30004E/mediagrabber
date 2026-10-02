"""Deterministic transport peer ONLY for Swift tests; no production test flags."""
import json
import os
import sys
import time
import uuid

mode = sys.argv[1]
session = str(uuid.uuid4())
sequence = 0

def emit(command, kind='response', type_=None, payload=None, **changes):
    global sequence
    sequence += 1
    value = dict(protocol_version='1.0', kind=kind, type=type_ or command['type'],
                 request_id=command['request_id'], session_id=session, job_id=None,
                 source_id=None, timestamp='2026-10-02T00:00:00Z', sequence=sequence,
                 payload=payload or {'status': 'completed', 'result': {}})
    value.update(changes)
    sys.stdout.write(json.dumps(value) + '\r\n'); sys.stdout.flush()

if mode == 'eof': sys.exit(0)
if mode == 'crash': sys.exit(7)
if mode == 'no-read': time.sleep(60); sys.exit(0)
if mode == 'small-output':
    os.write(1, b'small frame\n')
    time.sleep(60)
    sys.exit(0)
for line in sys.stdin:
    command = json.loads(line)
    if command['type'] == 'session.hello':
        capabilities = dict(selected_version='1.0', capabilities=['session.hello', 'analysis.start', 'jobs.enqueue',
                            'analysis.cancel', 'jobs.cancel', 'session.ping', 'session.shutdown'],
                            max_frame_bytes=1048576, max_analysis_inputs=100, max_concurrent_operations=4,
                            max_session_items=4096, durable_jobs=False, runtime_source='bundled', secret_ipc=False)
        emit(command, payload={'status': 'completed', 'result': capabilities})
        emit(command, 'event', 'session.ready', capabilities)
        if mode == 'close-stdout':
            os.close(1)
            time.sleep(60)
        elif mode == 'fill-stdin':
            emit(command, 'event', 'diagnostic', {'category': 'test', 'level': 'info', 'safe_message': 'will not read'})
            time.sleep(60)
    elif command['type'] == 'session.shutdown':
        emit(command)
        if mode == 'shutdown-hang':
            emit(command, 'event', 'diagnostic', {'category': 'test', 'level': 'info', 'safe_message': 'shutdown acknowledged'})
            time.sleep(60)
        break
    elif mode == 'timeout':
        continue
    elif mode == 'pending-on-shutdown':
        emit(command, 'event', 'diagnostic', {'category': 'test', 'level': 'info', 'safe_message': 'ping received'})
        continue
    elif mode == 'stderr-flood':
        os.write(2, b'cookie=must-not-be-protocol\n' * 100000)
        emit(command)
    elif mode == 'unknown':
        emit(command, 'event', 'future.event', {'cookie': 'must-not-be-retained'})
        emit(command)
    elif mode == 'malformed':
        sys.stdout.write('{bad\n'); sys.stdout.flush(); emit(command)
    elif mode == 'wrong-id':
        emit(command, request_id=str(uuid.uuid4()))
    elif mode == 'wrong-type':
        emit(command, type_='session.shutdown')
    elif mode == 'wrong-session':
        emit(command, session_id=str(uuid.uuid4()))
    elif mode == 'event-wrong-type':
        emit(command, 'event', 'analysis.completed', {'count': 0, 'effective_authentication': 'None'})
    elif mode == 'partial':
        sys.stdout.write('{'); sys.stdout.flush(); break
    elif mode == 'delay':
        time.sleep(0.15); emit(command)
    else:
        emit(command)
