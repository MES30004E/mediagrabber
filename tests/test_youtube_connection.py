import http.cookiejar
import io
from pathlib import Path

import pytest

from morgan_media_downloader import auth
from morgan_media_downloader.yt_runtime import RuntimeSnapshot


def cookie(name="SID", domain=".youtube.com"):
    return http.cookiejar.Cookie(0, name, "sensitive-value", None, False, domain, True,
                                True, "/", True, True, None, True, None, None, {})


def verify(monkeypatch, page=b'ytcfg.set({"LOGGED_IN":true});', cookies=None, failure=None, **kwargs):
    captured = {}
    class YDL:
        def __init__(self, options):
            captured.update(options)
            self.params = dict(options)
            self.cookiejar = list([cookie()] if cookies is None else cookies)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def urlopen(self, request):
            captured["target"] = request
            if failure: raise failure
            return io.BytesIO(page)
    function = getattr(auth, "verify_youtube_connection", None)
    assert callable(function), "Verification must report separate cookie/session evidence"
    result = function("Browser Cookies", "Firefox", "", "", runtime=RuntimeSnapshot("test", "Bundled", YDL), **kwargs)
    return result, captured


def test_server_confirmation_not_public_extraction_proves_sign_in(monkeypatch):
    result, captured = verify(monkeypatch, proxy="socks5h://127.0.0.1:9911", provider_url="http://localhost:4416")
    assert result.state == "authenticated" and result.cookies_readable is True
    assert "private" in result.message.lower() and "sensitive-value" not in repr(result)
    assert captured["cookiesfrombrowser"] == ("firefox", None, None, None)
    assert captured["proxy"] == "socks5h://127.0.0.1:9911"
    assert captured["target"] == "https://www.youtube.com/account"
    assert "cookiefile" not in captured


@pytest.mark.parametrize("page,state", [
    (b'ytcfg.set({"LOGGED_IN":false});', "reconnect"),
    (b'<html>Public access works</html>', "unconfirmed"),
    (b'ytcfg.set({"LOGGED_IN":"true"});', "unconfirmed"),
])
def test_cookie_presence_or_public_page_is_not_login_proof(monkeypatch, page, state):
    result, _ = verify(monkeypatch, page=page)
    assert result.state == state and result.cookies_readable is True
    assert not result.authenticated


def test_empty_youtube_cookie_source_is_actionable(monkeypatch):
    result, _ = verify(monkeypatch, cookies=[cookie(domain=".example.test")])
    assert result.state == "no_cookies" and not result.authenticated
    assert "profile" in result.message.lower()


@pytest.mark.parametrize("error,state", [
    ("HTTP Error 429: Too Many Requests token=private-token", "rate_limited"),
    ("Sign in to confirm you're not a bot Cookie: private-token", "verification_required"),
    ("PO Token required signature=private-token", "provider_required"),
    ("Permission denied /private/person/Cookies password=private-token", "cookies_unavailable"),
])
def test_errors_are_classified_without_raw_exception_details(monkeypatch, error, state):
    result, _ = verify(monkeypatch, failure=RuntimeError(error))
    assert result.state == state
    assert "private-token" not in repr(result) and "/private/person" not in repr(result)
    assert result.actions


def test_firefox_profiles_and_installed_browser_discovery_do_not_read_cookies(tmp_path):
    root = tmp_path / "Library/Application Support/Firefox"
    (root / "Profiles/abc.default").mkdir(parents=True)
    (root / "profiles.ini").write_text("[Profile0]\nName=Personal\nIsRelative=1\nPath=Profiles/abc.default\nDefault=1\n")
    apps = tmp_path / "Applications"; (apps / "Firefox.app").mkdir(parents=True)
    assert auth.browser_profiles("Firefox", tmp_path) == [("Personal", str(root / "Profiles/abc.default"))]
    discover = getattr(auth, "discover_browsers", None)
    assert callable(discover), "Connect must discover real browser sources"
    sources = discover(tmp_path, [apps])
    assert [source.name for source in sources] == ["Firefox"]
    assert sources[0].application == apps / "Firefox.app"


def test_deleted_chromium_profile_not_offered_from_stale_local_state(tmp_path):
    root = tmp_path / "Library/Application Support/Google/Chrome"; root.mkdir(parents=True)
    (root / "Local State").write_text('{"profile":{"info_cache":{"Profile 9":{"name":"Deleted"}}}}')
    assert auth.browser_profiles("Chrome", tmp_path) == [("Default", "")]


def test_auto_verification_uses_configured_source_without_changing_auto_download_policy(monkeypatch):
    function = getattr(auth, "verify_youtube_connection", None)
    assert callable(function)
    captured = {}
    class YDL:
        def __init__(self, options): captured.update(options); self.cookiejar = []
        def __enter__(self): return self
        def __exit__(self, *_): pass
    result = function("Auto", "Chrome", "Profile 2", "", runtime=RuntimeSnapshot("test", "Bundled", YDL))
    assert result.state == "no_cookies"
    assert captured["cookiesfrombrowser"] == ("chrome", "Profile 2", None, None)
    assert auth.authentication_options("Auto", "Chrome", "Profile 2") == {}


def test_import_verification_does_not_rewrite_sensitive_source(tmp_path, monkeypatch):
    from yt_dlp import YoutubeDL
    source = tmp_path / "cookies.txt"
    original = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tfixture-secret\n"
    source.write_text(original)
    monkeypatch.setattr(YoutubeDL, "urlopen", lambda *_: io.BytesIO(b'ytcfg.set({"LOGGED_IN":true});'))
    result = auth.verify_youtube_connection("Imported cookies.txt", "Chrome", "", str(source))
    assert result.authenticated
    assert source.read_text() == original, "Verification must not save/refresh the user's cookie file"


def test_none_mode_only_proves_public_access(monkeypatch):
    from yt_dlp import YoutubeDL
    monkeypatch.setattr(YoutubeDL, "urlopen", lambda *_: io.BytesIO(b""))
    result = auth.verify_youtube_connection("None", "Chrome", "", "")
    assert result.state == "public_access" and not result.authenticated
    assert result.cookies_readable is None
