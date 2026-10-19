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


def test_runtime_status_separates_check_channels_and_reports_rollback(tmp_path):
    settings = AppSettings()
    runtime = _runtime(tmp_path)
    runtime.check_and_update(False, channel="nightly")
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=runtime)
    try:
        status = dialog.yt_runtime_status.text()
        assert "Stable last successful check: Never" in status
        assert "Nightly last successful check: Never" in status
        assert "Nightly last check error: offline" in status
        assert "Rollback: No — bundled runtime active" in status
        assert "24 hours" in dialog.yt_check_startup.toolTip()
    finally:
        _dispose(dialog)

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


def test_accounts_connect_disconnect_and_verification_invalidation(tmp_path, monkeypatch):
    from morgan_media_downloader.auth import YouTubeConnection
    settings = AppSettings(connection_mode="Direct / Normal Network")
    from morgan_media_downloader.youtube_companion.bridge import CompanionController
    from test_companion import MemoryStore
    controller = CompanionController(tmp_path / "control", MemoryStore())
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=_runtime(tmp_path), companion_controller=controller)
    tasks = []
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, fn, **kw: tasks.append((fn, kw)))
    try:
        assert "Accounts" in dialog.pages, "Settings needs a discoverable account connection page"
        dialog.connect_browser.click()
        assert dialog.auth_mode.currentText() == "Browser Cookies"
        dialog._auth_test_ready(YouTubeConnection("authenticated", "YouTube reports signed in.", True))
        assert "signed" in dialog.auth_status.text().lower()
        dialog.profile.setEditText("Other profile")
        assert "verified" in dialog.auth_status.text().lower() or "not tested" in dialog.auth_status.text().lower()
        assert "authenticated" not in dialog.auth_status.toolTip()
        dialog.disconnect_youtube.click()
        assert tasks, "Keychain deletion must run outside the GUI callback"
        fn, callbacks = tasks[-1]; callbacks["on_result"](fn(None, None)); callbacks["on_finished"]()
        collected = dialog._collect()
        assert collected.authentication_mode == "None" and collected.cookies_file == "" and collected.browser_profile == ""
        assert settings.authentication_mode == "Auto", "Working copy must not persist before Apply"
    finally: _dispose(dialog)


def test_companion_accounts_capture_selects_secure_mode_without_saving_cookies(tmp_path, monkeypatch):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    from morgan_media_downloader.auth import BrowserSource
    from test_companion import MemoryStore, sample
    controller = CompanionController(tmp_path / "control", MemoryStore())
    installed = []; opened = []; persisted = []
    monkeypatch.setattr("morgan_media_downloader.youtube_companion.setup.install", lambda **kw: installed.append(kw))
    monkeypatch.setattr("morgan_media_downloader.settings_window.discover_browsers", lambda: [BrowserSource("Chrome", Path("/Applications/Google Chrome.app"))])
    monkeypatch.setattr("morgan_media_downloader.settings_window.subprocess.Popen", lambda argv, **kw: opened.append(argv))
    settings = AppSettings(authentication_mode="YouTube Companion")
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda value, _: persisted.append(value),
                            runtime_manager=_runtime(tmp_path), companion_controller=controller)
    tasks = []
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, fn, **kw: tasks.append((fn, kw)))
    try:
        generation = dialog._auth_generation
        dialog.connect_youtube.click()
        assert installed and "--incognito" in opened[0] and not persisted
        assert "Capture: Authorized" in dialog.auth_progress.text()
        controller.handle({"type": "ping", "incognito": True, "incognito_allowed": True}, ORIGIN)
        dialog._poll_companion()
        assert "Chrome reported Incognito readiness" in dialog.auth_progress.text()
        assert dialog._auth_generation > generation, "Reconnect must invalidate old verification callbacks"
        generation = dialog._auth_generation
        hello = controller.handle({"type": "hello"}, ORIGIN)
        controller.handle(dict(type="capture", operation_id=hello["operation_id"], nonce=hello["nonce"],
                              consent=True, incognito=True, store_id="incognito-store", cookies=[sample()]), ORIGIN)
        dialog._poll_companion()
        assert dialog._auth_generation > generation, "Replacement import must not reuse earlier verification evidence"
        assert dialog.auth_mode.currentText() == "YouTube Companion"
        assert "imported" in dialog.auth_status.text().lower() and "Verify" in dialog.auth_status.text()
        assert persisted and persisted[-1].authentication_mode == "YouTube Companion", "Successful capture activates without manual Apply"
        assert "Keychain: Stored" in dialog.auth_progress.text()
        assert "Verification: Not yet verified" in dialog.auth_progress.text()
        dialog.apply()
        assert persisted[-1].authentication_mode == "YouTube Companion" and persisted[-1].cookies_file == ""
        assert "synthetic-session" not in str(persisted[-1])
        dialog.disconnect_youtube.click()
        assert controller.store.data is not None, "Deletion is asynchronous"
        fn, callbacks = tasks[-1]; callbacks["on_result"](fn(None, None)); callbacks["on_finished"]()
        assert controller.store.data is None and dialog.auth_mode.currentText() == "None"
    finally: _dispose(dialog)


