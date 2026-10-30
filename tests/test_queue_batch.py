import time
import pytest

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.queue_batch import QueueBatch

APP = QApplication.instance() or QApplication([])


def drain(batch):
    deadline = time.monotonic() + 5
    while batch.busy and time.monotonic() < deadline: APP.processEvents()
    assert not batch.busy


def test_batch_yields_and_processes_bounded_stable_id_slices():
    batch = QueueBatch(); slices = []; heartbeat = []
    assert batch.start([str(i) for i in range(800)], lambda ids: slices.append(ids), "Pause")
    assert not slices
    QTimer.singleShot(0, lambda: heartbeat.append(len(slices)))
    drain(batch)
    assert max(map(len, slices)) <= 32
    assert [value for part in slices for value in part] == [str(i) for i in range(800)]
    assert heartbeat and heartbeat[0] < len(slices)
    assert batch.describe()["completed"] == 800


def test_cancel_stops_future_slices_and_second_admission_is_refused():
    batch = QueueBatch(); seen = []
    def apply(ids): seen.extend(ids); batch.cancel()
    assert batch.start([str(i) for i in range(800)], apply, "Cancel")
    assert not batch.start(["other"], lambda _: None, "Other")
    drain(batch)
    assert len(seen) == 32
    assert batch.describe()["pending"] == 768 and batch.describe()["cancelled"]


def test_atomic_slice_failure_is_counted_without_stopping_remaining_work():
    batch = QueueBatch(); seen = []
    def apply(ids):
        if ids[0] == "0": raise OSError("https://user:synthetic-secret@example.test")
        seen.extend(ids)
    batch.start([str(i) for i in range(65)], apply, "Pause"); drain(batch)
    info = batch.describe()
    assert info["failed"] == 32 and info["completed"] == 33 and info["pending"] == 0
    assert len(seen) == 33 and "synthetic-secret" not in info["error"]


@pytest.mark.parametrize("restart", [False, True])
def test_progress_cancellation_emits_one_completion_and_can_start_a_new_batch(restart):
    batch = QueueBatch(); finishes = []; applied = []
    batch.finished.connect(finishes.append)
    def stop(info):
        if info["label"] == "Old" and info["completed"]:
            batch.cancel()
            if restart: batch.start(["new"], lambda ids: applied.extend(ids), "New")
    batch.changed.connect(stop)
    batch.start([str(i) for i in range(65)], lambda _: None, "Old")
    drain(batch)
    assert [info["label"] for info in finishes] == (["Old", "New"] if restart else ["Old"])
    assert applied == (["new"] if restart else []) and finishes[0]["pending"] == 33


def test_pending_worker_removal_is_not_counted_complete_until_settled():
    from morgan_media_downloader.queue_batch import BatchOutcome
    batch = QueueBatch()
    batch.start(["active", "ready"], lambda _: BatchOutcome(completed=1, waiting=("active",)), "Remove")
    APP.processEvents()
    assert batch.busy and batch.describe()["completed"] == 1 and batch.describe()["pending"] == 1
    batch.settle("foreign"); assert batch.describe()["completed"] == 1
    batch.settle("active")
    assert not batch.busy and batch.describe()["completed"] == 2


def test_stop_preserves_inflight_removal_and_reports_failure_truthfully():
    from morgan_media_downloader.queue_batch import BatchOutcome
    batch = QueueBatch()
    batch.start([str(i) for i in range(65)], lambda ids: BatchOutcome(completed=len(ids)-1, waiting=(ids[0],)), "Remove")
    while not batch.describe()["completed"]: APP.processEvents()
    batch.cancel()
    assert batch.busy and batch.describe()["pending"] >= 1
    # All already-admitted in-flight IDs must settle; unprocessed IDs stay pending.
    for key in ("0", "32", "64"): batch.settle(key, "https://user:synthetic-secret@example.test")
    assert not batch.busy and batch.describe()["failed"] >= 1
    assert "synthetic-secret" not in batch.describe()["error"]


def test_sequential_cleanup_waits_for_settlement_and_stop_notifies_immediately():
    from morgan_media_downloader.queue_batch import BatchOutcome
    batch = QueueBatch(); slices = []; changes = []
    def apply(ids): slices.append(ids); return BatchOutcome(waiting=tuple(ids))
    batch.changed.connect(changes.append)
    batch.start([str(i) for i in range(65)], apply, "Cleanup", wait_each_slice=True)
    APP.processEvents(); APP.processEvents()
    assert len(slices) == 1
    batch.cancel()
    assert changes[-1]["cancelled"] and changes[-1]["pending"] == 65
    for key in slices[0]: batch.settle(key)
    assert not batch.busy and len(slices) == 1 and batch.describe()["pending"] == 33
