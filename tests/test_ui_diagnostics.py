import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from morgan_media_downloader.provider import ProviderStatus
from morgan_media_downloader.settings import AppSettings, SettingsStore
from morgan_media_downloader.ui import MainWindow
from morgan_media_downloader.yt_runtime import RuntimeSnapshot, YtDlpRuntimeManager


_APP = QApplication.instance() or QApplication([])


def _window(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path / "data")); monkeypatch.setenv("MORGAN_LOG_DIR", str(tmp_path / "logs"))
    SettingsStore(tmp_path / "data" / "settings.json").save(AppSettings(show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False))
    runtime = YtDlpRuntimeManager(tmp_path / "runtime", bundled_loader=lambda: RuntimeSnapshot("2026.07.04", "Bundled", object), provider_checker=lambda: None); runtime.initialize()
    monkeypatch.setattr("morgan_media_downloader.ui.check_provider", lambda *_: ProviderStatus("available", "test", "script"))
    window = MainWindow(runtime); window.dispatch_timer.stop(); window.show(); return window


def test_console_tab_adaptive_queue_job_details_and_warning_checklist(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Download", "Queue", "History", "Console", "Settings"]
    media = DownloadJob(MediaItem("https://test/media", "Media", source="YouTube"), DownloadOptions(download_dir=str(tmp_path)))
    media.status = JobStatus.COMPLETED_WARNINGS; media.warnings = ["Japanese subtitles unavailable"]
    media.verification = {"video": True, "audio": True, "subtitles": ["eng • mov_text"], "thumbnail": True, "metadata": True}
    torrent = DownloadJob(MediaItem("magnet:?x", "Torrent"), DownloadOptions(download_dir=str(tmp_path)), kind="torrent")
    window.jobs = {media.id: media, torrent.id: torrent}; window._refresh_queue()
    assert window.queue_table.horizontalHeaderItem(0).text() == "Title"
    assert "Connected peers" not in [window.queue_table.horizontalHeaderItem(i).text() for i in range(window.queue_table.columnCount())]
    window.queue_filter.setCurrentText("Torrents")
    assert "Connected peers" in [window.queue_table.horizontalHeaderItem(i).text() for i in range(window.queue_table.columnCount())]
    details = window._job_details_text(media); warnings = window._warning_details_text(media)
    assert "Completed with warnings" in details and "✓ Subtitle embedded" in warnings and "⚠ Japanese" in warnings
    window.console_store.append("YT-DLP", "job event", media.id); window._banner_job_id = media.id; window.view_job_console()
    assert window.tabs.currentWidget() is window.console_tab and "job event" in window.console_view.toPlainText()
    window.close(); _APP.processEvents()


def test_thumbnail_preview_slots_render_real_pixmap_and_handle_known_unknown_progress(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    image = QPixmap(80, 40); image.fill(); path = tmp_path / "thumbnail.png"; assert image.save(str(path))
    window.thumbnail_progress.show(); window._thumbnail_progress_ready({"thumbnail_progress": None})
    assert window.thumbnail_progress.minimum() == window.thumbnail_progress.maximum() == 0
    window._thumbnail_progress_ready({"thumbnail_progress": 72})
    assert window.thumbnail_progress.value() == 72 and "72%" in window.thumbnail.text()
    window._thumbnail_ready(str(path))
    assert window.thumbnail.pixmap() is not None and not window.thumbnail.pixmap().isNull()
    window._thumbnail_error("fixture failure", "")
    assert "unavailable" in window.thumbnail.text().lower()
    window.close(); _APP.processEvents()


def test_selected_job_and_details_survive_live_updates_reloads_and_transitions(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    jobs = []
    for index in range(30):
        job = DownloadJob(MediaItem(f"https://test/{index}", f"Media {index}", source="Fixture"),
                          DownloadOptions(download_dir=str(tmp_path)))
        jobs.append(job)
    active = jobs[15]; active.status = JobStatus.DOWNLOADING; active.total_bytes = 10_000
    window.jobs = {job.id: job for job in jobs}; window._refresh_queue()
    window.queue_table.selectRow(15); _APP.processEvents()
    window.view_job_details(); _APP.processEvents()
    inline_widget = window.job_details
    dialog_widget = window.details_dialog_text
    progress_widget = window.queue_table.cellWidget(15, 3)
    window.queue_table.verticalScrollBar().setValue(10)
    scroll_position = window.queue_table.verticalScrollBar().value()

    for step in range(1, 101):
        active.progress = float(step); active.downloaded_bytes = step * 100
        active.speed = 2048 + step; active.eta = 100 - step
        window._refresh_queue()
    assert window.selected_job_id == active.id
    assert window.job_details is inline_widget and window.details_dialog_text is dialog_widget
    assert "Progress: 100.0%" in window.job_details.toPlainText()
    assert "Media 15" in window.details_dialog_text.toPlainText()
    assert window.queue_table.cellWidget(15, 3) is progress_widget
    assert window.queue_table.verticalScrollBar().value() == scroll_position

    for status in (JobStatus.PAUSED, JobStatus.WAITING, JobStatus.COMPLETED, JobStatus.FAILED):
        active.status = status; window._refresh_queue()
        assert window.selected_job_id == active.id
        assert status.value in window.job_details.toPlainText()

    # Force a structural reload, then move the selected job to another queue view.
    window.queue_filter.setCurrentText("All"); _APP.processEvents()
    assert window.selected_job_id == active.id and "Media 15" in window.job_details.toPlainText()
    window.jobs.pop(active.id); window._refresh_queue()
    assert window.selected_job_id == "" and not window.job_details.toPlainText()
    assert window.details_dialog_text is not None and not window.details_dialog_text.toPlainText()
    window.close(); _APP.processEvents()
