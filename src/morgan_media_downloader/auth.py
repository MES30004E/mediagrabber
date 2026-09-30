from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .logging_setup import redact_secrets
from .yt_runtime import RuntimeSnapshot


YOUTUBE_ROBOTS_URL = "https://www.youtube.com/robots.txt"
BROWSER_KEYS = {"Chrome": "chrome", "Chromium": "chromium", "Firefox": "firefox",
                "Safari": "safari", "Edge": "edge"}


def normalise_authentication_mode(mode: str) -> str:
    return {"Browser cookies": "Browser Cookies", "None": "None",
            "Imported cookies.txt": "Imported cookies.txt", "Auto": "Auto"}.get(mode, mode)


def authentication_options(mode: str, browser: str = "Chrome", profile: str = "",
                           cookies_file: str = "") -> dict[str, Any]:
    mode = normalise_authentication_mode(mode)
    if mode == "Browser Cookies":
        browser_key = BROWSER_KEYS.get(browser, browser.casefold())
        return {"cookiesfrombrowser": (browser_key, profile or None, None, None)}
    if mode == "Imported cookies.txt":
        path = Path(cookies_file).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"cookies.txt not found: {path}")
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                header = stream.readline().strip()
        except OSError as error:
            raise ValueError("cookies.txt could not be read") from error
        if "netscape http cookie file" not in header.casefold():
            raise ValueError("cookies.txt invalid: expected Netscape cookies.txt format")
        return {"cookiefile": str(path)}
    return {}


def configured_authentication_options(browser: str = "Chrome", profile: str = "",
                                       cookies_file: str = "") -> tuple[str, dict[str, Any]]:
    """Choose the configured Auto fallback without ever combining cookie sources."""
    if cookies_file:
        return "Imported cookies.txt", authentication_options("Imported cookies.txt", cookies_file=cookies_file)
    return "Browser Cookies", authentication_options("Browser Cookies", browser, profile)


def requires_authentication(error: BaseException | str) -> bool:
    text = str(error).casefold()
    return any(term in text for term in (
        "private video", "private playlist", "members-only", "members only", "sign in required",
        "login required", "account verification", "age-restricted", "age restricted",
        "confirm you are not a bot", "confirm you're not a bot", "authentication required", "this video is private",
    ))


def format_unavailable(error: BaseException | str) -> bool:
    return "requested format is not available" in str(error).casefold()


def browser_profiles(browser: str, home: Path | None = None) -> list[tuple[str, str]]:
    """Return (friendly name, yt-dlp profile directory) without reading browser cookies."""
    home = home or Path.home()
    roots = {
        "Chrome": home / "Library/Application Support/Google/Chrome",
        "Chromium": home / "Library/Application Support/Chromium",
        "Edge": home / "Library/Application Support/Microsoft Edge",
    }
    root = roots.get(browser)
    if not root:
        return [("Default", "")]
    names: dict[str, str] = {}
    try:
        payload = json.loads((root / "Local State").read_text(encoding="utf-8"))
        cache = payload.get("profile", {}).get("info_cache", {})
        if isinstance(cache, dict):
            for directory, detail in cache.items():
                if isinstance(detail, dict):
                    names[directory] = str(detail.get("name") or directory)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    directories = [path.name for path in root.glob("Profile *") if path.is_dir()]
    if (root / "Default").is_dir() or "Default" in names:
        directories.insert(0, "Default")
    for directory in names:
        if directory not in directories:
            directories.append(directory)
    result = [(names.get(directory, directory), directory) for directory in directories]
    return result or [("Default", "")]


def test_youtube_login(mode: str, browser: str, profile: str, cookies_file: str,
                       proxy: str | None = None, runtime: RuntimeSnapshot | None = None) -> tuple[bool, str]:
    mode = normalise_authentication_mode(mode)
    if mode == "None":
        return False, "Not authenticated"
    if runtime is None:
        from yt_dlp import YoutubeDL
    else:
        YoutubeDL = runtime.youtube_dl
    options = {"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": 1, "proxy": proxy}
    try:
        if mode == "Auto":
            # Auto deliberately proves that ordinary public extraction works without
            # exposing account cookies. Explicit Browser Cookies tests cookie access.
            target = "https://www.youtube.com/watch?v=9UjexPhnxro"
        else:
            target = "https://www.youtube.com/feed/playlists"
            options.update(authentication_options(mode, browser, profile, cookies_file))
        with YoutubeDL(options) as ydl:
            ydl.extract_info(target, download=False)
        if mode == "Auto":
            return True, "No login required. Auto will use configured authentication only when YouTube requires it."
        return True, "Authenticated. YouTube accepted the configured login cookies."
    except (FileNotFoundError, ValueError) as error:
        return False, f"cookies.txt invalid: {redact_secrets(str(error))}"
    except Exception as error:
        safe = redact_secrets(str(error))
        if mode == "Browser Cookies" and any(term in safe.casefold() for term in ("cookie", "keyring", "keychain", "browser")):
            return False, f"Browser cookies unavailable: {safe}"
        return False, f"Authentication failed: {safe}"
