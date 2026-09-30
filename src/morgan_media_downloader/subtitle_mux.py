from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .media_verification import inspect_media
from .paths import find_binary


LANGUAGE_MAP = {"en": "eng", "zh": "zho", "zh-Hans": "zho", "zh-Hant": "zho", "ja": "jpn",
                "de": "deu", "fr": "fra", "es": "spa", "it": "ita", "ko": "kor", "pt": "por"}
LANGUAGE_NAMES = {"en": "English", "eng": "English", "zh": "Chinese", "zh-Hans": "Chinese (Simplified)",
                  "zh-Hant": "Chinese (Traditional)", "zho": "Chinese", "ja": "Japanese", "jpn": "Japanese",
                  "de": "German", "fr": "French", "es": "Spanish", "ko": "Korean", "pt": "Portuguese"}


def friendly_language(code: str) -> str:
    return f"{LANGUAGE_NAMES.get(code, code)} ({code})"


def parse_subtitle_languages(value: str) -> list[str]:
    return list(dict.fromkeys(part.strip() for part in (value or "en").split(",") if part.strip())) or ["en"]


def subtitle_download_flags(source: str) -> tuple[bool, bool]:
    return source != "Automatic captions only", source in {"Normal + automatic captions", "Automatic captions only"}


def subtitle_codec_for(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    if suffix in {".mp4", ".m4a", ".mov", ".m4v"}: return "mov_text"
    if suffix in {".mkv", ".mka"}: return "srt"
    if suffix == ".webm": return "webvtt"
    raise ValueError(f"Subtitle embedding is not supported for {suffix or 'this output format'}")


def mux_subtitles_atomically(media_path: str, tracks: list[dict[str, Any]], *, ffmpeg: str | None = None,
                             ffprobe: str | None = None,
                             runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict[str, Any]:
    """Mux sidecars, verify the temporary output, then atomically replace media."""
    media = Path(media_path)
    existing = [track for track in tracks if Path(str(track.get("filepath") or "")).is_file()]
    if not existing: raise FileNotFoundError("No downloaded subtitle sidecar was available for embedding")
    executable = ffmpeg or find_binary("ffmpeg")
    if not executable: raise FileNotFoundError("Bundled ffmpeg is unavailable")
    codec = subtitle_codec_for(media_path)
    temporary = media.with_name(f".{media.stem}.subtitle-mux-{uuid4().hex}{media.suffix}")
    command = [executable, "-hide_banner", "-loglevel", "error", "-y", "-i", str(media)]
    for track in existing: command.extend(["-i", str(track["filepath"])])
    # Map only playable streams. Some MP4 metadata atoms are exposed by ffmpeg
    # as generic data tracks (for example gpmd/text); copying those tracks can
    # trigger QuickTime's incompatible-media warning.
    command.extend(["-map", "0:v", "-map", "0:a?", "-map_metadata", "0", "-map_chapters", "0",
                    "-c:v", "copy", "-c:a", "copy"])
    # Add each requested sidecar as a selectable subtitle stream.
    for index, track in enumerate(existing, 1):
        command.extend(["-map", f"{index}:0"])
    command.extend(["-c:s", codec])
    for index, track in enumerate(existing):
        language = str(track.get("language") or "und")
        command.extend([f"-metadata:s:s:{index}", f"language={LANGUAGE_MAP.get(language, language)}"])
        if track.get("name"):
            command.extend([f"-metadata:s:s:{index}", f"title={track['name']}"])
    if media.suffix.casefold() in {".mp4", ".m4a", ".mov", ".m4v"}:
        command.extend(["-movflags", "+faststart"])
    command.append(str(temporary))
    try:
        result = runner(command, capture_output=True, text=True, timeout=300, check=False)
        if result.returncode != 0 or not temporary.is_file():
            raise RuntimeError("ffmpeg could not mux the requested subtitle stream")
        verification = inspect_media(str(temporary), ffprobe=ffprobe, runner=runner)
        if int(verification.get("subtitle_count") or 0) < len(existing):
            raise RuntimeError("ffprobe did not verify every requested subtitle stream")
        os.replace(temporary, media)
        return {"embedded": True, "verified": True, "codec": codec,
                "count": len(existing), "languages": [track.get("language") or "und" for track in existing],
                "conversion": [f"{Path(str(track['filepath'])).suffix.lstrip('.').upper()} -> {codec}" for track in existing]}
    finally:
        temporary.unlink(missing_ok=True)
