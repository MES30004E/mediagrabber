from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import application_support_dir, default_download_dir

DEFAULT_TOR_BROWSER = "/Applications/Tor Browser.app"


def _default_tor_browser() -> str:
    user_application = Path.home() / "Applications" / "Tor Browser.app"
    return str(user_application) if user_application.is_dir() else DEFAULT_TOR_BROWSER


@dataclass
class AppSettings:
    settings_schema_version: int = 6
    theme: str = "System"
    remember_window_size: bool = True
    remember_window_position: bool = True
    show_first_run_diagnostics: bool = True
    clipboard_url_detection: bool = True
    first_run_complete: bool = False
    window_width: int = 1180
    window_height: int = 760
    window_x: int | None = None
    window_y: int | None = None

    download_dir: str = str(default_download_dir())
    filename_template: str = "%(title)s.%(ext)s"
    quality: str = "Best"
    compatibility: str = "macOS / QuickTime"
    container: str = "Auto"
    audio_format: str = "Original/best audio"
    audio_bitrate: str = "Auto"
    concurrent_downloads: int = 2
    create_subfolders: str = "Auto"
    embed_thumbnail: bool = False
    embed_metadata: bool = True
    embed_chapters: bool = True
    embed_subtitles: bool = False
    write_subtitles: bool = False
    keep_original: bool = False
    subtitle_languages: str = "en"
    subtitle_source: str = "Normal subtitles"
    verify_postprocessing: bool = True

    converter_profile: str = "macOS / QuickTime"
    converter_container: str = "MP4"
    converter_video_codec: str = "H.264 / AVC"
    converter_audio_codec: str = "AAC"
    converter_subtitle_mode: str = "Convert if needed"
    converter_quality: str = "High"
    converter_resolution: str = "Keep Original"
    converter_frame_rate: str = "Keep Original"
    converter_audio_bitrate: str = "192 kbps"
    converter_output_dir: str = ""

    connection_mode: str = "Direct / Normal Network"
    tor_browser_path: str = field(default_factory=_default_tor_browser)
    managed_tor_auto_start: bool = True
    managed_tor_stop_on_exit: bool = True
    proxy_host: str = ""
    proxy_port: int = 0
    proxy_username: str = ""
    http_proxy_host: str = ""
    http_proxy_port: int = 0
    http_proxy_username: str = ""
    socks_proxy_host: str = ""
    socks_proxy_port: int = 0
    socks_proxy_username: str = ""

    authentication_mode: str = "Auto"
    cookies_browser: str = "Chrome"
    browser_profile: str = ""
    cookies_file: str = ""

    torrent_download_dir: str = str(default_download_dir() / "Torrents")
    torrent_max_active: int = 1
    torrent_upload_limit_kib: int = 0
    torrent_download_limit_kib: int = 0
    torrent_enable_dht: bool = True
    torrent_enable_pex: bool = True
    torrent_enable_trackers: bool = True
    torrent_enable_lpd: bool = True
    torrent_extra_public_trackers: bool = False
    torrent_continue_seeding: bool = False
    torrent_connection_mode: str = "System / Proton VPN"
    aria2c_path: str = ""

    provider_base_url: str = "http://127.0.0.1:4416"
    provider_server_home: str = ""
    yt_dlp_safe_options: str = ""
    yt_dlp_check_updates_on_startup: bool = True
    yt_dlp_auto_install_updates: bool = True
    console_detail: str = "Normal"


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or application_support_dir() / "settings.json"
        self.last_warning = ""
        self._legacy_path = self.path.with_name("preferences.json")

    def load(self) -> AppSettings:
        if not self.path.exists() and self._legacy_path.exists():
            try:
                legacy = self._load_path(self._legacy_path)
                self.save(legacy)
                return legacy
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        if not self.path.exists():
            return AppSettings()
        try:
            return self._load_path(self.path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            broken = self.path.with_name(f"settings.json.broken-{stamp}")
            try:
                self.path.replace(broken)
                self.last_warning = f"Settings were corrupt and moved to {broken}. Defaults were restored."
            except OSError:
                self.last_warning = f"Settings were corrupt and could not be recovered: {error}"
            return AppSettings()

    @staticmethod
    def _coerce(data: dict[str, Any]) -> AppSettings:
        allowed = AppSettings.__dataclass_fields__.keys()
        aliases = {"first_run_complete": "first_run_complete"}
        clean = {aliases.get(key, key): value for key, value in data.items() if aliases.get(key, key) in allowed}
        # Migrate the former single Tor mode without silently starting a process.
        if clean.get("connection_mode") == "Tor":
            clean["connection_mode"] = "External Tor"
        if clean.get("connection_mode") == "Direct":
            clean["connection_mode"] = "Direct / Normal Network"
        if clean.get("connection_mode") == "Custom SOCKS Proxy":
            clean["connection_mode"] = "Custom SOCKS5 Proxy"
        if clean.get("torrent_connection_mode") == "Direct":
            clean["torrent_connection_mode"] = "Direct / Normal Network"
        if clean.get("authentication_mode") == "Browser cookies":
            clean["authentication_mode"] = "Browser Cookies"
        if int(data.get("settings_schema_version") or 0) < 2 and clean.get("authentication_mode", "None") == "None":
            clean["authentication_mode"] = "Auto"
        # Managed Tor endpoints are runtime-only. Ignore any formerly persisted
        # control port so a conventional Tor Browser endpoint cannot return.
        clean.pop("tor_control_port", None)
        clean["settings_schema_version"] = 6
        return AppSettings(**clean)

    def _load_path(self, path: Path) -> AppSettings:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Settings root must be an object")
        return self._coerce(raw)

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp-{os.getpid()}")
        payload = json.dumps(asdict(settings), indent=2, ensure_ascii=False) + "\n"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            try:
                directory = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                pass
        finally:
            if temporary.exists():
                temporary.unlink()

    def reset(self) -> AppSettings:
        settings = AppSettings()
        self.save(settings)
        return settings

    def update(self, settings: AppSettings, **values: Any) -> AppSettings:
        for key, value in values.items():
            if key in settings.__dataclass_fields__:
                setattr(settings, key, value)
        self.save(settings)
        return settings