def test_verification_timestamp_and_provider_preflight_are_separate(tmp_path, monkeypatch):
    from morgan_media_downloader.auth import YouTubeConnection
    from morgan_media_downloader.provider import ProviderStatus
    settings = AppSettings(authentication_mode="YouTube Companion")
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=_runtime(tmp_path))
    tasks = []
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, fn, **kw: tasks.append((fn, kw)))
    monkeypatch.setattr("morgan_media_downloader.settings_window.check_provider", lambda *_: ProviderStatus("available", "token=must-not-display", "http"))
    monkeypatch.setattr("morgan_media_downloader.settings_window.find_runtime", lambda **kw: Path("/private/synthetic/node"))
    try:
        dialog._auth_test_ready(YouTubeConnection("authenticated", "Signed in — account identity not confirmed", True))
        assert dialog._verified_at and "Signed-in status confirmed" in dialog.auth_progress.text()
        assert "Not checked" in dialog.auth_progress.text(), "Sign-in must not assert provider readiness"
        dialog.readiness_check.click()
        fn, callbacks = tasks[-1]; callbacks["on_result"](fn(None, None)); callbacks["on_finished"]()
        text = dialog.auth_progress.text()
        assert "HTTP provider responding" in text and "download not tested" in text
        assert "must-not-display" not in text and "/private/synthetic" not in text
        dialog._runtime_action_finished()
        assert "HTTP provider responding" not in dialog.auth_progress.text()
        dialog.auth_mode.setCurrentText("None")
        assert "Needs verification" in dialog.auth_progress.text()
    finally: _dispose(dialog)


def test_managed_import_autosaves_only_authentication_not_unrelated_edits(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    from test_companion import MemoryStore, sample
    settings = AppSettings(quality="1080p", theme="Light")
    store = SettingsStore(tmp_path / "settings.json"); store.save(settings)
    controller = CompanionController(tmp_path / "control", MemoryStore())
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda value, _: store.save(value),
                            runtime_manager=_runtime(tmp_path), companion_controller=controller)
    try:
        dialog.quality.setCurrentText("360p"); dialog.theme.setCurrentText("Dark")
        dialog._pending_companion = controller.begin(); dialog._companion_deadline = float("inf")
        hello = controller.handle({"type": "hello"}, ORIGIN)
        controller.handle(dict(type="capture", operation_id=hello["operation_id"], nonce=hello["nonce"],
                              consent=True, incognito=True, store_id="incognito-store", cookies=[sample()]), ORIGIN)
        dialog._companion_deadline = 0  # Accepted capture may complete after the GUI's deadline.
        dialog._poll_companion()
        saved = store.load()
        assert saved.authentication_mode == "YouTube Companion"
        assert (saved.quality, saved.theme) == ("1080p", "Light")
        assert (dialog.quality.currentText(), dialog.theme.currentText()) == ("360p", "Dark")
        assert "synthetic-session" not in store.path.read_text()
        dialog.reject()
        assert store.load().quality == "1080p"
    finally: _dispose(dialog)


def test_provider_edit_invalidates_preflight_and_late_result(tmp_path, monkeypatch):
    from morgan_media_downloader.provider import ProviderStatus
    settings = AppSettings()
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=_runtime(tmp_path))
    tasks = []
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, fn, **kw: tasks.append((fn, kw)))
    monkeypatch.setattr("morgan_media_downloader.settings_window.check_provider", lambda *_: ProviderStatus("available", "", "http"))
    monkeypatch.setattr("morgan_media_downloader.settings_window.find_runtime", lambda **kw: None)
    try:
        dialog.readiness_check.click()
        fn, callbacks = tasks[-1]; payload = fn(None, None)
        dialog.provider_url.setText("http://127.0.0.1:9999")
        callbacks["on_result"](payload); callbacks["on_finished"]()
        assert "HTTP provider responding" not in dialog.auth_progress.text()
        assert "Not checked" in dialog.auth_progress.text()
    finally: _dispose(dialog)


def test_apply_refreshes_active_authentication_label(tmp_path):
    settings = AppSettings()
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=_runtime(tmp_path))
    try:
        dialog.auth_mode.setCurrentText("Browser Cookies"); dialog.apply()
        assert "Active authentication: Browser Cookies" in dialog.auth_progress.text()
    finally: _dispose(dialog)


