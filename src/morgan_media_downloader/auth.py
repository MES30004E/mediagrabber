from __future__ import annotations

import json
import configparser
import re
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    if mode == "YouTube Companion":
        from .youtube_companion.session import cookie_file
        try: return {"cookiefile": cookie_file()}
        except Exception:
            raise ValueError("Authentication required: secure YouTube session unavailable. Reconnect with Chrome Incognito and capture again.") from None
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


def fresh_authentication_options(options: dict[str, Any]) -> dict[str, Any]:
    """Give each yt-dlp context its own memory stream, including retry passes.

    yt-dlp consumes and saves file-like cookie sources on close. Never share a
    mutable cursor or an updated jar between contexts or persist it to disk.
    """
    result = dict(options)
    source = result.get("cookiefile")
    if isinstance(source, io.StringIO): result["cookiefile"] = io.StringIO(source.getvalue())
    return result


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
    if browser == "Firefox":
        root = home / "Library/Application Support/Firefox"
        config = configparser.ConfigParser(interpolation=None)
        try:
            config.read(root / "profiles.ini", encoding="utf-8")
            profiles = []
            for section in config.sections():
                if section.startswith("Profile") and config.has_option(section, "Path"):
                    path = Path(config.get(section, "Path"))
                    if config.getboolean(section, "IsRelative", fallback=True): path = root / path
                    if path.is_dir(): profiles.append((config.get(section, "Name", fallback=section), str(path)))
            return profiles or [("Default", "")]
        except (OSError, ValueError, configparser.Error):
            return [("Default", "")]
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
    if (root / "Default").is_dir():
        directories.insert(0, "Default")
    for directory in names:
        if directory not in directories and (root / directory).is_dir() and Path(directory).name == directory:
            directories.append(directory)
    result = [(names.get(directory, directory), directory) for directory in directories]
    return result or [("Default", "")]


@dataclass(frozen=True)
class BrowserSource:
    name: str
    application: Path | None


def discover_browsers(home: Path | None = None, applications: list[Path] | None = None) -> list[BrowserSource]:
    """Inspect app/profile locations only; never open cookie databases."""
    home = home or Path.home()
    applications = applications if applications is not None else [home / "Applications", Path("/Applications"), Path("/System/Applications")]
    bundles = {"Chrome": "Google Chrome.app", "Safari": "Safari.app", "Firefox": "Firefox.app",
               "Edge": "Microsoft Edge.app", "Chromium": "Chromium.app"}
    return [BrowserSource(name, app) for name, bundle in bundles.items()
            if (app := next((root / bundle for root in applications if (root / bundle).is_dir()), None)) is not None
            or any(value for _label, value in browser_profiles(name, home))]


@dataclass(frozen=True)
class YouTubeConnection:
    state: str
    message: str
    cookies_readable: bool | None = None
    actions: tuple[str, ...] = ("Sign in using browser", "Choose another profile", "Retry connection", "Import cookies.txt")

    @property
    def authenticated(self) -> bool:
        return self.state == "authenticated"


class _VerificationLogger:
    # Third-party debug/warning/error strings may contain credential paths or URLs.
    def debug(self, *_args, **_kwargs): pass
    def warning(self, *_args, **_kwargs): pass
    def error(self, *_args, **_kwargs): pass


def connection_failure(error: BaseException | str, cookies_readable: bool | None = None) -> YouTubeConnection:
    text = str(error).casefold()
    if any(term in text for term in ("429", "too many requests", "rate limit")):
        return YouTubeConnection("rate_limited", "YouTube is limiting requests. Wait before retrying; reconnecting may not help.", cookies_readable)
    if any(term in text for term in ("not a bot", "verification", "captcha", "challenge")):
        return YouTubeConnection("verification_required", "YouTube requires additional verification. Complete it in your browser; cookies cannot guarantee access.", cookies_readable)
    if any(term in text for term in ("po token", "po-token", "potoken", "provider")):
        return YouTubeConnection("provider_required", "A PO-token/provider requirement is blocking this operation. Review Advanced → PO-token provider.", cookies_readable)
    if any(term in text for term in ("could not find", "no such file", "profile missing")):
        return YouTubeConnection("profile_missing", "The selected browser profile or cookie database is missing. Detect browsers again and choose an existing signed-in profile.", False)
    if any(term in text for term in ("permission", "keychain", "keyring", "decrypt", "cookie database", "cookies unavailable")):
        return YouTubeConnection("cookies_unavailable", "Browser cookies could not be read. Check browser/macOS permissions, close the browser if its database is locked, choose another profile or import cookies.txt.", False)
    if any(term in text for term in ("sign in", "login", "expired", "private", "authentication")):
        return YouTubeConnection("reconnect", "The session was rejected or the account lacks permission. Sign in again and retry the selected profile.", cookies_readable)
    return YouTubeConnection("unavailable", "Connection could not be verified. Check the selected network, browser profile and cookie source, then retry.", cookies_readable)


