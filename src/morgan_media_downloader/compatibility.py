from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .media_verification import inspect_media
from .paths import find_binary


COMPATIBLE_PROFILES = {"macOS / QuickTime", "Universal"}
MP4_FORMAT_NAMES = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}


def is_mp4(details: dict[str, object]) -> bool:
    names = {part.strip().casefold() for part in str(details.get("format_name") or "").split(",")}
    return bool(names & MP4_FORMAT_NAMES)


def compatibility_risks(details: dict[str, object], profile: str) -> list[str]:
    if profile not in COMPATIBLE_PROFILES:
        return []
    risks: list[str] = []
    if not is_mp4(details): risks.append("Final container is not MP4")
    if details.get("faststart") is False: risks.append("MP4 fast start is not present")
    streams = list(details.get("streams") or [])
    videos = [s for s in streams if s.get("type") == "video" and not s.get("attached_pic")]
    audio = [s for s in streams if s.get("type") == "audio"]
    subtitles = [s for s in streams if s.get("type") == "subtitle"]
    artwork = [s for s in streams if s.get("attached_pic")]
    data_streams = [s for s in streams if s.get("type") == "data"]
    if len(videos) != 1: risks.append(f"Expected one primary video stream; found {len(videos)}")
    for stream in videos:
        codec, tag, pix_fmt = stream.get("codec"), stream.get("tag"), stream.get("pix_fmt")
        if codec == "hevc":
            if tag != "hvc1": risks.append("HEVC stream is not tagged hvc1")
        elif codec != "h264" or tag not in {"avc1", ""}:
            risks.append(f"Video codec {codec or 'unknown'} / {tag or 'untagged'} is not QuickTime-safe H.264")
        if codec == "h264" and pix_fmt not in {"yuv420p", ""}:
            risks.append(f"H.264 pixel format {pix_fmt or 'unknown'} is not yuv420p")
    for stream in audio:
        if stream.get("codec") != "aac" or stream.get("tag") not in {"mp4a", ""}:
            risks.append(f"Audio codec {stream.get('codec') or 'unknown'} / {stream.get('tag') or 'untagged'} is not AAC/mp4a")
    for stream in subtitles:
        if stream.get("codec") != "mov_text":
            risks.append(f"Subtitle codec {stream.get('codec') or 'unknown'} is not mov_text")
    if len(artwork) > 1: risks.append(f"Multiple attached artwork streams found ({len(artwork)})")
    for stream in artwork:
        if stream.get("codec") != "mjpeg":
            risks.append(f"Attached artwork codec {stream.get('codec') or 'unknown'} is not QuickTime-safe MJPEG")
    for stream in data_streams:
        # QuickTime chapter/timecode tracks are reported as bin_data/text or
        # tmcd by ffprobe and are expected. Other opaque data tracks are not.
        if stream.get("codec") not in {"tmcd"} and stream.get("tag") not in {"text", "tmcd"}:
            risks.append(f"Unexpected MP4 data stream {stream.get('codec') or 'unknown'} / "
                         f"{stream.get('tag') or 'untagged'} may not be QuickTime-safe")
    non_attached_extra = max(0, len(videos) - 1)
    if non_attached_extra: risks.append("Artwork or auxiliary video is exposed as an ordinary video stream")
    return risks


def compatibility_summary(details: dict[str, object], profile: str) -> dict[str, object]:
    streams = list(details.get("streams") or [])
    video = next((s for s in streams if s.get("type") == "video" and not s.get("attached_pic")), {})
    audio = next((s for s in streams if s.get("type") == "audio"), {})
    subtitle = next((s for s in streams if s.get("type") == "subtitle"), {})
    risks = compatibility_risks(details, profile)
    return {
        "profile": profile,
        "container": "MP4" if is_mp4(details) else str(details.get("format_name") or "Unknown"),
        "video_codec": f"{video.get('codec') or 'None'} / {video.get('tag') or 'untagged'}",
        "audio_codec": f"{audio.get('codec') or 'None'} / {audio.get('tag') or 'untagged'}",
        "subtitle_codec": subtitle.get("codec") or ("None" if not details.get("subtitle_count") else "Unknown"),
        "artwork": "QuickTime-compatible cover art" if details.get("thumbnail") else "None",
        "verified": not risks,
        "risks": risks,
    }


