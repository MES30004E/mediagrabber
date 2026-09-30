from __future__ import annotations

import re
import os
import platform
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .models import DownloadJob, JobStatus, MediaItem
from .logging_setup import redact_secrets
from .file_ownership import record_job_file
from .parsing import ensure_output_directory
from .paths import application_support_dir, bundle_root

TORRENT_TOR_ERROR = "BitTorrent over Tor is not supported by Morgan Media Downloader. Use Direct or System / Proton VPN."
PUBLIC_TRACKER_SOURCE = "https://github.com/ngosang/trackerslist (trackers_best.txt snapshot)"
PUBLIC_TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "https://tracker.gbitt.info/announce",
)


@dataclass
class TorrentFile:
    index: int
    path: str
    size: int


@dataclass
class TorrentMetadata:
    source: str
    name: str
    total_size: int = 0
    tracker_count: int = 0
    files: list[TorrentFile] = field(default_factory=list)
    is_magnet: bool = False
    is_private: bool = False
    trackers: list[str] = field(default_factory=list)

    def media_items(self) -> list[MediaItem]:
        if not self.files:
            return [MediaItem(self.source, self.name, source="Torrent", original_url=self.source, file_size=self.total_size)]
        return [MediaItem(self.source, Path(item.path).name, uploader=str(Path(item.path).parent), source="Torrent",
                          playlist_index=item.index, original_url=self.source, file_size=item.size) for item in self.files]


class BencodeError(ValueError):
    pass


def bdecode(payload: bytes) -> Any:
    offset = 0

    def read() -> Any:
        nonlocal offset
        if offset >= len(payload):
            raise BencodeError("Unexpected end of torrent metadata")
        token = payload[offset:offset + 1]
        if token == b"i":
            end = payload.index(b"e", offset); value = int(payload[offset + 1:end]); offset = end + 1; return value
        if token == b"l":
            offset += 1; result = []
            while payload[offset:offset + 1] != b"e": result.append(read())
            offset += 1; return result
        if token == b"d":
            offset += 1; result = {}
            while payload[offset:offset + 1] != b"e":
                key = read(); value = read(); result[key] = value
            offset += 1; return result
        if token.isdigit():
            colon = payload.index(b":", offset); length = int(payload[offset:colon]); offset = colon + 1
            value = payload[offset:offset + length]; offset += length; return value
        raise BencodeError(f"Invalid bencode token at byte {offset}")

    result = read()
    if offset != len(payload):
        raise BencodeError("Trailing data in torrent file")
    return result


def _text(value: bytes | str) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def analyse_torrent(source: str) -> TorrentMetadata:
    if source.lower().startswith("magnet:?"):
        query = parse_qs(urlparse(source).query)
        name = unquote(query.get("dn", ["Magnet download"])[0])
        trackers = deduplicate_trackers(query.get("tr", []))
        return TorrentMetadata(source, name, tracker_count=len(trackers), is_magnet=True, trackers=trackers)
    path = Path(source).expanduser()
    root = bdecode(path.read_bytes())
    if not isinstance(root, dict) or b"info" not in root:
        raise BencodeError("Torrent file has no info dictionary")
    info = root[b"info"]
    name = _text(info.get(b"name.utf-8") or info.get(b"name") or path.stem)
    files = []
    if b"files" in info:
        for index, entry in enumerate(info[b"files"], 1):
            parts = entry.get(b"path.utf-8") or entry.get(b"path") or []
            files.append(TorrentFile(index, "/".join(_text(part) for part in parts), int(entry.get(b"length", 0))))
    else:
        files.append(TorrentFile(1, name, int(info.get(b"length", 0))))
    announce_list = root.get(b"announce-list") or []
    tracker_urls = []
    for tier in announce_list:
        tracker_urls.extend(_text(value) for value in tier) if isinstance(tier, list) else tracker_urls.append(_text(tier))
    if root.get(b"announce"):
        tracker_urls.append(_text(root[b"announce"]))
    tracker_urls = deduplicate_trackers(tracker_urls)
    return TorrentMetadata(str(path), name, sum(item.size for item in files), len(tracker_urls), files,
                           is_private=bool(info.get(b"private", 0)), trackers=tracker_urls)


