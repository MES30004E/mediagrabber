from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .auth import (authentication_options, configured_authentication_options,
                   normalise_authentication_mode, requires_authentication, fresh_authentication_options)
from .compatibility import (COMPATIBLE_PROFILES, compatibility_summary,
                            ensure_compatible_output)
from .file_ownership import classify_job_file, record_job_file
from .formats import build_ydl_options, resolve_available_format
from .job_diagnostics import (apply_failure, playable_formats, safe_format_summary,
                              safe_request_stage)
from .logging_setup import redact_secrets
from .media_verification import verify_requested_postprocessing
from .models import DownloadJob, JobStatus, MediaItem
from .media_details import details_from_info
from .network import classify_tor_target
from .parsing import as_yt_dlp_target, ensure_output_directory, input_kind, is_watch_later
from .paths import find_binary
from .provider import provider_extractor_args, yt_dlp_javascript_options
from .spotify import fetch_public_metadata, match_confidence
from .subtitle_mux import mux_subtitles_atomically, parse_subtitle_languages, subtitle_download_flags
from .yt_runtime import RuntimeSnapshot

LOGGER = logging.getLogger(__name__)


class DownloadInterrupted(Exception):
    pass


def configure_provider_plugin() -> None:
    frozen_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    candidates = [
        frozen_root / "provider_plugin",
        Path.cwd() / "bgutil-ytdlp-pot-provider" / "plugin",
        Path(__file__).resolve().parents[2] / "bgutil-ytdlp-pot-provider" / "plugin",
    ]
    for candidate in candidates:
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def _ydl_class(runtime: RuntimeSnapshot | None = None):
    if runtime is not None:
        return runtime.youtube_dl
    configure_provider_plugin()
    from yt_dlp import YoutubeDL
    return YoutubeDL


def _media_from_info(info: dict[str, Any], original: str, confidence: float | None = None,
                     collection_title: str = "", collection_type: str = "") -> MediaItem:
    return MediaItem(
        source_url=info.get("webpage_url") or info.get("original_url") or info.get("url") or original,
        title=info.get("title") or "Untitled",
        uploader=info.get("uploader") or info.get("channel") or info.get("artist") or "",
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail") or "",
        source=info.get("extractor_key") or info.get("extractor") or "",
        playlist_index=info.get("playlist_index"),
        confidence=confidence,
        original_url=original,
        collection_title=collection_title,
        collection_type=collection_type,
        available_subtitles=sorted((info.get("subtitles") or {}).keys()),
        automatic_captions=sorted((info.get("automatic_captions") or {}).keys()),
        thumbnail_headers={key: str(value) for key, value in (info.get("http_headers") or {}).items()
                           if key.casefold() in {"user-agent", "referer", "origin", "accept", "accept-language"}},
        inspection=details_from_info(info) if "formats" in info else {},
    )


def analyse_target(value: str, proxy: str | None = None, provider_url: str = "http://127.0.0.1:4416",
                   provider_home: str = "", auth_options: dict[str, Any] | None = None,
                   runtime: RuntimeSnapshot | None = None, *, single_video: bool = False) -> list[MediaItem]:
    ydl_class = _ydl_class(runtime) if runtime is not None else _ydl_class()
    common = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "proxy": proxy,
        "extractor_args": provider_extractor_args(provider_url, provider_home),
    }
    common.update(fresh_authentication_options(auth_options or {}))
    common.update(yt_dlp_javascript_options())
    if single_video: common.update(noplaylist=True, extract_flat=False, socket_timeout=20, extractor_retries=1)
    if input_kind(value) == "spotify":
        results: list[MediaItem] = []
        with ydl_class(common) as ydl:
            for metadata in fetch_public_metadata(value, opener=ydl.urlopen):
                found = ydl.extract_info(f"ytsearch10:{metadata.search_query}", download=False)
                entries = (found or {}).get("entries") or []
                for entry in entries:
                    if entry:
                        results.append(_media_from_info(entry, value, match_confidence(metadata, entry)))
        return sorted(results, key=lambda item: item.confidence or 0, reverse=True)
    with ydl_class(common) as ydl:
        info = ydl.extract_info(as_yt_dlp_target(value), download=False)
    entries = (info or {}).get("entries")
    if single_video and entries is not None:
        raise ValueError("Inspect an individual video, not a playlist or search result.")
    if single_video and info and "formats" not in info:
        info = dict(info, formats=[info] if info.get("format_id") else [])
    if entries is not None:
        collection_title = str((info or {}).get("title") or (info or {}).get("playlist_title") or "")
        return [_media_from_info(entry, value, collection_title=collection_title, collection_type="Playlist")
                for entry in entries if entry]
    return [_media_from_info(info, value)] if info else []


