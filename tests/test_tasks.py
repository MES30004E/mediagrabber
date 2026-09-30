import os
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QThread
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.tasks import TaskManager


_APP = QApplication.instance() or QApplication([])


def _drain(manager: TaskManager, timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while manager.active_count and time.monotonic() < deadline:
        _APP.processEvents()
        time.sleep(0.001)
    assert manager.active_count == 0


def test_one_hundred_mixed_cancel_cycles_keep_workers_owned_and_callbacks_on_main_thread():
    manager = TaskManager()
    callback_threads = []
    for cycle in range(100):
        kind = ("analysis", "torrent-monitor", "download-media", "yt-runtime")[cycle % 4]
        task_id = manager.start(
            kind,
            lambda cancel, progress, value=cycle: (progress(value), cancel.wait(0.002), value)[-1],
            on_progress=lambda _value: callback_threads.append(QThread.currentThread()),
        )
        assert task_id in manager._records
        assert manager._records[task_id].thread.function is not None
        manager.cancel(task_id)
        _drain(manager)
    assert all(thread is _APP.thread() for thread in callback_threads)
    assert manager.shutdown(1000)


def test_shutdown_cancels_and_waits_without_destroying_a_running_qthread():
    manager = TaskManager()
    entered = threading.Event()

    def operation(cancel, _progress):
        entered.set()
        cancel.wait(2)

    manager.start("download-media", operation)
    assert entered.wait(1)
    assert manager.shutdown(2000)
    assert not any(record.thread.isRunning() for record in manager._records.values())
