from __future__ import annotations

import socket
import json
from dataclasses import dataclass
from urllib.parse import quote

from .yt_runtime import RuntimeSnapshot


@dataclass
class ProxyConfig:
    mode: str = "Direct"
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""

    def url(self) -> str | None:
        if self.mode in {"Direct", "Direct / Normal Network", "System / Proton VPN"}:
            return None
        if self.mode in {"Tor", "External Tor"}:
            return f"socks5h://{self.host or '127.0.0.1'}:{self.port or 9150}"
        if self.mode == "Managed Tor":
            if not self.port:
                raise ValueError("Managed Tor runtime SOCKS port is unavailable")
            return f"socks5h://{self.host or '127.0.0.1'}:{self.port}"
        scheme = "http" if self.mode == "Custom HTTP Proxy" else "socks5h"
        auth = ""
        if self.username:
            auth = quote(self.username, safe="")
            if self.password:
                auth += ":" + quote(self.password, safe="")
            auth += "@"
        if not self.host or not self.port:
            raise ValueError("Proxy host and port are required")
        return f"{scheme}://{auth}{self.host}:{self.port}"


def tcp_reachable(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_tor() -> tuple[bool, int | None]:
    for port in (9150, 9050):
        if tcp_reachable("127.0.0.1", port):
            return True, port
    return False, None


def test_tor_connection(runtime: RuntimeSnapshot | None = None) -> tuple[str, str]:
    available, port = detect_tor()
    if not available or not port:
        return "unavailable", "Tor unavailable. Start Tor Browser and retry."
    proxy = f"socks5h://127.0.0.1:{port}"
    return test_tor_proxy(proxy, runtime)


def test_tor_proxy(proxy: str, runtime: RuntimeSnapshot | None = None) -> tuple[str, str]:
    try:
        if runtime is None:
            from yt_dlp import YoutubeDL
        else:
            YoutubeDL = runtime.youtube_dl
        with YoutubeDL({"proxy": proxy, "socket_timeout": 8, "quiet": True}) as ydl:
            with ydl.urlopen("https://check.torproject.org/api/ip") as response:
                payload = json.load(response)
        if payload.get("IsTor"):
            return "available", f"Tor available through {proxy}"
        return "reachable", f"SOCKS proxy reachable at {proxy}, but the connection was not identified as Tor"
    except Exception as error:
        return "target_unavailable", f"Tor proxy reachable at {proxy}, but the Tor check service was unavailable: {error}"


def tor_exit_ip(proxy: str, runtime: RuntimeSnapshot | None = None) -> str:
    if runtime is None:
        from yt_dlp import YoutubeDL
    else:
        YoutubeDL = runtime.youtube_dl
    with YoutubeDL({"proxy": proxy, "socket_timeout": 10, "quiet": True}) as ydl:
        with ydl.urlopen("https://check.torproject.org/api/ip") as response:
            payload = json.load(response)
    return str(payload.get("IP") or "") if payload.get("IsTor") else ""


def test_media_connection(proxy: str | None, runtime: RuntimeSnapshot) -> tuple[str, str]:
    try:
        options = {"socket_timeout": 8, "quiet": True}
        if proxy:
            options["proxy"] = proxy
        with runtime.youtube_dl(options) as ydl:
            with ydl.urlopen("https://www.youtube.com/generate_204") as response:
                response.read(1)
        return "available", "Connection test succeeded"
    except Exception as error:
        return "unavailable", f"Connection test failed: {error}"


def managed_tor_health(tor, runtime: RuntimeSnapshot | None = None) -> tuple[str, str]:
    """Classify Tor process, bootstrap, SOCKS, and Internet as separate layers."""
    if not tor.available:
        return "process_unavailable", "Managed Tor executable is unavailable"
    if not tor.process or tor.process.poll() is not None:
        return "process_unavailable", "Managed Tor process is not running"
    if tor.state.startswith("Bootstrapping") or tor.state == "Starting":
        return "bootstrapping", tor.state
    if tor.state != "Connected" or not tor.port or not tcp_reachable("127.0.0.1", tor.port):
        return "socks_unavailable", "Managed Tor SOCKS endpoint is unavailable"
    state, detail = test_tor_proxy(tor.proxy_url, runtime)
    if state == "available": return "internet_working", detail
    return "internet_failed", detail


def classify_tor_target(health_state: str, error: BaseException | str) -> tuple[str, str]:
    message = str(error); lower = message.casefold()
    if "1034" in lower or "edge ip restricted" in lower:
        return "cloudflare_edge_restriction", "Cloudflare site configuration / edge restriction (Error 1034)."
    if health_state == "internet_working" and any(term in lower for term in (
            "403", "forbidden", "access denied", "http 429", "too many requests")):
        return "target_rejected", "Tor is working, but this website rejected the current Tor exit."
    return health_state, message
