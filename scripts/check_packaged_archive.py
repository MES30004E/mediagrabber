"""Hosted-only development archive round-trip; no upload or user installation."""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import platform
import sys
import tempfile

from morgan_media_downloader import __version__
from morgan_media_downloader.app_archives import build_development_archive, extract_development_archive
from morgan_media_downloader.app_installation import validate_signature


def verify(app: Path, commit: str, *, validator=None, launcher=None):
    if validator is None:
        if os.environ.get("GITHUB_ACTIONS") != "true" or sys.platform != "darwin" or platform.machine() != "arm64":
            raise RuntimeError("Actual archive qualification is hosted arm64 macOS only")
        validator = validate_signature
    if __package__:
        from .check_packaged_app import verify as launch
        from .check_packaged_replacement import fingerprint
    else:
        from check_packaged_app import verify as launch
        from check_packaged_replacement import fingerprint
    launcher = launcher or launch
    app = app.resolve(strict=True)
    before = fingerprint(app)
    before_modes = {str(path.relative_to(app)): path.lstat().st_mode & 0o7777 for path in app.rglob("*")}
    def verify_candidate(candidate):
        if candidate.resolve() != app:
            after = fingerprint(candidate)
            differences = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
            if differences: raise RuntimeError("Archive contents/symlinks changed before signature check: " + repr(differences[:20]))
            modes = {str(path.relative_to(candidate)): path.lstat().st_mode & 0o7777 for path in candidate.rglob("*")}
            changed = sorted(key for key in before_modes.keys() | modes.keys() if before_modes.get(key) != modes.get(key))
            print(json.dumps({"archive_mode_difference_count": len(changed), "sample": changed[:20]}, sort_keys=True))
        validator(candidate)
    with tempfile.TemporaryDirectory(prefix="morgan-archive-probe-") as temporary:
        root = Path(temporary)
        output = root / "archive"
        manifest = build_development_archive(app, output, __version__, commit, validator=verify_candidate)
        extracted = extract_development_archive(output / manifest["asset"]["name"], manifest, root / "extracted", validator=verify_candidate)
        if fingerprint(extracted) != before: raise RuntimeError("Archive round-trip changed bundle contents or symlinks")
        if launcher(extracted).get("result") != "passed": raise RuntimeError("Extracted GUI launch did not pass")
        if fingerprint(app) != before: raise RuntimeError("Archive probe changed its source bundle")
    return {"result": "passed", "archive_round_trip": True, "source_unchanged": True,
            "publication_approved": False, "source_commit": commit, "asset": manifest["asset"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path); parser.add_argument("commit")
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.app, arguments.commit), sort_keys=True))
