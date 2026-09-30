from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from morgan_media_downloader.compatibility import (compatibility_risks,
                                                    ensure_compatible_output)
from morgan_media_downloader.media_verification import inspect_media


ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / "resources" / "bin" / "ffmpeg"
FFPROBE = ROOT / "resources" / "bin" / "ffprobe"


def _ffmpeg(*args: object) -> None:
    result = subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
                             *map(str, args)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def _source(path: Path, video: str, audio: str, *, tag: str = "") -> None:
    command: list[object] = ["-f", "lavfi", "-i", "testsrc2=size=96x64:rate=10",
                             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                             "-t", "0.25", "-c:v", video]
    if video == "libx264": command += ["-pix_fmt", "yuv420p"]
    if video == "libx265": command += ["-pix_fmt", "yuv420p", "-x265-params", "log-level=error"]
    if video == "libaom-av1": command += ["-cpu-used", "8", "-crf", "40"]
    command += ["-c:a", audio]
    if tag: command += ["-tag:v", tag]
    command += [path]
    _ffmpeg(*command)


@pytest.mark.parametrize(("name", "video", "audio", "expected_conversion"), [
    ("h264_aac.mp4", "libx264", "aac", "remuxed"),
    ("h264_opus.mkv", "libx264", "libopus", "Audio -> AAC"),
    ("vp9_aac.mkv", "libvpx-vp9", "aac", "Video -> H.264"),
    ("vp9_opus.webm", "libvpx-vp9", "libopus", "Video -> H.264"),
    ("av1_opus.mkv", "libaom-av1", "libopus", "Video -> H.264"),
])
def test_controlled_sources_become_quicktime_safe(tmp_path, name, video, audio, expected_conversion):
    source = tmp_path / name; _source(source, video, audio)
    output, summary, conversions = ensure_compatible_output(
        str(source), "macOS / QuickTime", ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE))
    details = inspect_media(output, str(FFPROBE))
    streams = details["streams"]
    primary = next(s for s in streams if s["type"] == "video" and not s["attached_pic"])
    sound = next(s for s in streams if s["type"] == "audio")
    assert Path(output).suffix == ".mp4" and summary["verified"]
    assert primary["codec"] == "h264" and primary["tag"] == "avc1" and primary["pix_fmt"] == "yuv420p"
    assert sound["codec"] == "aac" and sound["tag"] == "mp4a"
    assert any(expected_conversion in item for item in conversions)
    data = Path(output).read_bytes()
    assert data.find(b"moov") < data.find(b"mdat")  # +faststart
    if source.suffix != ".mp4": assert not source.exists()


def test_hevc_is_retagged_hvc1_without_video_transcode(tmp_path):
    source = tmp_path / "hevc.mp4"; _source(source, "libx265", "aac", tag="hev1")
    output, summary, conversions = ensure_compatible_output(
        str(source), "macOS / QuickTime", ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE))
    primary = next(s for s in inspect_media(output, str(FFPROBE))["streams"]
                   if s["type"] == "video" and not s["attached_pic"])
    assert primary["codec"] == "hevc" and primary["tag"] == "hvc1"
    assert summary["verified"] and not any("Video -> H.264" in item for item in conversions)


def test_mov_text_subtitle_and_attached_artwork_remain_compatible(tmp_path):
    base = tmp_path / "base.mp4"; _source(base, "libx264", "aac")
    subtitle = tmp_path / "caption.srt"; subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:00,200\nHello\n", encoding="utf-8")
    subtitled = tmp_path / "subtitled.mp4"
    _ffmpeg("-i", base, "-i", subtitle, "-map", "0", "-map", "1", "-c", "copy",
            "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", subtitled)
    art = tmp_path / "cover.png"
    _ffmpeg("-f", "lavfi", "-i", "color=c=blue:size=64x64", "-frames:v", "1", art)
    decorated = tmp_path / "decorated.mp4"
    _ffmpeg("-i", subtitled, "-i", art, "-map", "0", "-map", "1:v", "-c", "copy",
            "-disposition:v:1", "attached_pic", decorated)
    output, summary, _ = ensure_compatible_output(
        str(decorated), "macOS / QuickTime", ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE))
    details = inspect_media(output, str(FFPROBE))
    primary = [s for s in details["streams"] if s["type"] == "video" and not s["attached_pic"]]
    artwork = [s for s in details["streams"] if s["attached_pic"]]
    assert summary["verified"] and details["subtitle_streams"][0]["codec"] == "mov_text"
    assert len(primary) == 1 and len(artwork) == 1 and details["thumbnail"] is True


def test_warning_detector_maps_known_quicktime_risks():
    details = {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "streams": [
        {"type": "video", "codec": "vp9", "tag": "vp09", "pix_fmt": "yuv444p", "attached_pic": False},
        {"type": "audio", "codec": "opus", "tag": "Opus", "attached_pic": False},
        {"type": "subtitle", "codec": "webvtt", "tag": "", "attached_pic": False},
        {"type": "video", "codec": "png", "tag": "", "attached_pic": False},
    ]}
    risks = compatibility_risks(details, "macOS / QuickTime")
    assert any("VP9" in risk.upper() for risk in risks)
    assert any("opus" in risk.lower() for risk in risks)
    assert any("webvtt" in risk.lower() for risk in risks)
    assert any("ordinary video stream" in risk for risk in risks)
