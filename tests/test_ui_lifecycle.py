import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.provider import ProviderStatus
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from morgan_media_downloader.settings import AppSettings, SettingsStore
from morgan_media_downloader.ui import AnalysisContext, MainWindow
from morgan_media_downloader.yt_runtime import RuntimeSnapshot, YtDlpRuntimeManager


_APP = QApplication.instance() or QApplication([])


def _spin(condition, timeout=2):
    deadline = time.monotonic() + timeout
    while condition() and time.monotonic() < deadline:
        _APP.processEvents()
        time.sleep(0.001)
    assert not condition()


def test_two_hundred_analyse_cancel_tab_console_and_settings_cycles_close_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MORGAN_LOG_DIR", str(tmp_path / "logs"))
    SettingsStore(tmp_path / "data" / "settings.json").save(
        AppSettings(show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False))
    runtime = YtDlpRuntimeManager(
        tmp_path / "runtime",
        bundled_loader=lambda: RuntimeSnapshot("2026.07.04", "Bundled", object),
        provider_checker=lambda: None,
    )
    runtime.initialize()
    monkeypatch.setattr("morgan_media_downloader.ui.check_provider",
                        lambda *_: ProviderStatus("available", "test", "script"))

    def analysis(values, proxy, settings, snapshot, context, cancel, progress):
        progress("Fetching metadata…")
        cancel.wait(0.003)
        return {"items": [], "torrent": None, "context": context}

    monkeypatch.setattr("morgan_media_downloader.ui._analysis_operation", analysis)
    warnings = []
    previous = qInstallMessageHandler(lambda _kind, _context, message: warnings.append(message))
    try:
        window = MainWindow(runtime)
        window.dispatch_timer.stop()
        window.show()
        for cycle in range(200):
            window.input.setPlainText(f"test search {cycle}")
            window.analyse()
            assert window.analysis_task_id
            window.tabs.setCurrentIndex(cycle % window.tabs.count())
            window.console_store.append("APP", f"cycle {cycle}")
            window._refresh_queue(); window.settings_panel._collect()
            window.analyse()  # Cancel the active analysis.
            _spin(lambda: bool(window.analysis_task_id))
        window.input.setPlainText("final running analysis")
        window.analyse()
        window.close()
        _spin(lambda: window.task_manager.active_count > 0)
        assert not window.clean_marker.exists()
    finally:
        qInstallMessageHandler(previous)
    dangerous = [message for message in warnings if "QObject" in message and
                 any(term in message.lower() for term in ("thread", "destroyed", "deleted"))]
    assert dangerous == []


