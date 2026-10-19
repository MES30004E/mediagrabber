from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .logging_setup import redact_secrets
from .paths import application_support_dir

LOGGER = logging.getLogger(__name__)
LATEST_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
OFFICIAL_RELEASE_PREFIX = "https://github.com/yt-dlp/yt-dlp/releases/download/"
STABLE_VERSION = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}$")
NIGHTLY_VERSION = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}\.\d{6}$")
NIGHTLY_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest"
NIGHTLY_RELEASE_PREFIX = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/download/"
CHANNELS = {"stable": (LATEST_RELEASE_API, OFFICIAL_RELEASE_PREFIX, STABLE_VERSION),
            "nightly": (NIGHTLY_RELEASE_API, NIGHTLY_RELEASE_PREFIX, NIGHTLY_VERSION)}
_VERSION_ASSIGNMENT = re.compile(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)


class RuntimeVerificationError(RuntimeError):
    pass


class ProviderCompatibilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    asset_url: str
    checksums_url: str
    channel: str = "stable"


@dataclass(frozen=True)
class RuntimeSnapshot:
    version: str
    source: str
    youtube_dl: type
    artifact: str = ""


def version_key(value: str) -> tuple[int, ...]:
    if not (STABLE_VERSION.fullmatch(value) or NIGHTLY_VERSION.fullmatch(value)):
        return (0,)
    return tuple(int(part) for part in value.split("."))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class YtDlpRuntimeManager:
    _import_lock = threading.RLock()

    def __init__(self, root: Path | None = None,
                 fetcher: Callable[[str, int], bytes] | None = None,
                 bundled_loader: Callable[[], RuntimeSnapshot] | None = None,
                 provider_checker: Callable[[], None] | None = None,
                 artifact_loader: Callable[[dict[str, Any], str], RuntimeSnapshot] | None = None):
        self.root = root or application_support_dir() / "runtime" / "yt-dlp"
        self.versions_dir = self.root / "versions"
        self.downloads_dir = self.root / "downloads"
        self.metadata_path = self.root / "metadata.json"
        self._fetcher = fetcher or self._https_get
        self._bundled_loader = bundled_loader or self._load_bundled
        self._provider_checker = provider_checker or self._check_provider_imports
        self._artifact_loader = artifact_loader
        self._lock = threading.RLock()
        self._check_lock = threading.Lock()
        self._active: RuntimeSnapshot | None = None
        self._bundled: RuntimeSnapshot | None = None
        self._metadata: dict[str, Any] = self._default_metadata()
        self.status = "Using bundled fallback"
        self.last_error = ""
        self.initialized = False

    @staticmethod
    def _default_metadata() -> dict[str, Any]:
        return {
            "schema": 1, "current": None, "previous": None, "use_bundled": False,
            "latest_stable": "", "last_checked": "", "last_update": "",
            "compatibility_error": "",
            "last_error": "", "checks": {},
        }

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _https_get(url: str, timeout: int) -> bytes:
        if not any(url == api or url.startswith(prefix) for api, prefix, _pattern in CHANNELS.values()):
            raise ValueError("Refusing non-official yt-dlp update URL")
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                       "User-Agent": "MorganMediaDownloader/0.1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def initialize(self) -> RuntimeSnapshot:
        with self._lock:
            self._bundled = self._bundled_loader()
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                self.versions_dir.mkdir(parents=True, exist_ok=True)
                self.downloads_dir.mkdir(parents=True, exist_ok=True)
                self._remove_abandoned_downloads()
                self._metadata = self._load_metadata()
                self.last_error = str(self._metadata.get("last_error") or "")
            except OSError as error:
                self.last_error = redact_secrets(str(error))
                self._metadata = self._default_metadata()
                self._active = self._bundled
                self.status = "Using bundled fallback"
                self.initialized = True
                LOGGER.warning("yt-dlp runtime directory unavailable; using bundled fallback: %s", self.last_error)
                return self._active
            if self._metadata.get("use_bundled"):
                self._activate_bundled("Bundled version selected")
            elif not self._activate_record(self._metadata.get("current"), "User Updated"):
                if not self._activate_record(self._metadata.get("previous"), "Previous User Updated"):
                    self._activate_bundled("Using bundled fallback")
            self.initialized = True
            self._cleanup_versions()
            LOGGER.info("yt-dlp active version %s (%s)", self._active.version, self._active.source)
            return self._active

    def snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            if not self.initialized:
                return self.initialize()
            assert self._active is not None
            return self._active

    @property
    def bundled_version(self) -> str:
        if self._bundled is None:
            self.snapshot()
        assert self._bundled is not None
        return self._bundled.version

    def describe(self) -> dict[str, str]:
        active = self.snapshot()
        with self._lock:
            current = self._metadata.get("current") or {}
            previous = self._metadata.get("previous") or {}
            rollback = (f"Previous {previous['version']}; bundled {self.bundled_version}" if self._record_valid(previous) else
                        f"Bundled {self.bundled_version}") if active.artifact else "No — bundled runtime active"
            info = {
                "active_version": active.version,
                "current_runtime_version": str(current.get("version") or active.version),
                "bundled_version": self.bundled_version,
                "latest_stable": str(self._metadata.get("latest_stable") or "Not checked"),
                "latest_nightly": str(self._metadata.get("latest_nightly") or "Not checked"),
                "active_channel": str(current.get("channel", "stable")) if active.artifact else "bundled",
                "last_error": self.last_error,
                "last_checked": str(self._metadata.get("last_checked") or "Never"),
                "last_update": str(self._metadata.get("last_update") or "Never"),
                "source": active.source,
                "status": self.status,
                "compatibility_error": str(self._metadata.get("compatibility_error") or ""),
                "rollback_available": rollback,
            }
            for channel in CHANNELS:
                check = self._metadata.get("checks", {}).get(channel, {})
                info[f"{channel}_last_checked"] = str(check.get("last_success") or "Never")
                info[f"{channel}_last_attempt"] = str(check.get("last_attempt") or "Never")
                info[f"{channel}_last_error"] = str(check.get("last_error") or "")
            return info

    def fetch_latest(self, timeout: int = 8, *, channel: str = "stable") -> ReleaseInfo:
        if channel not in CHANNELS: raise RuntimeVerificationError("Unsupported runtime channel")
        api, prefix, pattern = CHANNELS[channel]
        payload = json.loads(self._fetcher(api, timeout).decode("utf-8"))
        version = str(payload.get("tag_name") or "")
        if not pattern.fullmatch(version) or (channel == "stable" and payload.get("prerelease")) or payload.get("draft"):
            raise RuntimeVerificationError("Latest GitHub release does not match the selected runtime channel")
        assets = {asset.get("name"): asset.get("browser_download_url") for asset in payload.get("assets", [])}
        asset_url, sums_url = assets.get("yt-dlp"), assets.get("SHA2-256SUMS")
        if asset_url != f"{prefix}{version}/yt-dlp" or sums_url != f"{prefix}{version}/SHA2-256SUMS":
            raise RuntimeVerificationError("Official release assets are incomplete")
        return ReleaseInfo(version, asset_url, sums_url, channel)

    def check_and_update(self, auto_install: bool = True, force: bool = False, *, channel: str = "stable",
                         automatic: bool = False) -> dict[str, str]:
        if channel not in CHANNELS:
            raise RuntimeVerificationError("Unsupported runtime channel")
        self.snapshot()
        # A startup check and a manual action must not race candidate activation
        # or overwrite one another's channel/check ledger.
        with self._check_lock:
            with self._lock:
                check = self._metadata.setdefault("checks", {}).setdefault(channel, {})
                now = self._now()
                if automatic and not force:
                    try:
                        elapsed = (now - datetime.fromisoformat(check["last_attempt"])).total_seconds()
                        interval = 3600 if check.get("last_error") else 86400
                        if 0 <= elapsed < interval:
                            return self.describe()
                    except (KeyError, TypeError, ValueError):
                        pass
                check["last_attempt"] = now.isoformat()
                self._save_metadata()
            return self._check_and_update(auto_install, force, channel=channel)

    def _check_failed(self, error: Exception, status: str, channel: str) -> dict[str, str]:
        with self._lock:
            self.last_error = redact_secrets(str(error)) or type(error).__name__
            self.status = status
            self._metadata["last_error"] = self.last_error
            self._metadata["checks"][channel]["last_error"] = self.last_error
            self._save_metadata()
        LOGGER.warning("yt-dlp %s: %s", status, self.last_error)
        return self.describe()

    def _check_and_update(self, auto_install: bool, force: bool, *, channel: str) -> dict[str, str]:
        with self._lock:
            self.status = "Checking..."; self.last_error = ""
        try:
            release = self.fetch_latest(channel=channel)
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            return self._check_failed(error, "Check failed / Offline", channel)
        except Exception as error:
            return self._check_failed(error, "Check failed", channel)

        checked = self._now().isoformat()
        with self._lock:
            self._metadata[f"latest_{channel}"] = release.version
            self._metadata["last_checked_channel"] = channel
            self._metadata["last_checked"] = checked
            self._metadata["last_error"] = ""
            self._metadata["checks"][channel].update(last_success=checked, last_error="")
            self._save_metadata()
        active = self.snapshot()
        LOGGER.info("yt-dlp update check: current %s, latest %s %s", active.version, channel, release.version)
        current_record = self._metadata.get("current") or {}
        installed_version = str(current_record.get("version") or "")
        try:
            if version_key(release.version) <= version_key(active.version) and not force:
                self.status = "Up to date"
            elif installed_version == release.version and force:
                if self._activate_record(current_record, "User Updated"):
                    self._metadata["use_bundled"] = False; self._save_metadata(); self.status = "Updated"
                else:
                    self.status = "Using bundled fallback"
            elif version_key(release.version) > version_key(active.version) or force:
                self.status = "Update available"
                if auto_install:
                    self.install(release)
            else:
                self.status = "Up to date"
        except Exception as error:
            self.last_error = redact_secrets(str(error)) or type(error).__name__
            self.status = "Update failed"
            LOGGER.warning("yt-dlp update failed: %s", self.last_error)
            with self._lock:
                self._metadata["last_error"] = self.last_error
                self._save_metadata()
        return self.describe()

    def install(self, release: ReleaseInfo) -> RuntimeSnapshot:
        if release.channel not in CHANNELS: raise RuntimeVerificationError("Unsupported runtime channel")
        _api, prefix, pattern = CHANNELS[release.channel]
        if (not pattern.fullmatch(release.version) or release.asset_url != f"{prefix}{release.version}/yt-dlp"
                or release.checksums_url != f"{prefix}{release.version}/SHA2-256SUMS"):
            raise RuntimeVerificationError("Runtime assets do not match the official channel and version")
        with self._lock:
            self.status = "Downloading update..."
            LOGGER.info("yt-dlp update start: %s", release.version)
            descriptor, temporary_name = tempfile.mkstemp(prefix="yt-dlp-", suffix=".partial", dir=self.downloads_dir)
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                temporary.write_bytes(self._fetcher(release.asset_url, 30))
                actual_sha = sha256_file(temporary)
                sums = self._fetcher(release.checksums_url, 10).decode("utf-8")
                expected_sha = self._checksum_for(sums, "yt-dlp")
                LOGGER.info("yt-dlp download complete: %s SHA256 %s", release.version, actual_sha)
                if actual_sha != expected_sha:
                    raise RuntimeVerificationError("yt-dlp SHA256 checksum mismatch")
                self.status = "Verifying..."
                self._verify_zipapp(temporary, release.version)
                LOGGER.info("yt-dlp verification succeeded: %s", release.version)
                version_dir = self.versions_dir / release.version
                version_dir.mkdir(parents=True, exist_ok=True)
                artifact = version_dir / "yt-dlp"
                os.replace(temporary, artifact)
                os.chmod(artifact, 0o700)
                record = {"version": release.version, "channel": release.channel, "artifact": str(artifact), "sha256": actual_sha,
                          "source": release.asset_url, "downloaded_at": datetime.now(timezone.utc).isoformat()}
                old_current = self._metadata.get("current")
                try:
                    snapshot = self._import_artifact(record, "User Updated")
                    self._provider_checker()
                except Exception as error:
                    # A downloaded but incompatible candidate is not a successful
                    # activation. Preserve current/previous and their timestamps
                    # so restart and rollback do not select the rejected build.
                    self._metadata["rejected_candidate"] = record
                    self._metadata["compatibility_error"] = redact_secrets(str(error))
                    self._save_metadata()
                    if self._metadata.get("use_bundled") or not self._activate_record(old_current, "Previous User Updated"):
                        self._activate_bundled("Using bundled fallback")
                    self.status = f"PO-token provider incompatible — using {self._active.version}"
                    LOGGER.warning("yt-dlp %s installed but provider compatibility failed: %s", release.version,
                                   self._metadata["compatibility_error"])
                    return self._active
                self._metadata["previous"] = old_current if old_current and old_current.get("version") != release.version else self._metadata.get("previous")
                self._metadata["current"] = record
                self._metadata["last_update"] = record["downloaded_at"]
                self._metadata["compatibility_error"] = ""
                self.last_error = ""
                self._metadata["last_error"] = ""
                self._metadata.pop("rejected_candidate", None)
                self._metadata["use_bundled"] = False
                self._active = snapshot
                self._save_metadata()
                self.status = "Updated"
                self._cleanup_versions()
                LOGGER.info("yt-dlp activated: %s", release.version)
                return snapshot
            except Exception as error:
                self.status = "Update failed"; self.last_error = redact_secrets(str(error)) or type(error).__name__
                self._metadata["last_error"] = self.last_error
                self._save_metadata()
                LOGGER.warning("yt-dlp verification/update failed: %s", self.last_error)
                raise
            finally:
                if temporary.exists():
                    temporary.unlink()

    def rollback(self) -> RuntimeSnapshot:
        with self._lock:
            previous = self._metadata.get("previous")
            current = self._metadata.get("current")
            if previous and self._activate_record(previous, "Previous User Updated"):
                self._metadata["current"], self._metadata["previous"] = previous, current
                self._metadata["use_bundled"] = False
                self._metadata["compatibility_error"] = ""
                self._save_metadata(); self.status = "Rolled back"
            else:
                self._activate_bundled("Using bundled fallback")
                self._metadata["use_bundled"] = True; self._save_metadata()
            LOGGER.info("yt-dlp rollback active version: %s", self._active.version)
            return self._active

    def use_bundled(self) -> RuntimeSnapshot:
        with self._lock:
            self._activate_bundled("Using bundled fallback")
            self._metadata["use_bundled"] = True
            self._save_metadata()
            return self._active

    @staticmethod
    def _checksum_for(payload: str, filename: str) -> str:
        for line in payload.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[1].lstrip("*") == filename and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
                return parts[0].lower()
        raise RuntimeVerificationError(f"Official checksum for {filename} was not found")

    @staticmethod
    def _verify_zipapp(path: Path, expected_version: str) -> None:
        if not path.is_file() or path.stat().st_size < 100_000 or not zipfile.is_zipfile(path):
            raise RuntimeVerificationError("Downloaded yt-dlp is not the expected zipimport executable")
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "yt_dlp/__init__.py" not in names or "yt_dlp/version.py" not in names:
                raise RuntimeVerificationError("Downloaded runtime does not contain the yt_dlp package")
            version_source = archive.read("yt_dlp/version.py").decode("utf-8")
        match = _VERSION_ASSIGNMENT.search(version_source)
        if not match or match.group(1) != expected_version:
            raise RuntimeVerificationError("Downloaded runtime version does not match the release")

    def _record_valid(self, record: dict[str, Any] | None) -> bool:
        if not record or record.get("channel", "stable") not in CHANNELS:
            return False
        if not CHANNELS[record.get("channel", "stable")][2].fullmatch(str(record.get("version") or "")):
            return False
        artifact = Path(str(record.get("artifact") or ""))
        expected = str(record.get("sha256") or "")
        try:
            return artifact.is_file() and bool(expected) and sha256_file(artifact) == expected
        except OSError:
            return False

    def _activate_record(self, record: dict[str, Any] | None, source: str) -> bool:
        if not self._record_valid(record):
            return False
        try:
            snapshot = self._import_artifact(record, source)
            self._provider_checker()
            self._active = snapshot; self.status = "Up to date"
            return True
        except Exception as error:
            self.last_error = redact_secrets(str(error))
            LOGGER.warning("yt-dlp runtime %s failed to initialize: %s", record.get("version"), self.last_error)
            return False

    def _import_artifact(self, record: dict[str, Any], source: str) -> RuntimeSnapshot:
        if self._artifact_loader is not None:
            return self._artifact_loader(record, source)
        artifact = str(record["artifact"])
        expected = str(record["version"])
        with self._import_lock:
            saved = {name: module for name, module in sys.modules.items()
                     if name == "yt_dlp" or name.startswith("yt_dlp.") or name == "yt_dlp_plugins" or name.startswith("yt_dlp_plugins.")}
            self._purge_runtime_modules()
            sys.path.insert(0, artifact)
            importlib.invalidate_caches()
            try:
                package = importlib.import_module("yt_dlp")
                version = str(package.version.__version__)
                youtube_dl = package.YoutubeDL
                if version != expected:
                    raise RuntimeVerificationError(f"Imported yt-dlp {version}, expected {expected}")
                return RuntimeSnapshot(version, source, youtube_dl, artifact)
            except Exception:
                self._purge_runtime_modules()
                sys.modules.update(saved)
                try: sys.path.remove(artifact)
                except ValueError: pass
                raise

    def _load_bundled(self) -> RuntimeSnapshot:
        with self._import_lock:
            for path in list(sys.path):
                if str(path).startswith(str(self.versions_dir)):
                    sys.path.remove(path)
            self._purge_runtime_modules()
            importlib.invalidate_caches()
            package = importlib.import_module("yt_dlp")
            return RuntimeSnapshot(str(package.version.__version__), "Bundled", package.YoutubeDL)

    @staticmethod
    def _purge_runtime_modules() -> None:
        # yt-dlp patches a shared urllib3 regex at import. Unloading yt-dlp
        # without undoing its own override stacks wrappers at the next import;
        # 2026.08.19's __getattribute__ forwarding then loses .sub in urllib3 2.8.
        # Release only a verified chain of yt-dlp-owned wrappers ending in a
        # real regex. Never patch third-party classes or discard foreign wrappers.
        url_module = sys.modules.get("urllib3.util.url")
        original = getattr(url_module, "_PERCENT_RE", None) if url_module else None
        current = original
        seen = set()
        while (type(current).__module__ == "yt_dlp.networking._requests"
               and type(current).__name__ == "Urllib3PercentREOverride" and id(current) not in seen):
            seen.add(id(current)); current = vars(current).get("re")
        if current is not original and isinstance(current, re.Pattern):
            url_module._PERCENT_RE = current
        for name in list(sys.modules):
            if name == "yt_dlp" or name.startswith("yt_dlp.") or name == "yt_dlp_plugins" or name.startswith("yt_dlp_plugins."):
                sys.modules.pop(name, None)

    @staticmethod
    def _check_provider_imports() -> None:
        from .downloader import configure_provider_plugin
        configure_provider_plugin()
        # Use yt-dlp's loader because it intentionally executes plugin modules itself.
        # Importing them first would register providers twice on the first YoutubeDL use.
        plugins = importlib.import_module("yt_dlp.plugins")
        plugins.load_all_plugins()
        expected = {
            "yt_dlp_plugins.extractor.getpot_bgutil": "BgUtilPTPBase",
            "yt_dlp_plugins.extractor.getpot_bgutil_http": "BgUtilHTTPPTP",
            "yt_dlp_plugins.extractor.getpot_bgutil_script": "BgUtilScriptNodePTP",
        }
        for name, class_name in expected.items():
            module = sys.modules.get(name)
            if module is None or not hasattr(module, class_name):
                raise ProviderCompatibilityError(f"{name} was not discovered by yt-dlp")

    def _activate_bundled(self, status: str) -> None:
        # Reloading purges any external zipimport modules left by a failed compatibility test.
        self._active = self._bundled_loader()
        if self._bundled is None:
            self._bundled = self._active
        try:
            self._provider_checker()
        except Exception as error:
            self.last_error = redact_secrets(str(error))
            LOGGER.warning("Bundled yt-dlp provider compatibility check failed: %s", self.last_error)
        self.status = status
        LOGGER.info("yt-dlp fallback selected: %s (%s)", self._active.version, status)

    def _load_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return self._default_metadata()
        try:
            value = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict): raise ValueError("metadata root is not an object")
            metadata = {**self._default_metadata(), **value}
            if not isinstance(metadata.get("checks"), dict):
                metadata["checks"] = {}
            metadata["checks"] = {channel: check for channel, check in metadata["checks"].items()
                                  if channel in CHANNELS and isinstance(check, dict)}
            return metadata
        except (OSError, ValueError, json.JSONDecodeError):
            broken = self.metadata_path.with_name(f"metadata.json.broken-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
            try: self.metadata_path.replace(broken)
            except OSError: pass
            return self._default_metadata()

    def _save_metadata(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_name(f".{self.metadata_path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self._metadata, stream, indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.metadata_path); os.chmod(self.metadata_path, 0o600)
        finally:
            if temporary.exists(): temporary.unlink()

    def _remove_abandoned_downloads(self) -> None:
        if not self.downloads_dir.exists(): return
        for path in self.downloads_dir.iterdir():
            if path.is_file() and path.name.endswith(".partial"):
                try: path.unlink()
                except OSError: pass

    def _cleanup_versions(self) -> None:
        keep = {str((record or {}).get("version") or "") for record in
                (self._metadata.get("current"), self._metadata.get("previous"))}
        extras = sorted((path for path in self.versions_dir.iterdir() if path.is_dir() and path.name not in keep),
                        key=lambda path: version_key(path.name), reverse=True)
        keep.update(path.name for path in extras[:1])
        for path in extras[1:]:
            if path.name not in keep:
                shutil.rmtree(path, ignore_errors=True)


_MANAGER: YtDlpRuntimeManager | None = None


def get_runtime_manager() -> YtDlpRuntimeManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = YtDlpRuntimeManager()
    return _MANAGER
