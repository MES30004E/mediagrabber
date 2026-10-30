import hashlib
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest

from scripts import prepare_provider_bundle as packaging


def archive(name="node-v24.22.0-darwin-arm64/bin/node"):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:xz") as stream:
        for path, value in [(name, b"fixture-node"), ("node-v24.22.0-darwin-arm64/LICENSE", b"fixture license")]:
            info = tarfile.TarInfo(path); info.size = len(value); info.mode = 0o755
            stream.addfile(info, io.BytesIO(value))
    return output.getvalue()


@pytest.mark.parametrize("escaped_build", [False, True])
def test_stage_is_atomic_and_keeps_original_checkout_unmodified(tmp_path, monkeypatch, escaped_build):
    project = tmp_path / "project"; provider = project / "bgutil-ytdlp-pot-provider"
    server = provider / "server"; server.mkdir(parents=True)
    for name in ("package.json", "package-lock.json", "tsconfig.json"): (server / name).write_text("{}")
    for name in ("src", "types"): (server / name).mkdir(); (server / name / "fixture.ts").write_text("source")
    (server / "src/private-untracked.txt").write_text("synthetic private fixture")
    (provider / "LICENSE").write_text("upstream license")
    data = archive(); monkeypatch.setattr(packaging, "NODE_SHA256", hashlib.sha256(data).hexdigest())
    def run(command, *, cwd=None, env=None):
        if command[-2:] == ["rev-parse", "HEAD"]: return SimpleNamespace(stdout=packaging.PROVIDER_COMMIT + "\n")
        if "ls-files" in command: return SimpleNamespace(stdout="server/src/fixture.ts\0server/types/fixture.ts\0")
        if command[-1] == "--version": return SimpleNamespace(stdout="v24.22.0\n" if len(command) == 2 else "1.3.1\n")
        if "rebuild" in command:
            if escaped_build:
                # A malformed ancestor escapes the owned stage while the final
                # addon resolves back inside; checking the addon alone is unsafe.
                external = tmp_path / "unowned-compiler"; (external / "build").mkdir(parents=True)
                (external / "build/keep").write_text("must remain untouched")
                inside = Path(cwd) / "safe-addon"; inside.mkdir()
                (inside / "canvas.node").write_bytes(b"synthetic loadable addon")
                (external / "build/Release").symlink_to(inside, target_is_directory=True)
                (Path(cwd) / "node_modules").mkdir()
                (Path(cwd) / "node_modules/canvas").symlink_to(external, target_is_directory=True)
                return SimpleNamespace(stdout="")
            release = Path(cwd) / "node_modules/canvas/build/Release"
            (release / "obj.target/canvas/src").mkdir(parents=True)
            (release / "obj.target/canvas/src/ImageData.o").write_bytes(b"synthetic MH_OBJECT")
            (release / "canvas.node").write_bytes(b"synthetic loadable addon")
            (release.parent / "Makefile").write_text("synthetic build metadata")
        if str(command[-1]).endswith("typescript/bin/tsc"):
            (Path(cwd) / "build").mkdir(); (Path(cwd) / "build/generate_once.js").write_text("compiled fixture")
        return SimpleNamespace(stdout="")
    destination = tmp_path / "stage"
    if escaped_build:
        with pytest.raises(ValueError, match="owned build stage"):
            packaging.prepare(destination, project, fetcher=lambda *_: data, runner=run)
        assert (tmp_path / "unowned-compiler/build/keep").read_text() == "must remain untouched"
        assert not destination.exists()
        return
    result = packaging.prepare(destination, project, fetcher=lambda *_: data, runner=run)
    assert (destination / "bin/node").read_bytes() == b"fixture-node"
    assert (destination / "provider_server/build/generate_once.js").is_file()
    canvas = destination / "provider_server/node_modules/canvas"
    assert (canvas / "build/Release/canvas.node").read_bytes() == b"synthetic loadable addon"
    assert not (canvas / "build/Release/obj.target").exists(), "Native build objects must not require transferable xattr signatures"
    assert not (canvas / "build/Makefile").exists()
    assert not (server / "build").exists() and not (server / "node_modules").exists()
    assert not (destination / "provider_server/src/private-untracked.txt").exists()
    manifest = json.loads((destination / "provider-build.json").read_text())
    assert manifest["provider_commit"] == "7608dd51ee813b48cf9a6d68c6e42cb197ce10e0"
    assert manifest["node_sha256"] == hashlib.sha256(data).hexdigest()
    assert result == destination


def test_checksum_failure_never_activates_partial_stage(tmp_path, monkeypatch):
    project = tmp_path / "project"; project.mkdir()
    def run(*args, **kwargs): return SimpleNamespace(stdout=packaging.PROVIDER_COMMIT)
    with pytest.raises(ValueError, match="checksum"):
        packaging.prepare(tmp_path / "stage", project, runner=run, fetcher=lambda *_: b"corrupt")
    assert not (tmp_path / "stage").exists()


def test_existing_stage_is_never_overwritten(tmp_path):
    (tmp_path / "stage").mkdir(); (tmp_path / "stage/keep").write_text("existing")
    with pytest.raises(FileExistsError): packaging.prepare(tmp_path / "stage", tmp_path)
    assert (tmp_path / "stage/keep").read_text() == "existing"


def test_wrong_provider_pin_stops_before_download(tmp_path):
    with pytest.raises(ValueError, match="pin"):
        packaging.prepare(tmp_path / "stage", tmp_path,
                          runner=lambda *args, **kwargs: SimpleNamespace(stdout="different"),
                          fetcher=lambda *_: pytest.fail("Wrong pin must not fetch"))


def test_archive_cannot_escape_staging_directory(tmp_path, monkeypatch):
    data = archive("../escape"); monkeypatch.setattr(packaging, "NODE_SHA256", hashlib.sha256(data).hexdigest())
    with pytest.raises((ValueError, tarfile.TarError)):
        packaging.extract_node(data, tmp_path / "node")
    assert not (tmp_path / "escape").exists()