def analyse_with_authentication(value: str, proxy: str | None, provider_url: str, provider_home: str,
                                mode: str, browser: str, profile: str, cookies_file: str,
                                runtime: RuntimeSnapshot | None = None,
                                status: Callable[[str], None] | None = None, *, single_video: bool = False) -> tuple[list[MediaItem], str]:
    def analyse(auth):
        return analyse_target(value, proxy, provider_url, provider_home, auth, runtime,
                              **({"single_video": True} if single_video else {}))
    mode = normalise_authentication_mode(mode)
    if mode == "Auto":
        if is_watch_later(value):
            configured_name, configured = configured_authentication_options(browser, profile, "")
            return analyse(configured), f"Auto -> {configured_name}"
        try:
            return analyse({}), "Auto -> None"
        except BaseException as error:
            if not requires_authentication(error):
                raise
            # Auto's fallback is the configured browser profile. A stale hidden
            # cookies.txt path only applies when Imported cookies.txt is selected.
            configured_name, configured = configured_authentication_options(browser, profile, "")
            if status: status(f"Authentication required. Retrying with {configured_name}…")
            return analyse(configured), f"Auto -> {configured_name}"
    selected = authentication_options(mode, browser, profile, cookies_file)
    # Explicit authentication is an attempt invariant. Format/player failures
    # must not turn a selected account into an unauthenticated request.
    return analyse(selected), mode


def friendly_error(error: BaseException) -> str:
    from .job_diagnostics import classify_failure
    return str(classify_failure(error)["friendly"])


def _activate_resolved_format(ydl, selector: str):
    # YoutubeDL compiles this at construction; changing params alone does not
    # change process_ie_result's selector (including after a 403 refresh).
    if hasattr(ydl, "build_format_selector"):
        ydl.format_selector = ydl.build_format_selector(selector)
    ydl.params["format"] = selector


