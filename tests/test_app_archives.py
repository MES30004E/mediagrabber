import hashlib
import json
import os
import plistlib
import struct
import tarfile

import pytest

from morgan_media_downloader.app_archives import build_development_archive, extract_development_archive

COMMIT = "1" * 40
APP = "Morgan Media Downloader.app"


def bundle(root):
    app = root / APP; (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/MacOS/Morgan Media Downloader").write_bytes(struct.pack("<II", 0xFEEDFACF, 0x0100000C) + b"fixture")
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.morgan.media-downloader",
        "CFBundleExecutable": "Morgan Media Downloader", "CFBundleShortVersionString": "0.1.0", "LSMinimumSystemVersion": "15.0"}))
    (app / "Contents/version").write_text("fixture")
    (app / "Contents/current").symlink_to("version")
    return app


def validate(app):
    assert (app / "Contents/current").is_symlink()
    assert (app / "Contents/current").read_text() == "fixture"


def candidate(tmp_path):
    app = bundle(tmp_path / "source")
    output = tmp_path / "candidate"
    manifest = build_development_archive(app, output, "0.1.0", COMMIT, validator=validate)
    return app, output, manifest


def test_versioned_development_archive_round_trip_preserves_symlinks_and_source(tmp_path):
    app, output, manifest = candidate(tmp_path)
    assert manifest["channel"] == "development" and manifest["publication_approved"] is False
    assert manifest["version"] == "0.1.0" and manifest["source_commit"] == COMMIT
    assert manifest["architecture"] == "arm64" and manifest["minimum_macos"] == "15.0"
    archive = output / manifest["asset"]["name"]
    assert archive.name == "Morgan-Media-Downloader-0.1.0-macos-arm64.tar.gz"
    assert manifest["asset"]["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert json.loads((output / "release.json").read_text()) == manifest
    assert archive.name in (output / "SHA256SUMS").read_text()
    assert "Not approved for publication" in (output / "RELEASE_NOTES.md").read_text()
    result = extract_development_archive(archive, manifest, tmp_path / "extracted", validator=validate)
    validate(result); validate(app)


@pytest.mark.parametrize("version,commit", [("../../bad", COMMIT), ("0.2.0", COMMIT), ("0.1.0", "not-a-commit")])
def test_archive_rejects_wrong_version_or_commit_before_producing_a_candidate(tmp_path, version, commit):
    app = bundle(tmp_path / "source"); output = tmp_path / "candidate"
    with pytest.raises(ValueError): build_development_archive(app, output, version, commit, validator=validate)
    assert not output.exists()


def test_existing_candidate_is_never_overwritten(tmp_path):
    app, output, _ = candidate(tmp_path)
    (output / "keep").write_text("existing")
    with pytest.raises(FileExistsError): build_development_archive(app, output, "0.1.0", COMMIT, validator=validate)
    assert (output / "keep").read_text() == "existing"


def test_archive_output_inside_bundle_does_not_modify_source(tmp_path):
    app = bundle(tmp_path / "source")
    with pytest.raises(ValueError):
        build_development_archive(app, app / "new-parent/candidate", "0.1.0", COMMIT, validator=validate)
    assert not (app / "new-parent").exists()


def test_archive_refuses_a_bundle_with_non_arm64_executable(tmp_path):
    app = bundle(tmp_path / "source")
    (app / "Contents/MacOS/Morgan Media Downloader").write_bytes(struct.pack("<II", 0xFEEDFACF, 0x01000007))
    with pytest.raises(ValueError, match="arm64"):
        build_development_archive(app, tmp_path / "candidate", "0.1.0", COMMIT, validator=validate)
    assert not (tmp_path / "candidate").exists()


def test_corrupt_archive_is_rejected_before_creating_destination(tmp_path):
    _, output, manifest = candidate(tmp_path); archive = output / manifest["asset"]["name"]
    archive.write_bytes(archive.read_bytes()[:-1] + b"X")
    with pytest.raises(ValueError, match="integrity"):
        extract_development_archive(archive, manifest, tmp_path / "extracted", validator=validate)
    assert not (tmp_path / "extracted").exists()


@pytest.mark.parametrize("in_place", [False, True], ids=["pathname-swap", "same-inode-write"])
def test_extraction_reads_the_same_file_that_passed_its_integrity_check(tmp_path, monkeypatch, in_place):
    app, output, manifest = candidate(tmp_path)
    executable = app / "Contents/MacOS/Morgan Media Downloader"
    original_bytes = executable.read_bytes()
    executable.write_bytes(original_bytes + b"foreign")
    foreign = tmp_path / "foreign.tar.gz"
    with tarfile.open(foreign, "w:gz") as stream: stream.add(app, arcname=APP)
    executable.write_bytes(original_bytes)
    archive = output / manifest["asset"]["name"]
    original_digest = hashlib.file_digest
    def swap_after_hash(stream, algorithm):
        result = original_digest(stream, algorithm)
        if in_place: archive.write_bytes(foreign.read_bytes())
        else: os.replace(foreign, archive)
        return result
    monkeypatch.setattr(hashlib, "file_digest", swap_after_hash)
    extracted = extract_development_archive(archive, manifest, tmp_path / "extracted", validator=validate)
    assert (extracted / "Contents/MacOS/Morgan Media Downloader").read_bytes() == original_bytes


def test_chained_symlink_cannot_publish_a_link_outside_the_app(tmp_path):
    app, output, manifest = candidate(tmp_path)
    archive = output / manifest["asset"]["name"]
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(app, arcname=APP)
        alias = tarfile.TarInfo(f"{APP}/Contents/root-alias")
        alias.type = tarfile.SYMTYPE; alias.linkname = ".."; stream.addfile(alias)
        outside = tarfile.TarInfo(f"{APP}/Contents/root-alias/outside")
        outside.type = tarfile.SYMTYPE; outside.linkname = "../outside"; stream.addfile(outside)
    manifest["asset"].update(sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), size=archive.stat().st_size)
    with pytest.raises(ValueError, match="symlink"):
        extract_development_archive(archive, manifest, tmp_path / "extracted", validator=validate)
    assert not (tmp_path / "extracted").exists()


