from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea
from test_settings_window import _runtime, _dispose, _APP
from morgan_media_downloader.settings_window import SettingsWindow
from morgan_media_downloader.settings import AppSettings
from morgan_media_downloader.managed_tor import ManagedTor
from test_components import catalog, release
from morgan_media_downloader.diagnostics import CheckResult


def test_components_page_checks_in_worker_without_applying_unsaved_settings(tmp_path, monkeypatch):
    settings = AppSettings(); tasks = []; saved = []
    service = catalog(tmp_path, release)
    monkeypatch.setattr("morgan_media_downloader.components._binary_check", lambda name: CheckResult(name, True, name + " version fixture"))
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: saved.append(True),
                            runtime_manager=_runtime(tmp_path), component_catalog=service)
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, fn, **kw: tasks.append((kind, fn, kw)))
    try:
        assert "Updates" in dialog.pages
        dialog.download_dir.setText("/tmp/unsaved-component-fixture")
        dialog.components_check.click()
        assert len(tasks) == 1 and not saved
        kind, operation, callbacks = tasks[0]
        assert kind == "components" and not dialog.components_check.isEnabled()
        callbacks["on_result"](operation(None, None)); callbacks["on_finished"]()
        assert "v1.3.1" in dialog.component_labels["app"].text()
        assert "Last successful update: Not managed yet" in dialog.component_labels["app"].text()
        assert "unconfirmed" in dialog.component_labels["companion"].text()
        assert dialog.component_labels["app"].textFormat() == Qt.TextFormat.PlainText
        assert dialog.components_check.isEnabled() and not saved
        assert settings.download_dir != "/tmp/unsaved-component-fixture"
    finally: _dispose(dialog)


def test_background_update_tick_checks_component_catalog_without_rechecking_within_day(tmp_path, monkeypatch):
    from test_ui_diagnostics import _window
    from test_yt_runtime import release_payload
    window = _window(tmp_path, monkeypatch); urls = []
    window.settings.yt_dlp_check_updates_on_startup = True
    window.runtime_manager._fetcher = lambda *_: release_payload("2026.07.04")
    window.settings_panel.components.fetcher = lambda url, timeout: urls.append(url) or release(url, timeout)
    monkeypatch.setattr("morgan_media_downloader.components._binary_check", lambda name: CheckResult(name, False, "fixture unavailable"))
    def start(kind, operation, **callbacks):
        if kind not in {"yt-runtime", "components"}: return
        result = operation(None, None)
        if callbacks.get("on_result"): callbacks["on_result"](result)
        if callbacks.get("on_finished"): callbacks["on_finished"]()
    monkeypatch.setattr(window.task_manager, "start", start)
    try:
        window._start_yt_dlp_update_check(); window._start_yt_dlp_update_check()
        assert len(urls) == 3
        assert "v1.3.1" in window.settings_panel.component_labels["app"].text()
    finally: window.close(); _APP.processEvents()


def test_component_failure_restores_actions_and_offers_safe_recovery(tmp_path, monkeypatch):
    settings = AppSettings(); tasks = []
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=_runtime(tmp_path))
    monkeypatch.setattr(dialog.task_manager, "start", lambda kind, fn, **kw: tasks.append(kw))
    try:
        dialog.components_refresh.click()
        tasks[0]["on_error"]("private-fixture-detail", "traceback")
        tasks[0]["on_finished"]()
        assert "private-fixture-detail" not in dialog.components_status.text()
        assert "Retry" in dialog.components_status.text()
        assert dialog.components_check.isEnabled() and dialog.components_refresh.isEnabled()
    finally: _dispose(dialog)


def test_update_controls_fit_narrow_settings_page_without_horizontal_clipping(tmp_path):
    settings = AppSettings()
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=_runtime(tmp_path))
    try:
        dialog.stack.setCurrentWidget(dialog.pages["Updates"])
        dialog.resize(790, 610); dialog.show(); _APP.processEvents()
        scroll = dialog.pages["Updates"].findChild(QScrollArea)
        assert scroll.horizontalScrollBar().maximum() == 0
        assert dialog.components_check.width() <= scroll.viewport().width()
    finally: _dispose(dialog)


def test_runtime_card_refreshes_after_update_without_waiting_for_another_catalog_probe(tmp_path, monkeypatch):
    settings = AppSettings(); runtime = _runtime(tmp_path)
    dialog = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: None, runtime_manager=runtime)
    try:
        info = runtime.describe(); info["active_version"] = "2026.10.19"
        monkeypatch.setattr(runtime, "describe", lambda: info)
        dialog._refresh_runtime_status()
        assert "Installed: 2026.10.19" in dialog.component_labels["yt_dlp"].text()
    finally: _dispose(dialog)