def test_download_without_analyse_and_download_all_queue_independently(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MORGAN_LOG_DIR", str(tmp_path / "logs"))
    SettingsStore(tmp_path / "data" / "settings.json").save(
        AppSettings(show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False))
    runtime = YtDlpRuntimeManager(tmp_path / "runtime", bundled_loader=lambda: RuntimeSnapshot("2026.07.04", "Bundled", object), provider_checker=lambda: None)
    runtime.initialize()
    monkeypatch.setattr("morgan_media_downloader.ui.check_provider", lambda *_: ProviderStatus("available", "test", "script"))

    def analysis(values, proxy, settings, snapshot, context, cancel, progress):
        value = values[0]
        return {"items": [MediaItem(value, f"Title {value}", source="Test")],
                "torrent": None, "context": context}

    monkeypatch.setattr("morgan_media_downloader.ui._analysis_operation", analysis)
    window = MainWindow(runtime); window.dispatch_timer.stop(); window.show()
    window.input.setPlainText("one\ntwo")
    window.download_input()
    _spin(lambda: window.task_manager.active_count > 0)
    assert len(window.jobs) == 2
    assert all(job.status == JobStatus.WAITING for job in window.jobs.values())
    window.close(); _APP.processEvents()


def test_media_torrent_and_analysis_have_independent_task_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MORGAN_LOG_DIR", str(tmp_path / "logs"))
    SettingsStore(tmp_path / "data" / "settings.json").save(
        AppSettings(show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False,
                    concurrent_downloads=1, torrent_max_active=1))
    runtime = YtDlpRuntimeManager(tmp_path / "runtime", bundled_loader=lambda: RuntimeSnapshot("2026.07.04", "Bundled", object), provider_checker=lambda: None)
    runtime.initialize()
    monkeypatch.setattr("morgan_media_downloader.ui.check_provider", lambda *_: ProviderStatus("available", "test", "script"))

    def held(job, *args):
        cancel, progress = args[-2], args[-1]
        cancel.wait(2)
        return job

    monkeypatch.setattr("morgan_media_downloader.ui._media_download_operation", held)
    monkeypatch.setattr("morgan_media_downloader.ui._torrent_download_operation", held)
    window = MainWindow(runtime); window.dispatch_timer.stop(); window.show()
    media = DownloadJob(MediaItem("https://example.test/video", "Media"), DownloadOptions(download_dir=str(tmp_path)))
    torrent = DownloadJob(MediaItem("magnet:?xt=urn:btih:abc", "Torrent"), DownloadOptions(download_dir=str(tmp_path)), kind="torrent", torrent_source="magnet:?xt=urn:btih:abc")
    window.jobs = {media.id: media, torrent.id: torrent}
    window._dispatch()
    assert len(window.active) == 2
    assert window.analyse_button.isEnabled()
    window.input.setPlainText("another search")
    monkeypatch.setattr("morgan_media_downloader.ui._analysis_operation",
                        lambda values, proxy, settings, snapshot, context, cancel, progress: {"items": [], "torrent": None, "context": context})
    window.analyse()
    assert window.task_manager.active_ids("analysis")
    window.close(); _APP.processEvents()
    assert window.task_manager.active_count == 0


def test_input_change_marks_analysis_stale_and_connection_selection_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MORGAN_LOG_DIR", str(tmp_path / "logs"))
    SettingsStore(tmp_path / "data" / "settings.json").save(AppSettings(show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False))
    runtime = YtDlpRuntimeManager(tmp_path / "runtime", bundled_loader=lambda: RuntimeSnapshot("2026.07.04", "Bundled", object), provider_checker=lambda: None); runtime.initialize()
    monkeypatch.setattr("morgan_media_downloader.ui.check_provider", lambda *_: ProviderStatus("available", "test", "script"))
    window = MainWindow(runtime); window.dispatch_timer.stop(); window.show()
    window.input.setPlainText("https://example.test/old")
    context = AnalysisContext("a", "https://example.test/old", "preview", DownloadOptions(download_dir=str(tmp_path)))
    window._analysis_ready({"items": [MediaItem("https://example.test/old", "Old result")], "torrent": None, "context": context})
    window.input.setPlainText("https://example.test/new")
    assert window.analysis_stale
    assert not window.add_button.isEnabled()
    assert "Input changed" in window.summary.text()
    starts = []
    monkeypatch.setattr(window.managed_tor, "start", lambda: starts.append(True) or True)
    window._connection_changed("Managed Tor")
    assert starts == [True]
    assert SettingsStore(tmp_path / "data" / "settings.json").load().connection_mode == "Managed Tor"
    assert window.settings_panel.connection.currentText() == "Managed Tor"
    window.close(); _APP.processEvents()


def test_unclean_shutdown_marker_shows_recovery_banner_and_clean_close_removes_it(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    marker = data / "running.marker"
    marker.write_text("stale-pid", encoding="utf-8")
    monkeypatch.setenv("MORGAN_DATA_DIR", str(data))
    monkeypatch.setenv("MORGAN_LOG_DIR", str(tmp_path / "logs"))
    SettingsStore(data / "settings.json").save(
        AppSettings(show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False))
    runtime = YtDlpRuntimeManager(data / "runtime", bundled_loader=lambda: RuntimeSnapshot("2026.07.04", "Bundled", object), provider_checker=lambda: None)
    runtime.initialize()
    monkeypatch.setattr("morgan_media_downloader.ui.check_provider", lambda *_: ProviderStatus("available", "test", "script"))

    window = MainWindow(runtime)
    window.dispatch_timer.stop()
    window.show()
    assert window.previous_crash
    assert window.banner.isVisible()
    assert "did not close normally" in window.banner_text.text()
    window.close()
    _APP.processEvents()
    assert not marker.exists()


def test_converter_ui_presets_custom_switch_and_extension(tmp_path, monkeypatch):
    data = tmp_path / "data"; monkeypatch.setenv("MORGAN_DATA_DIR", str(data)); monkeypatch.setenv("MORGAN_LOG_DIR", str(tmp_path / "logs"))
    SettingsStore(data / "settings.json").save(AppSettings(show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False))
    runtime = YtDlpRuntimeManager(data / "runtime", bundled_loader=lambda: RuntimeSnapshot("2026.07.04", "Bundled", object), provider_checker=lambda: None); runtime.initialize()
    monkeypatch.setattr("morgan_media_downloader.ui.check_provider", lambda *_: ProviderStatus("available", "test", "script"))
    source = tmp_path / "movie.webm"; source.write_bytes(b"placeholder")
    window = MainWindow(runtime); window.dispatch_timer.stop(); window.open_video_converter(str(source), quicktime=True)
    assert (window.converter_profile.currentText(), window.converter_format.currentText(), window.converter_video.currentText(), window.converter_audio.currentText()) == ("macOS / QuickTime", "MP4", "H.264 / AVC", "AAC")
    window.converter_format.setCurrentText("MKV")
    assert window.converter_profile.currentText() == "Custom" and window.converter_output.text().endswith(".mkv")
    window.converter_profile.setCurrentText("Small File")
    assert (window.converter_format.currentText(), window.converter_video.currentText(), window.converter_quality.currentText()) == ("MP4", "HEVC / H.265", "Balanced")
    window.converter_video.setCurrentText("VP9"); assert window.converter_profile.currentText() == "Custom"
    window.converter_profile.setCurrentText("macOS / QuickTime")
    assert window.converter_video.currentText() == "H.264 / AVC"
    window._converter_details = {"format_name": "mov,mp4", "size": 1000, "duration": 1, "subtitles": [], "chapter_count": 0, "thumbnail": False,
                                 "streams": [{"index": 0, "type": "video", "codec": "h264", "pix_fmt": "yuv420p", "width": 96, "height": 64, "frame_rate": "10/1", "attached_pic": False},
                                             {"index": 1, "type": "audio", "codec": "aac", "sample_rate": "44100", "channel_layout": "mono", "attached_pic": False}]}
    window.converter_format.setCurrentText("WebM"); window.converter_video.setCurrentText("H.264 / AVC"); window.converter_audio.setCurrentText("AAC")
    assert not window.converter_convert.isEnabled()
    assert "not supported in WebM" in window.converter_result.toPlainText()
    window.close(); _APP.processEvents()
