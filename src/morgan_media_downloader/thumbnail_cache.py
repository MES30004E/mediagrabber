from __future__ import annotations

import hashlib
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path
from uuid import uuid4
from typing import Callable, Any


def thumbnail_cache_dir() -> Path:
    path = (Path(os.environ["MORGAN_CACHE_DIR"]) / "thumbnails" if os.environ.get("MORGAN_CACHE_DIR")
            else Path.home() / "Library" / "Caches" / "Morgan Media Downloader" / "thumbnails")
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_thumbnail_cache(*, max_bytes: int = 128 * 1024 * 1024, max_age_days: int = 30) -> None:
    root = thumbnail_cache_dir(); now = time.time(); files = sorted(
        (path for path in root.iterdir() if not path.name.startswith(".") and not path.name.endswith(".part") and path.is_file()), key=lambda path: path.stat().st_mtime)
    total = sum(path.stat().st_size for path in files)
    for path in files:
        stat = path.stat()
        if now - stat.st_mtime > max_age_days * 86400 or total > max_bytes:
            total -= stat.st_size
            path.unlink(missing_ok=True)


def fetch_thumbnail(url: str, headers: dict[str, str] | None = None,
                    progress: Callable[[int | None], None] | None = None,
                    proxy: str | None = None, runtime: Any = None, *, cancel_event=None) -> str:
    def check_cancelled():
        if cancel_event is not None and cancel_event.is_set(): raise InterruptedError("Thumbnail request cancelled")
    check_cancelled()
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    suffix = Path(urllib.parse.urlparse(url).path).suffix.casefold()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}: suffix = ".img"
    target = thumbnail_cache_dir() / f"{digest}{suffix}"
    if target.is_file() and target.stat().st_size:
        target.touch(); return str(target)
    allowed = {key: value for key, value in (headers or {}).items()
               if key.casefold() in {"user-agent", "referer", "origin", "accept", "accept-language"}}
    request = urllib.request.Request(url, headers=allowed)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.part")
    try:
        check_cancelled()
        if proxy:
            YoutubeDL = runtime.youtube_dl if runtime is not None else __import__("yt_dlp", fromlist=["YoutubeDL"]).YoutubeDL
            ydl_context = YoutubeDL({"proxy": proxy, "socket_timeout": 20, "quiet": True})
            response_context = ydl_context.urlopen(request)
        else:
            ydl_context = None
            response_context = urllib.request.urlopen(request, timeout=20)
        with response_context as response, temporary.open("wb") as stream:
            check_cancelled()
            total = int(response.headers.get("Content-Length") or 0)
            read = 0
            if progress: progress(0 if total else None)
            while True:
                check_cancelled()
                chunk = response.read(64 * 1024)
                check_cancelled()
                if not chunk: break
                read += len(chunk)
                if read > 15 * 1024 * 1024: raise ValueError("Thumbnail exceeded the 15 MB preview limit")
                stream.write(chunk)
                if progress: progress(min(100, int(read / total * 100)) if total else None)
        check_cancelled()
        temporary.replace(target); cleanup_thumbnail_cache(); return str(target)
    finally:
        if "ydl_context" in locals() and ydl_context is not None: ydl_context.close()
        temporary.unlink(missing_ok=True)
