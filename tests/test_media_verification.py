import json
import subprocess

from morgan_media_downloader.media_verification import inspect_media, verify_requested_postprocessing


def _runner(payload):
    def run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, json.dumps(payload), "")
    return run


def test_ffprobe_stream_metadata_detects_subtitles_artwork_and_metadata():
    payload = {"streams": [
        {"codec_type": "video", "disposition": {"attached_pic": 0}},
        {"codec_type": "audio"},
        {"codec_type": "subtitle", "codec_name": "mov_text", "tags": {"language": "eng", "title": "English"}},
        {"codec_type": "video", "disposition": {"attached_pic": 1}},
    ], "format": {"tags": {"title": "Example"}}}
    result = inspect_media("result.mp4", "/bundled/ffprobe", _runner(payload))
    assert result["video"] and result["audio"] and result["subtitle_count"] == 1
    assert result["subtitles"] == ["eng - English • mov_text"]
    assert result["subtitle_streams"] == [{"language": "eng", "title": "English", "codec": "mov_text"}]
    assert result["thumbnail"] and result["metadata"] and result["artwork_count"] == 1


def test_missing_optional_subtitle_and_thumbnail_are_warnings_not_media_failure():
    payload = {"streams": [{"codec_type": "video", "disposition": {}}, {"codec_type": "audio"}],
               "format": {"tags": {}}}
    details, warnings = verify_requested_postprocessing(
        "result.mp4", embed_thumbnail=True, embed_subtitles=True,
        ffprobe="/bundled/ffprobe", runner=_runner(payload))
    assert not details["thumbnail"] and details["subtitle_count"] == 0
    assert len(warnings) == 2


def test_unsupported_thumbnail_container_is_reported_without_failing():
    payload = {"streams": [{"codec_type": "video", "disposition": {}}], "format": {"tags": {}}}
    details, warnings = verify_requested_postprocessing(
        "result.webm", embed_thumbnail=True, embed_subtitles=False,
        ffprobe="/bundled/ffprobe", runner=_runner(payload))
    assert details["thumbnail"] == "Unsupported"
    assert "not supported" in warnings[0]
