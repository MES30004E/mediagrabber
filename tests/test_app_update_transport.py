"""Exercise real transport policy/streaming with only the external socket replaced."""
import io
import threading
import urllib.request

import pytest

from morgan_media_downloader import app_updates as module

URL = "https://github.com/MES30004E/mediagrabber/releases/download/v0.2.0/Morgan-Media-Downloader-0.2.0-macos-arm64.tar.gz"


@pytest.mark.parametrize("url", ["http://github.com/MES30004E/mediagrabber/releases/download/v0.2.0/release.json",
    "https://github.com/other/repo/releases/download/v0.2.0/release.json", "https://example.test/archive"])
def test_unapproved_initial_source_never_opens_a_socket(monkeypatch, url):
    def unexpected(*args, **kwargs): pytest.fail("Unapproved source reached HTTP opener")
    monkeypatch.setattr(module.urllib.request, "build_opener", unexpected)
    with pytest.raises(module.AppUpdateError, match="Unapproved"): module.fetch(url, 100)


def test_public_request_does_not_attach_authentication_or_cookie_handlers(monkeypatch):
    class Opener:
        def open(self, request, *, timeout):
            assert request.full_url == module.API and timeout == 15
            headers = {key.lower(): value for key, value in request.header_items()}
            assert "authorization" not in headers and "cookie" not in headers
            assert set(headers) == {"user-agent", "accept", "x-github-api-version"}
            return io.BytesIO(b"{}")
    def opener(*handlers):
        assert len(handlers) == 1 and isinstance(handlers[0], module._SafeRedirect)
        return Opener()
    monkeypatch.setattr(module.urllib.request, "build_opener", opener)
    assert module.fetch(module.API, 2) == b"{}"


@pytest.mark.parametrize("url", ["http://release-assets.githubusercontent.com/asset", "https://example.test/asset",
    "https://github.com.evil.test/asset", "https://user:synthetic-password@github.com/asset", "https://github.com:8443/asset"])
def test_release_redirect_rejects_unapproved_sources(url):
    with pytest.raises(module.AppUpdateError, match="unapproved"):
        module._SafeRedirect(URL).redirect_request(urllib.request.Request(URL), None, 302, "Found", {}, url)


def test_release_redirect_accepts_https_github_asset_host():
    url = "https://release-assets.githubusercontent.com/asset?synthetic=1"
    request = module._SafeRedirect(URL).redirect_request(urllib.request.Request(URL), None, 302, "Found", {}, url)
    assert request.full_url == url


def test_metadata_read_is_bounded(monkeypatch):
    monkeypatch.setattr(module, "_open", lambda _: io.BytesIO(b"12345"))
    with pytest.raises(module.AppUpdateError, match="size limit"): module.fetch(module.API, 4)


@pytest.mark.parametrize("data,expected", [(b"abcd", 3), (b"ab", 3)])
def test_streaming_rejects_oversized_or_truncated_body(tmp_path, monkeypatch, data, expected):
    monkeypatch.setattr(module, "_open", lambda _: io.BytesIO(data))
    with pytest.raises(module.AppUpdateError):
        module.download(URL, tmp_path / "archive", expected, threading.Event(), lambda *_: None)


def test_streaming_progress_and_cancellation_stop_before_reading_another_chunk(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "_open", lambda _: io.BytesIO(b"x" * 300000))
    cancel = threading.Event(); events = []
    def progress(event): events.append(event); cancel.set()
    destination = tmp_path / "archive"
    with pytest.raises(InterruptedError): module.download(URL, destination, 300000, cancel, progress)
    assert destination.stat().st_size == 262144
    assert events == [{"stage": "Downloading", "downloaded": 262144, "total": 300000}]


@pytest.mark.parametrize("source,target", [
    (module.API, "https://github.com/other/repository/releases/download/v9.9.9/release.json"),
    (module.API, "https://release-assets.githubusercontent.com/claimed-metadata"),
    (URL, "https://github.com/other/repository/releases/download/v9.9.9/release.json"),
    (URL, URL.replace("v0.2.0/", "v9.9.9/")),
])
def test_authoritative_metadata_and_asset_redirects_cannot_change_repository_or_release(monkeypatch, source, target):
    def opener(handler):
        class Opener:
            def open(self, request, **kwargs):
                return handler.redirect_request(request, None, 302, "Found", {}, target)
        return Opener()
    monkeypatch.setattr(module.urllib.request, "build_opener", opener)
    with pytest.raises(module.AppUpdateError, match="redirect"):
        module._open(source)
