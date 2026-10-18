from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .logging_setup import redact_secrets
from .models import DownloadJob


IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "avif", "gif"}
NON_MEDIA_PROTOCOLS = {"mhtml", "data", "images"}
PLAYABLE_PROTOCOLS = {"http", "https", "m3u8", "m3u8_native", "dash", "http_dash_segments",
                      "rtmp", "rtmpe", "rtmps", "rtsp", "f4m", "ism", "websocket_frag"}


def is_playable_format(value: dict[str, Any]) -> bool:
    """Return whether an extractor format represents fetchable audio/video."""
    if not isinstance(value, dict) or not value.get("url"):
        return False
    ext = str(value.get("ext") or "").casefold()
    protocol = str(value.get("protocol") or "").casefold()
    note = " ".join(str(value.get(key) or "") for key in ("format_note", "format", "resolution")).casefold()
    format_id = str(value.get("format_id") or "").casefold()
    if ext in IMAGE_EXTENSIONS or protocol in NON_MEDIA_PROTOCOLS:
        return False
    if protocol and protocol not in PLAYABLE_PROTOCOLS:
        return False
    if any(term in note or term in format_id for term in ("storyboard", "thumbnail", "image only", "sprite")):
        return False
    vcodec, acodec = value.get("vcodec"), value.get("acodec")
    if vcodec in (None, "none") and acodec in (None, "none"):
        # A direct media/manifest result may omit codec fields, but a format
        # entry explicitly declaring both as none is never playable.
        if vcodec == "none" and acodec == "none":
            return False
        return protocol in {"http", "https", "m3u8", "m3u8_native", "dash", "http_dash_segments"}
    return True


def playable_formats(info: dict[str, Any]) -> list[dict[str, Any]]:
    formats = list(info.get("formats") or [])
    if not formats and is_playable_format(info):
        direct = dict(info); direct.setdefault("format_id", "direct")
        formats = [direct]
    return [entry for entry in formats if is_playable_format(entry)]


def safe_format_summary(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("format_id", "ext", "resolution", "vcodec", "acodec", "protocol")
    return [{key: entry.get(key) for key in keys if entry.get(key) is not None} for entry in formats]


def classify_failure(error: BaseException | str, *, metadata_success: bool = False,
                     stage: str = "Analysis", connection: str = "") -> dict[str, Any]:
    safe = redact_secrets(str(error))
    lower = safe.casefold()
    rules = [
        (("the page needs to be reloaded",), "YouTube player extraction",
         "YouTube's player rejected per-video extraction. Playlist analysis does not prove download readiness. Check the yt-dlp runtime channel/update; keep the selected authentication."),
        (("po-token", "po token", "potoken", "token provider"), "PO-token provider",
         "The PO-token provider could not satisfy this request. Check provider compatibility and readiness separately from sign-in."),
        (("http error 403", "status code: 403", "http 403", "access forbidden"), "HTTP 403",
         "Metadata loaded, but the media server denied the download." if metadata_success else "HTTP 403 — the server refused access."),
        (("http error 404", "status code: 404", "http 404"), "HTTP 404", "HTTP 404 — the media was not found."),
        (("http error 429", "status code: 429", "too many requests"), "HTTP 429", "HTTP 429 — the server requested a slower retry rate."),
        (("requested format is not available",), "Requested format unavailable", "The requested media format was unavailable."),
        (("no compatible format", "no playable", "only images"), "No playable formats", "No playable media format was available."),
        (("private video",), "Private video", "This is a private video and requires an authorised account."),
        (("login required", "sign in", "authentication required", "confirm you are not a bot"), "Authentication required", "Authentication is required."),
        (("video unavailable",), "Video unavailable", "The video is unavailable."),
        (("geo", "country"), "Geo restricted", "The media is not available in the current region."),
        (("timed out", "timeout"), "Network timeout", "The connection timed out."),
        (("name or service not known", "dns", "nodename nor servname"), "DNS error", "The host name could not be resolved."),
        (("proxy",), "Proxy failure", "The configured proxy could not complete the request."),
        (("no space left", "disk full"), "Disk full", "The destination disk is full."),
        (("permission denied", "read-only file system"), "Destination unavailable", "The destination is not writable."),
        (("ffmpeg",), "ffmpeg failure", "Media post-processing failed."),
        (("subtitle",), "Subtitle processing error", "Subtitle processing failed."),
    ]
    code, friendly = "Download error", safe or type(error).__name__
    for needles, candidate, message in rules:
        if any(needle in lower for needle in needles):
            code, friendly = candidate, message
            break
    if code == "HTTP 403" and connection == "Managed Tor":
        # This becomes Target rejected Tor only after an independent Tor Internet
        # health check confirms the proxy itself is working.
        friendly = "The target returned HTTP 403 while using Managed Tor. Test Tor Internet connectivity to distinguish a site rejection."
    retry_options = {
        "YouTube player extraction": ["Check yt-dlp Updates", "Retry with configured authentication", "Technical Details"],
        "PO-token provider": ["Check Provider", "Technical Details"],
        "HTTP 403": ["Retry", "Retry Direct", "Retry with configured authentication", "Open Console"],
        "No playable formats": ["Retry Best Available", "Retry Without Authentication", "Technical Details"],
        "Requested format unavailable": ["Retry Best Available", "Retry Without Authentication", "Technical Details"],
        "Authentication required": ["Retry with configured authentication", "Technical Details"],
    }.get(code, ["Retry", "View Details", "Open Console"])
    return {"code": code, "friendly": friendly, "technical": safe, "stage": stage,
            "retry_options": retry_options, "timestamp": datetime.now(timezone.utc).isoformat()}


def apply_failure(job: DownloadJob, error: BaseException | str) -> None:
    result = classify_failure(error, metadata_success=job.metadata_success,
                              stage=job.failure_stage or "Analysis", connection=job.effective_connection)
    job.failure_code = result["code"]
    job.error = result["friendly"]
    job.technical_details = result["technical"]
    job.failure_stage = result["stage"]
    job.retry_options = list(result["retry_options"])
    job.last_failure_at = result["timestamp"]


def status_summary(job: DownloadJob) -> str:
    if job.failure_code:
        return f"Failed — {job.failure_code}"
    return job.status.value


def diagnostics_text(job: DownloadJob, *, app_version: str = "0.1", yt_dlp_version: str = "") -> str:
    fields = [
        ("App", f"Morgan Media Downloader {app_version}"), ("yt-dlp", yt_dlp_version or "Unknown"),
        ("Title", job.item.title), ("Source", job.item.original_url or job.item.source_url),
        ("Extractor", job.extractor_key or job.item.source or "Unknown"),
        ("Stage", job.failure_stage or job.postprocessing_stage or "Unknown"),
        ("Connection", job.effective_connection or "Unknown"),
        ("Authentication", job.effective_authentication or job.options.authentication_mode),
        ("Metadata", "Success" if job.metadata_success else "Failed"),
        ("Playable formats", str(job.formats_playable)), ("Error", job.failure_code or job.error or "None"),
        ("Retry count", str(job.retry_count)),
    ]
    return redact_secrets("\n".join(f"{name}: {value}" for name, value in fields))


def safe_request_stage(error: BaseException | str, current: str) -> str:
    lower = str(error).casefold()
    if "fragment" in lower: return "Media fragment"
    if "manifest" in lower or "m3u8" in lower or "mpd" in lower: return "Manifest"
    if "subtitle" in lower: return "Subtitle transfer"
    if "thumbnail" in lower: return "Thumbnail transfer"
    if re.search(r"https?://", lower) and current in {"Video transfer", "Audio transfer"}: return current
    return current
