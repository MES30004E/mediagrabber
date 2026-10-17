"""Render real Qt widgets with synthetic data and isolated state, no network.

Run with PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python
scripts/capture_local_ui.py --output .tools/ui-review/before
These renders are not a claim of native macOS, live account or playback QA.
"""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--theme", default="Light", choices=["System", "Light", "Dark"])
    parser.add_argument("--width", default=1180, type=int)
    parser.add_argument("--height", default=760, type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="morgan-ui-capture-") as directory:
        root = Path(directory)
        os.environ.update(MORGAN_DATA_DIR=str(root / "data"), MORGAN_LOG_DIR=str(root / "logs"), MORGAN_CACHE_DIR=str(root / "cache"))
        from PySide6.QtWidgets import QApplication
        from morgan_media_downloader.provider import ProviderStatus
        from morgan_media_downloader.settings import AppSettings, SettingsStore
        from morgan_media_downloader.yt_runtime import YtDlpRuntimeManager
        from morgan_media_downloader.models import MediaItem, DownloadOptions, DownloadJob, JobStatus
        from morgan_media_downloader.ui import MainWindow, AnalysisContext
        app = QApplication.instance() or QApplication([])
        SettingsStore(root / "data/settings.json").save(AppSettings(theme=args.theme, download_dir="Example output folder", show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False))
        runtime = YtDlpRuntimeManager(root / "runtime", provider_checker=lambda: None)
        runtime.initialize()
        with patch("morgan_media_downloader.ui.check_provider", return_value=ProviderStatus("unchecked", "Offline visual fixture", "")), patch("morgan_media_downloader.settings_window.discover_browsers", return_value=[]), patch("morgan_media_downloader.settings_window.browser_profiles", return_value=[("Default", "")]):
            window = MainWindow(runtime)
            window.resize(args.width, args.height)
            window.dispatch_timer.stop(); window.clipboard_timer.stop(); window.show(); app.processEvents()
            items = [MediaItem(f"https://example.test/{i}", title, uploader="Example channel", duration=280 + i * 40, source="YouTube", playlist_index=i + 1, collection_title="Design reference playlist") for i, title in enumerate(["A practical guide to the creative process", "Making space for your next idea", "Inside the studio — a conversation"])]
            window.input.setPlainText("https://example.test/playlist")
            window._analysis_ready({"context": AnalysisContext("capture", window.input.toPlainText(), "preview", DownloadOptions()), "items": items, "torrent": None})
            job = DownloadJob(items[0], DownloadOptions(download_dir="Example output folder"))
            job.status = JobStatus.PAUSED; job.progress = 42; job.downloaded_bytes = 80 * 1024 * 1024; job.total_bytes = 190 * 1024 * 1024
            window.jobs[job.id] = job; window.database.save_job(job); window._refresh_queue(); window._refresh_history()
            for index, name in enumerate(["download", "queue", "history", "console", "settings"]):
                window.tabs.setCurrentIndex(index)
                if name == "settings": window.settings_panel.sidebar.setCurrentRow(3)
                app.processEvents()
                assert window.grab().save(str(args.output / f"{name}.png"))
            window.close(); app.processEvents()
    print(f"Offscreen synthetic-data renders saved to {args.output}")


if __name__ == "__main__": main()
