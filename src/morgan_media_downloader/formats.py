from __future__ import annotations

from typing import Any

from .auth import authentication_options
from .job_diagnostics import is_playable_format
from .subtitle_mux import parse_subtitle_languages, subtitle_download_flags
from .media_details import format_identifier

VIDEO_HEIGHTS = {"2160p": 2160, "1440p": 1440, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}


def format_selector(quality: str, audio_format: str,
                    compatibility: str = "Original / Best Available") -> str:
    if audio_format != "Original/best audio":
        return "bestaudio/best"
    limit = f"[height<={VIDEO_HEIGHTS[quality]}]" if quality in VIDEO_HEIGHTS else ""
    if compatibility in {"macOS / QuickTime", "Universal"}:
        return (f"bestvideo[ext=mp4][vcodec^=avc1]{limit}+bestaudio[ext=m4a][acodec^=mp4a]/"
                f"best[ext=mp4][vcodec^=avc1][acodec^=mp4a]{limit}/"
                f"bestvideo{limit}+bestaudio/best{limit}/best")
    if quality in VIDEO_HEIGHTS:
        height = VIDEO_HEIGHTS[quality]
        return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
    return "bestvideo+bestaudio/best"


def _codec(value: object) -> str:
    return str(value or "").casefold()


def _quicktime_video(entry: dict[str, Any]) -> bool:
    audio = _codec(entry.get("acodec"))
    audio_ok = not audio or audio == "none" or audio == "aac" or audio.startswith("mp4a")
    return (entry.get("ext") == "mp4"
            and _codec(entry.get("vcodec")).startswith(("avc1", "h264")) and audio_ok)


def _quicktime_audio(entry: dict[str, Any]) -> bool:
    codec = _codec(entry.get("acodec"))
    return entry.get("ext") in {"m4a", "mp4"} and (codec.startswith("mp4a") or codec == "aac")


def _exact_id(entry: dict[str, Any]) -> str:
    identity = str(entry["format_id"])
    if format_identifier(identity) != identity: raise ValueError("Unsupported format identifier; inspect available streams again.")
    # The star permits video-only/audio-only formats; bare 'best' requires both.
    # Exact filters also prevent IDs like 'all' or 'mp4' becoming selector grammar.
    return f'best*[format_id="{identity}"]'


def resolve_available_format(formats: list[dict[str, Any]], quality: str, container: str,
                             audio_format: str,
                             compatibility: str = "Original / Best Available", *,
                             video_format_id: str = "", audio_format_id: str = "") -> tuple[str, list[str]]:
    """Resolve concrete format IDs from formats that extraction actually returned."""
    usable = [entry for entry in formats if entry.get("format_id") and is_playable_format(entry)]
    if not usable:
        raise ValueError("No compatible format was found with the current settings.")
    for label, identity, codec in (("video", video_format_id, "vcodec"), ("audio", audio_format_id, "acodec")):
        if identity and (format_identifier(identity) != identity or not any(
                str(entry["format_id"]) == identity and entry.get(codec) not in (None, "none") for entry in usable)):
            raise ValueError(f"The selected {label} stream is no longer available. Inspect the video again.")
    if video_format_id and audio_format != "Original/best audio":
        raise ValueError("A selected video stream cannot be used with audio-only conversion; clear the video override.")
    if audio_format_id:
        audio_choice = next(entry for entry in usable if str(entry["format_id"]) == audio_format_id)
        if audio_choice.get("vcodec") not in (None, "none"):
            raise ValueError("The selected audio override must be an audio-only stream.")
        if video_format_id and any(str(entry["format_id"]) == video_format_id and entry.get("acodec") not in (None, "none") for entry in usable):
            raise ValueError("Choose a video-only stream when overriding its audio track.")
        usable = [entry for entry in usable if str(entry["format_id"]) == audio_format_id or (
            entry.get("vcodec") not in (None, "none") and entry.get("acodec") in (None, "none"))]
    warnings: list[str] = []
    if audio_format != "Original/best audio":
        audio = [entry for entry in usable if entry.get("acodec") not in (None, "none")]
        if not audio:
            raise ValueError("No compatible audio format was found with the current settings.")
        best = max(audio, key=lambda entry: (float(entry.get("abr") or 0), float(entry.get("tbr") or 0)))
        return _exact_id(best), warnings

    limit = None if video_format_id else VIDEO_HEIGHTS.get(quality)
    videos = [entry for entry in usable if entry.get("vcodec") not in (None, "none")
              or (entry.get("vcodec") is None and entry.get("acodec") is None)]
    if video_format_id: videos = [entry for entry in videos if str(entry["format_id"]) == video_format_id]
    if limit is not None:
        within = [entry for entry in videos if int(entry.get("height") or 0) <= limit]
        if within:
            videos = within
            actual = max(int(entry.get("height") or 0) for entry in videos)
            if actual and actual < limit:
                warnings.append(f"{quality} unavailable. Using {actual}p.")
    if not videos:
        raise ValueError("No compatible video format was found with the current settings.")
    quicktime = compatibility in {"macOS / QuickTime", "Universal"}
    preferred_ext = "mp4" if quicktime else (container.casefold() if container != "Auto" else "")
    preferred = [entry for entry in videos if entry.get("ext") == preferred_ext] if preferred_ext else []
    compatible_video = [entry for entry in videos if _quicktime_video(entry)] if quicktime else []
    pool = compatible_video or preferred or videos
    if preferred_ext and not preferred:
        label = "MP4" if quicktime else container
        warnings.append(f"{label} streams were unavailable. Using the best available streams and converting when required.")
    best_video = max(pool, key=lambda entry: (
        int(entry.get("height") or 0), float(entry.get("fps") or 0), float(entry.get("tbr") or 0)))
    if best_video.get("vcodec") is None and best_video.get("acodec") is None:
        return _exact_id(best_video), warnings
    if best_video.get("acodec") not in (None, "none"):
        return _exact_id(best_video), warnings
    audios = [entry for entry in usable if entry.get("vcodec") in (None, "none")
              and entry.get("acodec") not in (None, "none")]
    if not audios:
        progressive = [entry for entry in videos if entry.get("acodec") not in (None, "none")]
        if progressive:
            return _exact_id(max(progressive, key=lambda entry: float(entry.get("tbr") or 0))), warnings
        raise ValueError("No compatible audio stream was found with the selected video.")
    compatible_audio = [entry for entry in audios if _quicktime_audio(entry)] if quicktime else []
    preferred_audio = [entry for entry in audios if entry.get("ext") in ({"m4a"} if preferred_ext == "mp4" else {preferred_ext})]
    best_audio = max(compatible_audio or preferred_audio or audios,
                     key=lambda entry: (float(entry.get("abr") or 0), float(entry.get("tbr") or 0)))
    return f"{_exact_id(best_video)}+{_exact_id(best_audio)}", warnings


