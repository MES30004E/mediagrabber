"""Read-only component inventory and public release metadata, never an installer."""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import __version__
from .diagnostics import _binary_check
from .logging_setup import redact_secrets
from .paths import application_support_dir, bundle_root, find_binary

REPOSITORIES = {"app": "MES30004E/mediagrabber", "provider": "Brainicism/bgutil-ytdlp-pot-provider"}
ENDPOINTS = {key: f"https://api.github.com/repos/{repo}/releases/latest" for key, repo in REPOSITORIES.items()}
TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")


def media_provenance(name, result):
    """Attribute a build record only to the bundled executable being inspected."""
    try:
        root = bundle_root().resolve(strict=True)
        executable = find_binary(name)
        if not executable or not Path(executable).resolve(strict=True).is_relative_to(root):
            return "Bundled build record not attributed to an external or unavailable executable"
        with (root / "media-build.json").open("rb") as stream: payload = stream.read(262145)
        if len(payload) > 262144: raise ValueError("Oversized build record")
        record = json.loads(payload)
        if not isinstance(record, dict) or type(record.get("schema")) is not int or record["schema"] != 1:
            raise ValueError("Unknown build record")
        version, deployment = record.get("ffmpeg_version"), record.get("deployment_target")
        if (not isinstance(version, str) or not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,3}){1,2}", version) or
                not isinstance(deployment, str) or not re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}", deployment)):
            raise ValueError("Invalid build version")
        matches = result.available and re.match(rf"{re.escape(name)} version {re.escape(version)}(?:\s|$)", result.detail)
        observation = "executable version matches" if matches else "executable version differs or is unconfirmed"
        return f"Bundled build record: FFmpeg {version}; macOS deployment target {deployment}; {observation}. Not runtime qualification."
    except (OSError, ValueError, TypeError, RecursionError):
        return "Bundled media build provenance unavailable or invalid; not inferred from the executable version"


def runtime_inventory(runtime):
    return {"id": "yt_dlp", "name": "yt-dlp", "installed": f"{runtime['active_version']} ({runtime['source']})",
            "latest": f"Stable {runtime['latest_stable']}; nightly {runtime['latest_nightly']}",
            "compatibility": runtime["compatibility_error"] or "Activation checks precede updates; live download not tested",
            "last_checked": runtime["last_checked"], "last_update": runtime["last_update"],
            "last_error": runtime["last_error"] or "None", "rollback": runtime["rollback_available"],
            "action": "Use the verified yt-dlp controls below"}


