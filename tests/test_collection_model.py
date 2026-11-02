import threading

from PySide6.QtCore import Qt
from PySide6.QtTest import QAbstractItemModelTester
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.collection_model import CollectionListModel, SUMMARY_ROLE
from morgan_media_downloader.models import JobStatus
from morgan_media_downloader.queue_model import COLLECTION_ROLE, QueueTableModel
from morgan_media_downloader.queue_selection import QueueFilterProxyModel
from test_queue_collections import job

APP = QApplication.instance() or QApplication([])


def test_native_collection_model_updates_one_job_without_rescanning_or_resetting(monkeypatch):
    model = CollectionListModel(); tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    values = [job(0), job(1), job(2, group="b", name="<b>Other</b>")]; model.sync(values)
    assert model.rowCount() == 3 and model.index(0,0).data(Qt.ItemDataRole.UserRole) == ""
    assert model.index(model.row_for_id("a"),0).data(SUMMARY_ROLE).total == 2
    resets=[]; changes=[]; model.modelReset.connect(lambda: resets.append(True))
    model.dataChanged.connect(lambda first,last,_roles: changes.append((first.row(),last.row())))
    def unexpected(_jobs): raise AssertionError("One progress update must not scan all jobs")
    monkeypatch.setattr(model.index_state,"sync",unexpected)
    values[0].progress=30; model.update_job(values[0])
    assert not resets and len(changes) <= 2 and model.summary("a").progress == 15
    assert "&lt;b&gt;Other&lt;/b&gt;" in model.index(model.row_for_id("b"),0).data(Qt.ItemDataRole.ToolTipRole)
    assert tester is not None


def test_collection_model_mutation_off_gui_thread_is_refused():
    model = CollectionListModel(); errors=[]
    def update():
        try: model.sync([job()])
        except RuntimeError as error: errors.append(str(error))
    thread=threading.Thread(target=update); thread.start(); thread.join()
    assert errors and model.summary("").total == 0


def test_collection_proxy_combines_cached_roles_and_live_membership():
    source=QueueTableModel(); proxy=QueueFilterProxyModel(); proxy.setSourceModel(source)
    values=[job(0),job(1,group="b",name="B"),job(2,status=JobStatus.FAILED)]
    source.sync(values,"Media","Direct")
    assert source.index(0,0).data(COLLECTION_ROLE) == "a"
    proxy.set_filters("media","Failed","Video",collection_id="a")
    assert proxy.rowCount()==1 and proxy.index(0,0).data(Qt.ItemDataRole.UserRole)=="2"
    values[2].collection_id="b"; source.update_job(values[2],"Direct")
    assert proxy.rowCount()==0
    proxy.set_filters("media","All","",collection_id="b")
    assert proxy.rowCount()==2
