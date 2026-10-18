"""Strict Chrome-cookie adapter and an in-memory yt-dlp cookie source."""
import io
import json
import math
import re
import time

MODE = "YouTube Companion"
MAX_SESSION_BYTES = 65536


def validate_cookies(cookies, store_id):
    if not isinstance(store_id, str) or not 1 <= len(store_id) <= 128:
        raise ValueError("capture.invalid")
    if not isinstance(cookies, list) or not 1 <= len(cookies) <= 200:
        raise ValueError("capture.invalid")
    if len(json.dumps(cookies, allow_nan=False).encode()) > MAX_SESSION_BYTES:
        raise ValueError("capture.limit")
    result = []; seen = set()
    required = {"name", "value", "domain", "path", "secure", "httpOnly", "hostOnly", "session", "sameSite", "storeId"}
    for cookie in cookies:
        if not isinstance(cookie, dict) or not required <= cookie.keys() or set(cookie) - required - {"expirationDate"}:
            raise ValueError("capture.attributes")  # Never flatten partitioned cookies.
        for field, limit in (("name", 128), ("value", 8192), ("domain", 253), ("path", 1024)):
            value = cookie[field]
            if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError("capture.invalid")
        domain = cookie["domain"].lstrip(".").lower()
        if not re.fullmatch(r"[a-z0-9.-]+", domain) or not (domain == "youtube.com" or domain.endswith(".youtube.com")):
            raise ValueError("capture.domain")
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9a-zA-Z-]+", cookie["name"]) or not cookie["path"].startswith("/"):
            raise ValueError("capture.invalid")
        if cookie["storeId"] != store_id or any(type(cookie[f]) is not bool for f in ("secure", "httpOnly", "hostOnly", "session")):
            raise ValueError("capture.store")
        if cookie["sameSite"] not in ("unspecified", "no_restriction", "lax", "strict"):
            raise ValueError("capture.attributes")
        if cookie["hostOnly"] and cookie["domain"].startswith("."): raise ValueError("capture.domain")
        expiration = cookie.get("expirationDate")
        if expiration is not None and (type(expiration) not in (int, float) or not math.isfinite(expiration) or not 0 <= expiration <= 1e12):
            raise ValueError("capture.expiry")
        if not cookie["session"] and expiration is None: raise ValueError("capture.expiry")
        identity = (domain, cookie["path"], cookie["name"])
        if identity in seen: raise ValueError("capture.duplicate")
        seen.add(identity); result.append(dict(cookie))
    return result


def cookie_file(store=None):
    if store is None:
        from .storage import KeychainSessionStore
        store = KeychainSessionStore()
    data = store.load()
    if not isinstance(data, dict) or not isinstance(data.get("cookies"), list) or not data["cookies"]:
        raise ValueError("session.missing")
    cookies = validate_cookies(data["cookies"], data["cookies"][0].get("storeId"))
    lines = ["# Netscape HTTP Cookie File"]
    for cookie in cookies:
        expiry = 0 if cookie["session"] else int(cookie["expirationDate"])
        if expiry and expiry <= time.time(): continue
        domain = cookie["domain"].lstrip(".") if cookie["hostOnly"] else "." + cookie["domain"].lstrip(".")
        if cookie["httpOnly"]: domain = "#HttpOnly_" + domain
        lines.append("\t".join([domain, "FALSE" if cookie["hostOnly"] else "TRUE", cookie["path"],
                                  "TRUE" if cookie["secure"] else "FALSE", str(expiry), cookie["name"], cookie["value"]]))
    if len(lines) == 1: raise ValueError("session.expired")
    return io.StringIO("\n".join(lines) + "\n")
