from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SPOTIFY_HOSTS = {"open.spotify.com", "play.spotify.com"}
YOUTUBE_MUSIC_HOSTS = {"music.youtube.com"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
WATCH_LATER_URL = "https://www.youtube.com/playlist?list=WL"
_INVALID_FILENAME = re.compile(r"[\x00-\x1f/:\\?*\"<>|]")


def split_input(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def is_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def is_torrent_input(value: str) -> bool:
    if value.lower().startswith("magnet:?"):
        return True
    path = Path(value).expanduser()
    return path.suffix.lower() == ".torrent" and path.is_file()


def _watch_later_target(value: str) -> str | None:
    """Recognise only the keyword and explicit YouTube Watch Later routes."""
    value = value.strip()
    if value == ":ytwatchlater":
        return value
    try:
        parsed = urlparse(value if "://" in value else "https://" + value)
        if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS:
            return None
        path = parsed.path.rstrip("/")
        if path == "/feed/watch_later" or (
                path == "/playlist" and parse_qs(parsed.query).get("list") == ["WL"]):
            return WATCH_LATER_URL
    except ValueError:
        pass
    return None


def input_kind(value: str) -> str:
    if _watch_later_target(value) is not None:
        return "url"
    if is_torrent_input(value):
        return "torrent"
    if not is_url(value):
        return "search"
    host = (urlparse(value).hostname or "").lower()
    if host in SPOTIFY_HOSTS or host.endswith(".spotify.com"):
        return "spotify"
    if host in YOUTUBE_MUSIC_HOSTS:
        return "youtube_music"
    return "url"


def as_yt_dlp_target(value: str, result_count: int = 10) -> str:
    if target := _watch_later_target(value):
        return target
    return value if is_url(value) else f"ytsearch{result_count}:{value}"


def sanitize_filename(value: str, replacement: str = "_") -> str:
    value = _INVALID_FILENAME.sub(replacement, value).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(rf"{re.escape(replacement)}+", replacement, value)
    if not value:
        return "download"
    return value[:240]


def ensure_output_directory(value: str) -> Path:
    path = Path(value).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise NotADirectoryError(str(path))
    probe = path / ".morgan-media-downloader-write-test"
    probe.touch(exist_ok=True)
    probe.unlink(missing_ok=True)
    return path
