import json
from pathlib import Path

import pytest

from morgan_media_downloader.settings import AppSettings, SettingsStore


def test_tor_default_discovers_current_users_application_without_personal_path(tmp_path, monkeypatch):
    user_home = tmp_path / "user"
    monkeypatch.setattr(Path, "home", lambda: user_home)
    assert AppSettings().tor_browser_path == "/Applications/Tor Browser.app"
    user_browser = user_home / "Applications" / "Tor Browser.app"
    user_browser.mkdir(parents=True)
    assert AppSettings().tor_browser_path == str(user_browser)


def test_saved_tor_location_is_not_overridden_by_default_discovery(tmp_path, monkeypatch):
    user_home = tmp_path / "user"
    monkeypatch.setattr(Path, "home", lambda: user_home)
    (user_home / "Applications" / "Tor Browser.app").mkdir(parents=True)
    store = SettingsStore(tmp_path / "settings.json")
    configured = AppSettings(tor_browser_path=str(tmp_path / "Chosen Tor Browser.app"))
    store.save(configured)
    assert store.load().tor_browser_path == configured.tor_browser_path


@pytest.mark.parametrize("field,value", [
    ("download_dir", "/tmp/downloads"), ("theme", "Dark"), ("quality", "1080p"),
    ("audio_format", "FLAC"), ("connection_mode", "Managed Tor"),
    ("tor_browser_path", "/Applications/Tor Browser.app"),
    ("authentication_mode", "Browser Cookies"), ("cookies_browser", "Firefox"),
    ("torrent_download_dir", "/tmp/torrents"), ("torrent_max_active", 3),
    ("torrent_enable_dht", False),
    ("create_subfolders", "Always for multi-file jobs"),
    ("clipboard_url_detection", False),
    ("torrent_enable_lpd", False),
    ("torrent_extra_public_trackers", True),
    ("http_proxy_host", "http-proxy.test"),
    ("socks_proxy_host", "socks-proxy.test"),
    ("converter_profile", "Custom"),
    ("converter_container", "WebM"),
    ("converter_video_codec", "VP9"),
    ("converter_audio_codec", "Opus"),
    ("converter_output_dir", "/tmp/converted"),
])
def test_setting_survives_new_store_instance(tmp_path: Path, field: str, value):
    path = tmp_path / "settings.json"
    settings = AppSettings(); setattr(settings, field, value)
    SettingsStore(path).save(settings)
    restored = SettingsStore(path).load()
    assert getattr(restored, field) == value
    assert path.stat().st_mode & 0o777 == 0o600


def test_corrupt_json_is_renamed_and_defaults_restored(tmp_path: Path):
    path = tmp_path / "settings.json"; path.write_text("{ definitely broken", encoding="utf-8")
    store = SettingsStore(path); restored = store.load()
    assert restored == AppSettings()
    assert store.last_warning
    assert list(tmp_path.glob("settings.json.broken-*"))
    assert not path.exists()


def test_legacy_preferences_are_migrated(tmp_path: Path):
    (tmp_path / "preferences.json").write_text(json.dumps({"theme": "Dark", "connection_mode": "Tor"}), encoding="utf-8")
    restored = SettingsStore(tmp_path / "settings.json").load()
    assert restored.theme == "Dark"
    assert restored.connection_mode == "External Tor"
    assert restored.authentication_mode == "Auto"
    assert (tmp_path / "settings.json").exists()


def test_schema_two_preserves_explicit_none_authentication(tmp_path: Path):
    path = tmp_path / "settings.json"
    SettingsStore(path).save(AppSettings(authentication_mode="None"))
    assert SettingsStore(path).load().authentication_mode == "None"


def test_legacy_managed_tor_control_port_is_not_persisted(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"connection_mode": "Managed Tor", "tor_control_port": 9151}))
    restored = SettingsStore(path).load()
    SettingsStore(path).save(restored)
    assert "tor_control_port" not in json.loads(path.read_text())


def test_all_qa_settings_survive_packaged_style_restart(tmp_path: Path):
    path = tmp_path / "Library" / "Application Support" / "Morgan Media Downloader" / "settings.json"
    configured = AppSettings(
        download_dir="/tmp/media", quality="1440p", audio_format="OPUS",
        filename_template="%(uploader)s - %(title)s.%(ext)s", connection_mode="Managed Tor",
        managed_tor_auto_start=False, tor_browser_path="/Applications/Tor Browser.app",
        authentication_mode="Browser Cookies", cookies_browser="Safari",
        torrent_download_dir="/tmp/torrents", concurrent_downloads=4,
        window_width=1333, window_height=811, theme="Dark",
    )
    SettingsStore(path).save(configured)  # Apply/OK persist through the same atomic store.
    restored = SettingsStore(path).load()  # Fresh process/store, as for packaged-app relaunch.
    for field in ("download_dir", "quality", "audio_format", "filename_template", "connection_mode",
                  "managed_tor_auto_start", "tor_browser_path", "authentication_mode", "cookies_browser",
                  "torrent_download_dir", "concurrent_downloads", "window_width", "window_height", "theme"):
        assert getattr(restored, field) == getattr(configured, field)


def test_cancel_style_discard_does_not_persist(tmp_path: Path):
    path = tmp_path / "settings.json"
    original = AppSettings(theme="Light")
    SettingsStore(path).save(original)
    working_copy = AppSettings(**vars(SettingsStore(path).load()))
    working_copy.theme = "Dark"  # Dialog Cancel discards this copy without calling save.
    assert SettingsStore(path).load().theme == "Light"
