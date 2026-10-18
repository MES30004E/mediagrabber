import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QMimeData, QPoint
from PySide6.QtGui import QPalette, QColor, QDragEnterEvent, QDragLeaveEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QPushButton
from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem, JobStatus

from test_ui_diagnostics import _window

APP = QApplication.instance() or QApplication([])


def test_sidebar_navigation_keyboard_and_existing_routes(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        nav = getattr(window.tabs, "navigation", None)
        assert nav is not None, "Top-level sections need sidebar navigation"
        nav.setCurrentRow(2); assert window.tabs.currentWidget() is window.tabs.widget(2)
        window.tabs.setCurrentWidget(window.console_tab); assert nav.currentRow() == 3
        window.activateWindow(); window.setFocus(); APP.processEvents()
        QTest.keyClick(window, Qt.Key.Key_1, Qt.KeyboardModifier.MetaModifier); APP.processEvents()
        assert window.tabs.currentIndex() == 0
        assert window.tabs.count() == 5
    finally: window.close(); APP.processEvents()


def test_theme_switch_restores_light_and_system_palette(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.settings.theme = "Dark"; window._apply_theme()
        assert APP.palette().color(QPalette.ColorRole.Window).lightness() < 80
        assert APP.palette().color(QPalette.ColorRole.Text).lightness() > 180
        window.settings.theme = "Light"; window._apply_theme()
        assert APP.palette().color(QPalette.ColorRole.Window).lightness() > 220
        assert APP.palette().color(QPalette.ColorRole.Text).lightness() < 80
        window.settings.theme = "System"; window._apply_theme()
        assert APP.palette().color(QPalette.ColorRole.Window) == APP.style().standardPalette().color(QPalette.ColorRole.Window)
    finally: window.close(); APP.processEvents()


def test_system_theme_refreshes_when_platform_reports_appearance_change(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.settings.theme = "System"
        stale = APP.palette(); stale.setColor(QPalette.ColorRole.Window, QColor("#010101")); APP.setPalette(stale)
        APP.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        assert APP.palette().color(QPalette.ColorRole.Window) == APP.style().standardPalette().color(QPalette.ColorRole.Window)
    finally: window.close(); APP.processEvents()


def test_closed_window_does_not_retheme_other_application_windows(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    window.settings.theme = "System"; window.close(); APP.processEvents()
    stale = APP.palette(); stale.setColor(QPalette.ColorRole.Window, QColor("#010101")); APP.setPalette(stale)
    window._system_appearance_changed()
    assert APP.palette().color(QPalette.ColorRole.Window) == QColor("#010101")


def test_settings_pages_scroll_and_auth_disclosure_preserves_config(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        panel = window.settings_panel
        for page in panel.pages.values():
            assert page.findChild(QScrollArea) is not None, "Every settings page must remain usable at small heights"
        disclosure = getattr(panel, "advanced_auth", None)
        assert disclosure is not None
        panel.auth_mode.setCurrentText("Browser Cookies")
        panel.browser.setCurrentText("Firefox"); panel.profile.setEditText("test-profile")
        disclosure.toggle.click(); disclosure.toggle.click()
        assert panel._collect().browser_profile == "test-profile"
        window.resize(900, 650); window.show_preferences(); APP.processEvents()
        assert panel.stack.width() > 300
    finally: window.close(); APP.processEvents()


def test_account_activation_uses_current_applied_settings_not_pending_form(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        panel = window.settings_panel
        window.settings.quality = "1080p"
        panel.quality.setCurrentText("360p")
        panel._persist_account_choice("YouTube Companion")
        assert window.settings.authentication_mode == "YouTube Companion"
        assert window.settings.quality == "1080p"
        assert window.settings_store.load().quality == "1080p"
        assert panel.quality.currentText() == "360p"
    finally: window.close(); APP.processEvents()


def test_download_primary_action_and_empty_states_are_actionable(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        assert window.download_button.property("primary") is True
        assert window.input.accessibleName()
        assert getattr(window, "queue_empty", None) is not None
        window.jobs.clear(); window._refresh_queue()
        assert not window.queue_empty.isHidden()
        job = DownloadJob(MediaItem("https://example.test/video", "Example"), DownloadOptions())
        window.jobs[job.id] = job; window._refresh_queue()
        assert window.queue_empty.isHidden(), "Empty-state help must disappear when jobs exist"
        window.history_search.setText("no results")
        assert not window.history_empty.isHidden()
    finally: window.close(); APP.processEvents()


def test_small_download_layout_never_squashes_options_or_table(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.resize(900, 650); APP.processEvents()
        assert window.quality.height() >= window.quality.minimumSizeHint().height()
        assert window.folder.height() >= window.folder.minimumSizeHint().height()
        assert window.item_table.height() >= 160
        window.more_button.click(); APP.processEvents()
        assert window.template.height() >= window.template.minimumSizeHint().height()
    finally: window.close(); APP.processEvents()


def test_drag_feedback_resets_when_pointer_leaves(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        data = QMimeData(); data.setText("https://example.test/video")
        event = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, data, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.input.dragEnterEvent(event)
        assert event.isAccepted() and window.input.property("dropActive") is True
        window.input.dragLeaveEvent(QDragLeaveEvent())
        assert window.input.property("dropActive") is False
    finally: window.close(); APP.processEvents()


def test_private_analysis_failure_keeps_auth_and_exposes_reconnect(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    window = _window(tmp_path, monkeypatch)
    monkeypatch.setattr(QMessageBox, "exec", lambda *_: QMessageBox.StandardButton.Cancel)
    try:
        window.settings.authentication_mode = "Browser Cookies"
        window.input.setPlainText("https://www.youtube.com/playlist?list=WL")
        window._show_worker_error("Private video: requested format is not available", "Cookie: fixture-private")
        assert "Reconnect" in window.account_button.text()
        assert not window.analysis_diagnostics.isHidden()
        assert window.settings.authentication_mode == "Browser Cookies"
        assert "fixture-private" not in window.console_store.text()
        window.account_button.click()
        assert window.tabs.currentWidget() is window.settings_panel
    finally: window.close(); APP.processEvents()


def test_non_youtube_auth_failure_uses_source_neutral_recovery(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.input.setPlainText("https://vimeo.com/private")
        window._show_worker_error("Private video: sign in required", "Cookie: fixture-secret")
        assert "YouTube" not in window.account_button.text()
        assert "fixture-secret" not in window._analysis_error_details
    finally: window.close(); APP.processEvents()


def test_explicit_auth_failed_retry_uses_reconnected_profile_not_old_snapshot(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.settings.authentication_mode = "Browser Cookies"
        window.settings.cookies_browser = "Firefox"; window.settings.browser_profile = "new-profile"
        job = DownloadJob(MediaItem("https://www.youtube.com/watch?v=fixture", "Private"),
                          DownloadOptions(authentication_mode="None", quality="720p"))
        job.status = JobStatus.FAILED; job.error = "Private video: sign in required"
        window._show_job_banner(job, "Authentication failed")
        account_action = getattr(window, "job_account_button", None)
        assert account_action is not None and not account_action.isHidden()
        other = DownloadJob(MediaItem("https://example.test/video", "Other"), DownloadOptions(authentication_mode="None"))
        other.status = JobStatus.FAILED; other.error = "Network unavailable"
        window.jobs = {job.id: job, other.id: other}
        window._resume([job, other])
        assert (job.options.authentication_mode, job.options.cookies_browser, job.options.browser_profile) == ("Browser Cookies", "Firefox", "new-profile")
        assert job.options.quality == "720p" and job.status == JobStatus.WAITING
        assert other.options.authentication_mode == "None", "Unrelated option snapshots must not be rewritten"
    finally: window.close(); APP.processEvents()


def test_compact_console_and_auth_banner_do_not_clip_action_labels(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.resize(900, 650); window.tabs.setCurrentWidget(window.console_tab); APP.processEvents()
        for button in window.console_tab.findChildren(QPushButton):
            assert button.width() >= button.minimumSizeHint().width(), button.text()
        job = DownloadJob(MediaItem("https://www.youtube.com/watch?v=fixture", "Example"), DownloadOptions())
        job.error = "Private video: sign in required"
        window.tabs.setCurrentIndex(1); window._show_job_banner(job, "Authentication failed — reconnect your account before retrying")
        APP.processEvents()
        for button in window.job_banner.findChildren(QPushButton):
            assert button.width() >= button.minimumSizeHint().width(), button.text()
    finally: window.close(); APP.processEvents()
