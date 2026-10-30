import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

from morgan_media_downloader.managed_tor import ManagedTor
from morgan_media_downloader.settings import AppSettings
from morgan_media_downloader.settings_window import SettingsWindow
from test_settings_window import _runtime, _dispose, _APP


class Stager:
    def __init__(self):
        self.calls = 0
        self.info = {"status": "No app update staged; nothing installed", "staged_version": "", "staged_path": "",
                     "last_stage": "", "last_error": ""}
    def describe(self): return dict(self.info)
    def stage_latest(self, cancel, progress):
        self.calls += 1; progress({"stage": "Downloading", "downloaded": 5, "total": 10})
        self.info.update(status="Verified candidate staged; not installed", staged_version="0.2.0",
                         staged_path="/synthetic/staged.app", last_stage="2026-10-29T12:00:00+00:00")
        return self.describe()


def dialog(tmp_path, saved):
    settings = AppSettings()
    stager = Stager()
    window = SettingsWindow(settings, ManagedTor(settings.tor_browser_path), lambda *_: saved.append(True),
                            runtime_manager=_runtime(tmp_path), app_update_manager=stager)
    return window, stager, settings


def test_app_staging_runs_in_worker_and_never_applies_or_installs(tmp_path, monkeypatch):
    saved = []; window, stager, settings = dialog(tmp_path, saved); tasks = []
    monkeypatch.setattr(window.task_manager, "start", lambda kind, operation, **callbacks: tasks.append((kind, operation, callbacks)))
    try:
        window.download_dir.setText("/synthetic/unsaved")
        window.app_stage_button.click()
        assert len(tasks) == 1 and tasks[0][0] == "app-update" and stager.calls == 0
        assert not window.app_stage_button.isEnabled() and window.app_stage_cancel.isEnabled()
        _, operation, callbacks = tasks[0]
        result = operation(threading.Event(), callbacks["on_progress"])
        assert "Downloading" in window.app_stage_status.text()
        callbacks["on_result"](result); callbacks["on_finished"]()
        text = window.app_stage_status.text()
        assert "0.2.0" in text and "not installed" in text
        assert "Last successful stage:" in text
        assert "Last successful update:" not in text
        assert not saved and settings.download_dir != "/synthetic/unsaved"
        assert window.app_stage_status.textFormat() == Qt.TextFormat.PlainText
        assert window.app_stage_button.isEnabled() and not window.app_stage_cancel.isEnabled()
    finally: _dispose(window)


def test_app_staging_cancel_and_error_restore_buttons_without_raw_error_leak(tmp_path, monkeypatch):
    window, stager, _ = dialog(tmp_path, []); tasks = []; cancelled = []
    monkeypatch.setattr(window.task_manager, "start", lambda kind, operation, **callbacks: tasks.append(callbacks))
    monkeypatch.setattr(window.task_manager, "cancel_kind", cancelled.append)
    try:
        window.app_stage_button.click(); window.app_stage_cancel.click()
        assert cancelled == ["app-update"]
        stager.info.update(status="Staging cancelled; nothing installed")
        tasks[0]["on_finished"]()
        assert "cancelled" in window.app_stage_status.text().lower()
        assert window.app_stage_button.isEnabled()
        window.app_stage_button.click()
        tasks[-1]["on_error"]("synthetic-private-cookie-value", "raw traceback")
        tasks[-1]["on_finished"]()
        assert "synthetic-private" not in window.app_stage_status.text()
        assert window.app_stage_button.isEnabled()
    finally: _dispose(window)


def test_app_stage_controls_fit_narrow_updates_page(tmp_path):
    window, _, _ = dialog(tmp_path, [])
    try:
        window.stack.setCurrentWidget(window.pages["Updates"])
        window.resize(790, 610); window.show(); _APP.processEvents()
        scroll = window.pages["Updates"].findChild(QScrollArea)
        assert scroll.horizontalScrollBar().maximum() == 0
        assert window.app_stage_button.width() <= scroll.viewport().width()
    finally: _dispose(window)
