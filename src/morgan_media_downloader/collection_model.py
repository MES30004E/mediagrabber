"""Native list adapter for the pure incremental collection index."""
from __future__ import annotations

from html import escape
from PySide6.QtCore import QAbstractListModel, QModelIndex, QThread, Qt

from .queue_collections import CollectionIndex

SUMMARY_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class CollectionListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.index_state=CollectionIndex(); self._ids=[""]; self._positions={"":0}

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self._ids)

    def row_for_id(self, key): return self._positions.get(key)

    def summary(self, key): return self.index_state.summary(key)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._ids): return None
        key=self._ids[index.row()]
        if role==Qt.ItemDataRole.UserRole: return key
        summary=self.summary(key)
        if role==SUMMARY_ROLE: return summary
        if role==Qt.ItemDataRole.DisplayRole:
            suffix=f" · {key[-6:]}" if key and key!="ungrouped" else ""
            return f"{summary.name} · {summary.total:,} jobs{suffix}"
        if role==Qt.ItemDataRole.ToolTipRole:
            text=summary.name+"\n"+", ".join(f"{name}: {count}" for name,count in summary.counts if count)
            return "<qt>"+escape(text).replace("\n","<br>")+"</qt>"
        return None

    def _check_thread(self):
        if QThread.currentThread()!=self.thread(): raise RuntimeError("Collection models require their GUI thread")

    def _changed(self, change):
        if change.structure:
            self.beginResetModel(); self._ids=["",*self.index_state.group_ids]
            self._positions={key:row for row,key in enumerate(self._ids)}; self.endResetModel()
        else:
            for key in change.groups:
                if (row:=self.row_for_id(key)) is not None:
                    self.dataChanged.emit(self.index(row,0),self.index(row,0),[int(Qt.ItemDataRole.DisplayRole),int(Qt.ItemDataRole.ToolTipRole),SUMMARY_ROLE])

    def sync(self, jobs):
        self._check_thread(); self._changed(self.index_state.sync(jobs))

    def update_job(self, job):
        self._check_thread(); self._changed(self.index_state.update_job(job))
