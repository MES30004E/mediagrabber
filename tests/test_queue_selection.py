import pytest

from PySide6.QtCore import Qt
from PySide6.QtTest import QAbstractItemModelTester
from PySide6.QtWidgets import QApplication, QTableView

from morgan_media_downloader.models import JobStatus
from morgan_media_downloader.queue_model import JOB_ID_ROLE, SEARCH_ROLE, STATUS_ROLE, QueueTableModel
from morgan_media_downloader.queue_selection import QueueFilterProxyModel, restore_ids, select_rows, status_matches, visible_rows
from test_queue_model import make_job

APP = QApplication.instance() or QApplication([])


def ids(proxy):
    return [proxy.index(row, 0).data(JOB_ID_ROLE) for row in range(proxy.rowCount())]


def test_combined_proxy_filters_raw_status_and_literal_search():
    source = QueueTableModel(); proxy = QueueFilterProxyModel(); proxy.setSourceModel(source)
    tester = QAbstractItemModelTester(proxy, QAbstractItemModelTester.FailureReportingMode.Fatal)
    first = make_job("CAFÉ [demo].*"); first.status = JobStatus.CONVERTING; first.postprocessing_stage = "Finalizing"
    first.item.original_url = "https://example.test/unique-origin"
    second = make_job("CAFÉ other", "torrent"); second.status = JobStatus.SEEDING
    completed = make_job("Done"); completed.status = JobStatus.COMPLETED_WARNINGS
    source.sync([first, second, completed], "All", "Direct")
    assert source.index(0, 0).data(STATUS_ROLE) == "Converting"
    assert "unique-origin" in source.index(0, 0).data(SEARCH_ROLE)
    proxy.set_filters("media", "Running", "café [DEMO].*")
    assert ids(proxy) == [first.id]
    proxy.set_filters("", "Running", "CAFÉ")
    assert ids(proxy) == [first.id, second.id]
    proxy.set_filters("", "Completed", "")
    assert ids(proxy) == [completed.id]
    proxy.set_filters("", "All", "unique-origin")
    assert ids(proxy) == [first.id] and tester is not None


@pytest.mark.parametrize("value,group,expected", [
    ("Analysing", "Running", True), ("Downloading", "Running", True), ("Converting", "Running", True),
    ("Fetching metadata", "Running", True), ("Seeding", "Running", True), ("Waiting", "Running", False),
    ("Completed with warnings", "Completed", True), ("Completed", "Completed", True),
    ("Failed", "Failed", True), ("Paused", "Paused", True), ("Cancelled", "Cancelled", True),
    ("Interrupted", "Interrupted", True), ("Waiting", "Waiting", True), ("Paused", "All", True),
])
def test_status_groups(value, group, expected):
    assert status_matches(value, group) is expected


def test_live_raw_status_and_nondisplayed_url_change_refilter_existing_rows():
    source = QueueTableModel(); proxy = QueueFilterProxyModel(); proxy.setSourceModel(source)
    job = make_job(); source.sync([job], "Media", "Direct")
    proxy.set_filters("media", "Paused", "new-url")
    assert proxy.rowCount() == 0
    job.status = JobStatus.PAUSED; job.item.source_url = "https://example.test/new-url"
    source.update_job(job, "Direct")
    assert ids(proxy) == [job.id]
    job.item.source_url = "https://example.test/old-url"; source.update_job(job, "Direct")
    assert proxy.rowCount() == 0


@pytest.mark.parametrize("kind,status,query", [("unknown", "All", ""), ("media", "unknown", ""), ("media", "All", None)])
def test_invalid_filter_refuses_before_replacing_previous_scope(kind, status, query):
    source = QueueTableModel(); proxy = QueueFilterProxyModel(); proxy.setSourceModel(source)
    job = make_job(); source.sync([job], "Media", "Direct"); proxy.set_filters("media", "Waiting", "Synthetic")
    with pytest.raises(ValueError): proxy.set_filters(kind, status, query)
    assert ids(proxy) == [job.id]