@pytest.mark.parametrize("change", [{"channel": "stable"}, {"publication_approved": True}, {"schema": True}, {"architecture": "x86_64"}])
def test_development_staging_does_not_accept_stable_or_invalid_metadata(tmp_path, change):
    _, output, manifest = candidate(tmp_path); manifest.update(change)
    with pytest.raises(ValueError):
        extract_development_archive(output / manifest["asset"]["name"], manifest, tmp_path / "extracted", validator=validate)
    assert not (tmp_path / "extracted").exists()


@pytest.mark.parametrize("kind", ["traversal", "absolute", "symlink-escape", "device", "duplicate", "case-collision", "hardlink"])
def test_hostile_archive_entries_fail_before_destination_creation(tmp_path, kind):
    _, output, manifest = candidate(tmp_path); archive = output / manifest["asset"]["name"]
    with tarfile.open(archive, "w:gz") as stream:
        entry = tarfile.TarInfo(f"{APP}/Contents/file")
        if kind == "traversal": entry.name = f"{APP}/../../escape"
        elif kind == "absolute": entry.name = "/escape"
        elif kind == "symlink-escape": entry.type = tarfile.SYMTYPE; entry.linkname = "../../../escape"
        elif kind == "device": entry.type = tarfile.CHRTYPE
        elif kind == "hardlink": entry.type = tarfile.LNKTYPE; entry.linkname = "/escape"
        stream.addfile(entry)
        if kind == "duplicate": stream.addfile(entry)
        if kind == "case-collision":
            second = tarfile.TarInfo(f"{APP}/Contents/FILE"); stream.addfile(second)
    manifest["asset"].update(sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), size=archive.stat().st_size)
    with pytest.raises(ValueError):
        extract_development_archive(archive, manifest, tmp_path / "extracted", validator=validate)
    assert not (tmp_path / "extracted").exists()


def test_archive_member_budget_is_enforced_before_extraction(tmp_path, monkeypatch):
    import morgan_media_downloader.app_archives as module
    _, output, manifest = candidate(tmp_path)
    monkeypatch.setattr(module, "MAX_MEMBERS", 2)
    with pytest.raises(ValueError, match="limit"):
        extract_development_archive(output / manifest["asset"]["name"], manifest, tmp_path / "extracted", validator=validate)
    assert not (tmp_path / "extracted").exists()


def test_stable_staging_has_a_separate_policy_and_rejects_development_candidates(tmp_path):
    from morgan_media_downloader.app_archives import extract_release_archive
    _, output, manifest = candidate(tmp_path); archive = output / manifest["asset"]["name"]
    with pytest.raises(ValueError): extract_release_archive(archive, manifest, tmp_path / "rejected", validator=validate)
    assert not (tmp_path / "rejected").exists()
    manifest.update(channel="stable", publication_approved=True)
    validate(extract_release_archive(archive, manifest, tmp_path / "stable", validator=validate))
