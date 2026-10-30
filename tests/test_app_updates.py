import hashlib
import json
import plistlib
import threading
import urllib.error

import pytest

from morgan_media_downloader.app_updates import AppUpdateError, AppUpdateManager
from morgan_media_downloader.app_archives import build_development_archive
from test_app_archives import bundle, validate, COMMIT

API = "https://api.github.com/repos/MES30004E/mediagrabber/releases/latest"
PREFIX = "https://github.com/MES30004E/mediagrabber/releases/download/v0.2.0/"


class Releases:
    def __init__(self, tmp_path):
        app = bundle(tmp_path / "source")
        path = app / "Contents/Info.plist"; info = plistlib.loads(path.read_bytes())
        info["CFBundleShortVersionString"] = "0.2.0"; path.write_bytes(plistlib.dumps(info))
        output = tmp_path / "release"
        self.manifest = build_development_archive(app, output, "0.2.0", COMMIT, validator=validate)
        self.manifest.update(channel="stable", publication_approved=True)
        self.archive = (output / self.manifest["asset"]["name"]).read_bytes()
        self.calls = []; self.fail = False; self.cancel_download = False
        self.release = {"tag_name": "v0.2.0", "draft": False, "prerelease": False,
                        "html_url": "https://github.com/MES30004E/mediagrabber/releases/tag/v0.2.0", "assets": []}
        self.sync()

    def sync(self):
        self.manifest_bytes = json.dumps(self.manifest).encode()
        def asset(name, data, identity):
            return {"id": identity, "name": name, "state": "uploaded", "size": len(data),
                    "digest": "sha256:" + hashlib.sha256(data).hexdigest(), "browser_download_url": PREFIX + name}
        self.release["assets"] = [asset("release.json", self.manifest_bytes, 1),
                                  asset(self.manifest["asset"]["name"], self.archive, 2)]

    def fetch(self, url, limit):
        self.calls.append(url)
        if self.fail: raise OSError("synthetic download failure")
        value = json.dumps(self.release).encode() if url == API else self.manifest_bytes
        assert len(value) <= limit
        return value

    def download(self, url, path, size, cancel, progress):
        self.calls.append(url)
        if self.fail: raise OSError("synthetic download failure")
        if self.cancel_download: cancel.set()
        path.write_bytes(self.archive)
        progress({"stage": "Downloading", "downloaded": len(self.archive), "total": size})


def manager(tmp_path, server, **kwargs):
    return AppUpdateManager(tmp_path / "updates", "0.1.0", fetcher=server.fetch, downloader=server.download,
                            validator=validate, platform_info=lambda: ("darwin", "arm64", "15.0"), **kwargs)


def test_newer_stable_update_stages_verified_candidate_without_installing(tmp_path):
    server = Releases(tmp_path); service = manager(tmp_path, server); events = []
    report = service.stage_latest(threading.Event(), events.append)
    assert report["staged_version"] == "0.2.0" and "not installed" in report["status"].lower()
    from pathlib import Path
    validate(Path(report["staged_path"]))
    assert report["last_stage"] and report["last_error"] == ""
    assert any(event["stage"] == "Downloading" for event in events)
    assert server.calls == [API, PREFIX + "release.json", PREFIX + server.manifest["asset"]["name"]]
    restarted = manager(tmp_path, server).describe()
    assert restarted["staged_version"] == "0.2.0" and "not installed" in restarted["status"].lower()
    assert "revalidation" in restarted["status"].lower()


@pytest.mark.parametrize("change", ["draft", "prerelease", "wrong-url", "missing-digest", "duplicate-asset", "dev-manifest", "wrong-commit", "wrong-platform", "wrong-size"])
def test_invalid_release_is_never_staged(tmp_path, change):
    server = Releases(tmp_path)
    if change in {"draft", "prerelease"}: server.release[change] = True
    elif change == "wrong-url": server.release["assets"][0]["browser_download_url"] = "https://example.test/release.json"
    elif change == "missing-digest": server.release["assets"][0].pop("digest")
    elif change == "duplicate-asset": server.release["assets"].append(server.release["assets"][0].copy())
    else:
        if change == "dev-manifest": server.manifest.update(channel="development", publication_approved=False)
        elif change == "wrong-commit": server.manifest["source_commit"] = "not-a-commit"
        elif change == "wrong-platform": server.manifest["architecture"] = "x86_64"
        elif change == "wrong-size": server.manifest["asset"]["size"] += 1
        server.sync()
    service = manager(tmp_path, server)
    with pytest.raises(Exception): service.stage_latest(threading.Event(), lambda *_: None)
    assert service.describe()["staged_version"] == "" and service.describe()["last_error"]
    assert len(server.calls) <= 2, "Invalid metadata must fail before downloading the app archive"


@pytest.mark.parametrize("failure", ["cancel", "corrupt", "network"])
def test_failure_or_cancel_keeps_previous_staged_app(tmp_path, failure):
    from pathlib import Path
    server = Releases(tmp_path); service = manager(tmp_path, server)
    previous = service.stage_latest(threading.Event(), lambda *_: None)
    if failure == "cancel": server.cancel_download = True
    elif failure == "corrupt": server.archive += b"corrupt"
    else: server.fail = True
    with pytest.raises(Exception): service.stage_latest(threading.Event(), lambda *_: None)
    current = service.describe()
    assert current["staged_path"] == previous["staged_path"]
    validate(Path(current["staged_path"]))
    assert len(list((tmp_path / "updates").glob("stage-*"))) == 1


