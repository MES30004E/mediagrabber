import json
import pytest

from morgan_media_downloader.models import MediaItem, DownloadJob, DownloadOptions
from morgan_media_downloader.yt_runtime import RuntimeSnapshot


def metadata():
    return {"title": "Synthetic video", "language": "en", "webpage_url": "https://www.youtube.com/watch?v=fixture",
            "formats": [
                {"format_id": "v1080", "url": "https://cdn.test/v?token=never-persist", "vcodec": "avc1", "acodec": "none", "height": 1080, "ext": "mp4"},
                {"format_id": "a-en", "url": "https://cdn.test/en", "vcodec": "none", "acodec": "mp4a", "ext": "m4a", "language": "en", "format_note": "English (original) (default)"},
                {"format_id": "a-ja", "url": "https://cdn.test/ja", "vcodec": "none", "acodec": "mp4a", "ext": "m4a", "language": "ja", "abr": 64},
                {"format_id": "storyboard", "url": "https://cdn.test/story", "vcodec": "none", "acodec": "none"}],
            "subtitles": {"en": [{"ext": "vtt", "url": "https://sub.test/?cookie=never-persist", "name": "English"}]},
            "automatic_captions": {"ja": [{"ext": "vtt", "url": "https://sub.test/ja"}]},
            "http_headers": {"Authorization": "never-persist"}}


def test_single_video_inspection_keeps_auth_proxy_and_provider_without_playlist_expansion(monkeypatch):
    from morgan_media_downloader.downloader import analyse_with_authentication
    seen = []
    class YDL:
        def __init__(self, options): seen.append(options)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, value, download=False):
            assert value == "https://www.youtube.com/watch?v=fixture&list=WL" and download is False
            return metadata()
    runtime = RuntimeSnapshot("synthetic", "Bundled", YDL)
    items, effective = analyse_with_authentication("https://www.youtube.com/watch?v=fixture&list=WL",
        "socks5h://127.0.0.1:9911", "http://127.0.0.1:4416", "", "Browser Cookies", "Firefox", "synthetic", "", runtime,
        single_video=True)
    assert effective == "Browser Cookies" and len(items) == 1
    assert seen[0]["noplaylist"] is True and seen[0]["extract_flat"] is False
    assert seen[0]["socket_timeout"] == 20 and seen[0]["extractor_retries"] == 1
    assert seen[0]["cookiesfrombrowser"] == ("firefox", "synthetic", None, None)
    assert seen[0]["proxy"].startswith("socks5h://") and "youtubepot-bgutilhttp" in seen[0]["extractor_args"]
    details = items[0].inspection
    assert [f["id"] for f in details["formats"]] == ["v1080", "a-en", "a-ja"]
    assert details["formats"][1]["original"] and details["formats"][1]["default"]
    assert details["formats"][2]["bitrate"] == 64
    assert details["manual_subtitles"] == ["en"] and details["automatic_subtitles"] == ["ja"]
    serialized = json.dumps(DownloadJob(items[0], DownloadOptions()).to_dict())
    assert "cdn.test" not in serialized and "sub.test" not in serialized and "never-persist" not in serialized


def test_missing_language_metadata_is_not_invented():
    from morgan_media_downloader.media_details import details_from_info
    info = metadata(); info.pop("language")
    for value in info["formats"]: value.pop("language", None); value.pop("format_note", None)
    details = details_from_info(info)
    assert details["language"] == ""
    assert all(not f["language"] and not f["original"] and not f["default"] for f in details["formats"])


def test_explicit_format_choices_are_revalidated_without_silent_fallback():
    from morgan_media_downloader.formats import resolve_available_format
    formats = metadata()["formats"]
    selected, _ = resolve_available_format(formats, "720p", "Auto", "Original/best audio", "macOS / QuickTime",
                                          video_format_id="v1080", audio_format_id="a-ja")
    assert selected == 'best*[format_id="v1080"]+best*[format_id="a-ja"]', "A per-item concrete video choice overrides batch quality"
    with pytest.raises(ValueError, match="selected audio"):
        resolve_available_format(formats, "Best", "Auto", "Original/best audio", audio_format_id="disappeared")
    with pytest.raises(ValueError, match="selected video"):
        resolve_available_format(formats, "Best", "Auto", "Original/best audio", video_format_id="disappeared")


def test_download_and_403_refresh_retain_selected_streams_and_authentication(tmp_path, monkeypatch):
    from test_downloader_policy import _run, FakeYDL
    from morgan_media_downloader.models import JobStatus
    job, run = _run(tmp_path, monkeypatch, mode="Browser Cookies", profile="synthetic")
    job.options.video_format_id = "v1080"; job.options.audio_format_id = "a-ja"
    extractions = []; transfers = []
    def extract(self, _url, download=False):
        extractions.append(self.params["cookiesfrombrowser"])
        value = dict(metadata(), ext="mp4")
        if len(extractions) > 1:
            value["formats"] = [f for f in value["formats"] if f["format_id"] != "a-ja"]
        return value
    def transfer(self, info, download=True):
        transfers.append(self.params["format"])
        raise RuntimeError("HTTP Error 403")
    monkeypatch.setattr(FakeYDL, "extract_info", extract)
    monkeypatch.setattr(FakeYDL, "process_ie_result", transfer)
    result = run()
    assert transfers == ['best*[format_id="v1080"]+best*[format_id="a-ja"]'], "Missing refreshed selection must not transfer a different audio track"
    assert extractions == [("chrome", "synthetic", None, None)] * 2
    assert result.status == JobStatus.FAILED and "selected audio" in result.error