def verify_youtube_connection(mode: str, browser: str, profile: str, cookies_file: str,
                              proxy: str | None = None, runtime: RuntimeSnapshot | None = None,
                              provider_url: str = "http://127.0.0.1:4416", provider_home: str = "") -> YouTubeConnection:
    """Verify cookie access and a bounded account page, never enumerate a library.

    The boolean server configuration is evidence of a signed-in web session, not
    proof of entitlement to any particular private video/playlist. Missing or
    changed page configuration is explicitly unconfirmed, never a success.
    """
    readable = None
    try:
        mode = normalise_authentication_mode(mode)
        options = {"quiet": True, "no_warnings": True, "logger": _VerificationLogger(),
                   "socket_timeout": 12, "retries": 0, "proxy": proxy}
        if mode == "Auto":
            _effective, selected = configured_authentication_options(browser, profile, cookies_file)
        else:
            selected = authentication_options(mode, browser, profile, cookies_file)
        options.update(selected)
        if runtime is None:
            from yt_dlp import YoutubeDL
        else: YoutubeDL = runtime.youtube_dl
        with YoutubeDL(options) as ydl:
            if mode == "None":
                with ydl.urlopen("https://www.youtube.com/generate_204") as response: response.read(1)
                return YouTubeConnection("public_access", "Public YouTube access works. Authentication is disabled; no signed-in access was tested.")
            try:
                jar = ydl.cookiejar  # yt-dlp owns supported browser extraction/decryption.
            finally:
                # Verification is read-only. YoutubeDL.close otherwise saves its
                # cookiejar back to an imported cookiefile, even on failed checks.
                if "cookiefile" in selected: ydl.params.pop("cookiefile", None)
            readable = True
            youtube_cookies = [c for c in jar if c.domain.lstrip(".") in ("youtube.com", "www.youtube.com") and not c.is_expired()]
            if not youtube_cookies:
                return YouTubeConnection("no_cookies", "The cookie source is readable but contains no current YouTube cookies. Sign in using the selected browser profile or import cookies.txt.", True)
            with ydl.urlopen("https://www.youtube.com/account") as response:
                page = response.read(2 * 1024 * 1024).decode("utf-8", "replace")
            for match in re.finditer(r"ytcfg\s*\.\s*set\s*\(\s*", page):
                try: config, _ = json.JSONDecoder().raw_decode(page[match.end():])
                except (ValueError, RecursionError): continue
                if isinstance(config, dict) and type(config.get("LOGGED_IN")) is bool:
                    if config["LOGGED_IN"]:
                        return YouTubeConnection("authenticated", "Signed in — account identity not confirmed. Private playlist/video permission is checked separately when you analyse it. No private library was enumerated.", True)
                    return YouTubeConnection("reconnect", "Cookies are readable, but YouTube reports signed out. Sign in again using the selected profile, then retry.", True)
            return YouTubeConnection("unconfirmed", "Cookies are readable, but this response did not confirm a signed-in session. Retry or analyse an authorised private URL; no private-access claim is made.", True)
    except (FileNotFoundError, ValueError):
        if mode == "YouTube Companion":
            return YouTubeConnection("reconnect", "The secure session is unavailable, expired or Keychain access was denied. Reconnect with Chrome Incognito and capture again; no browser-profile fallback was used.", False)
        return YouTubeConnection("source_missing", "The selected cookie source is missing or invalid. Choose another profile or a valid Netscape cookies.txt file.", False)
    except Exception as error:
        return connection_failure(error, readable)


def test_youtube_login(mode: str, browser: str, profile: str, cookies_file: str,
                       proxy: str | None = None, runtime: RuntimeSnapshot | None = None) -> tuple[bool, str]:
    result = verify_youtube_connection(mode, browser, profile, cookies_file, proxy, runtime)
    return result.authenticated, result.message
