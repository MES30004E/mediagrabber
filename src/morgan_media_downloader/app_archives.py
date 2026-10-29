"""Development-only app archive preparation and integrity-checked staging."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import posixpath
import re
import stat
import struct
import tarfile
import tempfile
import unicodedata

from .app_installation import validate_signature

APP_NAME = "Morgan Media Downloader.app"
MAX_ARCHIVE_BYTES = 2_147_483_648
MAX_EXPANDED_BYTES = 6_442_450_944
MAX_MEMBERS = 100_000
VERSION = re.compile(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}")


def _digest(path):
    with path.open("rb") as stream: return hashlib.file_digest(stream, "sha256").hexdigest()


def _asset_name(version):
    if not isinstance(version, str) or not VERSION.fullmatch(version): raise ValueError("Invalid app version")
    return f"Morgan-Media-Downloader-{version}-macos-arm64.tar.gz"


def _bundle_metadata(app, version):
    with (app / "Contents/Info.plist").open("rb") as stream: info = plistlib.load(stream)
    if (info.get("CFBundleIdentifier") != "com.morgan.media-downloader" or
            info.get("CFBundleExecutable") != "Morgan Media Downloader" or
            info.get("CFBundleShortVersionString", info.get("CFBundleVersion")) != version):
        raise ValueError("Bundle identity/version does not match candidate")
    minimum = info.get("LSMinimumSystemVersion")
    if not isinstance(minimum, str) or not re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}", minimum):
        raise ValueError("Missing or invalid minimum macOS version")
    with (app / "Contents/MacOS/Morgan Media Downloader").open("rb") as stream: header = stream.read(8)
    if header != struct.pack("<II", 0xFEEDFACF, 0x0100000C): raise ValueError("Candidate is not a thin arm64 Mach-O application")
    return minimum


def _entries(archive):
    members, names, size = [], set(), 0
    for entry in archive:
        path = PurePosixPath(entry.name)
        canonical = unicodedata.normalize("NFC", str(path)).casefold()
        if (path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != APP_NAME or
                canonical in names or not (entry.isfile() or entry.isdir() or entry.issym())):
            raise ValueError("Unsafe or duplicate app archive entry")
        if entry.issym():
            link = PurePosixPath(entry.linkname)
            resolved = posixpath.normpath(posixpath.join(str(path.parent), entry.linkname))
            if link.is_absolute() or not (resolved == APP_NAME or resolved.startswith(APP_NAME + "/")):
                raise ValueError("App archive symlink escapes bundle")
        size += max(0, entry.size)
        if len(members) >= MAX_MEMBERS or size > MAX_EXPANDED_BYTES: raise ValueError("App archive exceeds extraction limit")
        names.add(canonical); members.append(entry)
    if not members: raise ValueError("Empty app archive")
    return members


def _new_destination(destination):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink(): raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination.parent.resolve(strict=True) / destination.name


def _contained_links(app):
    root = app.resolve(strict=True)
    for path in app.rglob("*"):
        if not path.is_symlink(): continue
        try: target = path.resolve()
        except (OSError, RuntimeError) as error: raise ValueError("Invalid app symlink graph") from error
        if not target.is_relative_to(root): raise ValueError("Resolved app symlink escapes bundle")


def build_development_archive(app, destination, version, commit, *, validator=validate_signature):
    name = _asset_name(version)
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit): raise ValueError("Invalid source commit")
    app = Path(app).resolve(strict=True)
    if app.name != APP_NAME or not app.is_dir(): raise ValueError("Unexpected app bundle")
    _contained_links(app)
    minimum = _bundle_metadata(app, version)
    validator(app)
    if Path(destination).resolve().is_relative_to(app): raise ValueError("Candidate output must be separate from its source bundle")
    destination = _new_destination(destination)
    with tempfile.TemporaryDirectory(prefix=".morgan-archive-", dir=destination.parent) as temporary:
        output = Path(temporary) / "candidate"; output.mkdir()
        asset = output / name
        with tarfile.open(asset, "x:gz", dereference=False) as archive:
            for path in [app, *sorted(app.rglob("*"))]:
                info = archive.gettarinfo(str(path), str(Path(APP_NAME) / path.relative_to(app)))
                if stat.S_ISREG(path.lstat().st_mode):
                    # Materialize hard-linked inputs as ordinary files. The
                    # receiving format accepts only files, directories, symlinks.
                    info.type = tarfile.REGTYPE; info.linkname = ""; info.size = path.stat().st_size
                    with path.open("rb") as stream: archive.addfile(info, stream)
                else: archive.addfile(info)
        if asset.stat().st_size > MAX_ARCHIVE_BYTES: raise ValueError("Candidate archive exceeds size limit")
        with tarfile.open(asset, "r:gz") as archive: _entries(archive)
        manifest = {"schema": 1, "channel": "development", "publication_approved": False,
                    "version": version, "source_commit": commit, "platform": "macos", "architecture": "arm64",
                    "minimum_macos": minimum,
                    "asset": {"name": name, "size": asset.stat().st_size, "sha256": _digest(asset)}}
        manifest_path = output / "release.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        (output / "SHA256SUMS").write_text(f"{manifest['asset']['sha256']}  {name}\n{_digest(manifest_path)}  release.json\n")
        (output / "RELEASE_NOTES.md").write_text(f"# Morgan Media Downloader {version} — development candidate\n\n"
            f"Source commit: {commit}\n\nApple Silicon; minimum macOS {minimum}.\n\n"
            "Not approved for publication. Not a stable release, Developer ID signing, notarisation or licensing clearance.\n"
            "Live authenticated downloads, supported destination, complete source/licence obligations and explicit release approval remain separate gates.\n")
        validator(app)
        if destination.exists() or destination.is_symlink(): raise FileExistsError(destination)
        output.rename(destination)
    return manifest


def _validate_manifest(manifest):
    if not isinstance(manifest, dict): raise ValueError("Invalid development manifest")
    if (type(manifest.get("schema")) is not int or manifest["schema"] != 1 or manifest.get("channel") != "development" or
            manifest.get("publication_approved") is not False or manifest.get("platform") != "macos" or manifest.get("architecture") != "arm64"):
        raise ValueError("Not a supported development candidate")
    name = _asset_name(manifest.get("version"))
    if not isinstance(manifest.get("source_commit"), str) or not re.fullmatch(r"[0-9a-f]{40}", manifest["source_commit"]):
        raise ValueError("Invalid source commit")
    asset = manifest.get("asset")
    if (not isinstance(asset, dict) or asset.get("name") != name or type(asset.get("size")) is not int or
            not 0 < asset["size"] <= MAX_ARCHIVE_BYTES or not isinstance(asset.get("sha256"), str) or
            not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])):
        raise ValueError("Invalid candidate asset")
    return asset


def extract_development_archive(archive, manifest, destination, *, validator=validate_signature):
    asset = _validate_manifest(manifest)
    archive = Path(archive)
    with archive.open("rb") as source, tempfile.TemporaryFile(mode="w+b") as snapshot:
        if archive.name != asset["name"] or os.fstat(source.fileno()).st_size != asset["size"]:
            raise ValueError("Candidate archive integrity check failed")
        copied = 0
        while chunk := source.read(1_048_576):
            copied += len(chunk)
            if copied > asset["size"]: raise ValueError("Candidate archive integrity check failed")
            snapshot.write(chunk)
        snapshot.seek(0)
        if copied != asset["size"] or hashlib.file_digest(snapshot, "sha256").hexdigest() != asset["sha256"]:
            raise ValueError("Candidate archive integrity check failed")
        snapshot.seek(0)
        # The unlinked private snapshot is both hashed and parsed. Neither
        # pathname replacement nor writes to the caller's inode can alter it.
        with tarfile.open(fileobj=snapshot, mode="r:gz") as stream:
            members = _entries(stream)
            destination = _new_destination(destination)
            with tempfile.TemporaryDirectory(prefix=".morgan-extract-", dir=destination.parent) as temporary:
                output = Path(temporary) / "candidate"; output.mkdir()
                stream.extractall(output, members=members, filter="data")
                app = output / APP_NAME
                _contained_links(app)
                if _bundle_metadata(app, manifest["version"]) != manifest.get("minimum_macos"):
                    raise ValueError("Candidate deployment metadata mismatch")
                validator(app)
                if destination.exists() or destination.is_symlink(): raise FileExistsError(destination)
                output.rename(destination)
    return destination / APP_NAME
