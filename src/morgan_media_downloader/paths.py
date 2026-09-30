from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Morgan Media Downloader"


def application_support_dir() -> Path:
    root = Path(os.environ.get("MORGAN_DATA_DIR", "")) if os.environ.get("MORGAN_DATA_DIR") else Path.home() / "Library" / "Application Support" / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def logs_dir() -> Path:
    root = Path(os.environ.get("MORGAN_LOG_DIR", "")) if os.environ.get("MORGAN_LOG_DIR") else Path.home() / "Library" / "Logs" / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_download_dir() -> Path:
    return Path.home() / "Downloads" / APP_NAME


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def find_binary(name: str) -> str | None:
    candidates = [
        bundle_root() / "bin" / name,
        bundle_root() / "resources" / "bin" / name,
        Path(sys.executable).resolve().parent / name,
        Path.cwd() / "resources" / "bin" / name,
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which(name)
