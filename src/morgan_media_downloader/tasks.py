from __future__ import annotations

import inspect
import threading
import time
import traceback
import weakref
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from PySide6.QtCore import QCoreApplication, QObject, QThread, Qt, Signal, Slot


TaskFunction = Callable[[threading.Event, Callable[[object], None]], object]


class _Callback:
    """Weakly retain QObject-bound callbacks so tasks cannot keep windows alive."""

    def __init__(self, callback: Callable | None):
        self._value = weakref.WeakMethod(callback) if callback and inspect.ismethod(callback) else callback

    def call(self, *args) -> None:
        callback = self._value() if isinstance(self._value, weakref.WeakMethod) else self._value
        if callback is not None:
            callback(*args)


class TaskWorker(QObject):
    """Compatibility marker for old imports; tasks no longer create worker QObjects.

    A Python-backed QObject deleted in its worker thread can race with destruction
    of the owning QThread wrapper in PySide.  TaskThread now executes the callable
    directly, leaving every QObject wrapper owned and destroyed by the GUI thread.
    """

    progress = Signal(str, object)
    result = Signal(str, object)
    error = Signal(str, str, str)
    finished = Signal(str)

    def __init__(self, task_id: str, function: TaskFunction, cancel_event: threading.Event):
        super().__init__()
        self.task_id = task_id
        self.function = function
        self.cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:
            value = self.function(
                self.cancel_event,
                lambda payload: self.progress.emit(self.task_id, payload),
            )
            self.result.emit(self.task_id, value)
        except BaseException as error:
            self.error.emit(self.task_id, str(error), traceback.format_exc())
        finally:
            self.finished.emit(self.task_id)


class TaskThread(QThread):
    progress = Signal(str, object)
    result = Signal(str, object)
    error = Signal(str, str, str)
    worker_finished = Signal(str)
    ended = Signal(str)

    def __init__(
        self,
        task_id: str,
        function: TaskFunction,
        cancel_event: threading.Event,
        parent: QObject,
    ):
        super().__init__(parent)
        self.task_id = task_id
        self.function = function
        self.cancel_event = cancel_event
        self.finished.connect(self._relay_finished)

    def run(self) -> None:
        try:
            value = self.function(
                self.cancel_event,
                lambda payload: self.progress.emit(self.task_id, payload),
            )
            self.result.emit(self.task_id, value)
        except BaseException as error:
            self.error.emit(self.task_id, str(error), traceback.format_exc())
        finally:
            self.worker_finished.emit(self.task_id)

    @Slot()
    def _relay_finished(self) -> None:
        self.ended.emit(self.task_id)


@dataclass
class TaskRecord:
    task_id: str
    kind: str
    state: str
    cancel_event: threading.Event
    thread: TaskThread
    result_callback: _Callback
    error_callback: _Callback
    progress_callback: _Callback
    finished_callback: _Callback


class TaskManager(QObject):
    """Own every background QObject until its QThread has fully stopped."""

    task_started = Signal(str, str)
    task_finished = Signal(str, str)
    all_finished = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._records: dict[str, TaskRecord] = {}
        self._accepting = True
        self._shutting_down = False

    @property
    def active_count(self) -> int:
        return len(self._records)

    def active_ids(self, kind: str | None = None) -> list[str]:
        return [task_id for task_id, record in self._records.items() if kind is None or record.kind == kind]

    def start(
        self,
        kind: str,
        function: TaskFunction,
        *,
        task_id: str | None = None,
        on_result: Callable[[object], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
        on_progress: Callable[[object], None] | None = None,
        on_finished: Callable[[str], None] | None = None,
    ) -> str:
        if not self._accepting:
            raise RuntimeError("Task manager is shutting down")
        task_id = task_id or f"{kind}-{uuid4()}"
        if task_id in self._records:
            raise ValueError(f"Task already exists: {task_id}")
        cancel_event = threading.Event()
        thread = TaskThread(task_id, function, cancel_event, self)
        record = TaskRecord(
            task_id, kind, "Starting", cancel_event, thread,
            _Callback(on_result), _Callback(on_error), _Callback(on_progress), _Callback(on_finished),
        )
        self._records[task_id] = record
        thread.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        thread.result.connect(self._on_result, Qt.ConnectionType.QueuedConnection)
        thread.error.connect(self._on_error, Qt.ConnectionType.QueuedConnection)
        thread.worker_finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)
        thread.ended.connect(self._on_thread_finished, Qt.ConnectionType.QueuedConnection)
        record.state = "Running"
        self.task_started.emit(task_id, kind)
        thread.start()
        return task_id

    def cancel(self, task_id: str) -> bool:
        record = self._records.get(task_id)
        if record is None:
            return False
        record.state = "Cancelling"
        record.cancel_event.set()
        record.thread.requestInterruption()
        return True

    def cancel_kind(self, kind: str) -> None:
        for task_id in self.active_ids(kind):
            self.cancel(task_id)

    def cancel_all(self) -> None:
        for task_id in list(self._records):
            self.cancel(task_id)

    @Slot(str, object)
    def _on_progress(self, task_id: str, payload: object) -> None:
        record = self._records.get(task_id)
        if record and not self._shutting_down and not record.cancel_event.is_set():
            record.progress_callback.call(payload)

    @Slot(str, object)
    def _on_result(self, task_id: str, value: object) -> None:
        record = self._records.get(task_id)
        if record and not self._shutting_down and not record.cancel_event.is_set():
            record.result_callback.call(value)

    @Slot(str, str, str)
    def _on_error(self, task_id: str, message: str, details: str) -> None:
        record = self._records.get(task_id)
        if record and not self._shutting_down and not record.cancel_event.is_set():
            record.error_callback.call(message, details)

    @Slot(str)
    def _on_worker_finished(self, task_id: str) -> None:
        record = self._records.get(task_id)
        if record:
            record.state = "Finishing"

    @Slot(str)
    def _on_thread_finished(self, task_id: str) -> None:
        record = self._records.pop(task_id, None)
        if record is None:
            return
        record.state = "Finished"
        if not self._shutting_down:
            record.finished_callback.call(task_id)
        self.task_finished.emit(task_id, record.kind)
        record.thread.deleteLater()
        if not self._records:
            self.all_finished.emit()

    def shutdown(self, timeout_ms: int = 10_000) -> bool:
        self._accepting = False
        self._shutting_down = True
        self.cancel_all()
        deadline = time.monotonic() + max(timeout_ms, 0) / 1000
        for record in list(self._records.values()):
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if record.thread.isRunning() and remaining:
                record.thread.wait(remaining)
        QCoreApplication.processEvents()
        return not any(record.thread.isRunning() for record in self._records.values())