def ensure_compatible_output(path: str, profile: str, *, keep_original: bool = False,
                             output_path: str | None = None,
                             ffmpeg: str | None = None, ffprobe: str | None = None,
                             runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                             progress_callback: Callable[[dict[str, object]], None] | None = None
                             ) -> tuple[str, dict[str, object], list[str]]:
    """Produce an MP4 with compatible streams, copying streams that are already safe."""
    before = inspect_media(path, ffprobe=ffprobe, runner=runner)
    if profile not in COMPATIBLE_PROFILES:
        return path, compatibility_summary(before, profile), []
    streams = list(before.get("streams") or [])
    videos = [s for s in streams if s.get("type") == "video" and not s.get("attached_pic")]
    audios = [s for s in streams if s.get("type") == "audio"]
    subtitles = [s for s in streams if s.get("type") == "subtitle"]
    artwork = [s for s in streams if s.get("attached_pic")]
    video_copy = len(videos) == 1 and (
        (videos[0].get("codec") == "h264" and videos[0].get("pix_fmt") in {"yuv420p", ""}) or
        videos[0].get("codec") == "hevc")
    audio_copy = all(s.get("codec") == "aac" for s in audios)
    subtitle_copy = all(s.get("codec") == "mov_text" for s in subtitles)
    risks = compatibility_risks(before, profile)
    # Even a codec-safe MP4 is atomically remuxed to place the moov atom first.
    executable = ffmpeg or find_binary("ffmpeg")
    if not executable: raise FileNotFoundError("Bundled ffmpeg is unavailable")
    source = Path(path)
    target = Path(output_path) if output_path else (source if source.suffix.casefold() == ".mp4" else source.with_suffix(".mp4"))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.stem}.compat-{uuid4().hex}.mp4")
    command = [executable, "-y", "-i", str(source)]
    for stream in videos[:1] + audios + subtitles + artwork[:1]:
        command.extend(["-map", f"0:{stream['index']}"])
    command.extend(["-map_metadata", "0", "-map_chapters", "0"])
    command.extend(["-c:v:0", "copy" if video_copy else "libx264"])
    conversions: list[str] = []
    if not video_copy:
        command.extend(["-crf:v:0", "20", "-preset:v:0", "medium", "-pix_fmt:v:0", "yuv420p"])
        conversions.append("Video -> H.264/avc1 yuv420p")
    elif videos and videos[0].get("codec") == "hevc":
        command.extend(["-tag:v:0", "hvc1"])
    else:
        command.extend(["-tag:v:0", "avc1"])
    if audios:
        command.extend(["-c:a", "copy" if audio_copy else "aac"])
        if not audio_copy:
            command.extend(["-b:a", "192k"]); conversions.append("Audio -> AAC-LC/mp4a")
    if subtitles:
        command.extend(["-c:s", "copy" if subtitle_copy else "mov_text"])
        if not subtitle_copy: conversions.append("Subtitles -> mov_text")
    if artwork:
        artwork_video_index = 1
        command.extend([f"-c:v:{artwork_video_index}", "mjpeg", f"-disposition:v:{artwork_video_index}", "attached_pic"])
        if artwork[0].get("codec") != "mjpeg": conversions.append("Artwork -> attached MJPEG cover art")
    command.extend(["-movflags", "+faststart", str(temporary)])
    try:
        if progress_callback is not None and runner is subprocess.run:
            command[1:1] = ["-progress", "pipe:1", "-nostats"]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            started, duration, snapshot = time.monotonic(), float(before.get("duration") or 0), {}
            assert process.stdout is not None
            for raw in process.stdout:
                key, _, value = raw.strip().partition("="); snapshot[key] = value
                if key == "progress":
                    try: elapsed_media = int(snapshot.get("out_time_us") or 0) / 1_000_000
                    except ValueError: elapsed_media = 0.0
                    fraction = min(1.0, elapsed_media / duration) if duration else 0.0
                    elapsed_wall = time.monotonic() - started
                    eta = max(0.0, elapsed_wall / fraction - elapsed_wall) if fraction > 0 else None
                    progress_callback({"stage": "Converting", "progress": 15 + int(fraction * 75),
                                       "elapsed": elapsed_media, "total": duration,
                                       "fps": snapshot.get("fps") or "", "eta": eta,
                                       "speed": snapshot.get("speed") or ""})
                    snapshot = {}
            stderr = process.stderr.read() if process.stderr else ""; return_code = process.wait()
            result = subprocess.CompletedProcess(command, return_code, "", stderr)
        else:
            result = runner(command, capture_output=True, text=True, timeout=None, check=False)
        if result.returncode != 0 or not temporary.exists():
            raise RuntimeError((result.stderr or "ffmpeg compatibility processing failed").strip())
        after = inspect_media(str(temporary), ffprobe=ffprobe, runner=runner)
        summary = compatibility_summary(after, profile)
        if not summary["verified"]:
            raise RuntimeError("Compatibility verification failed: " + "; ".join(summary["risks"]))
        os.replace(temporary, target)
        if source != target and not keep_original: source.unlink(missing_ok=True)
        if not conversions: conversions.append("Compatible streams remuxed with MP4 fast start")
        return str(target), summary, conversions
    finally:
        temporary.unlink(missing_ok=True)
