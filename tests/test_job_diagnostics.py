from morgan_media_downloader.job_diagnostics import (
    apply_failure, classify_failure, diagnostics_text, is_playable_format,
    playable_formats, safe_format_summary, status_summary,
)
from morgan_media_downloader.models import DownloadJob, DownloadOptions, JobStatus, MediaItem


def test_playable_filter_excludes_storyboards_images_missing_urls_and_unknown_protocols():
    rejected = [
        {"format_id": "sb0", "url": "https://x", "ext": "mhtml", "format_note": "storyboard"},
        {"format_id": "img", "url": "https://x", "ext": "jpg", "vcodec": "none", "acodec": "none"},
        {"format_id": "none", "vcodec": "h264", "acodec": "none"},
        {"format_id": "odd", "url": "odd://x", "protocol": "unsupported", "vcodec": "h264", "acodec": "none"},
    ]
    assert not any(is_playable_format(value) for value in rejected)
    assert is_playable_format({"format_id": "hls", "url": "https://x/master.m3u8", "protocol": "m3u8_native", "vcodec": "h264", "acodec": "aac"})
    assert is_playable_format({"format_id": "html5", "url": "https://x/video.mp4", "protocol": "https", "vcodec": None, "acodec": None})


def test_generic_direct_media_and_safe_summary_never_include_signed_url():
    info = {"url": "https://cdn.test/v.mp4?token=secret", "protocol": "https", "ext": "mp4",
            "vcodec": "h264", "acodec": "aac", "http_headers": {"Referer": "https://page.test"}}
    formats = playable_formats(info)
    assert formats[0]["format_id"] == "direct"
    summary = safe_format_summary(formats)
    assert summary == [{"format_id": "direct", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "protocol": "https"}]
    assert "url" not in summary[0] and "http_headers" not in summary[0]


def test_failure_classification_distinguishes_403_404_429_and_metadata_state():
    result = classify_failure("HTTP Error 403: Forbidden", metadata_success=True, stage="Video transfer")
    assert result["code"] == "HTTP 403" and "Metadata loaded" in result["friendly"]
    assert classify_failure("HTTP Error 404")["code"] == "HTTP 404"
    assert classify_failure("HTTP Error 429")["code"] == "HTTP 429"


def test_failed_job_diagnostics_persist_without_signed_urls_or_credentials():
    job = DownloadJob(MediaItem("https://cdn.test/video?sig=secret", "Example"), DownloadOptions())
    job.metadata_success = True; job.failure_stage = "Media fragment"; job.extractor_key = "Generic"
    job.effective_authentication = "Auto -> None"; job.effective_connection = "Managed Tor"
    job.formats_total = 4; job.formats_playable = 3; job.retry_count = 1
    apply_failure(job, "HTTP Error 403 at https://cdn.test/chunk?token=hidden")
    job.status = JobStatus.FAILED
    restored = DownloadJob.from_dict(job.to_dict())
    assert restored.failure_code == "HTTP 403" and status_summary(restored) == "Failed — HTTP 403"
    output = diagnostics_text(restored, yt_dlp_version="2026.07.04")
    assert "Generic" in output and "Playable formats: 3" in output
    assert "secret" not in output and "hidden" not in output
