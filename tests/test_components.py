import json
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from test_yt_runtime import manager, ReleaseServer


def catalog(tmp_path, fetcher):
    from morgan_media_downloader.components import ComponentCatalog
    runtime = manager(tmp_path, ReleaseServer("2026.08.19")); runtime.initialize()
    return ComponentCatalog(runtime, root=tmp_path / "components", fetcher=fetcher)


def release(url, timeout):
    assert timeout == 8
    repo = url.split("/repos/")[1].split("/releases/")[0]
    return json.dumps({"tag_name": "v1.3.1", "draft": False, "prerelease": False,
                       "html_url": f"https://github.com/{repo}/releases/tag/v1.3.1"}).encode()


def test_release_inventory_persists_only_validated_official_metadata_and_survives_failure(tmp_path):
    service = catalog(tmp_path, release)
    records = service.check_releases()
    assert set(records) == {"app", "provider", "media_tools"}
    assert records["app"]["latest"] == "v1.3.1"
    checked = records["app"]["last_checked"]
    def offline(*_): raise OSError("https://fixture:synthetic-password@example.test")
    restarted = catalog(tmp_path, offline)
    records = restarted.check_releases()
    assert records["app"]["latest"] == "v1.3.1"
    assert records["app"]["last_checked"] == checked
    assert records["app"]["last_error"]
    assert "synthetic-password" not in restarted.path.read_text()


@pytest.mark.parametrize("payload", [
    {"tag_name": "v2", "draft": True}, {"tag_name": "v2", "prerelease": True},
    {"tag_name": "../../private"}, {"tag_name": "v2", "html_url": "https://example.test/release"},
    [], {"tag_name": "<script>"},
])
def test_invalid_release_cannot_replace_last_known_version(tmp_path, payload):
    service = catalog(tmp_path, release); service.check_releases()
    if isinstance(payload, dict):
        payload = {"tag_name": "v2", "draft": False, "prerelease": False,
                   "html_url": "https://github.com/MES30004E/mediagrabber/releases/tag/v2", **payload}
    service.fetcher = lambda *_: json.dumps(payload).encode()
    info = service.check_releases()
    assert info["app"]["latest"] == "v1.3.1"
    assert info["app"]["last_error"]


def test_automatic_catalog_checks_are_daily_and_failures_back_off(tmp_path, monkeypatch):
    now = datetime(2026, 10, 19, tzinfo=timezone.utc); calls = []
    def fetch(url, timeout): calls.append(url); return release(url, timeout)
    service = catalog(tmp_path, fetch); monkeypatch.setattr(service, "_now", lambda: now)
    service.check_releases(automatic=True); assert len(calls) == 3
    service.check_releases(automatic=True); assert len(calls) == 3
    service.check_releases(); assert len(calls) == 6
    now += timedelta(days=1)
    def fail(*_): calls.append("failure"); raise TimeoutError()
    service.fetcher = fail
    service.check_releases(automatic=True); assert len(calls) == 9
    service.check_releases(automatic=True); assert len(calls) == 9
    now += timedelta(hours=1)
    service.check_releases(automatic=True); assert len(calls) == 12


def test_404_does_not_claim_up_to_date_or_a_successful_check(tmp_path):
    def absent(url, *_): raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    service = catalog(tmp_path, absent)
    record = service.check_releases()["app"]
    assert not record.get("last_checked") and not record.get("latest")
    assert "404" in record["last_error"]


def test_github_retry_after_is_respected_even_by_manual_checks_and_after_restart(tmp_path, monkeypatch):
    now = datetime(2026, 10, 19, tzinfo=timezone.utc); calls = []
    def limited(url, *_):
        calls.append(url)
        raise urllib.error.HTTPError(url, 429, "Rate limited", {"Retry-After": "7200"}, None)
    service = catalog(tmp_path, limited); monkeypatch.setattr(service, "_now", lambda: now)
    service.check_releases(); assert len(calls) == 1
    restarted = catalog(tmp_path, limited); monkeypatch.setattr(restarted, "_now", lambda: now)
    now += timedelta(hours=1)
    restarted.check_releases(); assert len(calls) == 1
    now += timedelta(hours=1)
    restarted.check_releases(); assert len(calls) == 2


def test_relative_retry_after_starts_when_response_arrives_not_when_request_starts(tmp_path, monkeypatch):
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    def delayed(url, *_):
        nonlocal now
        now += timedelta(seconds=8)
        raise urllib.error.HTTPError(url, 429, "Rate limited", {"Retry-After": "60"}, None)
    service = catalog(tmp_path, delayed); monkeypatch.setattr(service, "_now", lambda: now)
    records = service.check_releases()
    assert records["app"]["retry_until"] == "2026-10-19T00:01:08+00:00"


def test_inventory_reports_real_local_components_without_fake_extension_or_update_success(tmp_path, monkeypatch):
    from morgan_media_downloader.diagnostics import CheckResult
    service = catalog(tmp_path, release)
    monkeypatch.setattr("morgan_media_downloader.components._binary_check", lambda name: CheckResult(name, True, f"{name} version 6.1.1 Copyright test"))
    rows = {row["id"]: row for row in service.inventory()}
    assert set(rows) == {"app", "yt_dlp", "provider", "ffmpeg", "ffprobe", "companion"}
    assert rows["ffmpeg"]["installed"] == "ffmpeg version 6.1.1 Copyright test"
    assert "unconfirmed" in rows["companion"]["compatibility"].lower()
    assert rows["app"]["last_update"] == "Not managed yet"
    assert rows["provider"]["rollback"] == "Not managed yet"
    assert rows["yt_dlp"]["installed"] == "2025.01.01 (Bundled)"


def test_public_fetcher_sends_no_credentials_and_bounds_response(tmp_path, monkeypatch):
    service = catalog(tmp_path, release); requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, size): assert size <= 2_097_153; return b"{}"
    def open_url(request, timeout): requests.append(request); return Response()
    monkeypatch.setattr("urllib.request.urlopen", open_url)
    service.fetcher = service._fetch
    service.check_releases()
    assert len(requests) == 3
    assert all(not any(k.lower() in {"authorization", "cookie"} for k, _ in r.header_items()) for r in requests)
    with pytest.raises(ValueError): service._fetch("https://example.test", 8)


def test_empty_media_tool_version_output_is_unavailable_not_a_catalog_crash(monkeypatch):
    from types import SimpleNamespace
    from morgan_media_downloader.diagnostics import _binary_check
    monkeypatch.setattr("morgan_media_downloader.diagnostics.find_binary", lambda _: "/fixture/tool")
    monkeypatch.setattr("morgan_media_downloader.diagnostics.subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""))
    result = _binary_check("ffmpeg")
    assert not result.available and "no version" in result.detail
