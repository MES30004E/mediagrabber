from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from morgan_media_downloader.yt_runtime import (
    LATEST_RELEASE_API,
    OFFICIAL_RELEASE_PREFIX,
    ReleaseInfo,
    RuntimeSnapshot,
    RuntimeVerificationError,
    YtDlpRuntimeManager,
    sha256_file,
    version_key,
)
from morgan_media_downloader.downloader import configure_provider_plugin


class BundledYDL:
    pass


def zipapp(version: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("yt_dlp/__init__.py", "from . import version\nclass YoutubeDL: pass\n")
        archive.writestr("yt_dlp/version.py", f"__version__ = '{version}'\n")
        archive.writestr("yt_dlp/padding.bin", b"0" * 110_000)
    return output.getvalue()


def release_payload(version: str) -> bytes:
    base = f"{OFFICIAL_RELEASE_PREFIX}{version}/"
    return json.dumps({
        "tag_name": version, "draft": False, "prerelease": False,
        "assets": [
            {"name": "yt-dlp", "browser_download_url": base + "yt-dlp"},
            {"name": "SHA2-256SUMS", "browser_download_url": base + "SHA2-256SUMS"},
        ],
    }).encode()


class ReleaseServer:
    def __init__(self, version: str, artifact: bytes | None = None):
        self.version = version
        self.artifact = artifact if artifact is not None else zipapp(version)
        self.calls: list[str] = []
        self.offline = False
        self.bad_checksum = False
        self.fail_download = False

    def __call__(self, url: str, _timeout: int) -> bytes:
        self.calls.append(url)
        if self.offline:
            raise OSError("offline")
        if url == LATEST_RELEASE_API:
            return release_payload(self.version)
        if url.endswith("/yt-dlp"):
            if self.fail_download:
                raise OSError("download interrupted")
            return self.artifact
        if url.endswith("/SHA2-256SUMS"):
            digest = "0" * 64 if self.bad_checksum else hashlib.sha256(self.artifact).hexdigest()
            return f"{digest}  yt-dlp\n".encode()
        raise AssertionError(url)


def manager(tmp_path: Path, server: ReleaseServer, provider=lambda: None) -> YtDlpRuntimeManager:
    def load_artifact(record, source):
        runtime_class = type(f"YDL_{record['version'].replace('.', '_')}", (), {})
        return RuntimeSnapshot(record["version"], source, runtime_class, record["artifact"])

    return YtDlpRuntimeManager(
        root=tmp_path / "runtime", fetcher=server,
        bundled_loader=lambda: RuntimeSnapshot("2025.01.01", "Bundled", BundledYDL),
        provider_checker=provider, artifact_loader=load_artifact,
    )


def install(mgr: YtDlpRuntimeManager, server: ReleaseServer) -> RuntimeSnapshot:
    version = server.version
    base = f"{OFFICIAL_RELEASE_PREFIX}{version}/"
    return mgr.install(ReleaseInfo(version, base + "yt-dlp", base + "SHA2-256SUMS"))


def test_bundled_fallback_offline_startup_and_version_comparison(tmp_path: Path):
    server = ReleaseServer("2025.01.01"); server.offline = True
    mgr = manager(tmp_path, server)
    assert mgr.initialize().source == "Bundled"
    assert server.calls == []  # Initialization itself never performs network I/O.
    assert mgr.check_and_update()["status"] == "Check failed / Offline"
    assert version_key("2026.07.04") > version_key("2026.7.3")
    assert version_key("nightly") == (0,)


def test_same_version_does_not_download_and_newer_can_be_check_only(tmp_path: Path):
    same = ReleaseServer("2025.01.01")
    mgr = manager(tmp_path / "same", same); mgr.initialize()
    assert mgr.check_and_update()["status"] == "Up to date"
    assert not any(url.endswith("/yt-dlp") for url in same.calls)

    newer = ReleaseServer("2026.07.04")
    mgr = manager(tmp_path / "newer", newer); mgr.initialize()
    result = mgr.check_and_update(auto_install=False)
    assert result["status"] == "Update available"
    assert result["latest_stable"] == "2026.07.04"
    assert mgr.snapshot().source == "Bundled"


def test_automatic_checks_are_daily_but_manual_checks_bypass_interval(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    server = ReleaseServer("2026.07.04")
    mgr = manager(tmp_path, server); mgr.initialize()
    monkeypatch.setattr(mgr, "_now", lambda: now)
    mgr.check_and_update(False, automatic=True)
    assert len(server.calls) == 1
    mgr.check_and_update(False, automatic=True)
    assert len(server.calls) == 1
    mgr.check_and_update(False)
    assert len(server.calls) == 2
    now += timedelta(hours=24)
    mgr.check_and_update(False, automatic=True)
    assert len(server.calls) == 3


def test_failed_check_survives_restart_without_losing_last_success_and_backs_off(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    server = ReleaseServer("2026.07.04")
    mgr = manager(tmp_path, server); mgr.initialize()
    monkeypatch.setattr(mgr, "_now", lambda: now)
    mgr.check_and_update(False)
    checked = mgr.describe()["last_checked"]
    now += timedelta(days=1)
    server.offline = True
    mgr.check_and_update(False, automatic=True)
    restarted = manager(tmp_path, server); restarted.initialize()
    monkeypatch.setattr(restarted, "_now", lambda: now)
    info = restarted.describe()
    assert info["last_error"] == "offline"
    assert info["last_checked"] == checked
    calls = len(server.calls)
    restarted.check_and_update(False, automatic=True)
    assert len(server.calls) == calls
    now += timedelta(hours=1)
    restarted.check_and_update(False, automatic=True)
    assert len(server.calls) == calls + 1


def test_channel_history_does_not_claim_nightly_check_was_a_stable_check(tmp_path):
    server = ReleaseServer("2026.07.04")
    mgr = manager(tmp_path, server); mgr.initialize()
    mgr.check_and_update(False)
    stable_checked = mgr.describe()["stable_last_checked"]
    mgr._fetcher = lambda *_: (_ for _ in ()).throw(OSError("nightly offline"))
    mgr.check_and_update(False, channel="nightly")
    info = mgr.describe()
    assert info["stable_last_checked"] == stable_checked
    assert info["nightly_last_checked"] == "Never"
    assert info["nightly_last_error"] == "nightly offline"
    assert info["stable_last_error"] == ""


def test_rollback_description_distinguishes_previous_and_bundled_fallback(tmp_path):
    first = ReleaseServer("2026.06.01")
    mgr = manager(tmp_path, first); mgr.initialize()
    assert mgr.describe()["rollback_available"] == "No — bundled runtime active"
    install(mgr, first)
    assert mgr.describe()["rollback_available"] == "Bundled 2025.01.01"
    second = ReleaseServer("2026.07.04"); mgr._fetcher = second; install(mgr, second)
    assert mgr.describe()["rollback_available"] == "Previous 2026.06.01; bundled 2025.01.01"


@pytest.mark.parametrize("failure", [OSError("https://synthetic:fixture-password@example.test/path"), TimeoutError()])
def test_direct_update_error_is_redacted_persisted_and_cleared_by_success(tmp_path, failure):
    server = ReleaseServer("2026.07.04")
    mgr = manager(tmp_path, server); mgr.initialize()
    mgr._fetcher = lambda *_: (_ for _ in ()).throw(failure)
    with pytest.raises(OSError):
        install(mgr, server)
    restarted = manager(tmp_path, server); restarted.initialize()
    assert restarted.describe()["last_error"]
    assert "fixture-password" not in restarted.metadata_path.read_text()
    assert "fixture-password" not in restarted.describe()["last_error"]
    install(restarted, server)
    again = manager(tmp_path, server); again.initialize()
    assert again.describe()["last_error"] == ""


def test_concurrent_automatic_checks_only_fetch_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    server = ReleaseServer("2026.07.04")
    mgr = manager(tmp_path, server); mgr.initialize()
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: mgr.check_and_update(False, automatic=True), range(4)))
    assert all(result["latest_stable"] == "2026.07.04" for result in results)
    assert len(server.calls) == 1


def test_empty_timeout_still_uses_hourly_failure_backoff_after_restart(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    calls = []
    def timeout(*_):
        calls.append(True)
        raise TimeoutError()
    server = ReleaseServer("2026.07.04")
    mgr = manager(tmp_path, server); mgr.initialize(); mgr._fetcher = timeout
    monkeypatch.setattr(mgr, "_now", lambda: now)
    mgr.check_and_update(False, automatic=True)
    restarted = manager(tmp_path, server); restarted.initialize(); restarted._fetcher = timeout
    monkeypatch.setattr(restarted, "_now", lambda: now)
    restarted.check_and_update(False, automatic=True)
    assert len(calls) == 1
    now += timedelta(hours=1)
    restarted.check_and_update(False, automatic=True)
    assert len(calls) == 2
    assert restarted.describe()["last_error"] == "TimeoutError"


def test_rollback_status_does_not_offer_missing_previous_artifact(tmp_path):
    first = ReleaseServer("2026.06.01")
    mgr = manager(tmp_path, first); mgr.initialize(); install(mgr, first)
    old = mgr.snapshot().artifact
    second = ReleaseServer("2026.07.04"); mgr._fetcher = second; install(mgr, second)
    Path(old).unlink()
    assert mgr.describe()["rollback_available"] == "Bundled 2025.01.01"


def test_explicit_nightly_channel_verifies_installs_restarts_and_rolls_back(tmp_path):
    nightly_api = "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest"
    prefix = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/download/"
    stable = ReleaseServer("2026.08.19")
    mgr = manager(tmp_path, stable); mgr.initialize(); install(mgr, stable)
    before = mgr.snapshot()
    artifact = zipapp("2026.10.10.233141"); calls = []
    def nightly(url, _timeout):
        calls.append(url)
        if url == nightly_api:
            return json.dumps({"tag_name": "2026.10.10.233141", "draft": False, "prerelease": True, "assets": [
                {"name": name, "browser_download_url": prefix + "2026.10.10.233141/" + name}
                for name in ("yt-dlp", "SHA2-256SUMS")]}).encode()
        if url.endswith("/SHA2-256SUMS"): return f"{hashlib.sha256(artifact).hexdigest()}  yt-dlp\n".encode()
        if url.endswith("/yt-dlp"): return artifact
        raise AssertionError(url)
    mgr._fetcher = nightly
    assert mgr.check_and_update(False, channel="nightly")["status"] == "Update available"
    assert mgr.snapshot() is before and calls == [nightly_api]
    result = mgr.check_and_update(True, channel="nightly")
    assert result["active_version"] == "2026.10.10.233141" and result["active_channel"] == "nightly"
    assert before.version == "2026.08.19" and mgr.snapshot().youtube_dl is not before.youtube_dl
    restarted = manager(tmp_path, stable)
    assert restarted.initialize().version == "2026.10.10.233141"
    assert restarted.rollback().version == "2026.08.19"


def test_runtime_install_rejects_mismatched_channel_assets_before_download(tmp_path):
    server = ReleaseServer("2026.08.19"); mgr = manager(tmp_path, server); mgr.initialize()
    with pytest.raises(RuntimeVerificationError):
        mgr.install(ReleaseInfo("2026.08.19", "https://github.com/attacker/runtime/releases/download/2026.08.19/yt-dlp",
                                OFFICIAL_RELEASE_PREFIX + "2026.08.19/SHA2-256SUMS"))
    assert not server.calls and mgr.snapshot().source == "Bundled"


def test_successful_verified_atomic_activation_and_user_runtime_precedence(tmp_path: Path):
    server = ReleaseServer("2026.07.04")
    mgr = manager(tmp_path, server); mgr.initialize()
    old_job = mgr.snapshot()
    result = mgr.check_and_update(auto_install=True)
    assert result["status"] == "Updated"
    assert (result["active_version"], result["source"]) == ("2026.07.04", "User Updated")
    metadata = json.loads(mgr.metadata_path.read_text())
    artifact = Path(metadata["current"]["artifact"])
    assert artifact.is_file()
    assert metadata["current"]["sha256"] == sha256_file(artifact)
    assert not list(mgr.root.rglob("*.partial"))
    assert not list(mgr.root.glob(".metadata.json.tmp-*"))
    assert old_job.youtube_dl is BundledYDL
    assert mgr.snapshot().youtube_dl is not old_job.youtube_dl

    restarted = manager(tmp_path, server)
    assert restarted.initialize().version == "2026.07.04"
    assert restarted.snapshot().source == "User Updated"
    assert server.calls.count(LATEST_RELEASE_API) == 1


def test_failed_download_and_checksum_preserve_working_runtime(tmp_path: Path):
    server = ReleaseServer("2026.07.04"); server.fail_download = True
    mgr = manager(tmp_path / "download", server); before = mgr.initialize()
    result = mgr.check_and_update()
    assert result["status"] == "Update failed"
    assert mgr.snapshot() is before

    server = ReleaseServer("2026.07.04"); server.bad_checksum = True
    mgr = manager(tmp_path / "checksum", server); before = mgr.initialize()
    result = mgr.check_and_update()
    assert result["status"] == "Update failed"
    assert "checksum mismatch" in mgr.last_error
    assert mgr.snapshot() is before


def test_corrupt_artifact_version_and_checksum_file_validation(tmp_path: Path):
    server = ReleaseServer("2026.07.04", zipapp("2026.07.03"))
    mgr = manager(tmp_path, server); mgr.initialize()
    with pytest.raises(RuntimeVerificationError, match="version"):
        install(mgr, server)
    assert mgr.snapshot().source == "Bundled"
    with pytest.raises(RuntimeVerificationError):
        mgr._checksum_for("not a checksum", "yt-dlp")


def test_rollback_and_corrupted_current_falls_back_to_previous(tmp_path: Path):
    first = ReleaseServer("2026.06.01")
    mgr = manager(tmp_path, first); mgr.initialize(); install(mgr, first)
    second = ReleaseServer("2026.07.04"); mgr._fetcher = second; install(mgr, second)
    assert mgr.rollback().version == "2026.06.01"
    assert mgr.snapshot().source == "Previous User Updated"

    data = json.loads(mgr.metadata_path.read_text())
    Path(data["current"]["artifact"]).write_bytes(b"corrupt")
    restarted = manager(tmp_path, second)
    assert restarted.initialize().version == "2026.07.04"
    assert restarted.snapshot().source == "Previous User Updated"


def test_corrupted_metadata_and_abandoned_partial_recover_safely(tmp_path: Path):
    server = ReleaseServer("2026.07.04")
    root = tmp_path / "runtime"; (root / "downloads").mkdir(parents=True)
    (root / "metadata.json").write_text("{broken")
    (root / "downloads" / "yt-dlp-dead.partial").write_bytes(b"partial")
    mgr = manager(tmp_path, server)
    assert mgr.initialize().source == "Bundled"
    assert not list((root / "downloads").glob("*.partial"))
    assert list(root.glob("metadata.json.broken-*"))


def test_cleanup_keeps_current_previous_and_one_extra(tmp_path: Path):
    server = ReleaseServer("2026.05.01")
    mgr = manager(tmp_path, server); mgr.initialize(); install(mgr, server)
    for version in ("2026.06.01", "2026.07.01"):
        server = ReleaseServer(version); mgr._fetcher = server; install(mgr, server)
    stray = mgr.versions_dir / "2025.12.31"; stray.mkdir(); (stray / "yt-dlp").write_bytes(b"old")
    mgr._cleanup_versions()
    versions = {path.name for path in mgr.versions_dir.iterdir()}
    assert {"2026.07.01", "2026.06.01"} <= versions
    assert len(versions) <= 3


def test_provider_incompatibility_keeps_update_but_uses_working_fallback(tmp_path: Path):
    server = ReleaseServer("2026.07.04")
    calls = 0

    def provider():
        nonlocal calls
        calls += 1
        raise RuntimeError("provider API changed")

    mgr = manager(tmp_path, server, provider); mgr.initialize()
    result = mgr.check_and_update()
    assert result["source"] == "Bundled"
    assert "provider API changed" in result["compatibility_error"]
    metadata = json.loads(mgr.metadata_path.read_text())
    assert metadata["current"] is None
    assert metadata["rejected_candidate"]["version"] == "2026.07.04"
    assert calls >= 1


def test_incompatible_candidate_does_not_replace_successful_runtime_metadata(tmp_path):
    server = ReleaseServer("2026.08.19"); state = {"version": "bundled"}
    mgr = manager(tmp_path, server)
    def load(record, source):
        state["version"] = record["version"]
        return RuntimeSnapshot(record["version"], source, type("Runtime", (), {}), record["artifact"])
    def check():
        if state["version"] == "2026.10.10.233141": raise RuntimeError("candidate provider API incompatible")
    mgr._artifact_loader = load; mgr._provider_checker = check
    mgr.initialize(); install(mgr, server)
    previous_time = mgr.describe()["last_update"]
    candidate = ReleaseServer("2026.10.10.233141"); mgr._fetcher = candidate
    prefix = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/download/2026.10.10.233141/"
    mgr.install(ReleaseInfo(candidate.version, prefix + "yt-dlp", prefix + "SHA2-256SUMS", "nightly"))
    assert mgr.snapshot().version == "2026.08.19"
    metadata = json.loads(mgr.metadata_path.read_text())
    assert metadata["current"]["version"] == "2026.08.19"
    assert mgr.describe()["last_update"] == previous_time


def test_rejected_candidate_keeps_user_selected_bundled_runtime(tmp_path):
    server = ReleaseServer("2026.08.19"); state = {"version": "bundled"}
    mgr = manager(tmp_path, server)
    def bundled():
        state["version"] = "bundled"
        return RuntimeSnapshot("2025.01.01", "Bundled", BundledYDL)
    def load(record, source):
        state["version"] = record["version"]
        return RuntimeSnapshot(record["version"], source, type("Runtime", (), {}), record["artifact"])
    def check():
        if state["version"] == "2026.10.10.233141": raise RuntimeError("provider mismatch")
    mgr._bundled_loader = bundled; mgr._artifact_loader = load; mgr._provider_checker = check
    mgr.initialize(); install(mgr, server); mgr.use_bundled()
    candidate = ReleaseServer("2026.10.10.233141"); mgr._fetcher = candidate
    prefix = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/download/2026.10.10.233141/"
    mgr.install(ReleaseInfo(candidate.version, prefix + "yt-dlp", prefix + "SHA2-256SUMS", "nightly"))
    assert mgr.snapshot().version == "2025.01.01" and mgr.snapshot().source == "Bundled"
    assert json.loads(mgr.metadata_path.read_text())["use_bundled"] is True
    restarted = manager(tmp_path, server)
    assert restarted.initialize().version == "2025.01.01"


def test_official_source_is_required(tmp_path: Path):
    server = ReleaseServer("2026.07.04")
    payload = json.loads(release_payload(server.version))
    payload["assets"][0]["browser_download_url"] = "https://example.test/yt-dlp"
    server.__call__ = lambda *_: json.dumps(payload).encode()  # Special methods resolve on the type.
    mgr = manager(tmp_path, server); mgr.initialize()
    mgr._fetcher = lambda *_: json.dumps(payload).encode()
    assert mgr.check_and_update()["status"] == "Check failed"


def test_frozen_provider_plugin_directory_is_discoverable(tmp_path: Path, monkeypatch):
    plugin_root = tmp_path / "provider_plugin"
    plugin_root.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    try:
        configure_provider_plugin()
        assert str(plugin_root) in sys.path
    finally:
        if str(plugin_root) in sys.path:
            sys.path.remove(str(plugin_root))
