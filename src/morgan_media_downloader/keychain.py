from __future__ import annotations

import subprocess

SERVICE = "Morgan Media Downloader Proxy"


def load_proxy_password(account: str) -> str:
    if not account:
        return ""
    result = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
        capture_output=True, text=True, timeout=5, check=False,
    )
    return result.stdout.rstrip("\n") if result.returncode == 0 else ""


def save_proxy_password(account: str, password: str) -> bool:
    if not account or not password:
        return False
    result = subprocess.run(
        ["/usr/bin/security", "add-generic-password", "-U", "-s", SERVICE, "-a", account, "-w", password],
        capture_output=True, text=True, timeout=8, check=False,
    )
    return result.returncode == 0
