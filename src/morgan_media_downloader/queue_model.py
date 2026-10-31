"""GUI-owned queue presentation; no per-row QObjects, workers or persistence."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QThread, Qt
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionProgressBar

from .display_format import human_bytes, human_duration
from .job_diagnostics import status_summary
from .models import DownloadJob, JobStatus

JOB_ID_ROLE = int(Qt.ItemDataRole.UserRole)
KIND_ROLE = JOB_ID_ROLE + 1
PROGRESS_ROLE = JOB_ID_ROLE + 2

COLUMNS = {
    "Media": ("Title", "Source", "Status", "Progress", "Downloaded / Total", "Speed", "ETA", "Format", "Destination"),
    "Torrents": ("Title", "Status", "Progress", "Downloaded / Total", "Down", "Up", "Connected peers", "Connected seeders", "ETA", "Destination"),
    "All": ("Title", "Type", "Status", "Progress", "Speed", "ETA", "Destination"),
}
FIELDS = ("Title", "Source", "Type", "Status", "Progress", "Downloaded / Total", "Speed", "Down", "Up", "Connected peers", "Connected seeders", "ETA", "Format", "Destination")
FIELD_INDEX = {name: index for index, name in enumerate(FIELDS)}
CHANGE_ROLES = [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.ToolTipRole), KIND_ROLE, PROGRESS_ROLE]


@dataclass(frozen=True)
class QueueRow:
    job_id: str
    kind: str
    cells: tuple[str, ...]
    progress: float | None
    tooltip: str


def presentation_row(job: DownloadJob, connection_mode: str) -> QueueRow:
    progress = float(job.progress)
    progress = max(0.0, min(100.0, progress)) if math.isfinite(progress) else None
    size = f"{human_bytes(job.downloaded_bytes)} / {human_bytes(job.total_bytes)}" if job.total_bytes else human_bytes(job.downloaded_bytes)
    format_name = "BitTorrent" if job.kind == "torrent" else (job.options.audio_format if job.options.audio_format != "Original/best audio" else f"{job.options.quality} / {job.options.container}")
    if job.status == JobStatus.FAILED:
        retained = f" • {job.progress:.1f}% • {human_bytes(job.downloaded_bytes)} retained" if job.downloaded_bytes else ""
        status = status_summary(job) + retained
    elif job.status == JobStatus.COMPLETED_WARNINGS: status = "Completed with warnings ⚠"
    elif job.status in {JobStatus.DOWNLOADING, JobStatus.CONVERTING} and job.postprocessing_stage: status = job.postprocessing_stage
    else: status = job.status.value
    speed = f"{human_bytes(job.speed)}/s" if job.speed else "—"
    cells = (job.item.title, job.item.source, "Torrent" if job.kind == "torrent" else "Media", status,
        f"{progress:.1f}%" if progress is not None else "—", size, speed, speed,
        f"{human_bytes(job.upload_speed)}/s" if job.upload_speed else "—", str(job.peers), str(job.seeds),
        human_duration(job.eta), format_name, job.output_file or job.options.download_dir)
    if job.kind == "torrent":
        tooltip = (f"Peer Discovery\nTrackers: {job.original_tracker_count} original + {job.additional_tracker_count} additional\n"
            f"DHT/PEX/Local Discovery: {'Disabled (private torrent)' if job.torrent_private else 'Configured in Settings'}")
    else:
        subtitle = f"Embed {job.options.subtitle_language}" if job.options.embed_subtitles else "Off"
        verification = ""
        if job.verification:
            verification = (f"\nVerified video: {job.verification.get('video')}\nVerified audio: {job.verification.get('audio')}"
                f"\nEmbedded subtitles: {job.verification.get('subtitle_count')}\nEmbedded thumbnail: {job.verification.get('thumbnail')}"
                f"\nMetadata: {job.verification.get('metadata')}")
        tooltip = (f"Quality: {job.options.quality}\nContainer: {job.options.container}"
            f"\nAuthentication: {job.effective_authentication or job.options.authentication_mode}\nConnection: {connection_mode}"
            f"\nThumbnail: {'Embed' if job.options.embed_thumbnail else 'Off'}\nSubtitles: {subtitle}{verification}")
    return QueueRow(job.id, "torrent" if job.kind == "torrent" else "media", cells, progress, tooltip)


def contiguous_ranges(rows: Iterable[int]) -> list[tuple[int, int]]:
    values = sorted(rows)
    if not values: return []
    result = []; first = last = values[0]
    for row in values[1:]:
        if row != last + 1:
            result.append((first, last)); first = row
        last = row
    result.append((first, last))
    return result


class QueueTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = "Media"; self.columns = COLUMNS[self.view]; self.connection_mode = ""
        self._ids: list[str] = []; self._rows: dict[str, QueueRow] = {}; self._positions: dict[str, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._ids)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return None
        if orientation == Qt.Orientation.Horizontal:
            return self.columns[section] if 0 <= section < len(self.columns) else None
        return str(section + 1) if 0 <= section < len(self._ids) else None

    def flags(self, index):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable if index.isValid() else Qt.ItemFlag.NoItemFlags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._ids) or not 0 <= index.column() < len(self.columns): return None
        row = self._rows[self._ids[index.row()]]; column = self.columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole: return row.cells[FIELD_INDEX[column]]
        if role == JOB_ID_ROLE: return row.job_id
        if role == KIND_ROLE: return row.kind
        if role == PROGRESS_ROLE and column == "Progress": return row.progress
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 0: return row.tooltip
        return None

    def index_for_id(self, job_id: str) -> QModelIndex:
        row = self._positions.get(job_id)
        return self.index(row, 0) if row is not None else QModelIndex()

    def _assert_gui_thread(self) -> None:
        if QThread.currentThread() != self.thread(): raise RuntimeError("Queue model mutations require its GUI thread")

    def _reindex(self) -> None:
        self._positions = {key: row for row, key in enumerate(self._ids)}

    def _notify(self, rows: Iterable[int]) -> None:
        for first, last in contiguous_ranges(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, len(self.columns)-1), CHANGE_ROLES)

    def sync(self, jobs: Iterable[DownloadJob], view: str, connection_mode: str) -> bool:
        self._assert_gui_thread()
        columns = COLUMNS[view]
        values = [presentation_row(job, connection_mode) for job in jobs]
        ids = [row.job_id for row in values]; rows = {row.job_id: row for row in values}
        if len(ids) != len(rows): raise ValueError("Queue IDs must be distinct")
        retained = [key for key in self._ids if key in rows]
        reordered = retained != [key for key in ids if key in self._rows]
        self.connection_mode = connection_mode
        if columns != self.columns or reordered:
            self.beginResetModel()
            self.view = view; self.columns = columns; self._ids = ids; self._rows = rows; self._reindex()
            self.endResetModel()
            return True
        structural = ids != self._ids
        for first, last in reversed(contiguous_ranges(i for i, key in enumerate(self._ids) if key not in rows)):
            self.beginRemoveRows(QModelIndex(), first, last)
            for key in self._ids[first:last+1]: self._rows.pop(key)
            del self._ids[first:last+1]; self._reindex()
            self.endRemoveRows()
        row = 0
        while row < len(ids):
            if row < len(self._ids) and self._ids[row] == ids[row]: row += 1; continue
            last = row
            while last < len(ids) and ids[last] not in self._rows: last += 1
            self.beginInsertRows(QModelIndex(), row, last-1)
            inserted = ids[row:last]; self._ids[row:row] = inserted
            self._rows.update((key, rows[key]) for key in inserted); self._reindex()
            self.endInsertRows(); row = last
        changed = []
        for key in ids:
            if self._rows[key] != rows[key]: self._rows[key] = rows[key]; changed.append(self._positions[key])
        self._notify(changed)
        return structural

    def update_job(self, job: DownloadJob, connection_mode: str) -> bool:
        self._assert_gui_thread()
        if job.id not in self._rows or connection_mode != self.connection_mode: return False
        row = presentation_row(job, connection_mode)
        if row != self._rows[job.id]:
            self._rows[job.id] = row; self._notify([self._positions[job.id]])
        return True


class QueueProgressDelegate(QStyledItemDelegate):
    """Use the native style to paint visible progress cells, never index widgets."""

    def paint(self, painter, option, index) -> None:
        progress = index.data(PROGRESS_ROLE)
        if progress is None:
            super().paint(painter, option, index)
            return
        bar = QStyleOptionProgressBar()
        bar.rect = option.rect.adjusted(4, 8, -4, -8)
        bar.state = option.state | QStyle.StateFlag.State_Horizontal
        bar.direction = option.direction; bar.palette = option.palette
        bar.minimum = 0; bar.maximum = 1000; bar.progress = int(progress * 10)
        bar.text = index.data(Qt.ItemDataRole.DisplayRole); bar.textVisible = True
        bar.textAlignment = Qt.AlignmentFlag.AlignCenter
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ProgressBar, bar, painter, option.widget)
