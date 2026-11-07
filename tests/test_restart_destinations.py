"""Repeated restarts must not grow paths or broaden file ownership."""
import copy
from pathlib import Path

import pytest

from morgan_media_downloader.database import Database
from morgan_media_downloader.file_ownership import delete_owned_files
from morgan_media_downloader.models import DownloadJob
from morgan_media_downloader.queue_restart import restart_job
from test_queue_restart import job_at


@pytest.mark.parametrize("kind", ["media", "torrent"])
@pytest.mark.parametrize("choices", [("keep", "keep", "replace"), ("replace", "replace", "keep")])
def test_restarts_after_database_reload_use_distinct_siblings_and_current_inventory(tmp_path, kind, choices):
    root = tmp_path / "downloads" / "collection"
    root.mkdir(parents=True)
    job = job_at(root)
    job.kind = kind
    job.torrent_file_paths = ["album/video.mp4"]
    previous_directories = {root}
    retained = []
    database_path = tmp_path / "queue.sqlite3"
    for choice in choices:
        current = Path(job.options.download_dir)
        current.mkdir(exist_ok=True)
        owned = []
        for field, filename in [("final_files", "video.mp4"), ("partial_files", "video.mp4.part"),
                                ("temporary_files", "video.tmp"), ("subtitle_files", "video.en.srt"),
                                ("thumbnail_files", "video.jpg")]:
            path = current / filename
            path.write_bytes(b"owned attempt output")
            setattr(job, field, [str(path)])
            owned.append(path)
        unknown = current / "unknown.part"
        unknown.write_bytes(b"not inventoried")
        retained.append(unknown)
        # Even stale inventory must not make Replace eligible to delete siblings.
        job.final_files.extend(str(path) for path in retained if path.parent != current)
        before = copy.deepcopy(job.to_dict())
        changed = restart_job(job, choice)
        assert job.to_dict() == before
        destination = Path(changed.options.download_dir)
        assert destination.parent == root, "A restart of a restored job must not nest another attempt"
        assert destination not in previous_directories and not destination.exists()
        assert changed.created_job_directory == str(destination)
        assert all(path.exists() for path in owned) if choice == "keep" else not any(path.exists() for path in owned)
        if choice == "keep":
            retained.extend(owned)
        assert all(path.exists() for path in retained)
        assert changed.options.authentication_mode == "Browser Cookies" and changed.options.quality == "720p"
        assert changed.torrent_file_paths == ["album/video.mp4"]
        database = Database(database_path)
        try:
            database.save_job(changed)
        finally:
            database.close()
        database = Database(database_path)
        try:
            job = database.load_jobs()[0]
        finally:
            database.close()
        previous_directories.add(destination)
    assert job.restart_base_directory == str(root)


@pytest.mark.parametrize("suffix", ["restart-personal", "restart-" + "a" * 32 + "/restart-" + "b" * 32])
def test_legacy_record_keeps_its_current_destination_without_guessing_ancestors(tmp_path, suffix):
    root = tmp_path / suffix
    root.mkdir(parents=True)
    legacy = job_at(root).to_dict()
    legacy.pop("restart_base_directory", None)
    job = DownloadJob.from_dict(legacy)
    first = restart_job(job, "keep")
    second = restart_job(DownloadJob.from_dict(first.to_dict()), "keep")
    assert Path(first.options.download_dir).parent == root
    assert Path(second.options.download_dir).parent == root
    assert first.options.download_dir != second.options.download_dir


@pytest.mark.parametrize("choice", ["keep", "replace"])
@pytest.mark.parametrize("invalid", ["none", "number", "blank", "relative", "wrong_parent", "shared_created", "non_attempt", "symlink"])
def test_invalid_restart_anchor_is_refused_before_cleanup(tmp_path, choice, invalid):
    root = tmp_path / "downloads"
    current = root / ("restart-" + "a" * 32)
    current.mkdir(parents=True)
    job = job_at(current)
    job.restart_base_directory = str(root)
    job.created_job_directory = str(current)
    if invalid == "none": job.restart_base_directory = None
    elif invalid == "number": job.restart_base_directory = 1
    elif invalid == "blank": job.restart_base_directory = " "
    elif invalid == "relative": job.restart_base_directory = "downloads"
    elif invalid == "wrong_parent": job.restart_base_directory = str(tmp_path)
    elif invalid == "shared_created": job.created_job_directory = str(root)
    elif invalid == "non_attempt":
        current = root / "personal-folder"; current.mkdir()
        job.options.download_dir = job.created_job_directory = str(current)
    elif invalid == "symlink":
        other = root / ("restart-" + "b" * 32); other.mkdir()
        current.rmdir(); current.symlink_to(other, target_is_directory=True)
    owned = current / "video.mp4"
    owned.write_bytes(b"must survive validation")
    job.final_files = [str(owned)]
    calls = []
    with pytest.raises(ValueError, match="restart|Restart"):
        restart_job(job, choice, cleaner=lambda *_a, **_kw: calls.append(True))
    assert not calls and owned.read_bytes() == b"must survive validation"


def test_clear_restarted_job_never_removes_the_shared_anchor_or_previous_attempt(tmp_path):
    original = tmp_path / "video.mp4"
    original.write_bytes(b"original")
    first = restart_job(job_at(tmp_path), "keep")
    prior = Path(first.options.download_dir); prior.mkdir()
    prior_output = prior / "video.mp4"; prior_output.write_bytes(b"previous attempt")
    first.final_files = [str(prior_output)]
    second = restart_job(DownloadJob.from_dict(first.to_dict()), "keep")
    current = Path(second.options.download_dir); current.mkdir()
    output = current / "video.mp4"; output.write_bytes(b"current attempt")
    second.final_files = [str(output), str(prior_output), str(original)]
    delete_owned_files(second, use_trash=False)
    assert not current.exists() and prior_output.exists() and original.exists() and tmp_path.exists()
    assert current.parent == prior.parent == tmp_path
