from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .network import detect_tor
from .managed_tor import tor_executable
from .parsing import ensure_output_directory
from .paths import find_binary
from .provider import check_provider
from .settings import AppSettings
from .torrent import format_aria2_diagnostic, inspect_aria2c
from .yt_runtime import YtDlpRuntimeManager, get_runtime_manager


@dataclass
class CheckResult:
    name: str
    available: bool
    detail: str
    status: str = ""


def _binary_check(name: str) -> CheckResult:
    path = find_binary(name)
    if not path:
        return CheckResult(name, False, f"{name} not found")
    try:
        result = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=4, check=False)
        lines = (result.stdout or result.stderr).splitlines()
        if not lines: return CheckResult(name, False, f"{name} returned no version information")
        first = lines[0]
        return CheckResult(name, result.returncode == 0, first)
    except (OSError, subprocess.TimeoutExpired) as error:
        return CheckResult(name, False, str(error))


def run_checks(settings: AppSettings, runtime_manager: YtDlpRuntimeManager | None = None) -> list[CheckResult]:
    try:
        ensure_output_directory(settings.download_dir)
        writable = CheckResult("Download folder", os.access(settings.download_dir, os.W_OK), settings.download_dir)
    except OSError as error:
        writable = CheckResult("Download folder", False, str(error))
    try:
        manager = runtime_manager or get_runtime_manager()
        runtime = manager.describe()
        detail = (f"Active version: {runtime['active_version']}\nSource: {runtime['source']}\n"
                  f"Latest stable: {runtime['latest_stable']}\nAuto update: "
                  f"{'Enabled' if settings.yt_dlp_check_updates_on_startup else 'Disabled'}")
        yt_result = CheckResult("yt-dlp", True, detail, runtime["status"])
    except Exception as error:
        yt_result = CheckResult("yt-dlp", False, str(error))
    provider = check_provider(settings.provider_base_url, settings.provider_server_home)
    tor, port = detect_tor()
    browser = Path(settings.tor_browser_path).expanduser()
    executable = tor_executable(settings.tor_browser_path)
    aria = inspect_aria2c(settings.aria2c_path)
    return [
        yt_result,
        _binary_check("ffmpeg"),
        _binary_check("ffprobe"),
        writable,
        CheckResult("PO-token provider", provider.state == "available", provider.detail),
        CheckResult("Tor Browser", browser.is_dir(), str(browser), "Found" if browser.is_dir() else "Not found"),
        CheckResult("Tor executable", executable is not None, str(executable or "Not found")),
        CheckResult("External Tor", tor, f"SOCKS5H endpoint 127.0.0.1:{port}" if port else "No local Tor SOCKS listener", "Running" if tor else "Not running"),
        CheckResult("Managed Tor", executable is not None, "Available while Tor Browser is closed" if executable else "Tor executable unavailable"),
        CheckResult("Torrent engine", aria.available, format_aria2_diagnostic(aria)),
    ]