def deduplicate_trackers(values: list[str] | tuple[str, ...]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        cleaned = str(value).strip()
        key = cleaned.casefold().rstrip("/")
        if cleaned and key not in seen:
            seen.add(key); result.append(cleaned)
    return result


def public_trackers(original: list[str], enabled: bool, private: bool) -> tuple[list[str], int]:
    original = deduplicate_trackers(original)
    if not enabled or private:
        return original, 0
    combined = deduplicate_trackers([*original, *PUBLIC_TRACKERS])
    return combined, len(combined) - len(original)


def bundled_aria2c_path() -> Path:
    packaged = bundle_root() / "bin" / "aria2c"
    return packaged if packaged.is_file() else bundle_root() / "resources" / "bin" / "aria2c"


def find_aria2c(configured: str = "") -> str | None:
    """Find aria2c in deterministic order without Homebrew assumptions."""
    candidates = [str(bundled_aria2c_path()), configured,
                  str(Path.home() / ".local" / "bin" / "aria2c"), shutil.which("aria2c") or ""]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    return None


@dataclass(frozen=True)
class Aria2Info:
    available: bool
    path: str = ""
    version: str = ""
    architecture: str = ""
    error: str = ""


def parse_aria2_version(output: str) -> str:
    match = re.search(r"^aria2 version\s+([^\s]+)", output, re.MULTILINE)
    return match.group(1) if match else ""


def inspect_aria2c(configured: str = "") -> Aria2Info:
    path = find_aria2c(configured)
    if not path:
        return Aria2Info(False, error="aria2c was not found")
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return Aria2Info(False, path=path, error=str(error))
    version = parse_aria2_version(result.stdout or result.stderr)
    architecture = "arm64" if platform.machine() == "arm64" else platform.machine()
    try:
        file_result = subprocess.run(["/usr/bin/file", path], capture_output=True, text=True, timeout=3, check=False)
        if "arm64" in file_result.stdout:
            architecture = "arm64"
        elif "x86_64" in file_result.stdout:
            architecture = "x86_64"
    except (OSError, subprocess.TimeoutExpired):
        pass
    error = "" if result.returncode == 0 and version else (result.stderr.strip() or "Unable to read aria2 version")
    return Aria2Info(not error, path, version, architecture, error)


def format_aria2_diagnostic(info: Aria2Info) -> str:
    if not info.available:
        return f"Unavailable\n{info.error or 'Select a trusted aria2c binary.'}"
    return f"Available\nVersion: {info.version}\nPath: {info.path}\nArchitecture: {info.architecture}"


def validate_torrent_connection(mode: str) -> None:
    if mode not in {"Direct", "Direct / Normal Network", "System / Proton VPN"}:
        raise ValueError(TORRENT_TOR_ERROR)


_DONE_TOTAL = re.compile(r"\s(?P<done>[\d.]+[KMGT]?i?B)/(?P<total>[\d.]+[KMGT]?i?B)", re.I)
_DOWNLOAD = re.compile(r"\bDL:(?P<value>[\d.]+[KMGT]?i?B)", re.I)
_UPLOAD = re.compile(r"\bUL:(?P<value>[\d.]+[KMGT]?i?B)", re.I)
_ETA = re.compile(r"\bETA:(?P<value>[\dhms]+)", re.I)
_PEERS = re.compile(r"CN:(\d+)")
_SEEDS = re.compile(r"(?:SD|SEED):(\d+)")


def _quantity(value: str | None) -> float:
    if not value: return 0.0
    match = re.match(r"([\d.]+)([KMGT]i?B|B)?", value, re.I)
    if not match: return 0.0
    scale = {"": 1, "b": 1, "kb": 1000, "kib": 1024, "mb": 1000 ** 2, "mib": 1024 ** 2,
             "gb": 1000 ** 3, "gib": 1024 ** 3, "tb": 1000 ** 4, "tib": 1024 ** 4}
    return float(match.group(1)) * scale.get((match.group(2) or "").lower(), 1)


def _eta_seconds(value: str | None) -> int | None:
    if not value: return None
    hours = re.search(r"(\d+)h", value); minutes = re.search(r"(\d+)m", value); seconds = re.search(r"(\d+)s", value)
    return (int(hours.group(1)) * 3600 if hours else 0) + (int(minutes.group(1)) * 60 if minutes else 0) + (int(seconds.group(1)) if seconds else 0)


def parse_torrent_progress(line: str) -> dict[str, float | int | None] | None:
    sizes = _DONE_TOTAL.search(line)
    if not sizes:
        return None
    done = int(_quantity(sizes.group("done")))
    total = int(_quantity(sizes.group("total")))
    download = _DOWNLOAD.search(line); upload = _UPLOAD.search(line); eta = _ETA.search(line)
    peers = _PEERS.search(line); seeds = _SEEDS.search(line)
    return {
        "downloaded_bytes": done,
        "total_bytes": total,
        "progress": done / total * 100 if total else 0.0,
        "speed": _quantity(download.group("value")) if download else 0.0,
        "upload_speed": _quantity(upload.group("value")) if upload else 0.0,
        "eta": _eta_seconds(eta.group("value")) if eta else None,
        "peers": int(peers.group(1)) if peers else 0,
        "seeds": int(seeds.group(1)) if seeds else 0,
    }


def build_torrent_command(job: DownloadJob, settings: Any, executable: str, destination: Path,
                          state_dir: Path | None = None) -> list[str]:
    validate_torrent_connection(settings.torrent_connection_mode)
    arguments = [
        executable, "--no-conf=true", "--dir", str(destination),
        "--console-log-level=notice", "--summary-interval=1", "--show-console-readout=true",
        "--file-allocation=none",
        f"--max-download-limit={settings.torrent_download_limit_kib}K" if settings.torrent_download_limit_kib else "--max-download-limit=0",
        f"--max-upload-limit={settings.torrent_upload_limit_kib}K" if settings.torrent_upload_limit_kib else "--max-upload-limit=0",
    ]
    private = bool(getattr(job, "torrent_private", False))
    dht = bool(getattr(settings, "torrent_enable_dht", True)) and not private
    pex = bool(getattr(settings, "torrent_enable_pex", True)) and not private
    lpd = bool(getattr(settings, "torrent_enable_lpd", True)) and not private
    arguments.extend([
        f"--enable-dht={'true' if dht else 'false'}",
        f"--enable-dht6={'true' if dht else 'false'}",
        f"--enable-peer-exchange={'true' if pex else 'false'}",
        f"--bt-enable-lpd={'true' if lpd else 'false'}",
    ])
    trackers, additional = public_trackers(
        list(getattr(job, "torrent_trackers", [])),
        bool(getattr(settings, "torrent_extra_public_trackers", False)), private,
    )
    job.original_tracker_count = len(deduplicate_trackers(list(getattr(job, "torrent_trackers", []))))
    job.additional_tracker_count = additional
    if trackers and getattr(settings, "torrent_enable_trackers", True):
        arguments.extend(["--bt-tracker", ",".join(trackers)])
    if state_dir is not None:
        state_dir.mkdir(parents=True, exist_ok=True)
        arguments.extend(["--dht-file-path", str(state_dir / "dht.dat"),
                          "--dht-file-path6", str(state_dir / "dht6.dat")])
    if job.torrent_file_indices:
        arguments.extend(["--select-file", ",".join(map(str, job.torrent_file_indices))])
    if not settings.torrent_continue_seeding:
        arguments.extend(["--seed-time", "0"])
    if not settings.torrent_enable_trackers:
        arguments.extend(["--bt-exclude-tracker", "*"])
    arguments.append(job.torrent_source or job.item.source_url)
    return arguments


def fetch_magnet_metadata(source: str, configured: str = "", timeout: int = 120) -> TorrentMetadata:
    executable = find_aria2c(configured)
    if not executable:
        raise FileNotFoundError("Torrent engine unavailable. Select a trusted aria2c binary in Settings.")
    with tempfile.TemporaryDirectory(prefix="morgan-magnet-") as temporary:
        arguments = [executable, "--no-conf=true", "--bt-metadata-only=true", "--bt-save-metadata=true",
                     "--seed-time=0", "--file-allocation=none", "--console-log-level=notice",
                     "--summary-interval=1", "--dht-file-path", str(Path(temporary) / "dht.dat"),
                     "--dht-file-path6", str(Path(temporary) / "dht6.dat"), "--dir", temporary, source]
        try:
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Timed out after {timeout} seconds while fetching magnet metadata") from None
        torrents = list(Path(temporary).glob("*.torrent"))
        if result.returncode != 0 or not torrents:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise RuntimeError(redact_secrets(detail[-1]) if detail else "Unable to fetch magnet metadata")
        metadata = analyse_torrent(str(torrents[0]))
        metadata.source = source
        metadata.is_magnet = True
        return metadata


def download_torrent(job: DownloadJob, settings: Any, changed: Callable[[DownloadJob], None],
                     stop_event: threading.Event) -> DownloadJob:
    executable = find_aria2c(settings.aria2c_path)
    if not executable:
        job.status = JobStatus.FAILED; job.error = "Torrent engine unavailable. Select a trusted aria2c binary in Settings."
        changed(job); return job
    try:
        destination = ensure_output_directory(job.options.download_dir)
        expected = [destination / relative for relative in job.torrent_file_paths]
        arguments = build_torrent_command(job, settings, executable, destination,
                                          application_support_dir() / "aria2")
        process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1)
        job.status = JobStatus.FETCHING_METADATA if job.torrent_source.startswith("magnet:?") else JobStatus.DOWNLOADING
        changed(job)
        assert process.stdout is not None
        while process.poll() is None:
            if stop_event.is_set():
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
                for path in expected:
                    if path.exists(): record_job_file(job, path, "temporary")
                    sidecar = Path(str(path) + ".aria2")
                    if sidecar.exists(): record_job_file(job, sidecar, "partial")
                return job
            line = process.stdout.readline()
            if not line: continue
            # The UI sets Paused/Cancelled before signalling the worker. Preserve
            # that requested state if a final buffered aria2 status line arrives.
            if stop_event.is_set():
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
                for path in expected:
                    if path.exists(): record_job_file(job, path, "temporary")
                    sidecar = Path(str(path) + ".aria2")
                    if sidecar.exists(): record_job_file(job, sidecar, "partial")
                return job
            if "download complete" in line.lower(): job.status = JobStatus.SEEDING
            elif progress := parse_torrent_progress(line):
                job.status = JobStatus.DOWNLOADING
                for key, value in progress.items(): setattr(job, key, value)
                changed(job)
        if process.returncode == 0:
            for path in expected:
                if path.exists(): record_job_file(job, path, "final")
            job.status = JobStatus.COMPLETED; job.progress = 100.0
            job.output_file = job.final_files[0] if job.final_files else ""
        else:
            job.status = JobStatus.FAILED; job.error = f"aria2c exited with status {process.returncode}"
    except (OSError, ValueError) as error:
        job.status = JobStatus.FAILED; job.error = redact_secrets(str(error))
    changed(job); return job
