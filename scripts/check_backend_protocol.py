"""Fail on Python/Swift identifier/version/limit drift; never generates fixtures."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from morgan_media_downloader.backend.protocol import VERSION, MAX_FRAME_BYTES, CommandType, EventType, parse_command


def check():
    swift = (ROOT / 'swift/Sources/MorganBackendClient/Protocol.swift').read_text()
    assert re.search(r'static let version = "' + re.escape(VERSION) + r'"', swift), 'Version drift'
    assert re.search(r'static let maximumFrameBytes = ' + str(MAX_FRAME_BYTES) + r'\b', swift), 'Frame limit drift'
    commands = swift.split('public enum CommandType:', 1)[1].split('public enum EventType:', 1)[0]
    events = swift.split('public init(identifier:', 1)[1].split('var terminal:', 1)[0]
    assert set(re.findall(r'case \w+ = "([^"]+)"', commands)) == {c.value for c in CommandType}, 'Command drift'
    assert set(re.findall(r'case "([^"]+)":', events)) == {e.value for e in EventType}, 'Event drift'
    fixtures = ROOT / 'tests/protocol_fixtures'
    paths = sorted(fixtures.glob('*.json'))
    assert len(paths) == 9, 'Review added/removed fixtures in both languages'
    for path in paths:
        raw = json.loads(path.read_bytes())
        assert raw['protocol_version'] == VERSION
        if raw['kind'] == 'command':
            assert parse_command(path.read_bytes()).type.value == raw['type']
        else:
            assert raw['type'] in ({e.value for e in EventType} | {c.value for c in CommandType})
    assert set(json.loads((fixtures / 'hello.response.json').read_text())['payload']['result']['capabilities']) == {c.value for c in CommandType}
    print('Python/Swift version, frame limit, command/event identifiers and 9 shared fixtures match.')


if __name__ == '__main__': check()