def download_job(job: DownloadJob, proxy: str | None, provider_url: str, provider_home: str,
                 progress: Callable[[DownloadJob], None], stop_event: threading.Event,
                 runtime: RuntimeSnapshot | None = None,
                 console: Callable[[str, str, str], None] | None = None,
                 tor_circuit: Callable[[DownloadJob, int], dict[str, Any]] | None = None) -> DownloadJob:
    ensure_output_directory(job.options.download_dir)

    def transition(status: JobStatus, stage: str, *, extractor=False, transfer=False, postprocess=False) -> None:
        now = time.time(); job.status = status; job.postprocessing_stage = stage
        job.active_extractor_task = extractor; job.active_transfer_task = transfer
        job.active_postprocess_task = postprocess; job.last_state_transition = now
        job.last_progress_timestamp = now

    def emit(category: str, message: str, level: str = "info") -> None:
        if console: console(category, redact_secrets(message), level)

    def hook(data: dict[str, Any]) -> None:
        if stop_event.is_set():
            raise DownloadInterrupted("Download paused or cancelled")
        status = data.get("status")
        if status == "downloading":
            if not job.active_transfer_task: transition(JobStatus.DOWNLOADING, "Downloading", transfer=True)
            info = data.get("info_dict") or {}
            if info.get("vcodec") in (None, "none") and info.get("acodec") not in (None, "none"):
                job.postprocessing_stage = "Downloading audio"
                job.failure_stage = "Audio transfer"
            elif info.get("acodec") in (None, "none") and info.get("vcodec") not in (None, "none"):
                job.postprocessing_stage = "Downloading video"
                job.failure_stage = "Video transfer"
            else:
                job.postprocessing_stage = "Downloading"
            job.technical_details = job.postprocessing_stage
            job.downloaded_bytes = int(data.get("downloaded_bytes") or 0)
            if job.downloaded_bytes: job.last_bytes_timestamp = time.time()
            job.last_progress_timestamp = time.time()
            job.total_bytes = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            job.progress = (job.downloaded_bytes / job.total_bytes * 100) if job.total_bytes else 0.0
            job.speed = float(data.get("speed") or 0)
            job.eta = data.get("eta")
            job.fragment_index = data.get("fragment_index")
            job.fragment_count = data.get("fragment_count")
            job.output_file = data.get("filename") or job.output_file
            if data.get("filename"): classify_job_file(job, data["filename"])
            if data.get("tmpfilename"): classify_job_file(job, data["tmpfilename"])
            emit("DOWNLOAD", f"{job.postprocessing_stage} • {job.progress:.1f}%")
        elif status == "finished":
            transition(JobStatus.CONVERTING, "Preparing media", postprocess=True)
            job.progress = 100.0
            job.output_file = data.get("filename") or job.output_file
            if data.get("filename"): classify_job_file(job, data["filename"])
        progress(job)

    def post_hook(data: dict[str, Any]) -> None:
        if not job.active_postprocess_task: transition(JobStatus.CONVERTING, "Post-processing", postprocess=True)
        processor = str(data.get("postprocessor") or "media")
        labels = {
            "FFmpegMerger": "Merging video + audio",
            "Merger": "Merging video + audio",
            "FFmpegExtractAudio": "Converting audio",
            "ExtractAudio": "Converting audio",
            "FFmpegMetadata": "Writing metadata",
            "Metadata": "Writing metadata",
            "EmbedThumbnail": "Embedding thumbnail",
            "FFmpegEmbedSubtitle": "Embedding subtitles",
            "EmbedSubtitle": "Embedding subtitles",
            "FFmpegSubtitlesConvertor": "Converting subtitles",
            "SubtitlesConvertor": "Converting subtitles",
            "FFmpegThumbnailsConvertor": "Downloading thumbnail",
            "ThumbnailsConvertor": "Downloading thumbnail",
            "MoveFiles": "Finalising output",
        }
        job.postprocessing_stage = labels.get(processor, f"Post-processing: {processor}")
        job.failure_stage = {
            "FFmpegMerger": "Merge", "Merger": "Merge", "FFmpegExtractAudio": "Conversion",
            "ExtractAudio": "Conversion", "FFmpegMetadata": "Metadata writing", "Metadata": "Metadata writing",
            "EmbedThumbnail": "Thumbnail embedding", "FFmpegThumbnailsConvertor": "Thumbnail transfer",
        }.get(processor, job.failure_stage)
        job.technical_details = job.postprocessing_stage
        info = data.get("info_dict") or {}
        if info.get("filepath"): classify_job_file(job, info["filepath"])
        emit("FFMPEG" if processor.startswith("FFmpeg") or processor in {"Merger", "Metadata"} else "APP",
             job.postprocessing_stage)
        progress(job)

    def completed_file(filename: str) -> None:
        record_job_file(job, filename, "final")
        job.output_file = filename

    class _YdlLogger:
        @staticmethod
        def _retry(message):
            if match := re.search(r"Retrying\s*(?:\(|)(\d+)/(\d+)", str(message), re.I):
                job.retry_count = max(job.retry_count, int(match.group(1)))
                job.postprocessing_stage = f"Retrying {match.group(1)}/{match.group(2)}"
                progress(job)
        def debug(self, message):
            if str(message).startswith("[debug]"): return
            self._retry(message)
            emit("YT-DLP", str(message))
        def info(self, message): self._retry(message); emit("YT-DLP", str(message))
        def warning(self, message): self._retry(message); emit("YT-DLP", str(message), "warning")
        def error(self, message): emit("YT-DLP", str(message), "error")

    def run_attempt(auth_name: str, auth_values: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        job.metadata_success = False
        job.formats_total = job.formats_playable = 0
        job.playable_format_summary = []
        # Subtitles are acquired in a separate optional pass after a valid media
        # output exists, so subtitle failures can never destroy or block media.
        ydl_options = build_ydl_options(job.options, proxy, include_subtitles=False, include_authentication=False)
        metadata_selector = ydl_options["format"]  # YoutubeDL may retain and mutate this options dictionary.
        ydl_options.pop("cookiesfrombrowser", None); ydl_options.pop("cookiefile", None)
        ydl_options.update(fresh_authentication_options(auth_values))
        ydl_options.update(yt_dlp_javascript_options())
        ydl_options.update({
            "progress_hooks": [hook], "postprocessor_hooks": [post_hook],
            "post_hooks": [completed_file],
            "extractor_args": provider_extractor_args(provider_url, provider_home),
            "logger": _YdlLogger(),
        })
        if ffmpeg := find_binary("ffmpeg"):
            ydl_options["ffmpeg_location"] = str(Path(ffmpeg).parent)
        job.effective_authentication = auth_name
        job.technical_details = f"Authentication: {auth_name}"
        progress(job)
        ydl_class = _ydl_class(runtime) if runtime is not None else _ydl_class()
        with ydl_class(ydl_options) as ydl:
            transition(JobStatus.ANALYSING, "Resolving media", extractor=True)
            job.failure_stage = "Analysis"
            emit("APP", "Starting media analysis")
            info = ydl.extract_info(job.item.source_url, download=False)
            if not info:
                raise ValueError("No compatible format was found with the current settings.")
            job.metadata_success = True
            job.extractor_key = str(info.get("extractor_key") or job.item.source or "")
            job.extractor_name = str(info.get("extractor") or job.extractor_key)
            all_formats = list(info.get("formats") or [])
            playable = playable_formats(info)
            job.formats_total = len(all_formats) if all_formats else 1
            job.formats_playable = len(playable)
            job.playable_format_summary = safe_format_summary(playable)
            emit("YT-DLP", f"Extractor: {job.extractor_key or 'Unknown'}")
            emit("YT-DLP", f"{job.formats_playable} playable format(s) found")
            job.failure_stage = "Format resolution"
            selected_streams = {key: getattr(job.options, key) for key in ("video_format_id", "audio_format_id")
                                if getattr(job.options, key, "")}
            try:
                selector, format_warnings = resolve_available_format(
                    playable, job.options.quality, job.options.container, job.options.audio_format,
                    job.options.compatibility, **selected_streams)
            except ValueError as error:
                availability = str(info.get("availability") or info.get("live_status") or "").casefold()
                if any(term in availability for term in ("private", "needs_auth", "premium", "subscriber", "members")):
                    raise RuntimeError(f"Authentication required: {error}") from None
                raise RuntimeError(f"Requested format is not available: {error}") from None
            job.warnings.extend(warning for warning in format_warnings if warning not in job.warnings)
            _activate_resolved_format(ydl, selector)
            job.active_extractor_task = False; job.active_transfer_task = True
            job.last_state_transition = time.time(); job.postprocessing_stage = "Starting transfer"
            progress(job)
            job.failure_stage = "Video transfer"
            try:
                result = (ydl.process_ie_result(info, download=True) if hasattr(ydl, "process_ie_result")
                          else ydl.extract_info(job.item.source_url, download=True))
            except BaseException as transfer_error:
                if "403" not in str(transfer_error).casefold(): raise
                # Signed media URLs and manifests can expire between analysis and
                # transfer. Re-extract once, then stop with the classified error.
                job.retry_count += 1
                job.postprocessing_stage = "Retrying after HTTP 403"
                progress(job)
                emit("DOWNLOAD", "HTTP 403 received; refreshing media information and retrying once", "warning")
                job.failure_stage = "Metadata refresh"
                job.metadata_success = False
                job.formats_total = job.formats_playable = 0
                job.playable_format_summary = []
                # Re-extraction must not be filtered by expired concrete IDs.
                # Obtain fresh metadata using the batch selector, then validate
                # explicit per-item choices against those fresh formats below.
                _activate_resolved_format(ydl, metadata_selector)
                refreshed = ydl.extract_info(job.item.source_url, download=False)
                if not refreshed: raise ValueError("No compatible format was found while refreshing media metadata.")
                job.metadata_success = True
                refreshed_playable = playable_formats(refreshed or {})
                job.formats_total = len((refreshed or {}).get("formats") or []) or 1
                job.formats_playable = len(refreshed_playable)
                job.playable_format_summary = safe_format_summary(refreshed_playable)
                job.failure_stage = "Format resolution"
                refreshed_selector, refreshed_warnings = resolve_available_format(
                    refreshed_playable, job.options.quality, job.options.container, job.options.audio_format,
                    job.options.compatibility, **selected_streams)
                job.warnings.extend(w for w in refreshed_warnings if w not in job.warnings)
                _activate_resolved_format(ydl, refreshed_selector)
                job.failure_stage = "Video transfer"
                result = (ydl.process_ie_result(refreshed, download=True) if hasattr(ydl, "process_ie_result")
                          else ydl.extract_info(job.item.source_url, download=True))
            return result or info, ydl

    def run_with_tor_retries(auth_name: str, auth_values: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        attempt = 0
        while True:
            try:
                return run_attempt(auth_name, auth_values)
            except BaseException as error:
                state, message = classify_tor_target("internet_working", error)
                if not tor_circuit or state != "target_rejected" or attempt >= job.tor_circuit_retry_limit:
                    if state == "cloudflare_edge_restriction":
                        job.failure_code = "Cloudflare edge restriction"; job.tor_target_result = "Cloudflare Error 1034"
                    elif tor_circuit and state == "target_rejected":
                        job.failure_code = "Target rejected Tor"; job.tor_target_result = "Rejected"
                        raise RuntimeError("Tor is working, but this website continues to reject the current Tor routes.") from error
                    raise
                attempt += 1; job.tor_circuit_retry = attempt; job.tor_target_result = str(error)
                transition(JobStatus.ANALYSING, "Changing Tor circuit", extractor=False)
                emit("TOR", f"Target rejected route; requesting NEWNYM — retry {attempt}/{job.tor_circuit_retry_limit}", "warning")
                progress(job)
                result = tor_circuit(job, attempt)
                job.tor_previous_exit_ip = str(result.get("previous_exit_ip") or "")
                job.tor_current_exit_ip = str(result.get("current_exit_ip") or "")
                job.tor_circuit_changed = result.get("changed") if isinstance(result.get("changed"), bool) else None
                job.tor_last_circuit_change = str(result.get("last_circuit_change") or "")
                emit("TOR", f"New exit: {job.tor_current_exit_ip or 'Unknown'}; changed: "
                     f"{'Yes' if job.tor_circuit_changed else 'No' if job.tor_circuit_changed is False else 'Unknown'}")
                transition(JobStatus.ANALYSING, "Retrying extraction", extractor=True)
                emit("TOR", "Re-running extraction from the original URL")
                progress(job)

    def acquire_and_embed_subtitles(auth_values: dict[str, Any]) -> None:
        if not (job.options.embed_subtitles or job.options.write_subtitles): return
        languages = parse_subtitle_languages(job.options.subtitle_language)
        normal, automatic = subtitle_download_flags(job.options.subtitle_source)
        job.subtitle_details = {"requested": languages, "source": job.options.subtitle_source,
                                "downloaded": False, "embedded": False, "verified": False}
        job.failure_stage = "Subtitle transfer"; job.postprocessing_stage = "Downloading subtitles"
        emit("SUBTITLE", f"Requesting subtitle language(s): {', '.join(languages)}"); progress(job)
        subtitle_options = build_ydl_options(job.options, proxy, include_subtitles=False, include_authentication=False)
        subtitle_options.update({"skip_download": True, "writesubtitles": normal,
                                 "writeautomaticsub": automatic, "subtitleslangs": languages,
                                 "writethumbnail": False, "postprocessors": [], "logger": _YdlLogger(),
                                 "extractor_args": provider_extractor_args(provider_url, provider_home)})
        subtitle_options.pop("format", None)
        subtitle_options.pop("embedthumbnail", None)
        subtitle_options.pop("cookiesfrombrowser", None); subtitle_options.pop("cookiefile", None)
        subtitle_options.update(fresh_authentication_options(auth_values))
        subtitle_options.update(yt_dlp_javascript_options())
        if ffmpeg := find_binary("ffmpeg"):
            subtitle_options["ffmpeg_location"] = str(Path(ffmpeg).parent)
        ydl_class = _ydl_class(runtime) if runtime is not None else _ydl_class()
        with ydl_class(subtitle_options) as subtitle_ydl:
            subtitle_result = subtitle_ydl.extract_info(job.item.source_url, download=True) or {}
        requested = subtitle_result.get("requested_subtitles") or {}
        tracks = []
        for language, value in requested.items():
            if not isinstance(value, dict) or not value.get("filepath"): continue
            record_job_file(job, value["filepath"], "subtitle")
            tracks.append({"language": language, "name": value.get("name") or language,
                           "filepath": value["filepath"], "ext": value.get("ext")})
        if not tracks:
            for language in languages:
                warning = f"No subtitles were available for language: {language}"
                if warning not in job.warnings: job.warnings.append(warning)
            emit("SUBTITLE", "No requested subtitle tracks were available", "warning")
            return
        job.subtitle_details["downloaded"] = True
        job.subtitle_details["files"] = [track["filepath"] for track in tracks]
        if not job.options.embed_subtitles: return
        job.failure_stage = "Subtitle embedding"; job.postprocessing_stage = "Embedding subtitles"
        emit("SUBTITLE", "Muxing selectable subtitle stream(s)"); progress(job)
        details = mux_subtitles_atomically(job.output_file, tracks)
        job.subtitle_details.update(details)
        emit("FFPROBE", f"Subtitle verified: {', '.join(details['languages'])} / {details['codec']}")
        if not job.options.write_subtitles:
            for track in tracks: Path(str(track["filepath"])).unlink(missing_ok=True)

    mode = normalise_authentication_mode(job.options.authentication_mode)
    try:
        first_name, first_auth = (("Auto -> None", {}) if mode == "Auto" else
                                  (mode, authentication_options(mode, job.options.cookies_browser,
                                                                job.options.browser_profile, job.options.cookies_file)))
        job.effective_connection = job.effective_connection or ("Proxy" if proxy else "Direct / Normal Network")
        try:
            result, ydl = run_with_tor_retries(first_name, first_auth)
            successful_auth = first_auth
        except BaseException as first_error:
            if mode == "Auto" and requires_authentication(first_error):
                configured_name, configured = configured_authentication_options(
                    job.options.cookies_browser, job.options.browser_profile, "")
                job.technical_details = f"Authentication required. Retrying with {configured_name}…"
                progress(job)
                result, ydl = run_with_tor_retries(f"Auto -> {configured_name}", configured); successful_auth = configured
            else:
                raise
        candidates = [result.get("filepath"), result.get("_filename")]
        candidates.extend(entry.get("filepath") for entry in (result.get("requested_downloads") or []))
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                completed_file(candidate)
        if not job.final_files:
            prepared = ydl.prepare_filename(result)
            if prepared and Path(prepared).exists(): completed_file(prepared)
        requested_subtitles = result.get("requested_subtitles") or {}
        for subtitle in requested_subtitles.values():
            if isinstance(subtitle, dict) and subtitle.get("filepath"):
                record_job_file(job, subtitle["filepath"], "subtitle")
        for thumbnail in result.get("thumbnails") or []:
            if isinstance(thumbnail, dict) and thumbnail.get("filepath"):
                record_job_file(job, thumbnail["filepath"], "thumbnail")
        if (job.options.audio_format == "Original/best audio"
                and job.options.compatibility in COMPATIBLE_PROFILES
                and job.output_file and Path(job.output_file).is_file()):
            original_output = job.output_file
            job.failure_stage = "Compatibility conversion"
            job.postprocessing_stage = "Optimising for QuickTime"
            job.technical_details = "Checking codecs and MP4 structure"
            emit("FFPROBE", f"Validating {job.options.compatibility} compatibility")
            progress(job)
            try:
                compatible_file, compatibility, conversions = ensure_compatible_output(
                    original_output, job.options.compatibility, keep_original=job.options.keep_original)
                completed_file(compatible_file)
                job.compatibility_details = compatibility
                job.compatibility_details["conversions"] = conversions
                emit("FFMPEG", "; ".join(conversions))
            except BaseException as compatibility_error:
                safe_compatibility_error = redact_secrets(str(compatibility_error))
                warning = ("Download completed, but compatibility processing failed; "
                           "the output may not open cleanly in QuickTime. " + safe_compatibility_error)
                if warning not in job.warnings: job.warnings.append(warning)
                job.compatibility_details = {"profile": job.options.compatibility, "verified": False,
                                             "risks": [safe_compatibility_error]}
                emit("FFMPEG", warning, "warning")
        try:
            acquire_and_embed_subtitles(successful_auth)
        except BaseException as subtitle_error:
            safe_subtitle_error = redact_secrets(str(subtitle_error))
            if "403" in safe_subtitle_error:
                warning = "Video downloaded successfully, but subtitle download failed: HTTP 403."
            elif "timed out" in safe_subtitle_error.casefold() or "timeout" in safe_subtitle_error.casefold():
                warning = "Video downloaded successfully, but subtitle download timed out."
            else:
                warning = "Media downloaded successfully, but subtitle embedding failed."
            if warning not in job.warnings: job.warnings.append(warning)
            job.subtitle_details.update({"embedded": False, "verified": False, "error": safe_subtitle_error})
            emit("SUBTITLE", warning, "warning")
        if job.options.verify_postprocessing and job.output_file and Path(job.output_file).is_file():
            job.postprocessing_stage = "Verifying output"; job.technical_details = "Verifying output"; progress(job)
            verification, warnings = verify_requested_postprocessing(
                job.output_file, embed_thumbnail=job.options.embed_thumbnail,
                embed_subtitles=job.options.embed_subtitles)
            job.verification = verification
            if job.options.compatibility in COMPATIBLE_PROFILES and job.options.audio_format == "Original/best audio":
                conversions = list(job.compatibility_details.get("conversions") or [])
                job.compatibility_details = compatibility_summary(verification, job.options.compatibility)
                job.compatibility_details["conversions"] = conversions
                if not job.compatibility_details["verified"]:
                    warning = ("Download completed, but output may not open cleanly in QuickTime: "
                               + "; ".join(job.compatibility_details["risks"]))
                    if warning not in job.warnings: job.warnings.append(warning)
            for warning in warnings:
                if warning == "No subtitles were available for the selected language." and any(
                        item.startswith("No subtitles were available for language:") for item in job.warnings):
                    continue
                if warning not in job.warnings: job.warnings.append(warning)
        job.status = JobStatus.COMPLETED_WARNINGS if job.warnings else JobStatus.COMPLETED
        job.active_extractor_task = job.active_transfer_task = job.active_postprocess_task = False
        if not job.warnings: job.failure_stage = ""
        job.technical_details = job.status.value
        job.progress = 100.0
    except DownloadInterrupted:
        job.active_extractor_task = job.active_transfer_task = job.active_postprocess_task = False
        if job.status not in {JobStatus.PAUSED, JobStatus.CANCELLED}:
            job.status = JobStatus.PAUSED
    except BaseException as error:
        job.active_extractor_task = job.active_transfer_task = job.active_postprocess_task = False
        safe_error = redact_secrets(str(error))
        optional = ((job.options.embed_thumbnail and "thumbnail" in safe_error.casefold())
                    or (job.options.embed_subtitles and "subtitle" in safe_error.casefold()))
        candidate = next((path for path in [job.output_file, *job.temporary_files]
                          if path and Path(path).is_file()), "")
        if optional and candidate:
            try:
                verification, warnings = verify_requested_postprocessing(
                    candidate, embed_thumbnail=job.options.embed_thumbnail,
                    embed_subtitles=job.options.embed_subtitles)
                if verification.get("video") or verification.get("audio"):
                    record_job_file(job, candidate, "final"); job.output_file = candidate
                    job.verification = verification
                    job.warnings.extend(warnings or [f"Optional post-processing warning: {friendly_error(error)}"])
                    job.status = JobStatus.COMPLETED_WARNINGS; job.progress = 100.0
                    job.technical_details = job.status.value
                else:
                    raise RuntimeError("Downloaded media contains no usable audio or video stream")
            except BaseException:
                job.status = JobStatus.FAILED; apply_failure(job, error)
        else:
            job.status = JobStatus.FAILED
            job.failure_stage = safe_request_stage(error, job.failure_stage or "Analysis")
            apply_failure(job, error)
        if job.status == JobStatus.FAILED: LOGGER.error("Download failed: %s", job.error)
    progress(job)
    return job