def test_equal_or_older_release_does_not_download_assets(tmp_path):
    server = Releases(tmp_path)
    service = AppUpdateManager(tmp_path / "updates", "0.2.0", fetcher=server.fetch,
                              downloader=server.download, validator=validate,
                              platform_info=lambda: ("darwin", "arm64", "15.0"))
    with pytest.raises(Exception, match="newer"): service.stage_latest(threading.Event(), lambda *_: None)
    assert server.calls == [API]


def test_rate_limit_is_respected_after_restart(tmp_path):
    server = Releases(tmp_path)
    def limited(url, limit):
        server.calls.append(url)
        raise urllib.error.HTTPError(url, 429, "rate limited", {"Retry-After": "3600"}, None)
    service = manager(tmp_path, server); service.fetcher = limited
    with pytest.raises(Exception): service.stage_latest(threading.Event(), lambda *_: None)
    restarted = manager(tmp_path, server)
    with pytest.raises(Exception, match="retry"): restarted.stage_latest(threading.Event(), lambda *_: None)
    assert server.calls == [API]


def test_rate_limit_reset_header_is_respected(tmp_path):
    import time
    server = Releases(tmp_path); reset = int(time.time()) + 3600
    def limited(url, limit):
        raise urllib.error.HTTPError(url, 403, "rate limited", {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)}, None)
    service = manager(tmp_path, server); service.fetcher = limited
    with pytest.raises(RuntimeError): service.stage_latest(threading.Event(), lambda *_: None)
    assert service.describe()["retry_until"] >= reset


def test_staging_ledger_failure_preserves_previous_candidate(tmp_path, monkeypatch):
    server = Releases(tmp_path); service = manager(tmp_path, server)
    previous = service.stage_latest(threading.Event(), lambda *_: None)
    original_save = service._save
    old_directory = service.describe()["stage_directory"]
    def fail_new_state(*args):
        record = args[0] if args else service._state
        if record["stage_directory"] != old_directory: raise OSError("Synthetic ledger failure")
        return original_save(*args)
    monkeypatch.setattr(service, "_save", fail_new_state)
    with pytest.raises(RuntimeError): service.stage_latest(threading.Event(), lambda *_: None)
    assert service.describe()["staged_path"] == previous["staged_path"]
    assert service.describe()["last_stage"] == previous["last_stage"]
    assert len(list((tmp_path / "updates").glob("stage-*"))) == 1


@pytest.mark.parametrize("system,arch,version", [("linux", "x86_64", ""), ("darwin", "x86_64", "15.0"), ("darwin", "arm64", "14.6")])
def test_incompatible_host_never_downloads_the_archive(tmp_path, system, arch, version):
    server = Releases(tmp_path); service = manager(tmp_path, server)
    service.platform_info = lambda: (system, arch, version)
    with pytest.raises(RuntimeError): service.stage_latest(threading.Event(), lambda *_: None)
    assert len(server.calls) <= 2
    assert not list((tmp_path / "updates").glob("stage-*"))


@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), -1, 10**30])
def test_invalid_persisted_retry_deadline_does_not_disable_manual_updates(tmp_path, deadline):
    import math
    server = Releases(tmp_path)
    root = tmp_path / "updates"; root.mkdir()
    (root / "state.json").write_text(json.dumps({"retry_until": deadline}))
    service = manager(tmp_path, server)
    assert math.isfinite(service.describe()["retry_until"]) and service.describe()["retry_until"] == 0
    assert service.stage_latest(threading.Event(), lambda *_: None)["staged_version"] == "0.2.0"


def test_concurrent_staging_is_refused_without_changing_the_running_operation(tmp_path):
    server = Releases(tmp_path); service = manager(tmp_path, server)
    entered = threading.Event(); release = threading.Event(); result = []
    def waiting_fetch(url, limit):
        if url == API:
            entered.set()
            assert release.wait(5), "Test must release its own bounded synthetic fetch"
        return server.fetch(url, limit)
    service.fetcher = waiting_fetch
    def first():
        try: result.append(service.stage_latest(threading.Event(), lambda *_: None))
        except Exception as error: result.append(error)
    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(AppUpdateError, match="already in progress"):
            service.stage_latest(threading.Event(), lambda *_: None)
    finally:
        release.set(); thread.join(5)
    assert not thread.is_alive()
    assert len(result) == 1 and isinstance(result[0], dict) and result[0]["staged_version"] == "0.2.0"
    assert len(server.calls) == 3


@pytest.mark.parametrize("document", ["release", "manifest"])
def test_duplicate_remote_json_members_are_rejected_before_downloading_app(tmp_path, document):
    server = Releases(tmp_path)
    if document == "manifest":
        # Deliberately ambiguous but digest-consistent bytes; last-key-wins parsing
        # must not allow a later value to hide a conflicting policy field.
        server.manifest_bytes = server.manifest_bytes.replace(b'"channel": "stable"', b'"channel": "development", "channel": "stable"')
        asset = server.release["assets"][0]
        asset.update(size=len(server.manifest_bytes), digest="sha256:" + hashlib.sha256(server.manifest_bytes).hexdigest())
    def ambiguous_fetch(url, limit):
        value = server.fetch(url, limit)
        if document == "release" and url == API:
            value = value.replace(b'"digest": "sha256:', b'"digest": "invalid", "digest": "sha256:')
        return value
    service = manager(tmp_path, server); service.fetcher = ambiguous_fetch
    with pytest.raises(AppUpdateError, match="Duplicate"):
        service.stage_latest(threading.Event(), lambda *_: None)
    assert service.describe()["staged_path"] == ""
    assert not any(url.endswith(".tar.gz") for url in server.calls)
