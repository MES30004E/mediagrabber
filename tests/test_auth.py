from pathlib import Path

import pytest

from morgan_media_downloader.auth import YOUTUBE_ROBOTS_URL, authentication_options, browser_profiles
from morgan_media_downloader.downloader import analyse_target, analyse_with_authentication


def test_browser_cookie_options_include_profile():
    assert authentication_options("Browser cookies", "Chrome", "Profile 2") == {
        "cookiesfrombrowser": ("chrome", "Profile 2", None, None)
    }


def test_none_and_auto_do_not_apply_stale_cookie_settings():
    assert authentication_options("None", "Chrome", "Profile 9", "/private/cookies.txt") == {}
    assert authentication_options("Auto", "Chrome", "Profile 9", "/private/cookies.txt") == {}


def test_imported_cookie_file_uses_yt_dlp_cookiefile(tmp_path: Path):
    cookie = tmp_path / "cookies.txt"; cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    assert authentication_options("Imported cookies.txt", cookies_file=str(cookie)) == {"cookiefile": str(cookie)}


def test_missing_cookie_file_fails_without_reading_cache():
    with pytest.raises(FileNotFoundError):
        authentication_options("Imported cookies.txt", cookies_file="/not/a/file")


@pytest.mark.parametrize("browser", ["Chrome", "Firefox", "Safari"])
def test_supported_browser_cookie_modes_reach_yt_dlp(browser: str):
    assert authentication_options("Browser cookies", browser)["cookiesfrombrowser"][0] == browser.lower()


def test_cookies_proxy_and_po_provider_coexist(monkeypatch):
    captured = {}

    class FakeYDL:
        def __init__(self, options): captured.update(options)
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def extract_info(self, *_args, **_kwargs):
            return {"title": "Public test", "webpage_url": "https://youtube.test/watch?v=1"}

    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda: FakeYDL)
    auth = authentication_options("Browser cookies", "Firefox", "qa-profile")
    analyse_target("https://youtube.test/watch?v=1", "socks5h://127.0.0.1:9150",
                   "http://127.0.0.1:4416", auth_options=auth)
    assert captured["cookiesfrombrowser"] == ("firefox", "qa-profile", None, None)
    assert captured["proxy"] == "socks5h://127.0.0.1:9150"
    assert captured["extractor_args"]["youtubepot-bgutilhttp"]["base_url"] == ["http://127.0.0.1:4416"]


@pytest.mark.parametrize("value,target", [
    (":ytwatchlater", ":ytwatchlater"),
    ("https://www.youtube.com/feed/watch_later", "https://www.youtube.com/playlist?list=WL"),
    ("https://www.youtube.com/playlist?list=WL", "https://www.youtube.com/playlist?list=WL"),
    ("https://www.youtube.com/playlist?list=PLprivatefixture", "https://www.youtube.com/playlist?list=PLprivatefixture"),
])
def test_private_collection_targets_keep_authenticated_analysis_boundary(monkeypatch, value, target):
    captured = {}

    class FakeYDL:
        def __init__(self, options): captured.update(options)
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def extract_info(self, received, download=False):
            assert received == target
            assert download is False
            return {"title": "Private fixture", "entries": [
                {"title": "Selected video", "webpage_url": "https://www.youtube.com/watch?v=fixture", "playlist_index": 1}]}

    monkeypatch.setattr("morgan_media_downloader.downloader._ydl_class", lambda: FakeYDL)
    items, effective = analyse_with_authentication(
        value, "socks5h://127.0.0.1:9150", "http://127.0.0.1:4416", "",
        "Browser Cookies", "Firefox", "test-profile", "")
    assert effective == "Browser Cookies"
    assert captured["cookiesfrombrowser"] == ("firefox", "test-profile", None, None)
    assert captured["proxy"] == "socks5h://127.0.0.1:9150"
    assert items[0].source_url == "https://www.youtube.com/watch?v=fixture"
    assert items[0].collection_title == "Private fixture"


def test_auto_public_starts_without_cookies(monkeypatch):
    attempts = []
    monkeypatch.setattr("morgan_media_downloader.downloader.analyse_target",
                        lambda *args, **kwargs: attempts.append(args[4]) or [])
    _, effective = analyse_with_authentication("url", None, "provider", "", "Auto",
                                                "Chrome", "Profile 1", "/stale/missing-cookies.txt")
    assert attempts == [{}]
    assert effective == "Auto -> None"


