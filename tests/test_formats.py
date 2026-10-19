from morgan_media_downloader.formats import build_ydl_options, format_selector, resolve_available_format
from morgan_media_downloader.models import DownloadOptions


def test_video_quality_selector_caps_height():
    assert "height<=1080" in format_selector("1080p", "Original/best audio")


def test_audio_selection_and_conversion():
    options = DownloadOptions(audio_format="MP3", audio_bitrate="320 kbps", download_dir="/tmp")
    result = build_ydl_options(options)
    assert result["format"] == "bestaudio/best"
    assert result["postprocessors"][0]["preferredcodec"] == "mp3"
    assert result["postprocessors"][0]["preferredquality"] == "320"


def test_proxy_is_passed_to_yt_dlp():
    options = DownloadOptions(download_dir="/tmp")
    assert build_ydl_options(options, "socks5h://127.0.0.1:9150")["proxy"].startswith("socks5h://")


def test_available_formats_are_inspected_and_best_mp4_pair_is_selected():
    formats = [
        {"format_id": "v720", "url": "u", "height": 720, "fps": 30, "tbr": 1000, "ext": "mp4", "vcodec": "avc1", "acodec": "none"},
        {"format_id": "v1080", "url": "u", "height": 1080, "fps": 30, "tbr": 2000, "ext": "mp4", "vcodec": "avc1", "acodec": "none"},
        {"format_id": "a", "url": "u", "abr": 128, "ext": "m4a", "vcodec": "none", "acodec": "aac"},
    ]
    assert resolve_available_format(formats, "Best", "MP4", "Original/best audio") == ('best*[format_id="v1080"]+best*[format_id="a"]', [])


def test_missing_quality_uses_highest_lower_and_reports_warning():
    formats = [
        {"format_id": "v", "url": "u", "height": 720, "tbr": 1, "ext": "webm", "vcodec": "vp9", "acodec": "none"},
        {"format_id": "a", "url": "u", "abr": 1, "ext": "webm", "vcodec": "none", "acodec": "opus"},
    ]
    selector, warnings = resolve_available_format(formats, "1080p", "MP4", "Original/best audio")
    assert selector == 'best*[format_id="v"]+best*[format_id="a"]'
    assert "1080p unavailable. Using 720p." in warnings
    assert any("MP4 streams were unavailable" in warning for warning in warnings)


def test_real_thumbnail_and_subtitle_postprocessors_are_configured():
    options = DownloadOptions(download_dir="/tmp", embed_thumbnail=True, embed_subtitles=True,
                              write_subtitles=False, subtitle_language="en,zh-Hans",
                              subtitle_source="Normal + automatic captions")
    result = build_ydl_options(options)
    keys = [processor["key"] for processor in result["postprocessors"]]
    assert "EmbedThumbnail" in keys and "FFmpegEmbedSubtitle" in keys
    assert result["writethumbnail"] and result["writesubtitles"] and result["writeautomaticsub"]
    assert result["subtitleslangs"] == ["en", "zh-Hans"]
    assert not result["keep_subs"]


def test_html5_direct_format_with_unknown_codecs_is_playable():
    formats = [{"format_id": "0", "url": "https://media.test/video.mp4", "protocol": "https",
                "ext": "mp4", "vcodec": None, "acodec": None}]
    assert resolve_available_format(formats, "Best", "Auto", "Original/best audio") == ('best*[format_id="0"]', [])


def test_automatic_captions_only_is_independent_from_normal_subtitles():
    options = DownloadOptions(download_dir="/tmp", embed_subtitles=True,
                              subtitle_source="Automatic captions only")
    result = build_ydl_options(options)
    assert not result["writesubtitles"] and result["writeautomaticsub"]


def test_quicktime_profile_prefers_h264_aac_before_higher_ranked_vp9_opus():
    formats = [
        {"format_id": "vp9", "url": "u", "height": 1080, "tbr": 3000, "ext": "webm", "vcodec": "vp9", "acodec": "none"},
        {"format_id": "h264", "url": "u", "height": 1080, "tbr": 2200, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none"},
        {"format_id": "opus", "url": "u", "abr": 160, "ext": "webm", "vcodec": "none", "acodec": "opus"},
        {"format_id": "aac", "url": "u", "abr": 128, "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
    ]
    assert resolve_available_format(
        formats, "Best", "Auto", "Original/best audio", "macOS / QuickTime")[0] == 'best*[format_id="h264"]+best*[format_id="aac"]'
    assert resolve_available_format(
        formats, "Best", "Auto", "Original/best audio", "Original / Best Available")[0] == 'best*[format_id="vp9"]+best*[format_id="opus"]'


def test_quicktime_profile_sets_mp4_merge_output():
    options = DownloadOptions(download_dir="/tmp", compatibility="macOS / QuickTime", container="Auto")
    assert build_ydl_options(options)["merge_output_format"] == "mp4"
