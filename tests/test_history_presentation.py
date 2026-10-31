from dataclasses import FrozenInstanceError

import pytest

from morgan_media_downloader.history_presentation import HistoryRefreshState, history_row
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem


def sample():
    return DownloadJob(MediaItem("https://example.test/source", "A title", original_url="https://example.test/original"),
        DownloadOptions(quality="720p"), id="fixture-id", created_at="2026-01-02T03:04:05.123456+00:00")


def test_history_row_matches_existing_columns_and_is_immutable():
    job = sample(); row = history_row(job)
    assert row.job_id == "fixture-id" and row.created_at == "2026-01-02T03:04:05.123456+00:00"
    assert row.cells == ("2026-01-02 03:04:05", "A title", "https://example.test/original",
        "https://example.test/source", "", "720p", "Waiting")
    with pytest.raises(FrozenInstanceError): row.job_id = "other-id"


def test_progress_and_unrendered_diagnostics_do_not_change_history_presentation():
    job = sample(); before = history_row(job)
    job.progress = 37.5; job.downloaded_bytes = 1536; job.total_bytes = 4096
    job.speed = 2048; job.eta = 7; job.updated_at = "later"; job.error = "synthetic failure details"
    job.warnings = ["Synthetic warning"]; job.item.thumbnail = "https://example.test/thumbnail"
    assert history_row(job) == before


@pytest.mark.parametrize("field", ["title", "original_url", "source_url", "output", "quality", "audio_format", "status", "order"])
def test_render_filter_and_order_fields_invalidate_in_place_mutations(field):
    job = sample(); before = history_row(job)
    if field == "title": job.item.title = "Another title"
    elif field == "original_url": job.item.original_url = "https://example.test/another-original"
    elif field == "source_url": job.item.source_url = "https://example.test/another-source"
    elif field == "output": job.output_file = "/synthetic/output.mp4"
    elif field == "quality": job.options.quality = "1080p"
    elif field == "audio_format": job.options.audio_format = "MP3"
    elif field == "status": job.status = JobStatus.PAUSED
    elif field == "order": job.created_at = "2026-01-02T03:04:05.999999+00:00"
    assert history_row(job) != before
    if field == "order": assert history_row(job).cells == before.cells
    if field == "audio_format": assert history_row(job).cells[5] == "MP3"


def test_quality_behind_selected_audio_format_is_not_a_visible_change():
    job = sample(); job.options.audio_format = "MP3"; before = history_row(job)
    job.options.quality = "1080p"
    assert history_row(job) == before


def test_state_keeps_snapshots_not_mutable_jobs_and_prunes_removed_ids():
    job = sample(); state = HistoryRefreshState(); row = history_row(job)
    assert state.needs_refresh(row)
    state.remember(row)
    job.progress = 25; assert not state.needs_refresh(history_row(job))
    job.item.title = "Changed"; assert state.needs_refresh(history_row(job))
    state.rendered([], {job.id})  # Filter hides it; do not discard known state.
    assert not state.needs_refresh(row)
    state.rendered([], set())
    assert state.needs_refresh(row)


def test_rendered_database_rows_replace_only_those_observed():
    first = sample(); second = sample(); second.id = "second-id"
    state = HistoryRefreshState(); first_row = history_row(first); second_row = history_row(second)
    state.rendered([first_row, second_row], {first.id, second.id})
    second.item.title = "Unpersisted mutation"
    first.status = JobStatus.PAUSED
    state.rendered([history_row(first)], {first.id, second.id})
    assert not state.needs_refresh(history_row(first))
    assert state.needs_refresh(history_row(second)), "Unobserved mutation must not be acknowledged"
    assert not state.needs_refresh(second_row)


def test_invalidated_presentation_requires_successful_render_not_just_remember():
    row = history_row(sample()); state = HistoryRefreshState(); state.remember(row)
    state.invalidate()
    assert state.needs_refresh(row)
    state.remember(row)
    assert state.needs_refresh(row)
    state.rendered([row], {row.job_id})
    assert not state.needs_refresh(row)