@pytest.mark.parametrize("value", [":ytwatchlater", "https://www.youtube.com/playlist?list=WL", "https://www.youtube.com/feed/watch_later"])
def test_auto_watch_later_starts_with_configured_authentication(monkeypatch, value):
    attempts = []
    monkeypatch.setattr("morgan_media_downloader.downloader.analyse_target", lambda *args: attempts.append(args[4]) or [])
    _, effective = analyse_with_authentication(value, None, "provider", "", "Auto", "Firefox", "chosen", "")
    assert attempts == [{"cookiesfrombrowser": ("firefox", "chosen", None, None)}]
    assert effective == "Auto -> Browser Cookies"


def test_arbitrary_missing_playlist_does_not_trigger_auth_fallback(monkeypatch):
    attempts = []
    def fail(*args):
        attempts.append(args[4]); raise RuntimeError("The playlist does not exist")
    monkeypatch.setattr("morgan_media_downloader.downloader.analyse_target", fail)
    with pytest.raises(RuntimeError, match="does not exist"):
        analyse_with_authentication("https://www.youtube.com/playlist?list=missing", None, "", "", "Auto", "Chrome", "", "")
    assert attempts == [{}]


def test_explicit_none_watch_later_does_not_read_cookies(monkeypatch):
    attempts = []
    monkeypatch.setattr("morgan_media_downloader.downloader.analyse_target", lambda *args: attempts.append(args[4]) or [])
    analyse_with_authentication(":ytwatchlater", None, "", "", "None", "Chrome", "", "")
    assert attempts == [{}]


def test_auto_login_required_retries_with_selected_browser_profile(monkeypatch):
    attempts = []
    def analyse(*args, **_kwargs):
        attempts.append(args[4])
        if len(attempts) == 1: raise RuntimeError("Sign in required")
        return []
    monkeypatch.setattr("morgan_media_downloader.downloader.analyse_target", analyse)
    _, effective = analyse_with_authentication("url", None, "provider", "", "Auto",
                                                "Chrome", "Profile 2", "")
    assert attempts == [{}, {"cookiesfrombrowser": ("chrome", "Profile 2", None, None)}]
    assert effective == "Auto -> Browser Cookies"


def test_public_cookie_format_failure_retries_once_without_cookies(monkeypatch):
    attempts = []
    def analyse(*args, **_kwargs):
        attempts.append(args[4])
        if len(attempts) == 1: raise RuntimeError("Requested format is not available")
        return []
    monkeypatch.setattr("morgan_media_downloader.downloader.analyse_target", analyse)
    _, effective = analyse_with_authentication("url", None, "provider", "", "Browser Cookies",
                                                "Firefox", "qa", "")
    assert len(attempts) == 2 and attempts[1] == {}
    assert effective == "Browser Cookies -> None"


def test_private_cookie_failure_never_drops_authentication(monkeypatch):
    attempts = []
    def analyse(*args, **_kwargs):
        attempts.append(args[4]); raise RuntimeError("Private video: requested format is not available")
    monkeypatch.setattr("morgan_media_downloader.downloader.analyse_target", analyse)
    with pytest.raises(RuntimeError):
        analyse_with_authentication("url", None, "provider", "", "Browser Cookies", "Chrome", "", "")
    assert len(attempts) == 1 and "cookiesfrombrowser" in attempts[0]


def test_robots_helper_url_is_exact_and_chrome_friendly_names_are_safe(tmp_path: Path):
    assert YOUTUBE_ROBOTS_URL == "https://www.youtube.com/robots.txt"
    root = tmp_path / "Library/Application Support/Google/Chrome"
    (root / "Default").mkdir(parents=True); (root / "Profile 1").mkdir()
    (root / "Local State").write_text('{"profile":{"info_cache":{"Default":{"name":"Morgan"},"Profile 1":{"name":"School"}}}}')
    assert browser_profiles("Chrome", tmp_path) == [("Morgan", "Default"), ("School", "Profile 1")]
