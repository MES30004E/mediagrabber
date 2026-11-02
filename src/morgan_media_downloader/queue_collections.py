"""Pure collection identity and incremental GUI-owned projections; no I/O/Qt."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
import hashlib
import json
import math
from uuid import uuid4

from .models import DownloadJob, JobStatus, MediaItem

STATUS_GROUPS = {
    "All": frozenset(status.value for status in JobStatus),
    "Waiting": frozenset({"Waiting"}),
    "Running": frozenset({"Analysing", "Downloading", "Converting", "Fetching metadata", "Seeding"}),
    "Completed": frozenset({"Completed", "Completed with warnings"}),
    "Failed": frozenset({"Failed"}), "Paused": frozenset({"Paused"}),
    "Cancelled": frozenset({"Cancelled"}), "Interrupted": frozenset({"Interrupted"}),
}
CATEGORIES = tuple(key for key in STATUS_GROUPS if key != "All") + ("Unknown",)


def status_matches(value: str, group: str) -> bool:
    if group not in STATUS_GROUPS: raise ValueError("Unknown queue status category")
    return group == "All" or value in STATUS_GROUPS[group]


def _text(value) -> str: return value.strip() if isinstance(value, str) else ""


def _provenance(item: MediaItem) -> tuple[str, str, str]:
    return _text(item.original_url), _text(item.collection_title), _text(item.collection_type)


def collection_key(job: DownloadJob) -> str:
    if _text(job.collection_id): return job.collection_id
    source, title, kind = _provenance(job.item)
    if source and title:
        return "legacy:" + hashlib.sha256(json.dumps((source, title, kind), ensure_ascii=False).encode()).hexdigest()
    return "ungrouped"


def assign_collections(items: list[MediaItem]) -> list[tuple[str, str]]:
    partitions = {}
    keys = [(_provenance(item) if all(_provenance(item)[:2]) else None) for item in items]
    unknown = keys.count(None)
    for item, key in zip(items, keys):
        if key not in partitions:
            name = key[1] if key else (item.title if unknown == 1 else f"Batch of {unknown} items")
            partitions[key] = ("import:" + uuid4().hex, _text(name)[:512] or "Imported media")
    return [partitions[key] for key in keys]


@dataclass(frozen=True)
class CollectionSummary:
    key: str
    name: str
    total: int
    counts: tuple[tuple[str, int], ...]
    progress: float | None
    known_progress: int


@dataclass(frozen=True)
class CollectionChange:
    groups: frozenset[str] = frozenset()
    structure: bool = False


@dataclass(frozen=True)
class _Entry:
    key: str
    name: str
    category: str
    progress: float | None


def _entry(job: DownloadJob) -> _Entry:
    key = collection_key(job)
    if _text(job.collection_id): name = _text(job.collection_name)[:512] or "Imported media"
    elif key == "ungrouped": name = "Ungrouped"
    else: name = "Legacy · " + _text(job.item.collection_title)[:512]
    category = next((name for name in CATEGORIES if name != "Unknown" and status_matches(job.status.value, name)), "Unknown")
    try: progress = float(job.progress)
    except (TypeError, ValueError): progress = math.nan
    progress = max(0., min(100., progress)) if math.isfinite(progress) else None
    if category == "Completed": progress = 100.
    return _Entry(key, name, category, progress)


@dataclass
class _Aggregate:
    name: str
    members: dict[str, None] = field(default_factory=dict)
    counts: Counter = field(default_factory=Counter)
    total: int = 0
    progress_sum: float = 0.
    known: int = 0

    def adjust(self, value: _Entry, delta: int):
        self.total += delta; self.counts[value.category] += delta
        if value.progress is not None: self.progress_sum += delta * value.progress; self.known += delta


class CollectionIndex:
    def __init__(self):
        self._entries: dict[str, _Entry] = {}; self._groups: dict[str, _Aggregate] = {}
        self._all = _Aggregate("All collections")

    @property
    def group_ids(self) -> tuple[str, ...]: return tuple(self._groups)

    def _replace(self, job_id: str, value: _Entry | None) -> CollectionChange:
        previous = self._entries.get(job_id)
        if previous == value: return CollectionChange()
        dirty = {""}; structure = False
        same_group = previous is not None and value is not None and previous.key == value.key
        if previous is not None:
            group = self._groups[previous.key]; group.adjust(previous, -1); self._all.adjust(previous, -1)
            dirty.add(previous.key)
            if not same_group: group.members.pop(job_id)
            if not group.total and not same_group: self._groups.pop(previous.key); structure = True
            if value is None: self._entries.pop(job_id)
        if value is not None:
            if value.key not in self._groups: self._groups[value.key] = _Aggregate(value.name); structure = True
            group = self._groups[value.key]; group.adjust(value, 1); self._all.adjust(value, 1)
            if not same_group: group.members[job_id] = None
            self._entries[job_id] = value; dirty.add(value.key)
        return CollectionChange(frozenset(dirty), structure)

    def update_job(self, job: DownloadJob) -> CollectionChange:
        return self._replace(job.id, _entry(job))

    def sync(self, jobs: Iterable[DownloadJob]) -> CollectionChange:
        present = set(); dirty = set(); structure = False
        for job in jobs:
            present.add(job.id); change = self.update_job(job)
            dirty.update(change.groups); structure |= change.structure
        for key in tuple(self._entries.keys()-present):
            change = self._replace(key, None); dirty.update(change.groups); structure |= change.structure
        return CollectionChange(frozenset(dirty), structure)

    def summary(self, key: str) -> CollectionSummary:
        group = self._all if not key else self._groups.get(key, _Aggregate("Unknown collection"))
        progress = max(0., min(100., group.progress_sum/group.known)) if group.known else None
        return CollectionSummary(key, group.name, group.total, tuple((category, group.counts[category]) for category in CATEGORIES), progress, group.known)

    def ids(self, key: str, status: str = "All") -> tuple[str, ...]:
        if status not in STATUS_GROUPS: raise ValueError("Unknown queue status category")
        members = self._entries if not key else self._groups.get(key, _Aggregate("")).members
        return tuple(job_id for job_id in members if status == "All" or self._entries[job_id].category == status)
