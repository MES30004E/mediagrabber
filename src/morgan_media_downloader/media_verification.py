from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from .paths import find_binary


THUMBNAIL_CONTAINERS = {".mp3", ".m4a", ".mp4", ".mkv"}


def _has_faststart(path: str) -> bool:
    try:
        with open(path, "rb") as stream: data = stream.read(4 * 1024 * 1024)
        moov, mdat = data.find(b"moov"), data.find(b"mdat")
        return moov >= 0 and mdat >= 0 and moov < mdat
    except OSError:
        return False


def _mutagen_has_artwork(path: str) -> bool:
    try:
        from mutagen import File
        media = File(path)
        tags = getattr(media, "tags", None)
        if not tags: return False
        if "covr" in tags and tags["covr"]: return True
        return any(str(key).startswith("APIC") for key in tags.keys())
    except Exception:
        return False


def inspect_media(path: str, ffprobe: str | None = None,
                  runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict[str, object]:
    executable = ffprobe or find_binary("ffprobe")
    if not executable:
        raise FileNotFoundError("Bundled ffprobe is unavailable")
    result = runner(
        [executable, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", "-show_chapters", path],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("ffprobe could not inspect the completed media")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    video = [stream for stream in streams if stream.get("codec_type") == "video"
             and not (stream.get("disposition") or {}).get("attached_pic")]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    subtitles = [stream for stream in streams if stream.get("codec_type") == "subtitle"]
    artwork = [stream for stream in streams if (stream.get("disposition") or {}).get("attached_pic")
               or stream.get("codec_type") == "attachment"]
    tags = (payload.get("format") or {}).get("tags") or {}
    subtitle_labels = []
    subtitle_streams = []
    for stream in subtitles:
        language = (stream.get("tags") or {}).get("language") or "und"
        title = (stream.get("tags") or {}).get("title")
        codec = stream.get("codec_name") or "unknown"
        subtitle_labels.append(f"{language}{' - ' + title if title else ''} • {codec}")
        subtitle_streams.append({"language": language, "title": title or "", "codec": codec})
    def stream_details(stream):
        disposition = stream.get("disposition") or {}
        return {
            "index": int(stream.get("index") or 0),
            "type": stream.get("codec_type") or "unknown",
            "codec": stream.get("codec_name") or "unknown",
            "tag": stream.get("codec_tag_string") or "",
            "profile": stream.get("profile") or "",
            "pix_fmt": stream.get("pix_fmt") or "",
            "sample_fmt": stream.get("sample_fmt") or "",
            "sample_rate": stream.get("sample_rate") or "",
            "channels": int(stream.get("channels") or 0),
            "channel_layout": stream.get("channel_layout") or "",
            "width": int(stream.get("width") or 0),
            "height": int(stream.get("height") or 0),
            "frame_rate": stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "",
            "bit_rate": int(stream.get("bit_rate") or 0),
            "tags": stream.get("tags") or {},
            "attached_pic": bool(disposition.get("attached_pic")),
            "disposition": disposition,
        }
    format_name = str((payload.get("format") or {}).get("format_name") or "")
    try: duration = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError): duration = 0.0
    format_payload = payload.get("format") or {}
    return {
        "video": bool(video), "audio": bool(audio), "subtitle_count": len(subtitles),
        "subtitles": subtitle_labels, "subtitle_streams": subtitle_streams,
        "thumbnail": bool(artwork) or _mutagen_has_artwork(path), "metadata": bool(tags),
        "format_name": format_name,
        "duration": duration,
        "size": int(format_payload.get("size") or 0),
        "bit_rate": int(format_payload.get("bit_rate") or 0),
        "tags": tags,
        "chapters": payload.get("chapters") or [],
        "chapter_count": len(payload.get("chapters") or []),
        "faststart": _has_faststart(path) if Path(path).suffix.casefold() in {".mp4", ".m4a", ".mov", ".m4v"} else None,
        "streams": [stream_details(stream) for stream in streams],
        "video_count": len(video), "audio_count": len(audio), "artwork_count": len(artwork),
    }


def verify_requested_postprocessing(path: str, *, embed_thumbnail: bool, embed_subtitles: bool,
                                    ffprobe: str | None = None,
                                    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
                                    ) -> tuple[dict[str, object], list[str]]:
    details = inspect_media(path, ffprobe, runner)
    warnings: list[str] = []
    suffix = Path(path).suffix.casefold()
    if embed_thumbnail and suffix not in THUMBNAIL_CONTAINERS:
        warnings.append("Media downloaded successfully, but thumbnail embedding was not supported for this format.")
        details["thumbnail"] = "Unsupported"
    elif embed_thumbnail and not details["thumbnail"]:
        warnings.append("Media downloaded successfully, but embedded thumbnail verification failed.")
    if embed_subtitles and not details["subtitle_count"]:
        warnings.append("No subtitles were available for the selected language.")
    return details, warnings
