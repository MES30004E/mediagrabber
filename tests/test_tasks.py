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


def test_finished_callback_failure_still_releases_thread_payload_and_completion_signals(monkeypatch):
    import gc
    import sys
    import weakref
    from PySide6.QtCore import QEvent
    from morgan_media_downloader.tasks import TaskThread

    class Payload: pass
    errors = []; finished = []; idle = []; references = []
    debug_names = ("last_exc", "last_type", "last_value", "last_traceback")
    previous_debug = {name: getattr(sys, name) for name in debug_names if hasattr(sys, name)}
    # Record text only: saving the traceback would itself retain the popped record.
    monkeypatch.setattr(sys, "excepthook", lambda _kind, error, _traceback: errors.append(str(error)))
    manager = TaskManager()
    manager.task_finished.connect(lambda key, kind: finished.append((key, kind)))
    manager.all_finished.connect(lambda: idle.append(True))
    def fail(_key): raise RuntimeError("synthetic finished callback failure")
    try:
        for number in range(3):
            payload = Payload(); references.append(weakref.ref(payload))
            manager.start("fixture", lambda _cancel, _report, captured=payload: None,
                          task_id=f"fixture-{number}", on_finished=fail)
            del payload
            _drain(manager)
        _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete); gc.collect()
        assert errors == ["synthetic finished callback failure"] * 3
        # PySide's exception reporting intentionally keeps the most recent
        # traceback in sys.last_*. That debugger root is not manager ownership.
        # Release this test's reported error before checking captured payloads.
        for name in debug_names:
            if hasattr(sys, name): delattr(sys, name)
        gc.collect()
        observed = (len(manager.findChildren(TaskThread)), sum(ref() is not None for ref in references), finished, idle)
        assert observed == (0, 0, [(f"fixture-{i}", "fixture") for i in range(3)], [True] * 3)
    finally:
        manager.shutdown(1000); manager.deleteLater()
        _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for name in debug_names:
            if name in previous_debug: setattr(sys, name, previous_debug[name])
            elif hasattr(sys, name): delattr(sys, name)
