import copy
import math
import random

from morgan_media_downloader.database import Database
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from morgan_media_downloader.queue_collections import CollectionIndex, assign_collections, collection_key


def job(number=0, group="a", name="Group A", status=JobStatus.WAITING, progress=0):
    return DownloadJob(MediaItem(f"https://example.test/{number}", f"Video {number}"), DownloadOptions(),
        id=str(number), collection_id=group, collection_name=name, status=status, progress=progress)


def test_admission_partitions_same_title_by_provenance_and_is_fresh_without_mutating_items():
    items = [MediaItem("u1", "One", original_url="https://example.test/list/a", collection_title="Same", collection_type="Playlist"),
        MediaItem("u2", "Two", original_url="https://example.test/list/a", collection_title="Same", collection_type="Playlist"),
        MediaItem("u3", "Three", original_url="https://example.test/list/b", collection_title="Same", collection_type="Playlist"),
        MediaItem("u4", "Four"), MediaItem("u5", "Five")]
    before = copy.deepcopy(items); assigned = assign_collections(items); again = assign_collections(items)
    assert items == before and len(assigned) == 5
    assert assigned[0][0] == assigned[1][0] and assigned[2][0] != assigned[0][0]
    assert assigned[3][0] == assigned[4][0] and assigned[3][0] not in {assigned[0][0], assigned[2][0]}
    assert {key for key, _ in assigned}.isdisjoint(key for key, _ in again)
    assert assigned[0][1] == assigned[2][1] == "Same" and assigned[3][1] == "Batch of 2 items"


def test_new_and_legacy_identity_survives_database_reopen_without_title_only_merging(tmp_path):
    current = job(); legacy = job(1); payload = legacy.to_dict(); payload.pop("collection_id"); payload.pop("collection_name")
    legacy = DownloadJob.from_dict(payload)
    legacy.item.collection_title = "Same"; legacy.item.original_url = "https://example.test/list/a"
    other = copy.deepcopy(legacy); other.id = "other"; other.item.original_url = "https://example.test/list/b"
    unknown = job(3, group=""); unknown.item.collection_title = "Same"; unknown.item.original_url = ""
    database = Database(tmp_path/"queue.sqlite3"); database.save_jobs([current, legacy, other, unknown]); database.close()
    database = Database(tmp_path/"queue.sqlite3")
    try: loaded = database.load_jobs()
    finally: database.close()
    index = CollectionIndex(); index.sync(loaded); by_id = {value.id:value for value in loaded}
    assert by_id["0"].collection_id == "a" and by_id["0"].collection_name == "Group A"
    assert collection_key(by_id["1"]) == collection_key(legacy) != collection_key(by_id["other"])
    assert index.summary(collection_key(legacy)).name.startswith("Legacy")
    assert index.ids(collection_key(unknown)) == ("3",)
    assert index.summary("").total == 4


def test_incremental_status_progress_and_membership_do_not_rebuild_other_jobs():
    values = [job(0, status=JobStatus.WAITING, progress=20), job(1, status=JobStatus.CONVERTING, progress=40),
        job(2, status=JobStatus.COMPLETED_WARNINGS, progress=0), job(3, group="b", name="B", progress=float("nan"))]
    index = CollectionIndex(); index.sync(values)
    summary = index.summary("a")
    assert summary.total == 3 and dict(summary.counts)["Running"] == 1 and dict(summary.counts)["Completed"] == 1
    assert math.isclose(summary.progress, 160/3) and summary.known_progress == 3
    assert index.summary("b").progress is None and index.summary("b").known_progress == 0
    values[1].status = JobStatus.FAILED; values[1].progress = 75; index.update_job(values[1])
    assert dict(index.summary("a").counts)["Failed"] == 1 and index.ids("a", "Completed") == ("2",)
    values[1].collection_id = "b"; values[1].collection_name = "B"; index.update_job(values[1])
    assert index.ids("a") == ("0", "2") and index.summary("b").progress == 75
    assert index.ids("") == ("0", "1", "2", "3"), "Progress/group updates must not reorder global action targets"
    index.sync(values[1:])
    assert index.summary("").total == 3 and index.ids("a") == ("2",)


def test_randomized_updates_match_independent_group_counts_and_progress():
    rng = random.Random(45); values = [job(i, group=f"g{i%4}", name=f"Group {i%4}") for i in range(40)]
    index = CollectionIndex(); index.sync(values)
    categories = {JobStatus.WAITING:"Waiting", JobStatus.DOWNLOADING:"Running", JobStatus.COMPLETED:"Completed",
                  JobStatus.COMPLETED_WARNINGS:"Completed", JobStatus.CANCELLED:"Cancelled", JobStatus.FAILED:"Failed"}
    for _ in range(300):
        target = rng.choice(values); target.collection_id = f"g{rng.randrange(4)}"; target.collection_name = target.collection_id
        target.status = rng.choice(list(categories)); target.progress = rng.randrange(101); index.update_job(target)
        for key in ("", "g0", "g1", "g2", "g3"):
            expected = [value for value in values if not key or value.collection_id == key]
            summary = index.summary(key)
            assert summary.total == len(expected)
            for category in {"Waiting", "Running", "Completed", "Cancelled", "Failed"}:
                assert dict(summary.counts)[category] == sum(categories[value.status] == category for value in expected)
            if expected:
                progress = sum(100 if value.status in {JobStatus.COMPLETED,JobStatus.COMPLETED_WARNINGS} else value.progress for value in expected)/len(expected)
                assert math.isclose(summary.progress, progress, abs_tol=1e-8)
