from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .models import MediaItem


_INVALID_MACOS = re.compile(r"[\x00/:]+")
_SPACE = re.compile(r"\s+")


def safe_component(value: str, fallback: str = "Media") -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = _INVALID_MACOS.sub("-", value)
    value = _SPACE.sub(" ", value).strip(" .-")
    return value[:180] or fallback


def common_torrent_root(paths: list[str]) -> str:
    roots = {Path(path).parts[0] for path in paths if Path(path).parts}
    return next(iter(roots)) if len(roots) == 1 else ""


def organised_folder(base: str, items: list[MediaItem], mode: str, *, torrent_name: str = "") -> str:
    root = Path(base).expanduser()
    is_collection = any(item.collection_title for item in items)
    if mode == "Never" or (len(items) <= 1 and not is_collection):
        return str(root)
    should_group = mode == "Auto" or mode == "Always for multi-file jobs"
    if not should_group:
        return str(root)
    title = torrent_name or next((item.collection_title for item in items if item.collection_title), "")
    if not title and torrent_name:
        title = torrent_name
    if not title:
        title = "Downloaded Media"
    component = safe_component(title)
    if root.name.casefold() == component.casefold():
        return str(root)
    if torrent_name:
        existing = common_torrent_root([item.uploader + "/" + item.title for item in items])
        if existing and safe_component(existing).casefold() == component.casefold():
            return str(root)
    return str(root / component)
