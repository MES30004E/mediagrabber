"""Actual scheduler capacity and immutable-admission contracts; no transfers."""
import copy
from types import SimpleNamespace

import pytest

from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from morgan_media_downloader.settings import AppSettings
from test_theme_ui import window


@pytest.fixture
def dispatch(window, monkeypatch):
    starts, writes, settings_copies, job_copies, routes, runtimes, activity = [], [], [], [], [], [], []
    original_copy = copy.deepcopy

    def snapshot(value, *args, **kwargs):
        if isinstance(value, AppSettings): settings_copies.append(value)
        if isinstance(value, DownloadJob): job_copies.append(value.id)
        return original_copy(value, *args, **kwargs)

    monkeypatch.setattr(copy, "deepcopy", snapshot)
    monkeypatch.setattr(window.task_manager, "start", lambda kind, operation, **kwargs: starts.append((kind, operation, kwargs)))
    monkeypatch.setattr(window.database, "save_job", lambda job: writes.append(job.id))
    monkeypatch.setattr(window, "_proxy", lambda: routes.append(True) or "synthetic-route")
    runtime = object()
    monkeypatch.setattr(window.runtime_manager, "snapshot", lambda: runtimes.append(True) or runtime)
    refresh = window._refresh_activity
    monkeypatch.setattr(window, "_refresh_activity", lambda: activity.append(True) or refresh())
    window.jobs = {}; window.active = {}
    window.settings.concurrent_downloads = 2; window.settings.torrent_max_active = 1
    try:
        yield SimpleNamespace(window=window, starts=starts, writes=writes,
            settings_copies=settings_copies, job_copies=job_copies, routes=routes,
            runtimes=runtimes, activity=activity, runtime=runtime)
    finally:
        window.active.clear(); window.jobs.clear()


def populate(state, kinds, *, active_media=0, active_torrents=0):
    jobs = []
    for index, kind in enumerate(["media"]*active_media + ["torrent"]*active_torrents + list(kinds)):
        job = DownloadJob(MediaItem(f"https://example.test/{index}", f"Fixture {index}"),
            DownloadOptions(authentication_mode="None"), id=f"fixture-{index}", kind=kind)
        if index < active_media + active_torrents:
            job.status = JobStatus.DOWNLOADING
            state.window.active[job.id] = "synthetic-owner-" + job.id
        jobs.append(job)
    state.window.jobs = {job.id: job for job in jobs}
    return jobs[active_media + active_torrents:]


@pytest.mark.parametrize("count", [800, 5000])
@pytest.mark.parametrize("kind", ["media", "torrent"])
@pytest.mark.parametrize("both_full", [False, True])
def test_full_kind_capacity_does_no_snapshot_route_runtime_or_write_work(dispatch, count, kind, both_full):
    media = 2 if kind == "media" or both_full else 0
    torrents = 1 if kind == "torrent" or both_full else 0
    waiting = populate(dispatch, [kind]*count, active_media=media, active_torrents=torrents)
    for _ in range(5): dispatch.window._dispatch()
    assert not dispatch.settings_copies and not dispatch.job_copies
    assert not dispatch.starts and not dispatch.writes and not dispatch.routes and not dispatch.runtimes
    assert len(dispatch.activity) == 5
    assert all(job.status == JobStatus.WAITING for job in waiting)


@pytest.mark.parametrize("kinds", [["media", "media", "torrent", "torrent"],
                                  ["torrent", "torrent", "media", "media"]])
def test_mixed_queue_retains_fifo_and_independent_type_budgets(dispatch, kinds):
    dispatch.window.settings.torrent_max_active = 2
    waiting = populate(dispatch, kinds, active_media=1, active_torrents=1)
    dispatch.window._dispatch()
    expected = [waiting[0].id, waiting[2].id]
    assert dispatch.writes == expected and dispatch.job_copies == expected
    assert len(dispatch.starts) == len(dispatch.settings_copies) == 2
    assert len(dispatch.routes) == len(dispatch.runtimes) == 1
    assert waiting[1].status == waiting[3].status == JobStatus.WAITING
    dispatch.window._dispatch()
    assert dispatch.writes == expected and len(dispatch.settings_copies) == 2


def test_admitted_workers_keep_independent_job_settings_route_and_runtime_snapshots(dispatch, monkeypatch):
    window = dispatch.window
    window.settings.authentication_mode = "None"
    waiting = populate(dispatch, ["media", "media", "torrent", "torrent"])
    received = []
    monkeypatch.setattr("morgan_media_downloader.ui._media_download_operation",
        lambda job, proxy, settings, runtime, cancel, progress, tor: received.append((job, settings, proxy, runtime)))
    monkeypatch.setattr("morgan_media_downloader.ui._torrent_download_operation",
        lambda job, settings, cancel, progress: received.append((job, settings, None, None)))
    window._dispatch()
    assert len(dispatch.settings_copies) == len(dispatch.job_copies) == len(dispatch.starts) == 3
    window.settings.authentication_mode = "Browser Cookies"
    waiting[0].item.title = "Changed after admission"
    for _, operation, _ in dispatch.starts: operation(None, None)
    assert len({id(settings) for _, settings, _, _ in received}) == 3
    assert all(settings.authentication_mode == "None" for _, settings, _, _ in received)
    assert received[0][0].item.title == "Fixture 0" and received[0][0] is not waiting[0]
    assert all(proxy == "synthetic-route" and runtime is dispatch.runtime for _, _, proxy, runtime in received[:2])
    assert waiting[3].status == JobStatus.WAITING


def test_rejected_media_route_does_not_snapshot_or_starve_torrent(dispatch, monkeypatch):
    waiting = populate(dispatch, ["media", "media", "torrent"])
    def reject(): raise ConnectionError("Synthetic route unavailable")
    monkeypatch.setattr(dispatch.window, "_proxy", reject)
    dispatch.window._dispatch()
    assert dispatch.writes == dispatch.job_copies == [waiting[2].id]
    assert len(dispatch.settings_copies) == len(dispatch.starts) == 1
    assert not dispatch.runtimes
    assert all(job.status == JobStatus.WAITING for job in waiting[:2])


def test_busy_batch_prevents_all_dispatch_work(dispatch, monkeypatch):
    populate(dispatch, ["media", "torrent"])
    # Restore the real QObject/service before the window fixture closes it.
    with monkeypatch.context() as patch:
        patch.setattr(dispatch.window, "queue_batch", SimpleNamespace(busy=True))
        dispatch.window._dispatch()
    assert not dispatch.starts and not dispatch.settings_copies and not dispatch.job_copies
    assert not dispatch.writes and not dispatch.routes and not dispatch.activity
