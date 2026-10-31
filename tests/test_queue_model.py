"""Real Qt model contracts, independent literal expectations and stable IDs."""
import copy
import pytest

from PySide6.QtCore import QPersistentModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtTest import QAbstractItemModelTester
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from morgan_media_downloader.queue_model import JOB_ID_ROLE, KIND_ROLE, PROGRESS_ROLE, QueueTableModel

APP = QApplication.instance() or QApplication([])


def make_job(title="Synthetic", kind="media"):
    job = DownloadJob(MediaItem("https://example.test/video", title, source="Fixture"),
        DownloadOptions(download_dir="/synthetic/downloads", authentication_mode="None"))
    job.kind = kind
    return job


def test_model_exposes_existing_media_and_torrent_columns_and_literal_progress():
    model = QueueTableModel()
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    job = make_job(); job.progress = 42.5; job.downloaded_bytes = 1024; job.total_bytes = 2048
    model.sync([job], "Media", "Direct")
    assert [model.headerData(i, Qt.Orientation.Horizontal) for i in range(model.columnCount())] == [
        "Title", "Source", "Status", "Progress", "Downloaded / Total", "Speed", "ETA", "Format", "Destination"]
    assert model.index(0, 0).data() == "Synthetic"
    assert model.index(0, 3).data() == "42.5%" and model.index(0, 3).data(PROGRESS_ROLE) == 42.5
    assert model.index(0, 4).data() == "1.0 KB / 2.0 KB"
    assert model.index(0, 0).data(JOB_ID_ROLE) == job.id
    assert "Authentication: None" in model.index(0, 0).data(Qt.ItemDataRole.ToolTipRole)
    assert "Connection: Direct" in model.index(0, 0).data(Qt.ItemDataRole.ToolTipRole)
    model.sync([job], "Torrents", "Direct")
    assert "Connected peers" in [model.headerData(i, Qt.Orientation.Horizontal) for i in range(model.columnCount())]
    assert not model.index(9, 0).isValid() and tester is not None


def test_in_place_mutation_notifies_only_changed_row_and_unchanged_refresh_is_silent():
    model = QueueTableModel(); jobs = [make_job(str(i)) for i in range(100)]
    model.sync(jobs, "Media", "Direct"); changes = []; resets = []
    model.dataChanged.connect(lambda first, last, roles: changes.append((first.row(), last.row(), roles)))
    model.modelReset.connect(lambda: resets.append(True))
    jobs[45].progress = 23.7; jobs[45].status = JobStatus.DOWNLOADING
    model.sync(jobs, "Media", "Direct")
    assert len(changes) == 1 and changes[0][:2] == (45, 45) and PROGRESS_ROLE in changes[0][2]
    assert model.index(45, 3).data() == "23.7%"
    changes.clear(); model.sync(jobs, "Media", "Direct")
    assert not changes and not resets
    changed = copy.deepcopy(jobs[7]); changed.progress = 91.0
    assert model.update_job(changed, "Direct")
    assert len(changes) == 1 and changes[0][:2] == (7, 7)
    assert model.index(7, 3).data() == "91.0%"
    assert not model.update_job(make_job("Unknown"), "Direct")


def test_incremental_insert_remove_preserves_persistent_identity_and_reset_only_for_reorder():
    model = QueueTableModel()
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    first, kept, third, added = [make_job(title) for title in ("first", "kept", "third", "added")]
    model.sync([first, kept, third], "Media", "Direct")
    persistent = QPersistentModelIndex(model.index(1, 0)); inserted = []; removed = []; resets = []
    model.rowsInserted.connect(lambda _, first, last: inserted.append((first, last)))
    model.rowsRemoved.connect(lambda _, first, last: removed.append((first, last)))
    model.modelReset.connect(lambda: resets.append(True))
    model.sync([kept, third, added], "Media", "Direct")
    assert inserted == [(2, 2)] and removed == [(0, 0)] and not resets
    assert persistent.isValid() and persistent.row() == 0 and persistent.data(JOB_ID_ROLE) == kept.id
    model.sync([added, third, kept], "Media", "Direct")
    assert len(resets) == 1 and model.index_for_id(kept.id).row() == 2
    model.sync([], "Media", "Direct")
    assert model.rowCount() == 0 and not model.index_for_id(kept.id).isValid() and tester is not None


def test_proxy_filters_kind_without_turning_visible_row_into_source_row_identity():
    model = QueueTableModel(); media = make_job(); torrent = make_job("Torrent", "torrent")
    model.sync([media, torrent], "All", "Direct")
    proxy = QSortFilterProxyModel(); proxy.setSourceModel(model)
    proxy.setFilterRole(KIND_ROLE); proxy.setFilterFixedString("torrent")
    assert proxy.rowCount() == 1 and proxy.index(0, 0).data(JOB_ID_ROLE) == torrent.id
    assert proxy.mapToSource(proxy.index(0, 0)).row() == 1
    assert proxy.mapFromSource(model.index_for_id(media.id)).isValid() is False


def test_mutation_from_background_thread_is_refused_before_any_model_change():
    import threading
    model = QueueTableModel(); errors = []
    def mutate():
        try: model.sync([make_job()], "Media", "Direct")
        except RuntimeError as error: errors.append(str(error))
    worker = threading.Thread(target=mutate); worker.start(); worker.join()
    assert errors and model.rowCount() == 0


@pytest.mark.parametrize("value, expected, text", [(float("nan"), None, "—"), (float("inf"), None, "—"), (-5, 0.0, "0.0%"), (125, 100.0, "100.0%")])
def test_invalid_progress_never_reaches_native_painter_as_nan_or_out_of_range(value, expected, text):
    model = QueueTableModel(); job = make_job(); job.progress = value
    model.sync([job], "Media", "Direct")
    assert model.index(0, 3).data(PROGRESS_ROLE) == expected
    assert model.index(0, 3).data() == text


def test_progress_delegate_really_paints_native_progress_without_allocating_row_widgets():
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QProgressBar, QStyleOptionViewItem, QTableView
    from morgan_media_downloader.queue_model import QueueProgressDelegate
    model = QueueTableModel(); job = make_job(); job.progress = 42.5
    model.sync([job], "Media", "Direct")
    table = QTableView(); table.setModel(model); delegate = QueueProgressDelegate(table)
    table.setItemDelegate(delegate)
    image = QImage(160, 40, QImage.Format.Format_ARGB32); image.fill(Qt.GlobalColor.transparent)
    before = image.copy(); painter = QPainter(image); option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 160, 40); option.widget = table; option.palette = table.palette()
    try: delegate.paint(painter, option, model.index(0, 3))
    finally: painter.end()
    assert image != before and not table.findChildren(QProgressBar)
    assert table.indexWidget(model.index(0, 3)) is None
    table.close()