def test_failed_checks_do_not_leak_details_or_overwrite_changed_source(tmp_path, monkeypatch):
    settings = AppSettings(connection_mode="Direct / Normal Network")
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=_runtime(tmp_path))
    tasks = []
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, fn, **kw: tasks.append((fn, kw)))
    def fail(*_args, **_kw): raise RuntimeError("private-token-must-not-leak")
    monkeypatch.setattr("morgan_media_downloader.settings_window.check_provider", fail)
    monkeypatch.setattr("morgan_media_downloader.settings_window.verify_youtube_connection", fail)
    try:
        for button in (dialog.readiness_check, dialog.auth_test):
            button.click(); fn, callbacks = tasks[-1]
            payload = fn(None, None)
            assert "private-token" not in str(payload)
            dialog.profile.setEditText(dialog.profile.currentText() + "changed")
            callbacks["on_result"](payload); callbacks["on_finished"]()
            assert "Needs verification" in dialog.auth_progress.text()
            assert "Failed to complete" not in dialog.auth_progress.text()
        dialog.auth_test.click(); fn, callbacks = tasks[-1]
        callbacks["on_result"](fn(None, None)); callbacks["on_finished"]()
        assert "Failed to complete" in dialog.auth_progress.text()
    finally: _dispose(dialog)


def test_capture_activation_failure_does_not_claim_active_mode(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    from test_companion import MemoryStore, sample
    settings = AppSettings()
    controller = CompanionController(tmp_path / "control", MemoryStore())
    def fail(_mode): raise OSError("synthetic-private-error-must-not-display")
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None,
                            runtime_manager=_runtime(tmp_path), companion_controller=controller, account_callback=fail)
    try:
        dialog._pending_companion = controller.begin(); dialog._companion_deadline = float("inf")
        hello = controller.handle({"type": "hello"}, ORIGIN)
        controller.handle(dict(type="capture", operation_id=hello["operation_id"], nonce=hello["nonce"],
                              consent=True, incognito=True, store_id="incognito-store", cookies=[sample()]), ORIGIN)
        dialog._poll_companion()
        assert controller.store.data is not None
        assert "Keychain: Stored" in dialog.auth_progress.text()
        assert "Active authentication: Auto" in dialog.auth_progress.text()
        assert "activation could not be saved" in dialog.auth_status.text()
        assert "synthetic-private-error" not in dialog.auth_status.text()
    finally: _dispose(dialog)


def test_auth_test_routes_custom_proxy_and_stale_result_is_ignored(tmp_path, monkeypatch):
    settings = AppSettings(connection_mode="Direct / Normal Network")
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=_runtime(tmp_path))
    calls = []
    def verify(*args):
        calls.append(args)
        from morgan_media_downloader.auth import YouTubeConnection
        return YouTubeConnection("authenticated", "Signed in.", True)
    monkeypatch.setattr("morgan_media_downloader.settings_window.verify_youtube_connection", verify, raising=False)
    tasks = []
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, function, **kw: tasks.append((function, kw)))
    try:
        dialog.connection.setCurrentText("Custom SOCKS5 Proxy")
        dialog.socks_proxy_host.setText("localhost"); dialog.socks_proxy_port.setValue(9911)
        dialog.auth_mode.setCurrentText("Browser Cookies")
        dialog._test_auth()
        function, callbacks = tasks[-1]
        result = function(None, None)
        assert calls and calls[0][4] == "socks5h://localhost:9911"
        dialog.cookies_file.setText("changed")
        callbacks["on_result"](result)
        assert "signed in" not in dialog.auth_status.text().lower()
    finally: _dispose(dialog)


def test_nightly_runtime_choice_is_explicit_and_captured_before_background_work(tmp_path, monkeypatch):
    settings = AppSettings()
    runtime = _runtime(tmp_path); calls = []; tasks = []
    monkeypatch.setattr(runtime, "check_and_update", lambda *args, **kw: calls.append((args, kw)))
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=runtime)
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, fn, **kw: tasks.append(fn))
    try:
        assert dialog.runtime_channel.currentData() == "stable"
        dialog.runtime_channel.setCurrentIndex(1)
        next(button for button in dialog.runtime_action_buttons if button.text() == "Update Now").click()
        dialog.runtime_channel.setCurrentIndex(0)
        tasks[-1](None, None)
        assert calls == [((True, True), {"channel": "nightly"})]
        assert settings.yt_dlp_auto_install_updates == dialog.yt_auto_install.isChecked()
    finally: _dispose(dialog)
