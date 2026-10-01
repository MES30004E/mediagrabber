"""Explicit Swift-facing DTOs, independent of internal dataclass layouts."""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from ..logging_setup import redact_secrets
from ..models import DownloadOptions
from .protocol import ProtocolError, object_fields, string


def safe_text(value: str, limit=1024) -> str:
    cleaned = redact_secrets(str(value))
    cleaned = re.sub(r'(?i)\b(token|password|cookie|authorization|secret|signature|sig|api_key)\s*[:=].*',
                     r'\1=[redacted]', cleaned)
    return cleaned[:limit]


def display_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('https', 'http') or not parts.hostname:
            return ''
        return safe_text(urlunsplit((parts.scheme, parts.hostname, parts.path, '', '')))
    except ValueError:
        return ''


def media_payload(item, source_id: str) -> dict:
    return {'source_id': source_id, 'title': safe_text(item.title), 'uploader': safe_text(item.uploader),
            'display_url': display_url(item.source_url), 'original_display_url': display_url(item.original_url),
            'duration_seconds': item.duration, 'source': safe_text(item.source),
            'playlist_index': item.playlist_index, 'confidence': item.confidence,
            'collection_title': safe_text(item.collection_title), 'collection_type': safe_text(item.collection_type),
            'available_subtitles': [safe_text(v, 64) for v in item.available_subtitles[:100]],
            'automatic_captions': [safe_text(v, 64) for v in item.automatic_captions[:100]]}


OPTION_STRINGS = ('compatibility', 'quality', 'container', 'audio_format', 'audio_bitrate',
                  'subtitle_source', 'subtitle_language', 'filename_template', 'download_dir')
OPTION_BOOLS = ('embed_thumbnail', 'embed_metadata', 'embed_chapters', 'embed_subtitles',
                'write_subtitles', 'verify_postprocessing', 'keep_original')


def options_from_payload(value: dict) -> DownloadOptions:
    object_fields(value, OPTION_STRINGS + OPTION_BOOLS)
    for key, val in value.items():
        if key in OPTION_STRINGS:
            string(val)
        elif type(val) is not bool:
            raise ProtocolError('protocol.invalid_message')
    # Explicit fields; additions to internal DownloadOptions do not change this schema.
    return DownloadOptions(**value)


def progress_payload(job) -> dict:
    return {'stage': safe_text(job.postprocessing_stage), 'downloaded_bytes': job.downloaded_bytes,
            'total_bytes': job.total_bytes or None, 'total_is_estimate': True,
            'percent': min(100., max(0., job.progress)) if job.total_bytes else None,
            'speed_bytes_per_second': job.speed, 'eta_seconds': job.eta,
            'fragment_index': job.fragment_index, 'fragment_count': job.fragment_count}


def error_payload(code: str, category='protocol', stage='validation', message='Command could not be processed.') -> dict:
    return {'code': code, 'category': category, 'stage': stage, 'safe_message': message,
            'retryable': False, 'retry_options': [], 'diagnostic_id': None}