class ComponentCatalog:
    def __init__(self, runtime_manager, *, root: Path | None = None, fetcher=None):
        self.runtime = runtime_manager
        self.path = (root or application_support_dir() / "runtime" / "components") / "releases.json"
        self.fetcher = fetcher or self._fetch
        self._lock = threading.RLock()
        self._records = self._load()

    @staticmethod
    def _now(): return datetime.now(timezone.utc)

    @staticmethod
    def _fetch(url, timeout):
        if url not in ENDPOINTS.values(): raise ValueError("Unapproved component metadata source")
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
            "User-Agent": "MorganMediaDownloader/0.1", "X-GitHub-Api-Version": "2026-03-10"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(2_097_153)
        if len(data) > 2_097_152: raise ValueError("Release metadata exceeds limit")
        return data

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict): return {}
            return {key: {field: str(value)[:1000] for field, value in record.items()
                          if field in {"latest", "release_url", "last_checked", "last_attempt", "last_error", "retry_until"}
                          and isinstance(value, str)} for key, record in data.items()
                    if key in REPOSITORIES and isinstance(record, dict)}
        except (OSError, ValueError): return {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=".releases-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(self._records, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally: Path(name).unlink(missing_ok=True)

    def check_releases(self, *, automatic=False):
        with self._lock:
            for key, url in ENDPOINTS.items():
                record = self._records.setdefault(key, {})
                now = self._now()
                try:
                    if now < datetime.fromisoformat(record["retry_until"]): continue
                except (KeyError, ValueError, TypeError): pass
                if automatic:
                    try:
                        age = (now - datetime.fromisoformat(record["last_attempt"])).total_seconds()
                        if 0 <= age < (3600 if record.get("last_error") else 86400): continue
                    except (KeyError, TypeError, ValueError): pass
                record["last_attempt"] = now.isoformat()
                try:
                    data = json.loads(self.fetcher(url, 8))
                    if not isinstance(data, dict): raise ValueError("Invalid release metadata")
                    tag = data.get("tag_name", "")
                    if (not isinstance(tag, str) or not TAG.fullmatch(tag) or
                            data.get("draft") is not False or data.get("prerelease") is not False):
                        raise ValueError("No validated stable release metadata")
                    expected = f"https://github.com/{REPOSITORIES[key]}/releases/tag/{tag}"
                    if data.get("html_url") != expected: raise ValueError("Unexpected release source")
                    record.update(latest=tag, release_url=expected, last_checked=self._now().isoformat(), last_error="")
                except urllib.error.HTTPError as error:
                    # A tokenless 404 can also mean private/unavailable; never
                    # turn it into 'up to date' or a successful release check.
                    record["last_error"] = f"GitHub returned HTTP {error.code}; no stable public release confirmed"
                    now = self._now()  # Relative retry delays begin at receipt, not request start.
                    headers = error.headers or {}
                    if error.code in (403, 429) or headers.get("Retry-After"):
                        delay = 60
                        try: delay = max(delay, float(headers.get("Retry-After", 0)))
                        except (ValueError, TypeError):
                            try: delay = max(delay, (parsedate_to_datetime(headers["Retry-After"]) - now).total_seconds())
                            except (KeyError, ValueError, TypeError): pass
                        if headers.get("X-RateLimit-Remaining") == "0":
                            try: delay = max(delay, float(headers["X-RateLimit-Reset"]) - now.timestamp())
                            except (KeyError, ValueError, TypeError): pass
                        retry = (now + timedelta(seconds=min(delay, 315_360_000))).isoformat()
                        for component in REPOSITORIES:
                            self._records.setdefault(component, {}).update(retry_until=retry,
                                last_error=f"GitHub HTTP {error.code}; retry no earlier than {retry}")
                except Exception as error:
                    record["last_error"] = redact_secrets(str(error)) or type(error).__name__
                self._save()
            return copy.deepcopy(self._records)

    def inventory(self):
        with self._lock: records = copy.deepcopy(self._records)
        def row(key, name, installed, compatibility, *, upstream=None, rollback="Not managed yet", action="Update through a qualified app release; not managed yet"):
            record = records.get(upstream or key, {})
            return {"id": key, "name": name, "installed": installed, "latest": record.get("latest") or "Not checked",
                    "compatibility": compatibility, "last_checked": record.get("last_checked") or "Never",
                    "last_update": "Not managed yet", "last_error": record.get("last_error") or "None",
                    "rollback": rollback, "action": action}
        rows = [row("app", "Morgan Media Downloader", __version__,
                    "Packaged app; release qualification not inferred" if getattr(sys, "frozen", False) else "Python source checkout; not an installed release")]
        rows.append(runtime_inventory(self.runtime.describe()))
        plugin = sys.modules.get("yt_dlp_plugins.extractor.getpot_bgutil")
        provider_version = str(getattr(plugin, "__version__", "Not loaded"))
        rows.append(row("provider", "PO-token provider plugin", provider_version,
                        "Plugin version only; server/token generation readiness is checked separately in Accounts"))
        for name in ("ffmpeg", "ffprobe"):
            result = _binary_check(name)
            item = row(name, name, redact_secrets(result.detail)[:500] if result.available else "Not available",
                       "Executable responds; codec/conversion compatibility not tested" if result.available else "Not available — check component paths",
                       upstream="app")
            item["latest"] = ("App release " + item["latest"] + "; media versions not confirmed" if item["latest"] != "Not checked"
                              else "Ships with app; no app release confirmed")
            item["provenance"] = media_provenance(name, result)
            rows.append(item)
        try:
            manifest = json.loads((bundle_root() / "companion/chrome/manifest.json").read_text())
            shipped = str(manifest["version"])
            requirement = str(manifest["minimum_chrome_version"])
        except (OSError, ValueError, KeyError, TypeError): shipped, requirement = "Not found", "unknown"
        companion = row("companion", "Cookie Companion", f"Shipped extension {shipped}; installed Chrome version unconfirmed",
                        f"Chrome minimum {requirement}; installed extension/native host compatibility unconfirmed")
        companion["latest"] = "Ships with app; no independent release check"
        companion["last_checked"] = "Local files inspected; browser not queried"
        companion["action"] = "Use Accounts → Companion setup instructions and readiness checks"
        rows.append(companion)
        return rows