def test_proxy_search_never_includes_authentication_paths():
    source = QueueTableModel(); proxy = QueueFilterProxyModel(); proxy.setSourceModel(source)
    job = make_job(); job.options.cookies_file = "/synthetic/private-cookie-path"
    job.options.browser_profile = "private-browser-profile"
    source.sync([job], "Media", "Direct")
    proxy.set_filters("", "All", "private-")
    assert proxy.rowCount() == 0


def test_missing_optional_url_or_site_metadata_does_not_break_queue_filtering():
    source = QueueTableModel(); proxy = QueueFilterProxyModel(); proxy.setSourceModel(source)
    job = make_job(); job.item.original_url = None; job.item.source = None
    source.sync([job], "Media", "Direct")
    proxy.set_filters("media", "All", "Synthetic")
    assert ids(proxy) == [job.id]


def test_selection_ranges_and_restore_use_uuid_not_proxy_row_numbers():
    source = QueueTableModel(); proxy = QueueFilterProxyModel(); proxy.setSourceModel(source)
    jobs = [make_job(str(i), "torrent" if i % 2 else "media") for i in range(8)]
    source.sync(jobs, "All", "Direct"); proxy.set_filters("torrent", "All", "")
    table = QTableView(); table.setModel(proxy)
    try:
        select_rows(table, [0, 2, 2, -1, 999])
        assert {index.data(JOB_ID_ROLE) for index in table.selectionModel().selectedRows()} == {jobs[1].id, jobs[5].id}
        source.sync(list(reversed(jobs)), "All", "Direct")
        restored = restore_ids(table, source, {jobs[1].id, jobs[2].id, jobs[5].id, "removed"})
        assert set(restored) == {jobs[1].id, jobs[5].id}
        assert {index.data(JOB_ID_ROLE) for index in table.selectionModel().selectedRows()} == set(restored)
        select_rows(table, [])
        assert not table.selectionModel().selectedRows()
    finally: table.close()


def test_visible_rows_are_viewport_only_including_partial_edges():
    source = QueueTableModel(); proxy = QueueFilterProxyModel(); proxy.setSourceModel(source)
    source.sync([make_job(str(i)) for i in range(100)], "Media", "Direct")
    table = QTableView(); table.setModel(proxy); table.resize(400, 210)
    table.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel); table.verticalHeader().setDefaultSectionSize(40)
    try:
        assert visible_rows(table) == []
        table.show(); APP.processEvents(); table.verticalScrollBar().setValue(21); APP.processEvents()
        rows = visible_rows(table)
        assert rows[0] == 0 and 1 < len(rows) < 10
        assert all(table.visualRect(proxy.index(row, 0)).intersects(table.viewport().rect()) for row in rows)
        assert not table.visualRect(proxy.index(rows[-1]+1, 0)).intersects(table.viewport().rect())
        proxy.set_filters("", "Failed", "")
        assert visible_rows(table) == []
    finally: table.close(); APP.processEvents()


def test_filter_updates_from_background_thread_are_refused_without_scope_change():
    import threading
    source = QueueTableModel(); proxy = QueueFilterProxyModel(); proxy.setSourceModel(source)
    media, torrent = make_job(), make_job("Torrent", "torrent")
    source.sync([media, torrent], "All", "Direct"); errors = []
    def change():
        try: proxy.set_filters("", "All", "")
        except RuntimeError as error: errors.append(str(error))
    worker = threading.Thread(target=change); worker.start(); worker.join()
    assert errors and ids(proxy) == [media.id]


def test_older_qt_capability_path_still_refilters_real_rows():
    import warnings
    class LegacyCapabilities(QueueFilterProxyModel):
        def __getattribute__(self, name):
            if name in {"beginFilterChange", "endFilterChange"}: raise AttributeError(name)
            return super().__getattribute__(name)
    source = QueueTableModel(); proxy = LegacyCapabilities(); proxy.setSourceModel(source)
    media, torrent = make_job(), make_job("Torrent", "torrent")
    source.sync([media, torrent], "All", "Direct")
    # Exercise our compatibility branch on the current binary, not a claim that
    # an older Qt runtime was installed. Its deprecated alias may warn here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        proxy.set_filters("torrent", "Waiting", "Torrent")
    assert ids(proxy) == [torrent.id]
