"""Synthetic large-playlist UI contracts; never fetch private media or cookies."""
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtTest import QTest
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QApplication, QPushButton

from morgan_media_downloader.models import MediaItem, DownloadOptions
from morgan_media_downloader.ui import AnalysisContext, MainWindow
from test_ui_diagnostics import _window

APP = QApplication.instance() or QApplication([])


def _populate(window, items):
    value = "https://example.test/playlist"
    window.input.setPlainText(value)
    context = AnalysisContext("playlist-fixture", value, "preview", DownloadOptions())
    window._analysis_ready({"items": items, "torrent": None, "context": context})
    APP.processEvents()


def test_filter_and_visible_selection_preserve_hidden_choices_and_enqueue(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        items = [MediaItem(f"https://example.test/{i}", title, uploader="Daft Punk", duration=120+i)
                 for i, title in enumerate(["Instant Crush", "Get Lucky", "Giorgio", "Lucky remix"])]
        _populate(window, items)
        window.playlist_filter.setText("lucky")
        assert [r for r in range(4) if not window.item_table.isRowHidden(r)] == [1, 3]
        window._select_items(False)  # Explicit Select None clears the whole checked set.
        window._select_items(True)   # Select All Visible only changes the filtered rows.
        assert [item.selected for item in items] == [False, True, False, True]
        window.playlist_filter.setText("Instant")
        window._invert_items()
        assert [item.selected for item in items] == [True, True, False, True]
        assert "3 selected" in window.selection_count.text() and "1 visible" in window.selection_count.text()
        window.enqueue_selected()
        assert {job.item.title for job in window.jobs.values()} == {"Instant Crush", "Get Lucky", "Lucky remix"}
    finally: window.close(); APP.processEvents()


def test_space_toggles_highlighted_rows_and_stale_input_stays_disabled(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        _populate(window, [MediaItem(f"https://example.test/{i}", str(i)) for i in range(4)])
        table = window.item_table
        window._select_items(False)
        for row in (1, 2):
            table.selectionModel().select(table.model().index(row, 2),
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        table.setFocus(); QTest.keyClick(table, Qt.Key.Key_Space)
        assert [item.selected for item in window.items] == [False, True, True, False]
        window.input.setPlainText("https://example.test/changed")
        window._select_items(True)
        assert not window.add_button.isEnabled(), "Bulk checks cannot authorize stale analysis"
    finally: window.close(); APP.processEvents()


def test_large_playlist_preview_is_lazy_and_follows_current_row(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); calls = []
    monkeypatch.setattr(window, "_start_thumbnail_preview", lambda item: calls.append(item.source_url))
    try:
        window.preview_section.setExpanded(True)
        _populate(window, [MediaItem(f"https://example.test/{i}", f"Track {i}", thumbnail=f"https://example.test/{i}.jpg", duration=60+i)
                           for i in range(828)])
        assert calls == ["https://example.test/0"], "Flat playlist analysis must not request all thumbnails or per-video metadata"
        window.item_table.setCurrentCell(827, 2)
        assert calls == ["https://example.test/0", "https://example.test/827"]
        assert "Track 827" in window.preview_details.text() and "14:47" in window.preview_details.text()
        window.playlist_filter.setText("Track 827")
        assert "828 selected" in window.selection_count.text() and "1 visible" in window.selection_count.text()
    finally: window.close(); APP.processEvents()


def test_collapsible_panels_and_proportions_restore_without_clipping_footer(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); runtime = window.runtime_manager
    try:
        window.resize(1000, 850); APP.processEvents()
        window.options_section.setExpanded(False)
        window.preview_section.setExpanded(True)
        window.playlist_splitter.setSizes([400, 160]); APP.processEvents()
        sizes = window.playlist_splitter.sizes()
        window._persist_settings()
        assert window.settings_store.load().playlist_panel_sizes == sizes
        normal_width = window.width()
        window.fullscreen_action.trigger(); APP.processEvents()
        assert window.isFullScreen()
        window._persist_settings()
        assert window.settings_store.load().window_width == normal_width, "Fullscreen must not overwrite the normal window size"
        window.fullscreen_action.trigger(); APP.processEvents()
        assert not window.isFullScreen()
        window.showFullScreen(); APP.processEvents()
        assert window.fullscreen_action.isChecked(), "Native window state must synchronize the menu action"
        window.showNormal(); APP.processEvents()
    finally: window.close(); APP.processEvents()
    reopened = MainWindow(runtime); reopened.dispatch_timer.stop(); reopened.show(); APP.processEvents()
    try:
        assert not reopened.options_section.toggle.isChecked()
        assert reopened.preview_section.toggle.isChecked()
        restored = reopened.playlist_splitter.sizes()
        assert abs(sizes[0]/sum(sizes) - restored[0]/sum(restored)) < .08
        reopened.resize(900, 650); APP.processEvents()
        assert reopened.add_button.isVisible()
        assert reopened.add_button.mapTo(reopened, reopened.add_button.rect().bottomRight()).y() < reopened.height()
    finally: reopened.close(); APP.processEvents()


def test_collapsed_preview_defers_thumbnail_until_expanded(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); calls = []
    monkeypatch.setattr(window, "_start_thumbnail_preview", lambda item: calls.append(item.source_url))
    try:
        window.preview_section.setExpanded(False)
        _populate(window, [MediaItem("https://example.test/a", "First", thumbnail="https://example.test/a.jpg")])
        assert calls == []
        window.preview_section.setExpanded(True)
        assert calls == ["https://example.test/a"]
    finally: window.close(); APP.processEvents()


def test_old_thumbnail_result_and_progress_cannot_replace_new_preview(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); tasks = []
    path = tmp_path / "synthetic-thumbnail.png"
    pixmap = QPixmap(4, 4); pixmap.fill(QColor("blue")); assert pixmap.save(str(path))
    def fetch(_url, _headers, report, *_, cancel_event=None):
        report(90); return str(path)
    monkeypatch.setattr("morgan_media_downloader.ui.fetch_thumbnail", fetch)
    monkeypatch.setattr(window.task_manager, "start", lambda kind, fn, **kw: tasks.append((fn, kw)) if kind == "thumbnail-preview" else None)
    try:
        window.preview_section.setExpanded(True)
        _populate(window, [MediaItem(f"https://example.test/{i}", f"Track {i}", thumbnail=f"https://example.test/{i}.jpg") for i in range(2)])
        old_fn, old = tasks[-1]
        window.item_table.setCurrentCell(1, 2)
        old["on_finished"](old["task_id"])
        new_fn, new = tasks[-1]
        old["on_result"](old_fn(None, old["on_progress"]))
        assert window.thumbnail.pixmap().isNull(), "A cancelled row's thumbnail must not replace the pending current row"
        assert "90%" not in window.thumbnail.text()
        new["on_result"](new_fn(None, new["on_progress"]))
        assert not window.thumbnail.pixmap().isNull()
    finally: window.close(); APP.processEvents()


def test_rapid_row_changes_keep_one_worker_and_only_latest_pending_thumbnail(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); tasks = []
    monkeypatch.setattr(window.task_manager, "start", lambda kind, fn, **kw: tasks.append((kind, fn, kw)))
    try:
        window.preview_section.setExpanded(True)
        _populate(window, [MediaItem(f"https://example.test/{i}", str(i), thumbnail=f"https://example.test/{i}.jpg") for i in range(20)])
        for row in range(1, 20): window.item_table.setCurrentCell(row, 2)
        thumbnails = [entry for entry in tasks if entry[0] == "thumbnail-preview"]
        assert len(thumbnails) == 1, "Cancelled network operations must finish before starting another worker"
        first = thumbnails[0][2]; first["on_finished"](first["task_id"])
        thumbnails = [entry for entry in tasks if entry[0] == "thumbnail-preview"]
        assert len(thumbnails) == 2
        urls = []
        def fetch(url, *args, **kwargs): urls.append(url); return None
        monkeypatch.setattr("morgan_media_downloader.ui.fetch_thumbnail", fetch)
        import threading
        thumbnails[1][1](threading.Event(), lambda *_: None)
        assert urls == ["https://example.test/19.jpg"]
    finally: window.close(); APP.processEvents()


def test_narrow_layout_keeps_primary_actions_inside_viewport_with_options_open(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        window.resize(900, 650); APP.processEvents()
        assert window.item_table.height() >= 4 * window.preview_section.height(), "Initial workspace must prioritize the playlist, not an empty preview"
        window.options_section.setExpanded(True); window.more_button.click(); APP.processEvents()
        folder_button = next(b for b in window.options_section.findChildren(QPushButton) if b.text() == "Choose Folder…")
        assert folder_button.mapTo(window, folder_button.rect().bottomRight()).x() < window.width()
        for button in (window.analyse_button, window.download_button, window.add_button):
            point = button.mapTo(window, button.rect().bottomRight())
            assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height()
    finally: window.close(); APP.processEvents()


def test_preview_never_falls_back_to_direct_when_selected_proxy_is_unavailable(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); tasks = []
    monkeypatch.setattr(window.task_manager, "start", lambda *args, **kwargs: tasks.append(args))
    def unavailable(): raise ConnectionError("synthetic unavailable Tor")
    monkeypatch.setattr(window, "_proxy", unavailable)
    try:
        window.preview_section.setExpanded(True)
        _populate(window, [MediaItem("https://example.test/video", "Example", thumbnail="https://example.test/thumb.jpg")])
        assert not any(args[0] == "thumbnail-preview" for args in tasks), "Thumbnail requests must not bypass the selected network route"
        assert "unavailable" in window.thumbnail.text().lower()
    finally: window.close(); APP.processEvents()


def test_collapsing_preview_before_restart_preserves_expanded_proportions(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch); runtime = window.runtime_manager
    try:
        window.resize(1100, 900); window.preview_section.setExpanded(True); APP.processEvents()
        window.playlist_splitter.setSizes([300, 220]); APP.processEvents()
        expanded = window.playlist_splitter.sizes()
        window.preview_section.setExpanded(False); APP.processEvents()
        window._persist_settings()
        assert window.settings_store.load().playlist_panel_sizes == expanded
    finally: window.close(); APP.processEvents()
    reopened = MainWindow(runtime); reopened.dispatch_timer.stop(); reopened.show(); APP.processEvents()
    try:
        assert not reopened.preview_section.toggle.isChecked()
        reopened.preview_section.setExpanded(True); APP.processEvents()
        restored = reopened.playlist_splitter.sizes()
        assert abs(expanded[0]/sum(expanded) - restored[0]/sum(restored)) < .08
    finally: reopened.close(); APP.processEvents()
