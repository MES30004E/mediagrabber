from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from morgan_media_downloader.local_converter import (
    ConversionOptions, build_conversion_plan, convert_local_video, detect_ffmpeg_encoders,
    output_with_container, preset_options,
)
from morgan_media_downloader.media_verification import inspect_media

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / "resources" / "bin" / "ffmpeg"
FFPROBE = ROOT / "resources" / "bin" / "ffprobe"


def _details(video="h264", audio="aac", subtitle="", container="mov,mp4,m4a,3gp,3g2,mj2"):
    streams = [
        {"index": 0, "type": "video", "codec": video, "tag": "avc1", "pix_fmt": "yuv420p",
         "width": 1920, "height": 1080, "frame_rate": "30/1", "attached_pic": False},
        {"index": 1, "type": "audio", "codec": audio, "tag": "mp4a", "sample_rate": "48000",
         "channel_layout": "stereo", "attached_pic": False},
    ]
    if subtitle: streams.append({"index": 2, "type": "subtitle", "codec": subtitle, "attached_pic": False})
    return {"format_name": container, "streams": streams, "size": 1_000_000, "duration": 10,
            "subtitles": [], "chapter_count": 0, "thumbnail": False}


def _make(path: Path, video: str, audio: str) -> None:
    command = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=10",
               "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "0.25",
               "-c:v", video]
    if video in {"libx264", "libx265"}: command += ["-pix_fmt", "yuv420p"]
    if video == "libx265": command += ["-x265-params", "log-level=error"]
    if video == "libaom-av1": command += ["-cpu-used", "8", "-crf", "40"]
    command += ["-c:a", audio, str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_preset_values_and_reset():
    mac = preset_options("macOS / QuickTime")
    universal = preset_options("Universal")
    small = preset_options("Small File")
    remux = preset_options("Original / Remux", ConversionOptions(container="MKV"))
    assert (mac.container, mac.video_codec, mac.audio_codec, mac.subtitle_mode) == ("MP4", "H.264 / AVC", "AAC", "Convert if needed")
    assert (universal.container, universal.video_codec, universal.audio_codec) == ("MP4", "H.264 / AVC", "AAC")
    assert (small.container, small.video_codec, small.audio_codec, small.custom_crf) == ("MP4", "HEVC / H.265", "AAC", 26)
    assert (remux.container, remux.video_codec, remux.audio_codec, remux.subtitle_mode) == ("MKV", "Copy", "Copy", "Copy as-is")
    customised = preset_options("Custom", small)
    assert customised.profile == "Custom" and customised.video_codec == "HEVC / H.265"
    assert preset_options("macOS / QuickTime", customised) == mac


@pytest.mark.parametrize(("container", "suffix"), [("MP4", ".mp4"), ("MOV", ".mov"), ("M4V", ".m4v"), ("MKV", ".mkv"), ("WebM", ".webm")])
def test_output_extension_tracks_container(container, suffix):
    assert output_with_container("movie.old", container).endswith(suffix)


def test_invalid_webm_combination_and_copy_incompatibility_are_blocked():
    invalid = build_conversion_plan(_details(), ConversionOptions(profile="Custom", container="WebM", video_codec="H.264 / AVC", audio_codec="AAC"))
    assert not invalid.valid and any("not supported in WebM" in error for error in invalid.errors)
    copy = build_conversion_plan(_details(video="vp9", audio="opus", container="webm"),
                                 ConversionOptions(profile="Original / Remux", container="MP4", video_codec="Copy", audio_codec="Copy"))
    assert not copy.valid and any("without conversion" in error for error in copy.errors)


def test_auto_and_selective_transcode_plans():
    remux = build_conversion_plan(_details(), ConversionOptions(profile="Custom", container="MKV", video_codec="Auto", audio_codec="Auto"))
    video_only = build_conversion_plan(_details(video="vp9"), ConversionOptions(profile="Custom", container="MP4", video_codec="H.264 / AVC", audio_codec="AAC"))
    audio_only = build_conversion_plan(_details(audio="opus"), ConversionOptions(profile="Custom", container="MP4", video_codec="H.264 / AVC", audio_codec="AAC"))
    full = build_conversion_plan(_details(video="vp9", audio="opus"), ConversionOptions(profile="Custom", container="MP4", video_codec="H.264 / AVC", audio_codec="AAC"))
    assert (remux.video_action, remux.audio_action, remux.mode) == ("Copy", "Copy", "Remux only")
    assert (video_only.video_action, video_only.audio_action) == ("Convert", "Copy")
    assert (audio_only.video_action, audio_only.audio_action) == ("Copy", "Convert")
    assert (full.video_action, full.audio_action, full.mode) == ("Convert", "Convert", "Full transcode")


@pytest.mark.parametrize(("container", "video", "audio"), [
    ("MP4", "H.264 / AVC", "AAC"), ("MP4", "HEVC / H.265", "AAC"),
    ("WebM", "VP9", "Opus"), ("WebM", "AV1", "Opus"),
    ("MKV", "Copy", "Copy"), ("MKV", "H.264 / AVC", "MP3"),
    ("MKV", "HEVC / H.265", "FLAC"),
])
def test_supported_video_and_audio_codec_combinations(container, video, audio):
    source = _details(video="h264", audio="aac", container="matroska")
    plan = build_conversion_plan(source, ConversionOptions(profile="Custom", container=container, video_codec=video, audio_codec=audio))
    assert plan.valid


def test_resolution_never_upscales_unless_enabled():
    source = _details(); source["streams"][0]["height"] = 720
    safe = build_conversion_plan(source, ConversionOptions(profile="Custom", resolution="1080p", allow_upscaling=False))
    upscale = build_conversion_plan(source, ConversionOptions(profile="Custom", resolution="1080p", allow_upscaling=True))
    assert safe.video_action == "Copy"
    assert upscale.video_action == "Convert"


def test_subtitle_policies_are_container_aware():
    source = _details(subtitle="ass", container="matroska")
    convert = build_conversion_plan(source, ConversionOptions(container="MP4", subtitle_mode="Convert if needed"))
    preserve = build_conversion_plan(source, ConversionOptions(container="MP4", subtitle_mode="Preserve if compatible"))
    copy = build_conversion_plan(source, ConversionOptions(container="MP4", subtitle_mode="Copy as-is"))
    assert convert.subtitle_action == "Convert"
    assert preserve.subtitle_action == "Strip incompatible" and preserve.valid
    assert copy.subtitle_action == "Copy" and not copy.valid


def test_requested_encoders_exist_in_bundled_ffmpeg():
    available = detect_ffmpeg_encoders(str(FFMPEG))
    assert all(available.values())


@pytest.mark.parametrize(("source_name", "source_video", "source_audio", "options", "expected"), [
    ("source.webm", "libvpx-vp9", "libopus", ConversionOptions(profile="Custom", container="MP4", video_codec="H.264 / AVC", audio_codec="AAC"), ("h264", "aac")),
    ("source.mp4", "libx264", "aac", ConversionOptions(profile="Custom", container="MKV", video_codec="Copy", audio_codec="Copy", subtitle_mode="Strip subtitles"), ("h264", "aac")),
    ("source.mp4", "libx264", "aac", ConversionOptions(profile="Custom", container="MOV", video_codec="Copy", audio_codec="Copy", subtitle_mode="Strip subtitles"), ("h264", "aac")),
    ("source.mp4", "libx264", "aac", ConversionOptions(profile="Custom", container="M4V", video_codec="Copy", audio_codec="Copy", subtitle_mode="Strip subtitles"), ("h264", "aac")),
    ("source.mp4", "libx264", "aac", ConversionOptions(profile="Custom", container="WebM", video_codec="VP9", audio_codec="Opus", subtitle_mode="Strip subtitles"), ("vp9", "opus")),
])
def test_controlled_container_conversions(tmp_path, source_name, source_video, source_audio, options, expected):
    source = tmp_path / source_name; _make(source, source_video, source_audio)
    output = tmp_path / ("result" + {"MP4": ".mp4", "MKV": ".mkv", "MOV": ".mov", "M4V": ".m4v", "WebM": ".webm"}[options.container])
    events = []; result = convert_local_video(str(source), str(output), options, events.append, str(FFMPEG), str(FFPROBE))
    details = inspect_media(result["output"], str(FFPROBE)); streams = details["streams"]
    video = next(s for s in streams if s["type"] == "video" and not s["attached_pic"])
    audio = next(s for s in streams if s["type"] == "audio")
    assert (video["codec"], audio["codec"]) == expected
    assert events[-1]["stage"] == "Completed" and result["final_size"] > 0


def test_replace_original_is_verified_then_atomically_replaced(tmp_path):
    source = tmp_path / "replace.mp4"; _make(source, "libx264", "aac")
    options = ConversionOptions(replace_original=True)
    result = convert_local_video(str(source), str(source), options, ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE))
    assert result["output"] == str(source) and source.exists()
    assert inspect_media(str(source), str(FFPROBE))["streams"]


