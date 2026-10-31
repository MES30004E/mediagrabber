"""Native queue filtering and batched selection; no jobs, workers or persistence."""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QModelIndex, QSortFilterProxyModel, QThread
from PySide6.QtWidgets import QTableView

from .models import JobStatus
from .queue_model import JOB_ID_ROLE, KIND_ROLE, SEARCH_ROLE, STATUS_ROLE, QueueTableModel, contiguous_ranges

STATUS_GROUPS = {
    "All": frozenset(status.value for status in JobStatus),
    "Waiting": frozenset({"Waiting"}),
    "Running": frozenset({"Analysing", "Downloading", "Converting", "Fetching metadata", "Seeding"}),
    "Completed": frozenset({"Completed", "Completed with warnings"}),
    "Failed": frozenset({"Failed"}), "Paused": frozenset({"Paused"}),
    "Cancelled": frozenset({"Cancelled"}), "Interrupted": frozenset({"Interrupted"}),
}


def status_matches(value: str, group: str) -> bool:
    if group not in STATUS_GROUPS: raise ValueError("Unknown queue status category")
    return group == "All" or value in STATUS_GROUPS[group]


class QueueFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "media"; self.status = "All"; self.query = ""
        self.setDynamicSortFilter(True)

    def set_filters(self, kind: str, status: str, query: str) -> None:
        if QThread.currentThread() != self.thread(): raise RuntimeError("Queue filters require their GUI thread")
        if not all(isinstance(value, str) for value in (kind, status, query)) or kind not in {"", "media", "torrent"} or status not in STATUS_GROUPS:
            raise ValueError("Invalid queue filter")
        query = query.strip().casefold()
        if (kind, status, query) == (self.kind, self.status, self.query): return
        modern = hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange")
        if modern: self.beginFilterChange()
        self.kind, self.status, self.query = kind, status, query
        if modern: self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else: self.invalidateFilter()  # Qt6.7–6.9 compatibility, before deprecation.

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source = self.sourceModel()
        if source is None: return False
        index = source.index(source_row, 0, source_parent)
        return ((not self.kind or index.data(KIND_ROLE) == self.kind) and
                status_matches(index.data(STATUS_ROLE), self.status) and
                (not self.query or self.query in (index.data(SEARCH_ROLE) or "")))


def select_rows(view: QTableView, rows: Iterable[int]) -> None:
    """One native selection operation; caller owns UUID memory/reconciliation."""
    model = view.model(); selection = view.selectionModel()
    if model is None or selection is None: return
    valid = sorted({row for row in rows if type(row) is int and 0 <= row < model.rowCount()})
    ranges = QItemSelection()
    for first, last in contiguous_ranges(valid):
        ranges.select(model.index(first, 0), model.index(last, model.columnCount()-1))
    selection.select(ranges, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
    selection.setCurrentIndex(model.index(valid[0], 0) if valid else QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
    view.viewport().update()


def restore_ids(view: QTableView, source: QueueTableModel, ids: Iterable[str]) -> tuple[str, ...]:
    proxy = view.model()
    if proxy is None: return ()
    rows = [index.row() for key in ids if (index := proxy.mapFromSource(source.index_for_id(key))).isValid()]
    select_rows(view, rows)
    return tuple(index.data(JOB_ID_ROLE) for index in view.selectionModel().selectedRows())


def visible_rows(view: QTableView) -> list[int]:
    model = view.model()
    if model is None or not model.rowCount() or not view.isVisible() or not view.viewport().height(): return []
    first = view.rowAt(0); last = view.rowAt(view.viewport().height()-1)
    if first < 0: return []
    if last < 0: last = model.rowCount()-1
    return [row for row in range(first, last+1) if not view.isRowHidden(row)]
