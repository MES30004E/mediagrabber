import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from morgan_media_downloader.backend.protocol import CommandType, ProtocolError, parse_command
from morgan_media_downloader.backend.adapters import media_payload, options_from_payload, progress_payload
from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem


def command(type='session.hello', payload=None, session_id=None, job_id=None):
    return {'protocol_version': '1.0', 'kind': 'command', 'type': type,
            'request_id': str(uuid4()), 'session_id': session_id, 'job_id': job_id,
            'source_id': None, 'timestamp': datetime.now(timezone.utc).isoformat(),
            'payload': payload if payload is not None else {'supported_versions': ['1.0']}}


def parse(value):
    return parse_command(json.dumps(value).encode())


def test_hello_is_a_typed_correlated_command():
    raw = command()
    parsed = parse(raw)
    assert parsed.type == CommandType.HELLO
    assert parsed.request_id == raw['request_id']
    assert parsed.payload.supported_versions == ('1.0',)


@pytest.mark.parametrize('raw,code', [
    (b'{broken', 'protocol.invalid_json'),
    (b'\xff', 'protocol.invalid_json'),
    (b'[]', 'protocol.invalid_message'),
    (b'{"kind":"command"}', 'protocol.invalid_message'),
])
def test_malformed_messages_have_safe_errors(raw, code):
    with pytest.raises(ProtocolError) as exc:
        parse_command(raw)
    assert exc.value.code == code
    assert 'broken' not in str(exc.value)


@pytest.mark.parametrize('field,value', [
    ('request_id', 'row-1'), ('kind', 'event'), ('timestamp', 'yesterday'),
    ('timestamp', '2026-10-01T12:00:00'), ('payload', []), ('job_id', 3),
])
def test_invalid_envelope_fields_are_rejected(field, value):
    raw = command(); raw[field] = value
    with pytest.raises(ProtocolError):
        parse(raw)


def test_version_and_unknown_command_are_explicit():
    raw = command(); raw['protocol_version'] = '2.0'
    with pytest.raises(ProtocolError, match='supported'):
        parse(raw)
    raw = command('arbitrary.shell', {})
    with pytest.raises(ProtocolError) as exc:
        parse(raw)
    assert exc.value.code == 'protocol.unknown_command'


@pytest.mark.parametrize('payload', [
    {}, {'inputs': []}, {'inputs': 'search'}, {'inputs': [3]},
    {'inputs': ['search'], 'config': {'password': 'private-value'}},
    {'inputs': ['search'], 'config': {'proxy': {'mode': 'Custom HTTP Proxy', 'host': 'user:secret@host', 'port': 80}}},
    {'inputs': ['search'], 'config': {'proxy': {'mode': 'Custom HTTP Proxy', 'host': 'host', 'port': True}}},
])
def test_analysis_payload_validation_prevents_engine_work(payload):
    with pytest.raises(ProtocolError):
        parse(command('analysis.start', payload, str(uuid4())))


def test_analysis_configuration_preserves_nonsecret_references():
    config = {'authentication_mode': 'Browser Cookies', 'cookies_browser': 'Firefox',
              'browser_profile': 'qa', 'cookies_file': '', 'provider_url': 'http://127.0.0.1:4416',
              'provider_home': '', 'proxy': {'mode': 'Custom SOCKS5 Proxy', 'host': '127.0.0.1', 'port': 1080}}
    parsed = parse(command('analysis.start', {'inputs': [':ytwatchlater'], 'config': config}, str(uuid4())))
    assert parsed.payload.inputs == (':ytwatchlater',)
    assert parsed.payload.config.proxy_url == 'socks5h://127.0.0.1:1080'
    assert parsed.payload.config.browser_profile == 'qa'


def test_media_adapter_omits_headers_and_signed_thumbnail_and_cookie_values():
    source_id = str(uuid4())
    item = MediaItem('https://media.test/watch?v=1&token=secret-value', 'Demo token=secret-value',
                     thumbnail='https://media.test/image?sig=secret-value',
                     thumbnail_headers={'Cookie': 'secret-value'}, original_url='https://media.test/?sig=secret-value')
    payload = media_payload(item, source_id)
    assert payload['source_id'] == source_id
    assert payload['title'].startswith('Demo')
    assert 'secret-value' not in json.dumps(payload)
    assert 'thumbnail_headers' not in payload and 'thumbnail' not in payload
    assert payload['display_url'] == 'https://media.test/watch'


def test_options_adapter_has_explicit_types_and_allowlist():
    options = options_from_payload({'download_dir': '/selected/media', 'quality': '720p', 'embed_subtitles': True})
    assert isinstance(options, DownloadOptions)
    assert options.quality == '720p' and options.embed_subtitles is True
    for invalid in [{'download_dir': 1}, {'embed_subtitles': 'true'}, {'password': 'secret'}, {'id': 'row'}]:
        with pytest.raises(ProtocolError):
            options_from_payload(invalid)


def test_progress_adapter_expresses_unknown_totals_and_stage():
    job = DownloadJob(MediaItem('url', 'Title'), DownloadOptions())
    job.downloaded_bytes = 32; job.postprocessing_stage = 'Starting transfer'
    payload = progress_payload(job)
    assert payload['total_bytes'] is None and payload['percent'] is None
    assert payload['stage'] == 'Starting transfer'
    job.total_bytes = 64; job.progress = 50
    assert progress_payload(job)['percent'] == 50


def test_nonfinite_upstream_numbers_are_json_safe():
    item = MediaItem('url', 'Title', duration=float('nan'), confidence=float('inf'))
    payload = media_payload(item, str(uuid4()))
    assert payload['duration_seconds'] is None and payload['confidence'] is None
    job = DownloadJob(item, DownloadOptions()); job.speed = float('nan')
    assert progress_payload(job)['speed_bytes_per_second'] == 0
    json.dumps(progress_payload(job), allow_nan=False)


@pytest.mark.parametrize('template', ['../escape.%(ext)s', '/absolute.%(ext)s', 'nested/../../escape'])
def test_filename_template_cannot_escape_selected_destination(template):
    with pytest.raises(ProtocolError):
        options_from_payload({'filename_template': template})


def test_outgoing_envelope_is_typed_independently_of_job_models():
    from morgan_media_downloader.backend.protocol import WireMessage
    message = WireMessage('event', 'session.ready', str(uuid4()), str(uuid4()), None, None,
                          '2026-10-01T12:00:00Z', 1, {'selected_version': '1.0'})
    wire = message.to_dict()
    assert wire['protocol_version'] == '1.0' and wire['sequence'] == 1
    assert 'job_revision' not in wire and 'attempt_id' not in wire


def test_deep_json_nesting_is_a_safe_protocol_error():
    with pytest.raises(ProtocolError) as exc:
        parse_command(b'[' * 10000 + b'0' + b']' * 10000)
    assert exc.value.code == 'protocol.invalid_json'


def test_frame_byte_limit_excludes_line_terminator(monkeypatch):
    import morgan_media_downloader.backend.protocol as protocol
    raw = json.dumps(command()).encode()
    monkeypatch.setattr(protocol, 'MAX_FRAME_BYTES', len(raw))
    assert parse_command(raw + b'\n').type == CommandType.HELLO