def test_hevc_aac_ass_to_mp4_copies_av_and_converts_only_subtitle(tmp_path):
    base = tmp_path / "hevc.mp4"; _make(base, "libx265", "aac")
    subtitle = tmp_path / "caption.ass"; subtitle.write_text(
        "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,16,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:00.20,Default,,0,0,0,,Hello\n")
    source = tmp_path / "hevc-sub.mkv"
    result = subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-i", str(subtitle),
                             "-map", "0", "-map", "1", "-c", "copy", "-metadata:s:s:0", "language=eng", str(source)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    options = ConversionOptions(profile="Custom", container="MP4", video_codec="HEVC / H.265", audio_codec="AAC", subtitle_mode="Convert if needed")
    converted = convert_local_video(str(source), str(tmp_path / "hevc-sub.mp4"), options, ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE))
    details = converted["after"]; video = next(s for s in details["streams"] if s["type"] == "video" and not s["attached_pic"])
    assert converted["plan"]["video_action"] == converted["plan"]["audio_action"] == "Copy"
    assert converted["plan"]["subtitle_action"] == "Convert"
    assert video["codec"] == "hevc" and video["tag"] == "hvc1"
    assert details["subtitle_streams"] == [{"language": "eng", "title": "", "codec": "mov_text"}]


