from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot

from .logging_setup import redact_secrets


@dataclass(frozen=True)
class ConsoleEvent:
    timestamp: str
    category: str
    message: str
    job_id: str = ""
    level: str = "info"

    @property
    def line(self) -> str:
        return f"{self.timestamp} [{self.category.upper()}] {self.message}"


class ConsoleStore(QObject):
    """Bounded, redacted event store. Append is invoked on the GUI thread."""

    event_added = Signal(object)
    cleared = Signal()

    def __init__(self, limit: int = 10_000, parent: QObject | None = None):
        super().__init__(parent)
        self.limit = max(1, limit)
        self._events: deque[ConsoleEvent] = deque(maxlen=self.limit)

    @Slot(str, str, str, str)
    def append(self, category: str, message: str, job_id: str = "", level: str = "info") -> ConsoleEvent:
        event = ConsoleEvent(datetime.now().strftime("%H:%M:%S"), category,
                             redact_secrets(str(message)), job_id, level.casefold())
        self._events.append(event)
        self.event_added.emit(event)
        return event

    def clear(self) -> None:
        self._events.clear(); self.cleared.emit()

    def events(self, category: str = "All", job_id: str = "") -> list[ConsoleEvent]:
        category_key = category.casefold()
        aliases = {"yt-dlp": "yt-dlp", "subtitles": "subtitle", "thumbnail": "thumbnail",
                   "aria2": "aria2", "tor": "tor", "app": "app"}
        result = []
        for event in self._events:
            if job_id and event.job_id != job_id: continue
            if category_key == "warnings" and event.level != "warning": continue
            if category_key == "errors" and event.level != "error": continue
            if category_key not in {"all", "warnings", "errors"} and event.category.casefold() != aliases.get(category_key, category_key): continue
            result.append(event)
        return result

    def text(self, category: str = "All", job_id: str = "") -> str:
        return "\n".join(event.line for event in self.events(category, job_id))
