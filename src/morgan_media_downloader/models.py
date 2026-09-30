from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class JobStatus(str, Enum):
    WAITING = "Waiting"
    ANALYSING = "Analysing"
    DOWNLOADING = "Downloading"
    CONVERTING = "Converting"
    COMPLETED = "Completed"
    COMPLETED_WARNINGS = "Completed with warnings"
    FAILED = "Failed"
    PAUSED = "Paused"
    CANCELLED = "Cancelled"
    FETCHING_METADATA = "Fetching metadata"
    SEEDING = "Seeding"
    INTERRUPTED = "Interrupted"


@dataclass
class MediaItem:
    source_url: str
    title: str
    uploader: str = ""
    duration: float | None = None
    thumbnail: str = ""
    source: str = ""
    playlist_index: int | None = None
    selected: bool = True
    confidence: float | None = None
    original_url: str = ""
    file_size: int = 0
    collection_title: str = ""
    collection_type: str = ""
    available_subtitles: list[str] = field(default_factory=list)
    automatic_captions: list[str] = field(default_factory=list)
    thumbnail_headers: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass
class DownloadOptions:
    compatibility: str = "macOS / QuickTime"
    quality: str = "Best"
    container: str = "Auto"
    audio_format: str = "Original/best audio"
    audio_bitrate: str = "Auto"
    embed_thumbnail: bool = False
    embed_metadata: bool = True
    embed_chapters: bool = True
    embed_subtitles: bool = False
    write_subtitles: bool = False
    subtitle_source: str = "Normal subtitles"
    verify_postprocessing: bool = True
    keep_original: bool = False
    subtitle_language: str = "en"
    filename_template: str = "%(title)s.%(ext)s"
    download_dir: str = ""
    cookies_browser: str = "None"
    authentication_mode: str = "Auto"
    browser_profile: str = ""
    cookies_file: str = ""


@dataclass
class DownloadJob:
    item: MediaItem
    options: DownloadOptions
    id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.WAITING
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0
    eta: int | None = None
    fragment_index: int | None = None
    fragment_count: int | None = None
    output_file: str = ""
    error: str = ""
    technical_details: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    kind: str = "media"
    upload_speed: float = 0.0
    peers: int = 0
    seeds: int = 0
    torrent_source: str = ""
    torrent_file_indices: list[int] = field(default_factory=list)
    torrent_file_paths: list[str] = field(default_factory=list)
    torrent_private: bool = False
    torrent_trackers: list[str] = field(default_factory=list)
    original_tracker_count: int = 0
    additional_tracker_count: int = 0
    final_files: list[str] = field(default_factory=list)
    partial_files: list[str] = field(default_factory=list)
    temporary_files: list[str] = field(default_factory=list)
    subtitle_files: list[str] = field(default_factory=list)
    thumbnail_files: list[str] = field(default_factory=list)
    created_job_directory: str = ""
    warnings: list[str] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    effective_authentication: str = ""
    postprocessing_stage: str = ""
    extractor_key: str = ""
    extractor_name: str = ""
    effective_connection: str = ""
    metadata_success: bool = False
    formats_total: int = 0
    formats_playable: int = 0
    playable_format_summary: list[dict[str, Any]] = field(default_factory=list)
    failure_stage: str = ""
    failure_code: str = ""
    retry_count: int = 0
    last_failure_at: str = ""
    retry_options: list[str] = field(default_factory=list)
    subtitle_details: dict[str, Any] = field(default_factory=dict)
    compatibility_details: dict[str, Any] = field(default_factory=dict)
    active_extractor_task: bool = False
    active_transfer_task: bool = False
    active_postprocess_task: bool = False
    last_progress_timestamp: float = 0.0
    last_bytes_timestamp: float = 0.0
    last_state_transition: float = 0.0
    tor_process_state: str = "Unknown"
    tor_bootstrap: int = 0
    tor_socks_state: str = "Unknown"
    tor_socks_endpoint: str = ""
    tor_control_endpoint: str = ""
    tor_internet_state: str = "Unknown"
    tor_current_exit_ip: str = ""
    tor_previous_exit_ip: str = ""
    tor_circuit_changed: bool | None = None
    tor_circuit_retry: int = 0
    tor_circuit_retry_limit: int = 3
    tor_target_result: str = "Unknown"
    tor_last_circuit_change: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        # Request headers are useful only for the in-memory preview fetch. They
        # may contain session context and are never written to job history.
        result["item"]["thumbnail_headers"] = {}
        result["status"] = self.status.value
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DownloadJob":
        data = dict(value)
        media_fields = MediaItem.__dataclass_fields__.keys()
        option_fields = DownloadOptions.__dataclass_fields__.keys()
        job_fields = cls.__dataclass_fields__.keys()
        data["item"] = MediaItem(**{k: v for k, v in data["item"].items() if k in media_fields})
        data["options"] = DownloadOptions(**{k: v for k, v in data["options"].items() if k in option_fields})
        data["status"] = JobStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in job_fields})
