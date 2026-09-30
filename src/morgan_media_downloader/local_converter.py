from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .compatibility import compatibility_summary
from .media_verification import inspect_media
from .paths import find_binary

CONTAINERS = ("MP4", "MOV", "M4V", "MKV", "WebM")
VIDEO_CODECS = ("Auto", "Copy", "H.264 / AVC", "HEVC / H.265", "VP9", "AV1")
AUDIO_CODECS = ("Auto", "Copy", "AAC", "MP3", "Opus", "FLAC")
SUBTITLE_MODES = ("Preserve if compatible", "Convert if needed", "Copy as-is", "Strip subtitles")
PROFILES = ("macOS / QuickTime", "Universal", "Small File", "Original / Remux", "Custom")
QUALITY_LEVELS = ("Auto", "Very High", "High", "Balanced", "Small File", "Custom CRF")
RESOLUTIONS = ("Keep Original", "2160p", "1440p", "1080p", "720p", "480p", "Custom")
FRAME_RATES = ("Keep Original", "60", "30", "24")
AUDIO_BITRATES = ("Auto", "96 kbps", "128 kbps", "160 kbps", "192 kbps", "256 kbps", "320 kbps")

EXTENSIONS = {"MP4": ".mp4", "MOV": ".mov", "M4V": ".m4v", "MKV": ".mkv", "WebM": ".webm"}
FORMAT_ALIASES = {
    "MP4": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}, "MOV": {"mov"},
    "M4V": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}, "MKV": {"matroska"}, "WebM": {"webm"},
}
VIDEO_NAMES = {"H.264 / AVC": "h264", "HEVC / H.265": "hevc", "VP9": "vp9", "AV1": "av1"}
VIDEO_ENCODERS = {"H.264 / AVC": "libx264", "HEVC / H.265": "libx265", "VP9": "libvpx-vp9", "AV1": "libaom-av1"}
AUDIO_NAMES = {"AAC": "aac", "MP3": "mp3", "Opus": "opus", "FLAC": "flac"}
AUDIO_ENCODERS = {"AAC": "aac", "MP3": "libmp3lame", "Opus": "libopus", "FLAC": "flac"}
ALLOWED_VIDEO = {
    "MP4": {"h264", "hevc"}, "MOV": {"h264", "hevc"}, "M4V": {"h264", "hevc"},
    "MKV": {"h264", "hevc", "vp9", "av1"}, "WebM": {"vp9", "av1"},
}
ALLOWED_AUDIO = {
    "MP4": {"aac", "mp3"}, "MOV": {"aac"}, "M4V": {"aac", "mp3"},
    "MKV": {"aac", "mp3", "opus", "flac"}, "WebM": {"opus"},
}
ALLOWED_SUBTITLES = {
    "MP4": {"mov_text"}, "MOV": {"mov_text"}, "M4V": {"mov_text"},
    "MKV": {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text"}, "WebM": {"webvtt"},
}
SUBTITLE_ENCODER = {"MP4": "mov_text", "MOV": "mov_text", "M4V": "mov_text", "MKV": "srt", "WebM": "webvtt"}


@dataclass(frozen=True)
class ConversionOptions:
    profile: str = "macOS / QuickTime"
    container: str = "MP4"
    video_codec: str = "H.264 / AVC"
    audio_codec: str = "AAC"
    subtitle_mode: str = "Convert if needed"
    quality: str = "High"
    custom_crf: int = 22
    resolution: str = "Keep Original"
    custom_height: int = 1080
    allow_upscaling: bool = False
    frame_rate: str = "Keep Original"
    audio_bitrate: str = "192 kbps"
    preserve_metadata: bool = True
    preserve_chapters: bool = True
    preserve_artwork: bool = True
    replace_original: bool = False


@dataclass(frozen=True)
class ConversionPlan:
    options: ConversionOptions
    video_action: str
    audio_action: str
    subtitle_action: str
    artwork_action: str
    resolved_video_codec: str
    resolved_audio_codec: str
    mode: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    estimated_size: int | None = None

    @property
    def valid(self) -> bool: return not self.errors

    def as_dict(self) -> dict[str, object]:
        value = asdict(self); value["valid"] = self.valid; return value


def preset_options(profile: str, current: ConversionOptions | None = None) -> ConversionOptions:
    base = current or ConversionOptions()
    if profile == "macOS / QuickTime":
        return ConversionOptions(profile=profile)
    if profile == "Universal":
        return replace(ConversionOptions(), profile=profile, quality="Balanced")
    if profile == "Small File":
        return replace(ConversionOptions(), profile=profile, video_codec="HEVC / H.265", quality="Balanced",
                       custom_crf=26, audio_bitrate="160 kbps")
    if profile in {"Original / Remux", "Original / Best Available"}:
        return replace(base, profile="Original / Remux", video_codec="Copy", audio_codec="Copy",
                       subtitle_mode="Copy as-is", quality="Auto", frame_rate="Keep Original",
                       resolution="Keep Original")
    return replace(base, profile="Custom")


def default_conversion_output(path: str, container: str = "MP4") -> str:
    source, extension = Path(path), EXTENSIONS.get(container, ".mp4")
    candidate = source.with_name(f"{source.stem} - converted{extension}")
    index = 2
    while candidate.exists():
        candidate = source.with_name(f"{source.stem} - converted {index}{extension}"); index += 1
    return str(candidate)


def output_with_container(path: str, container: str) -> str:
    return str(Path(path).with_suffix(EXTENSIONS[container]))


def detect_ffmpeg_encoders(ffmpeg: str | None = None) -> dict[str, bool]:
    executable = ffmpeg or find_binary("ffmpeg")
    if not executable: return {name: False for name in (*VIDEO_ENCODERS, *AUDIO_ENCODERS)}
    result = subprocess.run([executable, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15, check=False)
    listing = result.stdout + result.stderr
    return {name: bool(re.search(rf"\b{re.escape(encoder)}\b", listing))
            for name, encoder in {**VIDEO_ENCODERS, **AUDIO_ENCODERS}.items()}


def _primary(details: dict[str, object], kind: str) -> dict[str, object]:
    return next((s for s in details.get("streams", []) if s.get("type") == kind and not s.get("attached_pic")), {})


def _resolve_auto(container: str, source_codec: str, allowed: dict[str, set[str]], fallback: str) -> str:
    return source_codec if source_codec in allowed[container] else fallback


def _target_height(options: ConversionOptions) -> int | None:
    if options.resolution == "Keep Original": return None
    if options.resolution == "Custom": return options.custom_height
    return int(options.resolution.removesuffix("p"))


def _crf(codec: str, quality: str, custom: int) -> int:
    if quality == "Custom CRF": return custom
    table = {
        "h264": {"Very High": 18, "High": 20, "Balanced": 23, "Small File": 25, "Auto": 22},
        "hevc": {"Very High": 21, "High": 24, "Balanced": 26, "Small File": 29, "Auto": 26},
        "vp9": {"Very High": 24, "High": 28, "Balanced": 32, "Small File": 36, "Auto": 32},
        "av1": {"Very High": 24, "High": 28, "Balanced": 32, "Small File": 36, "Auto": 32},
    }
    return table.get(codec, table["h264"]).get(quality, 22)


def build_conversion_plan(details: dict[str, object], options: ConversionOptions,
                          encoders: dict[str, bool] | None = None) -> ConversionPlan:
    errors: list[str] = []; warnings: list[str] = []
    if options.container not in CONTAINERS: errors.append("Unsupported output format")
    if errors:
        return ConversionPlan(options, "None", "None", "None", "None", "", "", "Invalid", tuple(errors), ())
    video, audio = _primary(details, "video"), _primary(details, "audio")
    audio_streams = [s for s in details.get("streams", []) if s.get("type") == "audio"]
    source_video, source_audio = str(video.get("codec") or ""), str(audio.get("codec") or "")
    fallback_video = "vp9" if options.container == "WebM" else "h264"
    fallback_audio = "opus" if options.container == "WebM" else "aac"
    requested_video = (source_video if options.video_codec == "Copy" else
                       _resolve_auto(options.container, source_video, ALLOWED_VIDEO, fallback_video)
                       if options.video_codec == "Auto" else VIDEO_NAMES.get(options.video_codec, ""))
    requested_audio = (source_audio if options.audio_codec == "Copy" else
                       _resolve_auto(options.container, source_audio, ALLOWED_AUDIO, fallback_audio)
                       if options.audio_codec == "Auto" else AUDIO_NAMES.get(options.audio_codec, ""))
    if video and requested_video not in ALLOWED_VIDEO[options.container]:
        errors.append(f"{options.video_codec} is not supported in {options.container}.")
    if audio and requested_audio not in ALLOWED_AUDIO[options.container]:
        errors.append(f"{options.audio_codec} is not supported in {options.container}.")
    if options.video_codec == "Copy" and video and source_video not in ALLOWED_VIDEO[options.container]:
        errors.append("The video stream cannot be remuxed into the selected container without conversion.")
    if options.audio_codec == "Copy" and audio and any(str(s.get("codec") or "") not in ALLOWED_AUDIO[options.container] for s in audio_streams):
        errors.append("The audio stream cannot be remuxed into the selected container without conversion.")
    available = encoders or {}
    for label, resolved, source, mapping in ((options.video_codec, requested_video, source_video, VIDEO_ENCODERS),
                                             (options.audio_codec, requested_audio, source_audio, AUDIO_ENCODERS)):
        if resolved and resolved != source:
            display = next((name for name, codec in ({**VIDEO_NAMES, **AUDIO_NAMES}).items() if codec == resolved), label)
            if available and display in mapping and not available.get(display, False):
                errors.append(f"Selected codec unavailable in bundled ffmpeg: {display}")
    target_height = _target_height(options)
    resize = bool(video and target_height and (options.allow_upscaling or int(video.get("height") or 0) > target_height))
    fps_change = bool(video and options.frame_rate != "Keep Original")
    quicktime_pixel_conversion = bool(
        video and options.profile in {"macOS / QuickTime", "Universal"}
        and requested_video == "h264" and video.get("pix_fmt") not in {"yuv420p", ""})
    video_action = "Copy" if video and requested_video == source_video and not resize and not fps_change and not quicktime_pixel_conversion else "Convert" if video else "None"
    audio_action = "Copy" if audio and all(str(s.get("codec") or "") == requested_audio for s in audio_streams) else "Convert" if audio else "None"
    subtitles = [s for s in details.get("streams", []) if s.get("type") == "subtitle"]
    subtitle_codecs = {str(s.get("codec") or "") for s in subtitles}
    if not subtitles or options.subtitle_mode == "Strip subtitles": subtitle_action = "Strip" if subtitles else "None"
    elif options.subtitle_mode == "Copy as-is":
        subtitle_action = "Copy"
        if not subtitle_codecs <= ALLOWED_SUBTITLES[options.container]:
            errors.append(f"The subtitle streams cannot be copied into {options.container}.")
    elif subtitle_codecs <= ALLOWED_SUBTITLES[options.container]: subtitle_action = "Copy"
    elif options.subtitle_mode == "Convert if needed": subtitle_action = "Convert"
    else:
        subtitle_action = "Strip incompatible"
        warnings.append("Incompatible subtitle streams will be omitted")
    artwork = bool(details.get("thumbnail"))
    artwork_streams = [s for s in details.get("streams", []) if s.get("attached_pic") or s.get("type") == "attachment"]
    artwork_supported = any(s.get("attached_pic") for s in artwork_streams) or options.container == "MKV"
    artwork_action = "Preserve" if artwork and options.preserve_artwork and options.container != "WebM" and artwork_supported else "Strip" if artwork else "None"
    if artwork and options.preserve_artwork and artwork_action == "Strip": warnings.append(f"Artwork cannot be preserved safely in {options.container}")
    changed = [video_action == "Convert", audio_action == "Convert", subtitle_action == "Convert"]
    mode = "Full transcode" if video_action == audio_action == "Convert" else "Partial transcode" if any(changed) else "Remux only"
    input_size = int(details.get("size") or 0)
    estimate = int(input_size * (0.55 if options.profile == "Small File" else 0.8)) if input_size and any(changed) else input_size or None
    return ConversionPlan(options, video_action, audio_action, subtitle_action, artwork_action,
                          requested_video, requested_audio, mode, tuple(dict.fromkeys(errors)), tuple(warnings), estimate)


def format_analysis(details: dict[str, object], plan: ConversionPlan) -> str:
    video, audio = _primary(details, "video"), _primary(details, "audio")
    source_names = {**{v: k for k, v in VIDEO_NAMES.items()}, **{v: k for k, v in AUDIO_NAMES.items()}}
    def fps(value: object) -> str:
        try:
            left, right = str(value).split("/", 1); return f"{float(left) / float(right):.3g} fps"
        except (ValueError, ZeroDivisionError): return str(value or "Unknown")
    subtitles = ", ".join(details.get("subtitles") or []) or "None"
    size = int(details.get("size") or 0)
    estimate = f"~{plan.estimated_size:,} bytes" if plan.estimated_size else "Unknown"
    errors = "\nErrors:\n- " + "\n- ".join(plan.errors) if plan.errors else ""
    return (
        f"INPUT\nContainer: {details.get('format_name') or 'Unknown'}\n"
        f"Video: {source_names.get(video.get('codec'), video.get('codec') or 'None')} — "
        f"{video.get('width') or '?'}×{video.get('height') or '?'} — {fps(video.get('frame_rate'))}\n"
        f"Audio: {source_names.get(audio.get('codec'), audio.get('codec') or 'None')} — "
        f"{audio.get('channel_layout') or 'Unknown'} — {audio.get('sample_rate') or '?'} Hz\n"
        f"Subtitles: {subtitles}\nChapters: {details.get('chapter_count', 0)}\n"
        f"Artwork: {'Present' if details.get('thumbnail') else 'None'}\n"
        f"Input size: {size:,} bytes\nQuickTime compatibility: "
        f"{'Compatible' if compatibility_summary(details, 'macOS / QuickTime')['verified'] else 'Not compatible'}\n\n"
        f"CONVERSION PLAN\nContainer: {plan.options.container}\n"
        f"Video: {video.get('codec') or 'None'} → {plan.resolved_video_codec or 'None'} ({plan.video_action})\n"
        f"Audio: {audio.get('codec') or 'None'} → {plan.resolved_audio_codec or 'None'} ({plan.audio_action})\n"
        f"Subtitles: {plan.subtitle_action}\nArtwork: {plan.artwork_action}\n"
        f"Resolution: {plan.options.resolution}\nFrame rate: {plan.options.frame_rate}\n"
        f"Estimated mode: {plan.mode}\nEstimated output: {estimate}{errors}")


def analyse_local_video(path: str, profile: str | ConversionOptions = "macOS / QuickTime",
                        ffmpeg: str | None = None) -> dict[str, object]:
    options = profile if isinstance(profile, ConversionOptions) else preset_options(profile)
    details = inspect_media(path)
    plan = build_conversion_plan(details, options, detect_ffmpeg_encoders(ffmpeg))
    return {"path": path, "details": details, "compatibility": compatibility_summary(details, options.profile),
            "plan": plan.as_dict(), "analysis_text": format_analysis(details, plan)}


def _build_command(source: Path, temporary: Path, details: dict[str, object], plan: ConversionPlan,
                   executable: str) -> list[str]:
    options = plan.options; streams = list(details.get("streams") or [])
    video = next((s for s in streams if s.get("type") == "video" and not s.get("attached_pic")), None)
    audios = [s for s in streams if s.get("type") == "audio"]
    subtitles = [s for s in streams if s.get("type") == "subtitle"]
    artwork = next((s for s in streams if s.get("attached_pic") or s.get("type") == "attachment"), None)
    command = [executable, "-hide_banner", "-y", "-progress", "pipe:1", "-nostats", "-i", str(source)]
    if video: command += ["-map", f"0:{video['index']}"]
    for stream in audios: command += ["-map", f"0:{stream['index']}"]
    if plan.subtitle_action not in {"None", "Strip", "Strip incompatible"}:
        for stream in subtitles: command += ["-map", f"0:{stream['index']}"]
    if artwork and plan.artwork_action == "Preserve": command += ["-map", f"0:{artwork['index']}"]
    command += ["-map_metadata", "0" if options.preserve_metadata else "-1",
                "-map_chapters", "0" if options.preserve_chapters else "-1"]
    if video:
        if plan.video_action == "Copy": command += ["-c:v:0", "copy"]
        else:
            label = next(name for name, codec in VIDEO_NAMES.items() if codec == plan.resolved_video_codec)
            command += ["-c:v:0", VIDEO_ENCODERS[label], "-crf:v:0", str(_crf(plan.resolved_video_codec, options.quality, options.custom_crf))]
            if plan.resolved_video_codec in {"h264", "hevc"}: command += ["-preset:v:0", "medium", "-pix_fmt:v:0", "yuv420p"]
            elif plan.resolved_video_codec == "vp9": command += ["-b:v:0", "0", "-row-mt:v:0", "1"]
            else: command += ["-cpu-used:v:0", "6"]
            target_height = _target_height(options)
            if target_height and (options.allow_upscaling or int(video.get("height") or 0) > target_height):
                command += ["-vf:v:0", f"scale=-2:{target_height}"]
            if options.frame_rate != "Keep Original": command += ["-r:v:0", options.frame_rate]
        if plan.resolved_video_codec == "hevc" and options.container in {"MP4", "MOV", "M4V"}: command += ["-tag:v:0", "hvc1"]
        elif plan.resolved_video_codec == "h264" and options.container in {"MP4", "MOV", "M4V"}: command += ["-tag:v:0", "avc1"]
    if audios:
        if plan.audio_action == "Copy": command += ["-c:a", "copy"]
        else:
            label = next(name for name, codec in AUDIO_NAMES.items() if codec == plan.resolved_audio_codec)
            command += ["-c:a", AUDIO_ENCODERS[label]]
            if plan.resolved_audio_codec in {"aac", "mp3", "opus"}:
                bitrate = options.audio_bitrate.replace(" kbps", "k") if options.audio_bitrate != "Auto" else "192k"
                command += ["-b:a", bitrate]
    if subtitles and plan.subtitle_action not in {"None", "Strip", "Strip incompatible"}:
        command += ["-c:s", "copy" if plan.subtitle_action == "Copy" else SUBTITLE_ENCODER[options.container]]
    if artwork and plan.artwork_action == "Preserve":
        if artwork.get("type") == "attachment": command += ["-c:t", "copy"]
        else: command += ["-c:v:1", "mjpeg", "-disposition:v:1", "attached_pic"]
    if options.container in {"MP4", "MOV", "M4V"}: command += ["-movflags", "+faststart"]
    command += [str(temporary)]
    return command


def verify_conversion(path: str, source_details: dict[str, object], plan: ConversionPlan,
                      ffprobe: str | None = None) -> dict[str, object]:
    details = inspect_media(path, ffprobe=ffprobe)
    if Path(path).suffix.casefold() != EXTENSIONS[plan.options.container]:
        raise RuntimeError("Verification failed: output extension does not match the selected format")
    names = {part.strip().casefold() for part in str(details.get("format_name") or "").split(",")}
    if not names & FORMAT_ALIASES[plan.options.container]: raise RuntimeError("Verification failed: output container does not match the selected format")
    video, audio = _primary(details, "video"), _primary(details, "audio")
    if video and video.get("codec") != plan.resolved_video_codec: raise RuntimeError("Verification failed: video codec does not match the conversion plan")
    output_audio = [s for s in details.get("streams", []) if s.get("type") == "audio"]
    if any(s.get("codec") != plan.resolved_audio_codec for s in output_audio): raise RuntimeError("Verification failed: audio codec does not match the conversion plan")
    if video and (not video.get("width") or not video.get("height") or not video.get("pix_fmt") or not video.get("frame_rate")):
        raise RuntimeError("Verification failed: video structure is incomplete")
    if audio and (not audio.get("sample_rate") or not audio.get("channel_layout")):
        raise RuntimeError("Verification failed: audio structure is incomplete")
    source_duration, output_duration = float(source_details.get("duration") or 0), float(details.get("duration") or 0)
    if source_duration and abs(output_duration - source_duration) > max(0.5, source_duration * 0.02):
        raise RuntimeError("Verification failed: output duration differs from the input")
    subtitle_codecs = {s.get("codec") for s in details.get("streams", []) if s.get("type") == "subtitle"}
    if not subtitle_codecs <= ALLOWED_SUBTITLES[plan.options.container]: raise RuntimeError("Verification failed: incompatible subtitle codec in output")
    if plan.options.preserve_chapters and source_details.get("chapter_count") and not details.get("chapter_count"):
        raise RuntimeError("Verification failed: chapters were not preserved")
    if plan.options.preserve_metadata and source_details.get("metadata") and not details.get("metadata"):
        raise RuntimeError("Verification failed: metadata was not preserved")
    if plan.artwork_action == "Preserve" and not details.get("thumbnail"):
        raise RuntimeError("Verification failed: artwork was not preserved")
    if plan.options.profile in {"macOS / QuickTime", "Universal"}:
        summary = compatibility_summary(details, plan.options.profile)
        if not summary["verified"]: raise RuntimeError("Verification failed: " + "; ".join(summary["risks"]))
    return details


def convert_local_video(path: str, output_path: str, profile: str | ConversionOptions = "macOS / QuickTime",
                        progress: Callable[[dict[str, object]], None] | None = None,
                        ffmpeg: str | None = None, ffprobe: str | None = None) -> dict[str, object]:
    source = Path(path)
    if not source.is_file(): raise FileNotFoundError("Input media does not exist")
    options = profile if isinstance(profile, ConversionOptions) else preset_options(profile)
    extension = EXTENSIONS[options.container]
    output = Path(output_path).with_suffix(extension)
    if not options.replace_original and source.resolve() == output.resolve():
        raise ValueError("Choose a new output file; enable Replace Original only when intended")
    if progress: progress({"stage": "Analysing", "progress": 5})
    details = inspect_media(str(source), ffprobe=ffprobe)
    executable = ffmpeg or find_binary("ffmpeg")
    if not executable: raise FileNotFoundError("Bundled ffmpeg is unavailable")
    plan = build_conversion_plan(details, options, detect_ffmpeg_encoders(executable))
    if not plan.valid: raise ValueError("Invalid container/codec combination: " + " ".join(plan.errors))
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise OSError("Output path is unavailable") from error
    required = max(int(details.get("size") or 0), plan.estimated_size or 0)
    try: available = shutil.disk_usage(output.parent).free
    except OSError: available = required
    if required and available < required: raise OSError("Insufficient disk space for conversion")
    temporary = output.with_name(f".{output.stem}.convert-{uuid4().hex}{extension}")
    command = _build_command(source, temporary, details, plan, executable)
    if progress: progress({"stage": "Preparing", "progress": 12, "plan": plan.as_dict()})
    started = time.monotonic(); process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    snapshot: dict[str, str] = {}; duration = float(details.get("duration") or 0)
    assert process.stdout is not None
    for raw in process.stdout:
        key, _, value = raw.strip().partition("="); snapshot[key] = value
        if key == "progress" and progress:
            try: media_elapsed = int(snapshot.get("out_time_us") or 0) / 1_000_000
            except ValueError: media_elapsed = 0.0
            fraction = min(1.0, media_elapsed / duration) if duration else 0.0
            elapsed = time.monotonic() - started
            eta = max(0.0, elapsed / fraction - elapsed) if fraction else None
            stages = []
            if plan.video_action == "Convert": stages.append("video")
            if plan.audio_action == "Convert": stages.append("audio")
            if plan.subtitle_action == "Convert": stages.append("subtitles")
            stage = "Converting " + " + ".join(stages) if stages else "Remuxing"
            progress({"stage": stage, "progress": 12 + int(fraction * 78), "elapsed": elapsed,
                      "eta": eta, "fps": snapshot.get("fps") or "", "speed": snapshot.get("speed") or ""})
            snapshot = {}
    stderr = process.stderr.read() if process.stderr else ""; return_code = process.wait()
    try:
        if return_code != 0 or not temporary.is_file():
            raise RuntimeError("Conversion failed. Open Console or View Details for ffmpeg diagnostics. " + stderr[-1200:])
        if progress and (options.preserve_metadata or options.preserve_chapters or options.preserve_artwork):
            progress({"stage": "Writing metadata", "progress": 92})
        if progress: progress({"stage": "Verifying", "progress": 94})
        verified = verify_conversion(str(temporary), details, plan, ffprobe)
        os.replace(temporary, output)
        if options.replace_original and source.resolve() != output.resolve(): source.unlink()
        if progress: progress({"stage": "Completed", "progress": 100})
        video_name = next((name for name, codec in VIDEO_NAMES.items() if codec == plan.resolved_video_codec), plan.resolved_video_codec)
        audio_name = next((name for name, codec in AUDIO_NAMES.items() if codec == plan.resolved_audio_codec), plan.resolved_audio_codec)
        conversions = ([f"Video -> {video_name}" if plan.video_action == "Convert" else "Video copied"] if plan.video_action != "None" else [])
        conversions += ([f"Audio -> {audio_name}" if plan.audio_action == "Convert" else "Audio copied"] if plan.audio_action != "None" else [])
        conversions += [f"Subtitles: {plan.subtitle_action}", f"Container: {options.container}"]
        return {"input": str(source), "output": str(output), "before": details, "after": verified,
                "compatibility": compatibility_summary(verified, options.profile), "plan": plan.as_dict(),
                "conversions": conversions, "final_size": output.stat().st_size, "command": command}
    finally:
        temporary.unlink(missing_ok=True)
