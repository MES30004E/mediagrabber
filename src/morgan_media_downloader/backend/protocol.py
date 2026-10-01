"""Strict Phase 1 command schema. Never include input values in validation errors."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from urllib.parse import urlsplit
from uuid import UUID

from ..network import ProxyConfig

VERSION = '1.0'
MAX_FRAME_BYTES = 1024 * 1024


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str = 'Invalid command fields.'):
        self.code = code
        super().__init__(message)


class CommandType(str, Enum):
    HELLO = 'session.hello'
    ANALYSE = 'analysis.start'
    DOWNLOAD = 'jobs.enqueue'
    CANCEL_ANALYSIS = 'analysis.cancel'
    CANCEL_JOB = 'jobs.cancel'
    PING = 'session.ping'
    SHUTDOWN = 'session.shutdown'


class EventType(str, Enum):
    READY = 'session.ready'
    ANALYSIS_STARTED = 'analysis.started'
    ANALYSIS_ITEM = 'analysis.item'
    ANALYSIS_COMPLETED = 'analysis.completed'
    ANALYSIS_FAILED = 'analysis.failed'
    ANALYSIS_CANCELLED = 'analysis.cancelled'
    DOWNLOAD_STARTED = 'download.started'
    DOWNLOAD_PROGRESS = 'download.progress'
    DOWNLOAD_PROCESSING = 'download.processing'
    DOWNLOAD_COMPLETED = 'download.completed'
    DOWNLOAD_FAILED = 'download.failed'
    JOB_CANCELLED = 'job.cancelled'
    AUTH_REQUIRED = 'auth.required'
    AUTH_FAILED = 'auth.failed'
    DIAGNOSTIC = 'diagnostic'
    ERROR = 'error'


def identifier(value, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise ProtocolError('protocol.invalid_message')
    try:
        return str(UUID(value))
    except ValueError:
        raise ProtocolError('protocol.invalid_message') from None


def string(value, *, maximum=8192):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise ProtocolError('protocol.invalid_message')
    return value


def object_fields(value, allowed):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ProtocolError('protocol.invalid_message')
    return value


@dataclass(frozen=True)
class Configuration:
    authentication_mode: str = 'Auto'
    cookies_browser: str = 'Chrome'
    browser_profile: str = ''
    cookies_file: str = ''
    provider_url: str = 'http://127.0.0.1:4416'
    provider_home: str = ''
    proxy_url: str | None = None

    @classmethod
    def parse(cls, value):
        fields = object_fields(value, ('authentication_mode', 'cookies_browser', 'browser_profile',
                                      'cookies_file', 'provider_url', 'provider_home', 'proxy'))
        values = {key: string(val) for key, val in fields.items() if key != 'proxy'}
        if values.get('authentication_mode', 'Auto') not in ('Auto', 'None', 'Browser Cookies', 'Imported cookies.txt'):
            raise ProtocolError('protocol.invalid_message')
        if values.get('cookies_browser', 'Chrome') not in ('Chrome', 'Chromium', 'Edge', 'Firefox', 'Safari', 'None'):
            raise ProtocolError('protocol.invalid_message')
        try:
            endpoint = urlsplit(values.get('provider_url', cls.provider_url))
            if endpoint.scheme not in ('http', 'https') or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                raise ValueError
            endpoint.port
        except ValueError:
            raise ProtocolError('protocol.invalid_message') from None
        proxy = object_fields(fields.get('proxy', {}), ('mode', 'host', 'port'))
        mode = string(proxy.get('mode', 'Direct'))
        host = string(proxy.get('host', ''))
        port = proxy.get('port', 0)
        if mode not in ('Direct', 'Direct / Normal Network', 'System / Proton VPN',
                        'Custom HTTP Proxy', 'Custom SOCKS5 Proxy', 'External Tor'):
            raise ProtocolError('protocol.invalid_message')
        if (host and not re.fullmatch(r'[A-Za-z0-9._-]+', host)) or type(port) is not int or not 0 <= port <= 65535:
            raise ProtocolError('protocol.invalid_message')
        try:
            values['proxy_url'] = ProxyConfig(mode, host, port).url()
        except ValueError:
            raise ProtocolError('protocol.invalid_message') from None
        return cls(**values)


@dataclass(frozen=True)
class Hello:
    supported_versions: tuple[str, ...]


@dataclass(frozen=True)
class Analyse:
    inputs: tuple[str, ...]
    config: Configuration


@dataclass(frozen=True)
class Download:
    analysis_request_id: str
    source_ids: tuple[str, ...]
    options: dict
    config: Configuration | None


@dataclass(frozen=True)
class Cancel:
    target_request_id: str | None = None


@dataclass(frozen=True)
class Empty:
    pass


@dataclass(frozen=True)
class Command:
    type: CommandType
    request_id: str
    session_id: str | None
    job_id: str | None
    source_id: str | None
    payload: Hello | Analyse | Download | Cancel | Empty


def _payload(kind, value):
    if not isinstance(value, dict):
        raise ProtocolError('protocol.invalid_message')
    if kind == CommandType.HELLO:
        object_fields(value, ('supported_versions', 'capabilities'))
        versions = value.get('supported_versions')
        if not isinstance(versions, list) or not versions or len(versions) > 16:
            raise ProtocolError('protocol.invalid_message')
        return Hello(tuple(string(v, maximum=16) for v in versions))
    if kind == CommandType.ANALYSE:
        object_fields(value, ('inputs', 'config', 'purpose', 'settings_revision'))
        inputs = value.get('inputs')
        if not isinstance(inputs, list) or not 1 <= len(inputs) <= 100:
            raise ProtocolError('protocol.invalid_message')
        inputs = tuple(string(v, maximum=65536) for v in inputs)
        if any(not v.strip() for v in inputs) or value.get('purpose', 'preview') != 'preview':
            raise ProtocolError('protocol.invalid_message')
        if type(value.get('settings_revision', 0)) is not int or value.get('settings_revision', 0) < 0:
            raise ProtocolError('protocol.invalid_message')
        return Analyse(inputs, Configuration.parse(value.get('config', {})))
    if kind == CommandType.DOWNLOAD:
        object_fields(value, ('analysis_request_id', 'source_ids', 'options', 'config'))
        sources = value.get('source_ids')
        if not isinstance(sources, list) or not 1 <= len(sources) <= 4:
            raise ProtocolError('protocol.invalid_message')
        sources = tuple(identifier(v) for v in sources)
        if len(set(sources)) != len(sources):
            raise ProtocolError('protocol.invalid_message')
        from .adapters import options_from_payload
        options = value.get('options', {})
        options_from_payload(options)
        return Download(identifier(value.get('analysis_request_id')), sources, dict(options),
                        Configuration.parse(value['config']) if 'config' in value else None)
    if kind == CommandType.CANCEL_ANALYSIS:
        object_fields(value, ('target_request_id',))
        return Cancel(identifier(value.get('target_request_id')))
    if kind == CommandType.CANCEL_JOB:
        object_fields(value, ('expected_job_revision',))
        revision = value.get('expected_job_revision')
        if type(revision) is not int or revision < 0:
            raise ProtocolError('protocol.invalid_message')
        return Cancel()
    object_fields(value, ())
    return Empty()


def parse_command(raw: bytes) -> Command:
    if len(raw) > MAX_FRAME_BYTES:
        raise ProtocolError('protocol.frame_too_large')
    try:
        value = json.loads(raw.decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError):
        raise ProtocolError('protocol.invalid_json', 'Invalid JSON frame.') from None
    required = ('protocol_version', 'kind', 'type', 'request_id', 'session_id', 'job_id', 'source_id', 'timestamp', 'payload')
    if not isinstance(value, dict) or any(key not in value for key in required):
        raise ProtocolError('protocol.invalid_message')
    if value['protocol_version'] != VERSION:
        raise ProtocolError('protocol.unsupported_version', 'Protocol version is not supported.')
    if value['kind'] != 'command':
        raise ProtocolError('protocol.invalid_message')
    try:
        stamp = datetime.fromisoformat(string(value['timestamp']))
        if stamp.tzinfo is None:
            raise ValueError
    except ValueError:
        raise ProtocolError('protocol.invalid_message') from None
    try:
        kind = CommandType(value['type'])
    except (ValueError, TypeError):
        raise ProtocolError('protocol.unknown_command', 'Unknown command.') from None
    job_id = identifier(value['job_id'], optional=True)
    if kind == CommandType.CANCEL_JOB and job_id is None:
        raise ProtocolError('protocol.invalid_message')
    return Command(kind, identifier(value['request_id']), identifier(value['session_id'], optional=True),
                   job_id, identifier(value['source_id'], optional=True), _payload(kind, value['payload']))
