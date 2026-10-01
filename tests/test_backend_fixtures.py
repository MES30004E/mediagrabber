import json
from pathlib import Path

from morgan_media_downloader.backend.adapters import media_payload, progress_payload, error_payload
from morgan_media_downloader.backend.protocol import parse_command
from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem

FIXTURES = Path(__file__).parent / 'protocol_fixtures'


def load(name):
    return json.loads((FIXTURES / name).read_text())


def test_golden_requests_are_accepted_by_versioned_parser():
    names = ['hello.request.json', 'analyse-url.request.json', 'analyse-search.request.json', 'analyse-watch-later.request.json']
    for name in names:
        raw = load(name)
        assert parse_command(json.dumps(raw).encode()).request_id == raw['request_id']


def test_golden_media_progress_and_errors_match_explicit_adapters():
    item = load('analysis-item.event.json')
    assert media_payload(MediaItem('https://www.youtube.com/watch?v=fixture', 'Example video'), item['source_id']) == item['payload']['item']
    job = DownloadJob(MediaItem('url', 'Title'), DownloadOptions())
    job.postprocessing_stage = 'Downloading'; job.downloaded_bytes = 32; job.total_bytes = 64; job.progress = 50
    assert progress_payload(job) == load('download-progress.event.json')['payload']
    assert error_payload('protocol.invalid_json') == load('error.event.json')['payload']['error']


def test_golden_event_envelopes_have_stable_required_fields():
    for name in ['hello.response.json', 'ready.event.json', 'analysis-item.event.json', 'download-progress.event.json', 'error.event.json']:
        raw = load(name)
        assert raw['protocol_version'] == '1.0'
        assert raw['kind'] in ('event', 'response')
        assert type(raw['sequence']) is int and raw['sequence'] > 0
        assert {'request_id', 'session_id', 'job_id', 'source_id', 'timestamp', 'payload'} <= raw.keys()
