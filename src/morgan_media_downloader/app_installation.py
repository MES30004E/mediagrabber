"""Verified-copy replacement primitive; callers must stop the app first."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import sys
import tempfile
import unicodedata

from .logging_setup import redact_secrets


class InstallationError(RuntimeError):
    pass


class RecoveryRequired(InstallationError):
    def __init__(self, backup, target=None):
        self.backup = backup
        message = (f"Automatic restoration failed. The previous app is preserved at: {backup}" if backup is not None else
                   f"No previous app existed. Inspect the destination at: {target}; the source candidate is unchanged.")
        super().__init__(message)


def check_destination(target: Path):
    target = target.absolute()
    if target.suffix != ".app" or target.is_symlink() or not target.parent.is_dir():
        raise InstallationError("Choose a real .app path with an existing parent directory; symlink targets are refused")
    if target.exists() and not target.is_dir(): raise InstallationError("Destination is not an app directory")
    target = target.parent.resolve(strict=True) / target.name
    try:
        with tempfile.TemporaryDirectory(prefix=".morgan-volume-check-", dir=target.parent) as temporary:
            root = Path(temporary); (root / "original").write_bytes(b"morgan-volume-check")
            os.symlink("original", root / "link")
            if not (root / "link").is_symlink() or (root / "link").read_bytes() != b"morgan-volume-check":
                raise OSError("Symlink preservation failed")
            os.replace(root / "original", root / "renamed")
            if (root / "renamed").read_bytes() != b"morgan-volume-check": raise OSError("Rename failed")
    except OSError as error:
        raise InstallationError("Destination cannot preserve bundle symlinks and renames; installation refused (including exFAT). No destination fallback was selected.") from error
    return target


@contextmanager
def _installation_lock(target):
    parent = target.parent.stat()
    identity = f"{parent.st_dev}:{parent.st_ino}:{unicodedata.normalize('NFC', target.name).casefold()}"
    name = hashlib.sha256(identity.encode()).hexdigest()[:16]
    descriptor = os.open(target.parent / f".morgan-{name}.install.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise InstallationError("Installation lock is not privately owned")
        try: fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error: raise InstallationError("Another installation is in progress") from error
        yield
    finally: os.close(descriptor)


def require_app_stopped(target):
    if sys.platform != "darwin": raise InstallationError("Native app installation is macOS only")
    result = subprocess.run(["/bin/ps", "-ww", "-axo", "pid=,comm="], capture_output=True, text=True, timeout=10, check=True)
    for record in result.stdout.splitlines():
        parts = record.strip().split(None, 1)
        if len(parts) != 2 or parts[0] == str(os.getpid()): continue
        executable = Path(parts[1])
        # Conservative across copies and App Translocation: any matching bundle
        # name, or the main GUI executable, must be closed. Do not kill anything.
        if executable.name == "Morgan Media Downloader" or any(parent.name == target.name for parent in executable.parents):
            raise InstallationError("Close Morgan Media Downloader and its bundle processes before replacement")


def validate_signature(candidate):
    with (candidate / "Contents/Info.plist").open("rb") as stream: info = plistlib.load(stream)
    if info.get("CFBundleIdentifier") != "com.morgan.media-downloader" or info.get("CFBundleExecutable") != "Morgan Media Downloader":
        raise InstallationError("Unexpected application bundle identity")
    try:
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(candidate)],
                       capture_output=True, text=True, timeout=60, check=True)
    except subprocess.CalledProcessError as error:
        detail = redact_secrets(str(error.stderr or "No signature diagnostic available"))[:1500]
        raise InstallationError("Signature verification failed: " + detail) from None


def copy_bundle(source, target):
    subprocess.run(["/usr/bin/ditto", str(source), str(target)], capture_output=True, text=True, timeout=300, check=True)


def install_verified_app(source: Path, target: Path, *, validator=validate_signature, cloner=copy_bundle,
                         ensure_stopped=require_app_stopped) -> Path | None:
    source, target = source.absolute(), target.absolute()
    if source.is_symlink() or not source.is_dir() or source.suffix != ".app": raise InstallationError("Candidate must be a real app directory")
    target = check_destination(target)
    source = source.resolve()
    destination = target.resolve()
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise InstallationError("Candidate and destination must be separate app trees")
    with _installation_lock(target):
        ensure_stopped(target)
        original_identity = (target.stat().st_dev, target.stat().st_ino) if target.exists() else None
        with tempfile.TemporaryDirectory(prefix=".morgan-candidate-", dir=target.parent) as temporary:
            root = Path(temporary); candidate = root / target.name
            cloner(source, candidate)
            validator(candidate)  # The old installation has not moved yet.
            candidate_info = candidate.lstat()
            candidate_identity = (candidate_info.st_dev, candidate_info.st_ino)
            ensure_stopped(target)
            if target.is_symlink() or ((target.stat().st_dev, target.stat().st_ino) if target.exists() else None) != original_identity:
                raise InstallationError("Destination changed while the candidate was being validated; nothing was replaced")
            backup = None; backup_root = None
            if target.exists():
                backup_root = Path(tempfile.mkdtemp(prefix=".morgan-backup-", dir=target.parent))
                backup = backup_root / target.name
                try: os.replace(target, backup)
                except BaseException as error:
                    if backup.exists(): raise RecoveryRequired(backup, target) from error
                    backup_root.rmdir(); raise
            activated = False
            try:
                os.replace(candidate, target)
                activated = True
                validator(target)
            except BaseException:
                try:
                    if target.exists():
                        if not activated: raise InstallationError("Destination reappeared during activation; refusing to move another actor's app")
                        current_info = target.lstat()
                        if (current_info.st_dev, current_info.st_ino) != candidate_identity:
                            raise InstallationError("Destination changed after activation; refusing to move another actor's app")
                        os.replace(target, root / "rejected.app")
                    if backup is not None: os.replace(backup, target)
                except BaseException as error:
                    # No automatic cleanup owns backup_root: the only known
                    # working copy must survive even if restoration fails.
                    raise RecoveryRequired(backup, target) from error
                if backup_root is not None: backup_root.rmdir()
                raise
            return backup  # Retained for rollback, not deleted after activation.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-destination", type=Path)
    parser.add_argument("source", nargs="?", type=Path); parser.add_argument("target", nargs="?", type=Path)
    arguments = parser.parse_args()
    if arguments.check_destination:
        check_destination(arguments.check_destination)
        print("Destination supports the required symlink/rename operations; this is not complete app qualification.")
    elif arguments.source and arguments.target:
        backup = install_verified_app(arguments.source, arguments.target)
        print(f"Verified app installed. Previous app retained at: {backup}" if backup else "Verified app installed; no previous app existed.")
    else: parser.error("Provide --check-destination APP, or SOURCE_APP TARGET_APP")
