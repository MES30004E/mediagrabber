"""Tokenless stable application update staging; never replaces an installation."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from .app_archives import APP_NAME, MAX_ARCHIVE_BYTES, _asset_name, _validate_manifest, extract_release_archive
from .app_installation import validate_signature
from .logging_setup import redact_secrets

API = "https://api.github.com/repos/MES30004E/mediagrabber/releases/latest"
REPOSITORY = "https://github.com/MES30004E/mediagrabber"
HEADERS = {"User-Agent": "MorganMediaDownloader/0.1", "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2026-03-10"}


class AppUpdateError(RuntimeError):
    pass


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", value):
        raise AppUpdateError("Unsupported application version")
    return tuple(map(int, value.split(".")))


def _cancelled(cancel):
    if cancel.is_set(): raise InterruptedError("App update staging cancelled; nothing installed")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, source):
        super().__init__()
        self.source = source

    def redirect_request(self, request, fp, code, message, headers, newurl):
        if self.source == API:
            raise AppUpdateError("Authoritative app release metadata must not redirect")
        parsed = urllib.parse.urlsplit(newurl)
        if (parsed.scheme != "https" or parsed.hostname not in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or (parsed.hostname == "github.com" and newurl != self.source)):
            raise AppUpdateError("App release download redirected to an unapproved source")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def _open(url):
    if url != API and not re.fullmatch(re.escape(REPOSITORY) + r"/releases/download/v[0-9.]+/(?:release\.json|Morgan-Media-Downloader-[0-9.]+-macos-arm64\.tar\.gz)", url):
        raise AppUpdateError("Unapproved app release source")
    return urllib.request.build_opener(_SafeRedirect(url)).open(urllib.request.Request(url, headers=HEADERS), timeout=15)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise AppUpdateError("Duplicate app release JSON member")
        result[key] = value
    return result


def fetch(url, limit):
    with _open(url) as response: data = response.read(limit + 1)
    if len(data) > limit: raise AppUpdateError("App release response exceeds size limit")
    return data


def download(url, destination, expected_size, cancel, progress):
    total = 0
    with _open(url) as response, destination.open("xb") as output:
        while True:
            _cancelled(cancel)
            chunk = response.read(262144)
            if not chunk: break
            total += len(chunk)
            if total > expected_size: raise AppUpdateError("App archive exceeds its declared size")
            output.write(chunk)
            progress({"stage": "Downloading", "downloaded": total, "total": expected_size})
        output.flush(); os.fsync(output.fileno())
    if total != expected_size: raise AppUpdateError("App archive download is incomplete")


class AppUpdateManager:
    def __init__(self, root, installed_version, *, fetcher=fetch, downloader=download, validator=validate_signature, platform_info=None):
        self.root = Path(root).absolute(); self.installed_version = installed_version
        self.fetcher, self.downloader, self.validator = fetcher, downloader, validator
        self.platform_info = platform_info or (lambda: (sys.platform, platform.machine(), platform.mac_ver()[0]))
        self._operation_lock = threading.Lock(); self._state_lock = threading.RLock()
        self._state = {"status": "No app update staged; current installation unchanged", "staged_version": "",
                       "stage_directory": "", "last_stage": "", "last_error": "", "retry_until": 0}
        self._load()

    def _load(self):
        try:
            if self.root.is_symlink() or (self.root / "state.json").is_symlink(): return
            with (self.root / "state.json").open("rb") as stream: data = stream.read(16385)
            if len(data) > 16384: return
            record = json.loads(data)
            if not isinstance(record, dict): return
            for key in ("staged_version", "last_stage", "last_error"):
                if isinstance(record.get(key), str): self._state[key] = redact_secrets(record[key])[:500]
            stage = record.get("stage_directory")
            if isinstance(stage, str) and re.fullmatch(r"stage-[0-9a-f]{32}", stage): self._state["stage_directory"] = stage
            deadline = record.get("retry_until")
            if type(deadline) in (int, float) and 0 <= deadline <= time.time() + 604800:
                self._state["retry_until"] = deadline
            if self._state["stage_directory"]:
                self._state["status"] = "Previously staged; revalidation required before installation; not installed"
        except (OSError, ValueError, TypeError, RecursionError): pass

    def _save(self, record=None):
        if self.root.is_symlink(): raise AppUpdateError("App staging directory must not be a symlink")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True); self.root.chmod(0o700)
        fd, name = tempfile.mkstemp(prefix=".state-", dir=self.root)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(self._state if record is None else record, stream); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.root / "state.json")
        finally: Path(name).unlink(missing_ok=True)

    def describe(self):
        with self._state_lock:
            result = copy.deepcopy(self._state)
        result["staged_path"] = ""
        if result["stage_directory"]:
            app = self.root / result["stage_directory"] / "extracted" / APP_NAME
            if app.is_dir() and not app.is_symlink() and app.resolve().is_relative_to(self.root.resolve()):
                result["staged_path"] = str(app)
            else:
                result["staged_version"] = ""
                result["status"] = "Staged candidate unavailable; stage again. Nothing installed"
        return result

    @staticmethod
    def _asset(release, name, version, maximum):
        assets = release.get("assets")
        if not isinstance(assets, list) or len(assets) > 200: raise AppUpdateError("Invalid release assets")
        matches = [entry for entry in assets if isinstance(entry, dict) and entry.get("name") == name]
        if len(matches) != 1: raise AppUpdateError("Required app release asset missing or duplicated")
        asset = matches[0]
        if (asset.get("state") != "uploaded" or asset.get("browser_download_url") != f"{REPOSITORY}/releases/download/v{version}/{name}" or
                type(asset.get("size")) is not int or not 0 < asset["size"] <= maximum or
                not isinstance(asset.get("digest"), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", asset["digest"])):
            raise AppUpdateError("Release asset source, size or SHA-256 digest is invalid")
        return asset

    def _json(self, url, limit):
        data = self.fetcher(url, limit)
        if not isinstance(data, bytes) or len(data) > limit: raise AppUpdateError("App metadata response exceeds limit")
        return json.loads(data, object_pairs_hook=_unique_object), data

    def stage_latest(self, cancel, progress):
        if not self._operation_lock.acquire(blocking=False): raise AppUpdateError("App update staging already in progress")
        pending = None
        try:
            with self._state_lock:
                if time.time() < self._state["retry_until"]: raise AppUpdateError("App update rate limited; retry later")
            _cancelled(cancel)
            system, architecture, os_version = self.platform_info()
            if system != "darwin" or architecture != "arm64": raise AppUpdateError("App updates require Apple Silicon macOS")
            progress({"stage": "Checking stable app release"})
            release, _ = self._json(API, 2_097_152)
            if not isinstance(release, dict) or release.get("draft") is not False or release.get("prerelease") is not False:
                raise AppUpdateError("No supported stable app release confirmed")
            tag = release.get("tag_name")
            if not isinstance(tag, str) or not tag.startswith("v"): raise AppUpdateError("Invalid app release tag")
            version = tag[1:]
            if _version(version) <= _version(self.installed_version): raise AppUpdateError("No newer stable app release")
            if release.get("html_url") != f"{REPOSITORY}/releases/tag/{tag}": raise AppUpdateError("Unexpected app release repository")
            manifest_asset = self._asset(release, "release.json", version, 65536)
            binary_asset = self._asset(release, _asset_name(version), version, MAX_ARCHIVE_BYTES)
            _cancelled(cancel)
            manifest, raw = self._json(manifest_asset["browser_download_url"], 65536)
            if len(raw) != manifest_asset["size"] or "sha256:" + hashlib.sha256(raw).hexdigest() != manifest_asset["digest"]:
                raise AppUpdateError("App release manifest integrity check failed")
            asset = _validate_manifest(manifest, channel="stable")
            if manifest["version"] != version or asset["size"] != binary_asset["size"] or "sha256:" + asset["sha256"] != binary_asset["digest"]:
                raise AppUpdateError("App release manifest does not match its release assets")
            minimum = manifest.get("minimum_macos")
            if not isinstance(minimum, str) or not re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}", minimum): raise AppUpdateError("Invalid minimum macOS version")
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", os_version or "") or tuple(map(int, os_version.split("."))) < tuple(map(int, minimum.split("."))):
                raise AppUpdateError("App release is incompatible with this macOS version")
            _cancelled(cancel)
            with self._state_lock: self._save()
            with tempfile.TemporaryDirectory(prefix=".stage-", dir=self.root) as temporary:
                stage = Path(temporary); archive = stage / asset["name"]
                self.downloader(binary_asset["browser_download_url"], archive, asset["size"], cancel, progress)
                _cancelled(cancel)
                progress({"stage": "Verifying archive and staged application"})
                extract_release_archive(archive, manifest, stage / "extracted", validator=self.validator)
                _cancelled(cancel)
                (stage / "release.json").write_bytes(raw)
                destination = self.root / ("stage-" + uuid4().hex)
                stage.rename(destination)
                pending = destination
                with self._state_lock:
                    record = dict(self._state, stage_directory=destination.name, staged_version=version,
                        last_stage=datetime.now(timezone.utc).isoformat(), last_error="",
                        status="Verified candidate staged; not installed. Destination and post-exit replacement remain unresolved")
                    self._save(record)
                    self._state = record
                    pending = None
            return self.describe()
        except Exception as error:
            message = redact_secrets(str(error))[:500] or type(error).__name__
            if pending is not None:
                try: shutil.rmtree(pending)
                except OSError: message += "; uncommitted staging files could not be removed"
            with self._state_lock:
                self._state["last_error"] = "" if isinstance(error, InterruptedError) else message
                self._state["status"] = "Staging cancelled; nothing installed" if isinstance(error, InterruptedError) else "App update staging failed; nothing installed"
                if isinstance(error, urllib.error.HTTPError) and error.code in (403, 429):
                    delay = 60
                    try: delay = max(delay, float((error.headers or {}).get("Retry-After", 0)))
                    except (ValueError, TypeError):
                        try: delay = max(delay, parsedate_to_datetime(error.headers["Retry-After"]).timestamp() - time.time())
                        except (KeyError, ValueError, TypeError): pass
                    if (error.headers or {}).get("X-RateLimit-Remaining") == "0":
                        try: delay = max(delay, float(error.headers["X-RateLimit-Reset"]) - time.time())
                        except (KeyError, ValueError, TypeError): pass
                    self._state["retry_until"] = time.time() + min(delay, 604800)
                try: self._save()
                except OSError: message += "; staging status could not be saved"
            raise AppUpdateError(message) from None
        finally: self._operation_lock.release()
