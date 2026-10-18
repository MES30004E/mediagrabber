import copy
import io
import json
import struct

import pytest


def sample():
    return {"name": "SID", "value": "synthetic-session", "domain": ".youtube.com", "path": "/",
            "secure": True, "httpOnly": True, "hostOnly": False, "session": False,
            "expirationDate": 2147483647, "sameSite": "lax", "storeId": "incognito-store"}


class MemoryStore:
    def __init__(self): self.data = None
    def save(self, data): self.data = data
    def load(self): return self.data
    def delete(self): self.data = None


def test_native_capture_requires_pending_origin_consent_and_is_single_use(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    controller = CompanionController(tmp_path, MemoryStore())
    with pytest.raises(ValueError): controller.handle({"type": "hello"}, "chrome-extension://foreign/")
    with pytest.raises(ValueError): controller.handle({"type": "hello"}, ORIGIN)
    operation = controller.begin()
    hello = controller.handle({"type": "hello"}, ORIGIN)
    assert hello["operation_id"] == operation
    packet = {"type": "capture", "operation_id": operation, "nonce": hello["nonce"],
              "consent": True, "incognito": True, "store_id": "incognito-store", "cookies": [sample()]}
    denied = dict(packet, consent=False)
    with pytest.raises(ValueError): controller.handle(denied, ORIGIN)
    assert controller.store.data is None
    assert controller.handle(packet, ORIGIN)["status"] == "imported"
    assert "synthetic-session" not in json.dumps(controller.receipt())
    with pytest.raises(ValueError): controller.handle(packet, ORIGIN)


def test_native_readiness_is_reported_only_for_current_authorized_operation(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    controller = CompanionController(tmp_path, MemoryStore()); operation = controller.begin()
    controller.handle({"type": "ping", "incognito": True, "incognito_allowed": True}, ORIGIN)
    status = controller.poll_status(operation)
    assert status["extension_ready"] is True and status["operation_id"] == operation
    assert "nonce" not in status and "cookies" not in status
    assert controller.poll_status("other-operation") is None
    controller.handle({"type": "ping", "incognito": False, "incognito_allowed": True}, ORIGIN)
    assert controller.poll_status(operation)["extension_ready"] is False


def test_poll_reconciles_completed_capture_before_expiry_and_defers_while_locked(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    controller = CompanionController(tmp_path, MemoryStore()); operation = controller.begin()
    with controller._lock():
        assert controller.poll_status(operation, expire=True) == {"busy": True}
    hello = controller.handle({"type": "hello"}, ORIGIN)
    controller.handle(dict(type="capture", operation_id=operation, nonce=hello["nonce"], consent=True,
                          incognito=True, store_id="incognito-store", cookies=[sample()]), ORIGIN)
    assert controller.poll_status(operation, expire=True)["receipt"]["status"] == "imported"
    next_operation = controller.begin()
    assert controller.poll_status(next_operation, expire=True) == {"expired": True}
    with pytest.raises(ValueError): controller.handle({"type": "hello"}, ORIGIN)
    assert "synthetic-session" not in json.dumps(controller.poll_status(operation))


@pytest.mark.parametrize("change", [
    {"domain": "google.com"}, {"domain": "youtube.com.attacker.test"}, {"storeId": "normal"},
    {"value": "bad\nCookie: injected"}, {"expirationDate": float("nan")},
    {"partitionKey": {"topLevelSite": "https://other.test"}}, {"name": "bad\tname"},
])
def test_cookie_scope_and_attributes_are_validated(change):
    from morgan_media_downloader.youtube_companion.session import validate_cookies
    with pytest.raises(ValueError): validate_cookies([dict(sample(), **change)], "incognito-store")


def test_no_plaintext_fallback_and_failed_replacement_reports_failure(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    class FailingStore(MemoryStore):
        def save(self, data): raise RuntimeError("Do not echo any storage exception")
    controller = CompanionController(tmp_path, FailingStore()); operation = controller.begin()
    hello = controller.handle({"type": "hello"}, ORIGIN)
    packet = dict(type="capture", operation_id=operation, nonce=hello["nonce"], consent=True,
                  incognito=True, store_id="incognito-store", cookies=[sample()])
    assert controller.handle(packet, ORIGIN)["status"] == "storage_failed"
    assert all("synthetic-session" not in path.read_text() for path in tmp_path.iterdir() if path.is_file())


def test_session_cookiefile_is_in_memory_preserves_scope_and_can_be_removed():
    from morgan_media_downloader.youtube_companion.session import cookie_file
    store = MemoryStore(); store.save({"cookies": [sample()]})
    stream = cookie_file(store)
    assert isinstance(stream, io.StringIO)
    assert "#HttpOnly_.youtube.com\tTRUE" in stream.getvalue()
    from yt_dlp.cookies import YoutubeDLCookieJar
    jar = YoutubeDLCookieJar(stream); jar.load()
    entries = list(jar)
    assert entries[0].domain == ".youtube.com" and entries[0].secure
    # yt-dlp strips the Netscape HttpOnly marker during load; this is browser
    # JS policy, not an HTTP-cookie scope flag. Preserve the source attributes.
    assert store.data["cookies"][0]["httpOnly"] is True
    store.delete()
    with pytest.raises(ValueError): cookie_file(store)


def test_native_framing_rejects_truncated_oversized_and_duplicate_keys():
    from morgan_media_downloader.youtube_companion.native_host import read_message
    duplicate = b'{"type":"x","type":"y"}'
    for payload in [b"\x02", struct.pack("=I", 200000), struct.pack("=I", 5) + b"{}",
                    struct.pack("=I", len(duplicate)) + duplicate]:
        with pytest.raises(ValueError): read_message(io.BytesIO(payload))


def test_managed_session_reaches_existing_analysis_and_verification_without_disk(monkeypatch):
    from morgan_media_downloader import auth
    from morgan_media_downloader.youtube_companion.storage import KeychainSessionStore
    monkeypatch.setattr(KeychainSessionStore, "load", lambda _: {"cookies": [sample()]})
    options = auth.authentication_options("YouTube Companion")
    assert isinstance(options.get("cookiefile"), io.StringIO)
    assert "cookiesfrombrowser" not in options
    assert auth.authentication_options("None") == {}


def test_watch_later_format_failure_cannot_retry_without_managed_auth(monkeypatch):
    from morgan_media_downloader.downloader import analyse_with_authentication
    from morgan_media_downloader.youtube_companion.storage import KeychainSessionStore
    monkeypatch.setattr(KeychainSessionStore, "load", lambda _: {"cookies": [sample()]})
    attempts = []
    def extract(*args):
        attempts.append(args[4]); raise RuntimeError("Requested format is not available")
    monkeypatch.setattr("morgan_media_downloader.downloader.analyse_target", extract)
    with pytest.raises(RuntimeError):
        analyse_with_authentication(":ytwatchlater", None, "", "", "YouTube Companion", "Chrome", "", "")
    assert len(attempts) == 1 and isinstance(attempts[0].get("cookiefile"), io.StringIO)


def test_repeated_extraction_keeps_managed_cookie_source_reusable(monkeypatch):
    from morgan_media_downloader.auth import authentication_options
    from morgan_media_downloader.downloader import analyse_target
    from morgan_media_downloader.youtube_companion.storage import KeychainSessionStore
    from morgan_media_downloader.yt_runtime import RuntimeSnapshot
    from yt_dlp import YoutubeDL
    monkeypatch.setattr(KeychainSessionStore, "load", lambda _: {"cookies": [sample()]})
    received = []
    class OfflineYoutubeDL(YoutubeDL):
        def extract_info(self, *_args, **_kwargs):
            received.append([cookie.value for cookie in self.cookiejar])
            return {"title": "Synthetic", "webpage_url": "https://www.youtube.com/watch?v=test"}
    options = authentication_options("YouTube Companion")
    runtime = RuntimeSnapshot("test", "Bundled", OfflineYoutubeDL)
    for _ in range(2): analyse_target("synthetic search", auth_options=options, runtime=runtime)
    assert received == [["synthetic-session"], ["synthetic-session"]]


def test_poll_does_not_block_while_native_capture_owns_keychain_lock(tmp_path):
    import fcntl
    import os
    import subprocess
    import sys
    from pathlib import Path
    from morgan_media_downloader.youtube_companion.bridge import CompanionController
    controller = CompanionController(tmp_path, MemoryStore()); controller.begin()
    fd = os.open(tmp_path / "lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        root = Path(__file__).resolve().parents[1]
        code = 'from pathlib import Path; import sys; from morgan_media_downloader.youtube_companion.bridge import CompanionController; assert CompanionController(Path(sys.argv[1])).receipt() is None'
        result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)],
                                env=dict(os.environ, PYTHONPATH=str(root / "src")), capture_output=True, timeout=2)
        assert result.returncode == 0, result.stderr
    finally: os.close(fd)


def test_old_settings_window_cannot_cancel_new_capture_request(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    controller = CompanionController(tmp_path, MemoryStore())
    old = controller.begin(); new = controller.begin()
    controller.cancel(old)
    assert controller.handle({"type": "hello"}, ORIGIN)["operation_id"] == new
    controller.cancel(new)
    with pytest.raises(ValueError): controller.handle({"type": "hello"}, ORIGIN)


def test_expired_capture_and_cookie_session_require_reconnect(tmp_path, monkeypatch):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    from morgan_media_downloader.youtube_companion.session import cookie_file
    controller = CompanionController(tmp_path, MemoryStore()); controller.begin()
    monkeypatch.setattr("morgan_media_downloader.youtube_companion.bridge.time.time", lambda: 9000000000)
    with pytest.raises(ValueError, match="expired"): controller.handle({"type": "hello"}, ORIGIN)
    controller.store.save({"cookies": [sample()]})
    with pytest.raises(ValueError, match="expired"): cookie_file(controller.store)


def test_replace_and_disconnect_failure_never_erase_old_session(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    class Store(MemoryStore):
        def save(self, data): raise ValueError("synthetic storage denial")
        def delete(self): raise ValueError("synthetic deletion denial")
    store = Store(); store.data = {"cookies": [sample()]}
    controller = CompanionController(tmp_path, store); operation = controller.begin()
    hello = controller.handle({"type": "hello"}, ORIGIN)
    result = controller.handle(dict(type="capture", operation_id=operation, nonce=hello["nonce"], consent=True,
                                    incognito=True, store_id="incognito-store", cookies=[dict(sample(), value="replacement")]), ORIGIN)
    assert result["status"] == "storage_failed" and store.data["cookies"][0]["value"] == "synthetic-session"
    with pytest.raises(ValueError): controller.disconnect()
    assert store.data is not None


def test_control_symlink_is_rejected_without_reading_target(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import CompanionController, ORIGIN
    controller = CompanionController(tmp_path / "control", MemoryStore()); controller.begin()
    (controller.root / "pending.json").unlink()
    target = tmp_path / "unrelated"; target.write_text("private synthetic target")
    (controller.root / "pending.json").symlink_to(target)
    with pytest.raises(OSError): controller.handle({"type": "hello"}, ORIGIN)
    assert target.read_text() == "private synthetic target"


def test_download_option_builder_can_defer_authentication_to_attempt(monkeypatch):
    from morgan_media_downloader.formats import build_ydl_options
    from morgan_media_downloader.models import DownloadOptions
    from morgan_media_downloader.youtube_companion.storage import KeychainSessionStore
    def denied(_): raise AssertionError("Attempt already owns a snapshot; do not reload Keychain")
    monkeypatch.setattr(KeychainSessionStore, "load", denied)
    result = build_ydl_options(DownloadOptions(authentication_mode="YouTube Companion"), include_authentication=False)
    assert "cookiefile" not in result and "cookiesfrombrowser" not in result


def test_missing_secure_session_is_a_failed_job_not_uncaught_queue_error(tmp_path, monkeypatch):
    import threading
    from morgan_media_downloader.downloader import download_job
    from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem, JobStatus
    from morgan_media_downloader.youtube_companion.storage import KeychainSessionStore
    monkeypatch.setattr(KeychainSessionStore, "load", lambda _: None)
    job = DownloadJob(MediaItem("https://www.youtube.com/watch?v=synthetic", "Synthetic"),
                      DownloadOptions(download_dir=str(tmp_path), authentication_mode="YouTube Companion"))
    result = download_job(job, None, "", "", lambda _: None, threading.Event())
    assert result.status == JobStatus.FAILED
    assert "auth" in (result.failure_code + result.error).lower()
