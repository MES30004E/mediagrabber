import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from morgan_media_downloader.auth import authentication_options
from morgan_media_downloader.managed_tor import ManagedTor
from morgan_media_downloader.settings import AppSettings, SettingsStore
from morgan_media_downloader.settings_window import SettingsWindow
from morgan_media_downloader.yt_runtime import RuntimeSnapshot, YtDlpRuntimeManager

_APP = QApplication.instance() or QApplication([])


def _runtime(tmp_path: Path) -> YtDlpRuntimeManager:
    runtime = YtDlpRuntimeManager(
        tmp_path / "yt-runtime",
        fetcher=lambda *_: (_ for _ in ()).throw(OSError("offline")),
        bundled_loader=lambda: RuntimeSnapshot("2025.01.01", "Bundled", object),
        provider_checker=lambda: None,
    )
    runtime.initialize()
    return runtime


def _dispose(dialog: SettingsWindow) -> None:
    dialog.timer.stop()
    dialog.reject()
    dialog.deleteLater()
    _APP.processEvents()


def test_real_settings_dialog_apply_ok_cancel_and_restart(tmp_path: Path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    original = AppSettings()
    store.save(original)

    def persist(settings: AppSettings, _password: str):
        store.save(settings)

    runtime = _runtime(tmp_path)
    dialog = SettingsWindow(store.load(), ManagedTor(original.tor_browser_path), persist, runtime_manager=runtime)
    assert {button.text() for button in dialog.runtime_action_buttons} == {
        "Check Now", "Update Now", "Roll Back", "Use Bundled Version"}
    assert "Current version: 2025.01.01" in dialog.yt_runtime_status.text()
    assert "Runtime source: Bundled" in dialog.yt_runtime_status.text()
    dialog.download_dir.setText("/tmp/qa-media")
    dialog.quality.setCurrentText("1440p")
    dialog.audio_format.setCurrentText("OPUS")
    dialog.filename.setText("%(uploader)s - %(title)s.%(ext)s")
    dialog.connection.setCurrentText("Managed Tor")
    dialog.tor_auto.setChecked(False)
    dialog.tor_path.setText("/Applications/Tor Browser.app")
    dialog.auth_mode.setCurrentText("Browser Cookies")
    dialog.browser.setCurrentText("Safari")
    dialog.torrent_dir.setText("/tmp/qa-torrents")
    dialog.concurrency.setValue(4)
    dialog.theme.setCurrentText("Dark")
    dialog.yt_check_startup.setChecked(False)
    dialog.yt_auto_install.setChecked(False)
    dialog.apply()
    _dispose(dialog)

    restored = SettingsStore(path).load()
    assert (restored.download_dir, restored.quality, restored.audio_format) == ("/tmp/qa-media", "1440p", "OPUS")
    assert restored.filename_template == "%(uploader)s - %(title)s.%(ext)s"
    assert (restored.connection_mode, restored.managed_tor_auto_start) == ("Managed Tor", False)
    assert (restored.tor_browser_path, restored.authentication_mode, restored.cookies_browser) == (
        "/Applications/Tor Browser.app", "Browser Cookies", "Safari")
    assert (restored.torrent_download_dir, restored.concurrent_downloads, restored.theme) == ("/tmp/qa-torrents", 4, "Dark")
    assert not restored.yt_dlp_check_updates_on_startup
    assert not restored.yt_dlp_auto_install_updates

    ok_dialog = SettingsWindow(SettingsStore(path).load(), ManagedTor(restored.tor_browser_path), persist, runtime_manager=runtime)
    ok_dialog.quality.setCurrentText("1080p")
    ok_dialog.theme.setCurrentText("Light")
    ok_dialog._ok()
    _dispose(ok_dialog)
    assert (SettingsStore(path).load().quality, SettingsStore(path).load().theme) == ("1080p", "Light")

    cancel_dialog = SettingsWindow(SettingsStore(path).load(), ManagedTor(restored.tor_browser_path), persist, runtime_manager=runtime)
    cancel_dialog.quality.setCurrentText("360p")
    cancel_dialog.theme.setCurrentText("Dark")
    _dispose(cancel_dialog)
    assert (SettingsStore(path).load().quality, SettingsStore(path).load().theme) == ("1080p", "Light")


def test_authentication_controls_and_targeted_reset_do_not_change_other_settings(tmp_path: Path, monkeypatch):
    # A fresh Mac (and Cloud) may have no Chrome profile. Never depend on
    # the developer's browser installation or create a synthetic profile.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings = AppSettings(download_dir="/keep/media", quality="1440p", connection_mode="Managed Tor",
                           authentication_mode="Browser Cookies", cookies_browser="Firefox",
                           browser_profile="qa", cookies_file="/secret/cookies.txt")
    captured = []
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path),
                            lambda value, _passwords: captured.append(value), runtime_manager=_runtime(tmp_path))
    assert dialog.browser.isEnabled() and dialog.profile.isEnabled()
    assert not dialog.cookies_file.isEnabled()
    dialog.auth_mode.setCurrentText("Imported cookies.txt")
    assert not dialog.browser.isEnabled() and dialog.cookies_file.isEnabled()
    dialog._reset_authentication()
    reset = dialog._collect()
    assert (reset.authentication_mode, reset.cookies_browser, reset.browser_profile, reset.cookies_file) == (
        "Auto", "Chrome", "", "")
    assert authentication_options("Browser Cookies", reset.cookies_browser, reset.browser_profile) == {
        "cookiesfrombrowser": ("chrome", None, None, None)
    }
    assert (reset.download_dir, reset.quality, reset.connection_mode) == (
        "/keep/media", "1440p", "Managed Tor")
    _dispose(dialog)