def build_ydl_options(options: Any, proxy: str | None = None, *, include_subtitles: bool = True,
                      include_authentication: bool = True) -> dict[str, Any]:
    languages = parse_subtitle_languages(options.subtitle_language)
    normal_subtitles, automatic_subtitles = subtitle_download_flags(
        getattr(options, "subtitle_source", "Normal subtitles"))
    want_subtitles = bool(options.embed_subtitles or options.write_subtitles) and include_subtitles
    postprocessors: list[dict[str, Any]] = []
    output = {
        "format": format_selector(options.quality, options.audio_format,
                                  getattr(options, "compatibility", "macOS / QuickTime")),
        "outtmpl": str(__import__("pathlib").Path(options.download_dir) / options.filename_template),
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "retry_sleep_functions": {"http": lambda n: min(2 ** n, 8), "fragment": lambda n: min(2 ** n, 8)},
        "writethumbnail": options.embed_thumbnail,
        "embedthumbnail": options.embed_thumbnail,
        "addmetadata": options.embed_metadata,
        "embedchapters": options.embed_chapters,
        "writesubtitles": bool(want_subtitles and normal_subtitles),
        "writeautomaticsub": bool(want_subtitles and automatic_subtitles),
        "subtitleslangs": languages or ["en"],
        "keep_subs": bool(options.write_subtitles),
        "keepvideo": options.keep_original,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
    }
    if proxy:
        output["proxy"] = proxy
    if include_authentication:
        output.update(authentication_options(
            getattr(options, "authentication_mode", "Auto"),
            getattr(options, "cookies_browser", "Chrome"),
            getattr(options, "browser_profile", ""),
            getattr(options, "cookies_file", ""),
        ))
    compatibility = getattr(options, "compatibility", "macOS / QuickTime")
    if options.audio_format == "Original/best audio":
        if compatibility in {"macOS / QuickTime", "Universal"}:
            output["merge_output_format"] = "mp4"
        elif options.container != "Auto":
            output["merge_output_format"] = options.container.lower()
    if options.audio_format != "Original/best audio":
        codec = options.audio_format.lower()
        postprocessor = {"key": "FFmpegExtractAudio", "preferredcodec": codec}
        if options.audio_bitrate != "Auto":
            postprocessor["preferredquality"] = options.audio_bitrate.split()[0]
        postprocessors.append(postprocessor)
    if options.embed_metadata or options.embed_chapters:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": bool(options.embed_metadata),
                               "add_chapters": bool(options.embed_chapters)})
    if options.embed_subtitles and include_subtitles:
        postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": bool(options.write_subtitles)})
    if options.embed_thumbnail:
        postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    if postprocessors:
        output["postprocessors"] = postprocessors
    return output
