from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from .models import DownloadJob, JobStatus


def _normal(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _inside_download(job: DownloadJob, path: str | Path) -> bool:
    try:
        Path(_normal(path)).relative_to(Path(job.options.download_dir).expanduser().resolve(strict=False))
        return True
    except ValueError:
        return False


def record_job_file(job: DownloadJob, path: str | Path, category: str) -> None:
    if not path or not _inside_download(job, path):
        return
    value = _normal(path)
    field = {
        "final": "final_files", "partial": "partial_files", "temporary": "temporary_files",
        "subtitle": "subtitle_files", "thumbnail": "thumbnail_files",
    }[category]
    values: list[str] = getattr(job, field)
    if value not in values:
        values.append(value)


def classify_job_file(job: DownloadJob, path: str | Path, *, final: bool = False) -> None:
    name = Path(path).name.casefold()
    if final:
        record_job_file(job, path, "final")
    elif name.endswith((".part", ".ytdl", ".aria2")):
        record_job_file(job, path, "partial")
    elif name.endswith((".vtt", ".srt", ".ass", ".lrc")):
        record_job_file(job, path, "subtitle")
    elif name.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif")):
        record_job_file(job, path, "thumbnail")
    else:
        record_job_file(job, path, "temporary")


def owned_paths(job: DownloadJob, *, include_final: bool = True) -> list[Path]:
    fields = [job.partial_files, job.temporary_files, job.subtitle_files, job.thumbnail_files]
    if include_final:
        fields.insert(0, job.final_files)
    unique: dict[str, Path] = {}
    for values in fields:
        for value in values:
            if _inside_download(job, value):
                unique[_normal(value)] = Path(_normal(value))
    return list(unique.values())


def delete_restart_state(job: DownloadJob, *, delete_final: bool = False) -> list[str]:
    removed: list[str] = []
    for path in owned_paths(job, include_final=delete_final):
        if not delete_final and str(path) in job.final_files:
            continue
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
            removed.append(str(path))
    job.partial_files.clear(); job.temporary_files.clear(); job.subtitle_files.clear(); job.thumbnail_files.clear()
    if delete_final:
        job.final_files.clear(); job.output_file = ""
    job.progress = 0.0; job.downloaded_bytes = 0; job.total_bytes = 0
    job.speed = 0.0; job.eta = None; job.fragment_index = None; job.fragment_count = None
    job.postprocessing_stage = ""; job.technical_details = ""; job.error = ""
    job.warnings.clear(); job.verification.clear()
    return removed


def prepare_resumable_job(job: DownloadJob) -> None:
    """Resume/Retry changes state only; owned partial data is intentionally retained."""
    job.status = JobStatus.WAITING
    job.error = ""
    job.technical_details = "Resuming from available partial data…"


def _folder_contains_only_owned(folder: Path, paths: list[Path]) -> bool:
    if not folder.is_dir():
        return False
    owned = {_normal(path) for path in paths}
    allowed_directories = {str(parent) for path in paths for parent in path.parents if parent == folder or folder in parent.parents}
    for path in folder.rglob("*"):
        if path.is_file() or path.is_symlink():
            if _normal(path) not in owned: return False
        elif path.is_dir() and _normal(path) not in allowed_directories:
            return False
    return True


def _move_to_trash(path: Path) -> bool:
    trash = Path.home() / ".Trash"
    try:
        trash.mkdir(exist_ok=True)
        destination = trash / path.name
        if destination.exists():
            destination = trash / f"{path.stem}-{uuid4().hex[:8]}{path.suffix}"
        shutil.move(str(path), str(destination))
        return True
    except OSError:
        return False


def delete_owned_files(job: DownloadJob, *, use_trash: bool = True) -> list[str]:
    paths = owned_paths(job, include_final=True)
    removed: list[str] = []
    folder = Path(job.created_job_directory).expanduser().resolve(strict=False) if job.created_job_directory else None
    if folder and _inside_download(job, folder) and _folder_contains_only_owned(folder, paths):
        if use_trash and _move_to_trash(folder):
            return [str(path) for path in paths]
        if not use_trash:
            shutil.rmtree(folder)
            return [str(path) for path in paths]
    for path in paths:
        if not (path.is_file() or path.is_symlink()):
            continue
        if use_trash and str(path) in job.final_files and _move_to_trash(path):
            removed.append(str(path)); continue
        path.unlink(missing_ok=True)
        removed.append(str(path))
    return removed


def primary_output(job: DownloadJob) -> str:
    existing = [path for path in job.final_files if Path(path).exists()]
    if existing:
        return existing[0]
    return job.output_file if job.output_file and Path(job.output_file).exists() else ""