@pytest.mark.parametrize("video,audio", [("v1080+bestaudio", ""), ("", "https://cdn.test/secret")])
def test_stream_ids_cannot_inject_format_selectors(video, audio):
    from morgan_media_downloader.formats import resolve_available_format
    with pytest.raises(ValueError):
        resolve_available_format(metadata()["formats"], "Best", "Auto", "Original/best audio", video_format_id=video, audio_format_id=audio)


@pytest.mark.parametrize("identity", ["best", "worst", "all", "mp4", "b", "best.2"])
def test_reported_ids_are_exact_ids_not_yt_dlp_selector_keywords(identity):
    from yt_dlp import YoutubeDL
    from morgan_media_downloader.formats import resolve_available_format
    formats = [{"format_id": identity, "height": 360, "ext": "mp4", "vcodec": "avc1", "acodec": "aac", "url": "https://media.test/low"},
               {"format_id": "other", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "aac", "url": "https://media.test/high"}]
    selector, _ = resolve_available_format(formats, "Best", "Auto", "Original/best audio", video_format_id=identity)
    with YoutubeDL({"quiet": True}) as ydl:
        selected = list(ydl.build_format_selector(selector)({"formats": formats, "incomplete_formats": False, "has_merged_format": True}))
    assert [f["format_id"] for f in selected] == [identity]


def test_exact_audio_video_merge_uses_reported_ids_with_real_offline_yt_dlp():
    from yt_dlp import YoutubeDL
    from morgan_media_downloader.formats import resolve_available_format
    formats = [dict(metadata()["formats"][0], format_id="best"), dict(metadata()["formats"][2], format_id="all")]
    selector, _ = resolve_available_format(formats, "Best", "Auto", "Original/best audio", video_format_id="best", audio_format_id="all")
    with YoutubeDL({"quiet": True}) as ydl:
        selected = list(ydl.build_format_selector(selector)({"formats": formats, "incomplete_formats": False, "has_merged_format": False}))
    assert len(selected) == 1
    assert [f["format_id"] for f in selected[0]["requested_formats"]] == ["best", "all"]


def test_real_yt_dlp_cached_selector_is_replaced_before_processing_result(tmp_path):
    import copy
    import threading
    from yt_dlp import YoutubeDL
    from morgan_media_downloader.downloader import download_job
    observed = []
    info = {"id": "fixture", "title": "Synthetic", "extractor": "generic", "extractor_key": "Generic",
            "webpage_url": "https://example.test/video", "formats": [
                {"format_id": "low", "height": 360, "ext": "mp4", "vcodec": "avc1", "acodec": "aac", "url": "https://media.test/low"},
                {"format_id": "high", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "aac", "url": "https://media.test/high"}]}
    class OfflineYDL(YoutubeDL):
        def extract_info(self, *args, **kwargs): return copy.deepcopy(info)
        def urlopen(self, *args, **kwargs): raise AssertionError("Offline selector test must not use the network")
        def process_ie_result(self, value, download=True):
            self.params["check_formats"] = False
            processed = super().process_ie_result(value, download=False)
            observed.append(processed["format_id"])
            return processed
    options = DownloadOptions(download_dir=str(tmp_path), authentication_mode="None", video_format_id="low", verify_postprocessing=False)
    job = DownloadJob(MediaItem("https://example.test/video", "Synthetic"), options)
    download_job(job, None, "http://127.0.0.1:4416", "", lambda *_: None, threading.Event(), RuntimeSnapshot("synthetic", "Bundled", OfflineYDL))
    assert observed == ["low"], "Updating params alone leaves YoutubeDL's compiled selector pointing at the batch default"


@pytest.mark.parametrize("explicit", [False, True])
def test_real_yt_dlp_refresh_extracts_fresh_metadata_before_revalidating_choices(tmp_path, explicit):
    import threading
    from yt_dlp import YoutubeDL
    from morgan_media_downloader.downloader import download_job
    transfers = []; extractions = []
    class OfflineYDL(YoutubeDL):
        def urlopen(self, *args, **kwargs): raise AssertionError("No network in selector regression")
        def extract_info(self, *args, **kwargs):
            identity = "old" if not extractions else "new"; extractions.append(identity)
            self.params["check_formats"] = False
            return super().process_ie_result({"id": "fixture", "title": "Synthetic", "extractor": "generic", "extractor_key": "Generic",
                "webpage_url": "https://example.test/video", "formats": [{"format_id": identity, "height": 720,
                "ext": "mp4", "vcodec": "avc1", "acodec": "aac", "url": "https://media.test/stream"}]}, download=False)
        def process_ie_result(self, value, download=True):
            processed = super().process_ie_result(value, download=False)
            transfers.append(processed["format_id"])
            if len(transfers) == 1: raise RuntimeError("HTTP Error 403")
            return processed
    options = DownloadOptions(download_dir=str(tmp_path), authentication_mode="None", verify_postprocessing=False,
                              video_format_id="old" if explicit else "")
    result = download_job(DownloadJob(MediaItem("https://example.test/video", "Synthetic"), options), None,
        "http://127.0.0.1:4416", "", lambda *_: None, threading.Event(), RuntimeSnapshot("synthetic", "Bundled", OfflineYDL))
    assert extractions == ["old", "new"]
    assert result.metadata_success, "The old compiled ID must not prevent refreshed metadata from being returned"
    assert transfers == (["old"] if explicit else ["old", "new"])
