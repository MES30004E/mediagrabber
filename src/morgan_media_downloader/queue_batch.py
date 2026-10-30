"""GUI-owned bounded action admission; never creates per-job workers."""
from collections import deque
from collections.abc import Callable, Iterable

from PySide6.QtCore import QObject, QTimer, Signal

from .logging_setup import redact_secrets


class QueueBatch(QObject):
    changed = Signal(dict)
    finished = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step)
        self.busy = False; self._stepping = False; self._apply = None
        self._generation = 0
        self._ids = deque()
        self._info = dict(label="", completed=0, failed=0, skipped=0, pending=0, cancelled=False, error="")

    def describe(self): return dict(self._info)

    def start(self, ids: Iterable[str], apply: Callable[[list[str]], int | None], label: str) -> bool:
        if self.busy: return False
        self._generation += 1; generation = self._generation
        self._ids = deque(dict.fromkeys(ids)); self._apply = apply
        self._info = dict(label=label, completed=0, failed=0, skipped=0, pending=len(self._ids), cancelled=False, error="")
        self.busy = True
        self.changed.emit(self.describe())
        if self.busy and generation == self._generation: self._timer.start(0)
        return True

    def cancel(self):
        if not self.busy: return
        self._info["cancelled"] = True; self._timer.stop()
        if not self._stepping: self._finish()

    def _finish(self):
        if not self.busy: return
        self.busy = False; self._apply = None; self._ids.clear()
        self.finished.emit(self.describe())

    def _step(self):
        if not self.busy: return
        generation = self._generation
        ids = [self._ids.popleft() for _ in range(min(32, len(self._ids)))]
        self._stepping = True
        try:
            skipped = (self._apply(ids) or 0) if ids else 0
            if type(skipped) is not int or not 0 <= skipped <= len(ids): raise ValueError("Invalid batch outcome count")
            self._info["completed"] += len(ids) - skipped
            self._info["skipped"] += skipped
        except Exception as error:
            self._info["failed"] += len(ids)
            self._info["error"] = redact_secrets(str(error))[:500] or type(error).__name__
        finally: self._stepping = False
        self._info["pending"] = len(self._ids)
        self.changed.emit(self.describe())
        if not self.busy or generation != self._generation: return
        if self._info["cancelled"] or not self._ids: self._finish()
        else: self._timer.start(0)
