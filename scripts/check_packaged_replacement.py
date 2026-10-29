"""Exercise app replacement only on owned copies; never install a user app."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from morgan_media_downloader.app_installation import install_verified_app


def fingerprint(app):
    result = {}
    for path in sorted(app.rglob("*")):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode): value = ("link", os.readlink(path))
        elif stat.S_ISDIR(info.st_mode): value = ("directory",)
        elif stat.S_ISREG(info.st_mode):
            with path.open("rb") as stream: value = ("file", hashlib.file_digest(stream, "sha256").hexdigest())
        else: raise RuntimeError("Unexpected special file in app bundle")
        result[str(path.relative_to(app))] = value
    return result


def verify(app: Path, *, installer=None, launcher=None):
    if installer is None:
        if sys.platform != "darwin" or os.environ.get("GITHUB_ACTIONS") != "true":
            raise RuntimeError("Actual packaged replacement qualification is hosted macOS only")
        installer = install_verified_app
    if launcher is None:
        # Both import forms support pytest's package import and direct CLI use.
        if __package__: from .check_packaged_app import verify as launcher
        else: from check_packaged_app import verify as launcher
    app = app.resolve(strict=True)
    before = fingerprint(app)
    with tempfile.TemporaryDirectory(prefix="morgan-replacement-probe-") as temporary:
        root = Path(temporary).resolve(strict=True)
        target = root / "Morgan Media Downloader.app"
        if installer(app, target) is not None:
            raise RuntimeError("First installation reported an unexpected backup")
        previous = target.stat()
        backup = installer(app, target)
        if backup is None or not backup.is_relative_to(root) or not backup.is_dir():
            raise RuntimeError("Replacement did not retain its previous app in the owned fixture")
        retained = backup.stat()
        if (retained.st_dev, retained.st_ino) != (previous.st_dev, previous.st_ino):
            raise RuntimeError("Retained backup is not the previous installation")
        if fingerprint(backup) != before or fingerprint(target) != before:
            raise RuntimeError("Replacement or backup changed bundle contents or symlinks")
        if launcher(target).get("result") != "passed":
            raise RuntimeError("Replacement GUI launch did not pass")
        if fingerprint(app) != before:
            raise RuntimeError("Replacement qualification changed its source bundle")
    return {"result": "passed", "first_install": True, "backup_retained": True,
            "source_unchanged": True, "replacement_launch": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    print(json.dumps(verify(parser.parse_args().app), sort_keys=True))
