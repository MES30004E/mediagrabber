from morgan_media_downloader.downloader import _media_from_info


def test_playlist_entry_parsing():
    item = _media_from_info({"title": "Episode", "webpage_url": "https://example.test/e", "playlist_index": 3, "duration": 90}, "https://example.test/list")
    assert item.playlist_index == 3
    assert item.original_url.endswith("/list")


def test_progress_fields_are_representable():
    from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem
    job = DownloadJob(MediaItem("url", "title"), DownloadOptions())
    job.downloaded_bytes, job.total_bytes, job.speed, job.eta = 74, 91, 5.8, 3
    encoded = job.to_dict()
    assert encoded["downloaded_bytes"] == 74
    assert encoded["eta"] == 3
