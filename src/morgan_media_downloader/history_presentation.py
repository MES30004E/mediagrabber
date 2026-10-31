"""Immutable history presentation snapshots, owned by the GUI; no I/O or Qt."""
from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from .models import DownloadJob


@dataclass(frozen=True)
class HistoryRow:
    job_id: str
    created_at: str
    cells: tuple[str, ...]


def history_row(job: DownloadJob) -> HistoryRow:
    return HistoryRow(job.id, job.created_at, (
        job.created_at[:19].replace("T", " "), job.item.title, job.item.original_url,
        job.item.source_url, job.output_file,
        job.options.audio_format if job.options.audio_format != "Original/best audio" else job.options.quality,
        job.status.value,
    ))


class HistoryRefreshState:
    """Remember only rows actually read from the DB or successfully persisted.

    Hidden rows remain known, but unrelated mutable jobs never enter the cache.
    A failed presentation leaves its pending change unacknowledged for retry.
    """

    def __init__(self) -> None:
        self._rows: dict[str, HistoryRow] = {}
        self._dirty = False

    def needs_refresh(self, row: HistoryRow) -> bool:
        return self._dirty or self._rows.get(row.job_id) != row

    def invalidate(self) -> None:
        self._dirty = True

    def remember(self, row: HistoryRow) -> None:
        self._rows[row.job_id] = row

    def rendered(self, rows: Iterable[HistoryRow], existing_ids: Collection[str]) -> None:
        self._rows = {key: row for key, row in self._rows.items() if key in existing_ids}
        self._rows.update((row.job_id, row) for row in rows)
        self._dirty = False
