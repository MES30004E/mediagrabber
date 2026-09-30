from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProviderStatus:
    state: str
    detail: str
    mode: str = "none"


def _valid_script_home(path: Path) -> bool:
    return (path / "build" / "generate_once.js").is_file() or (path / "src" / "generate_once.ts").is_file()


def find_script_home(configured: str = "") -> Path | None:
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    env_home = os.environ.get("MORGAN_BGUTIL_HOME")
    if env_home:
        candidates.append(Path(env_home).expanduser() / "server")
    candidates.extend([
        Path.cwd() / "bgutil-ytdlp-pot-provider" / "server",
        Path.home() / "bgutil-ytdlp-pot-provider" / "server",
    ])
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        # project/dist/App.app/Contents/MacOS/executable -> project
        if len(executable.parents) > 4:
            candidates.append(executable.parents[4] / "bgutil-ytdlp-pot-provider" / "server")
    for candidate in candidates:
        if _valid_script_home(candidate):
            return candidate.resolve()
    return None


def find_runtime() -> Path | None:
    candidates: list[Path] = []
    if found := shutil.which("node"):
        candidates.append(Path(found))
    if found := shutil.which("deno"):
        candidates.append(Path(found))
    candidates.extend(sorted(Path.home().glob(".nvm/versions/node/*/bin/node"), reverse=True))
    candidates.append(Path.home() / ".deno" / "bin" / "deno")
    for runtime in candidates:
        if not runtime.is_file():
            continue
        try:
            output = subprocess.run([str(runtime), "--version"], capture_output=True, text=True, timeout=3, check=False).stdout
            version = output.splitlines()[0].lstrip("v").split(".")
            minimum = 20 if runtime.name == "node" else 2
            if version and int(version[0]) >= minimum:
                return runtime
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    return None


def check_provider(base_url: str, script_home: str = "") -> ProviderStatus:
    try:
        request = urllib.request.Request(base_url.rstrip("/") + "/ping", headers={"User-Agent": "MorganMediaDownloader/0.1"})
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.load(response)
        return ProviderStatus("available", f"HTTP provider {payload.get('version', 'unknown')} at {base_url}", "http")
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        home = find_script_home(script_home)
        runtime = find_runtime()
        if home and runtime:
            return ProviderStatus("available", f"Script provider via {runtime.name} ({home})", "script")
        if home:
            return ProviderStatus("error", "Provider script found, but Node 20+ or Deno 2+ is unavailable", "script")
        return ProviderStatus("not_running", f"HTTP provider is not running at {base_url}", "none")


def provider_extractor_args(base_url: str, script_home: str = "") -> dict[str, dict[str, list[str]]]:
    args: dict[str, dict[str, list[str]]] = {"youtubepot-bgutilhttp": {"base_url": [base_url]}}
    if home := find_script_home(script_home):
        args["youtubepot-bgutilscript"] = {"server_home": [str(home)]}
    return args
