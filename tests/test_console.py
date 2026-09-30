import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from morgan_media_downloader.console import ConsoleStore


_APP = QApplication.instance() or QApplication([])


def test_console_is_bounded_filterable_job_specific_and_redacted():
    store = ConsoleStore(limit=3)
    store.append("APP", "start")
    store.append("YT-DLP", "https://cdn.test/file?token=secret", "job-a")
    store.append("SUBTITLE", "warning", "job-a", "warning")
    store.append("ERROR", "Authorization: hidden", "job-b", "error")
    assert len(store.events()) == 3
    assert store.events("Warnings", "job-a")[0].message == "warning"
    assert "secret" not in store.text() and "hidden" not in store.text()
    assert "[query redacted]" in store.text("yt-dlp", "job-a")
