"""Credential-free inspection summaries. Never retain stream/subtitle URLs."""
from __future__ import annotations

import re
import math
from .job_diagnostics import is_playable_format


def format_identifier(value) -> str:
    value = str(value or "")
    return value if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) else ""


def language_code(value) -> str:
    value = str(value or "")
    return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}", value) else ""


def details_from_info(info: dict) -> dict:
    formats = []
    for value in (info.get("formats") or [])[:2000]:
        identity = format_identifier(value.get("format_id"))
        if not identity or not is_playable_format(value): continue
        video = value.get("vcodec") not in (None, "none")
        audio = value.get("acodec") not in (None, "none")
        note = str(value.get("format_note") or "").casefold()
        bitrate = value.get("abr") if not video else value.get("tbr")
        formats.append({"id": identity, "video": video, "audio": audio,
                        "extension": format_identifier(value.get("ext")),
                        "height": value.get("height") if type(value.get("height")) is int else None,
                        "bitrate": bitrate if type(bitrate) in (int, float) and math.isfinite(bitrate) and bitrate >= 0 else None,
                        "video_codec": format_identifier(value.get("vcodec")),
                        "audio_codec": format_identifier(value.get("acodec")),
                        "language": language_code(value.get("language")),
                        # Explicit extractor labels, not a guess from uploader or preference rank.
                        "original": "(original)" in note, "default": "(default)" in note})
    def subtitles(key):
        return sorted(code for code, entries in (info.get(key) or {}).items() if language_code(code) and entries)
    return {"language": language_code(info.get("language")), "formats": formats,
            "manual_subtitles": subtitles("subtitles"), "automatic_subtitles": subtitles("automatic_captions"),
            "formats_truncated": len(info.get("formats") or []) > 2000}
