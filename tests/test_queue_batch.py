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