def test_metadata_chapters_and_artwork_are_preserved_and_verified(tmp_path):
    base = tmp_path / "base.mp4"; _make(base, "libx264", "aac")
    artwork = tmp_path / "cover.jpg"
    subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:size=64x64", "-frames:v", "1", str(artwork)], check=True)
    metadata = tmp_path / "metadata.txt"; metadata.write_text(
        ";FFMETADATA1\ntitle=Converter QA\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=200\ntitle=Intro\n")
    source = tmp_path / "decorated.mp4"
    command = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-i", str(artwork),
               "-f", "ffmetadata", "-i", str(metadata), "-map", "0:v:0", "-map", "0:a:0", "-map", "1:v:0",
               "-map_metadata", "2", "-map_chapters", "2", "-c:v:0", "copy", "-c:a", "copy", "-c:v:1", "mjpeg",
               "-disposition:v:1", "attached_pic", str(source)]
    made = subprocess.run(command, capture_output=True, text=True); assert made.returncode == 0, made.stderr
    before = inspect_media(str(source), str(FFPROBE)); assert before["metadata"] and before["chapter_count"] == 1 and before["thumbnail"]
    converted = convert_local_video(str(source), str(tmp_path / "preserved.mp4"), ConversionOptions(), ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE))
    after = converted["after"]
    assert after["metadata"] and after["chapter_count"] == 1 and after["thumbnail"]
    assert after["video_count"] == 1 and after["artwork_count"] == 1
