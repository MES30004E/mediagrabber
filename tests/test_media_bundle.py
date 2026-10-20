import hashlib
import io
import json
from pathlib import Path
import tarfile
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import prepare_media_bundle as packaging


def archive(root):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:xz") as stream:
        for name in ("configure", "COPYING", "COPYING.GPLv3"):
            data = b"synthetic source fixture"
            info = tarfile.TarInfo(f"{root}/{name}"); info.size = len(data)
            stream.addfile(info, io.BytesIO(data))
    return output.getvalue()


def inputs(monkeypatch):
    archives = {}
    for name, spec in packaging.SOURCES.items():
        data = archive(spec["directory"]); archives[spec["url"]] = data
        monkeypatch.setitem(spec, "sha256", hashlib.sha256(data).hexdigest())
    return archives


def builder(*, nonfree=False, missing_encoder=False):
    def run(command, *, cwd=None, env=None):
        if command[:2] == ["brew", "--prefix"]: return SimpleNamespace(stdout="/fixture/brew/" + command[2])
        if command[:2] == ["brew", "info"]: return SimpleNamespace(stdout=json.dumps({"formulae": [{"name": "synthetic"}]}))
        if command[0] == "make":
            if Path(cwd).name.startswith("ffmpeg"):
                for name in ("ffmpeg", "ffprobe"): (Path(cwd) / name).write_text("synthetic compiled binary")
            else:
                (Path(cwd) / "src").mkdir(exist_ok=True); (Path(cwd) / "src/aria2c").write_text("synthetic aria2c")
        if "-version" in command:
            return SimpleNamespace(stdout=f"{Path(command[0]).name} version 9.0.2\nconfiguration: --enable-gpl" + (" --enable-nonfree" if nonfree else ""))
        if "-encoders" in command:
            encoders = ["libx264", "libx265", "libvpx-vp9", "libaom-av1", "aac", "libmp3lame", "libopus", "flac"]
            return SimpleNamespace(stdout="\n".join(" V..... " + item for item in encoders if not missing_encoder or item != "libaom-av1"))
        if command[-1] == "--version": return SimpleNamespace(stdout="aria2 version 1.37.0\n")
        return SimpleNamespace(stdout="")
    return run


def test_media_stage_contains_only_new_verified_binaries_and_provenance(tmp_path, monkeypatch):
    archives = inputs(monkeypatch)
    original = tmp_path / "resources/bin"; original.mkdir(parents=True); (original / "ffmpeg").write_text("keep existing")
    stage = packaging.prepare(tmp_path / "stage", fetcher=archives.__getitem__, runner=builder())
    assert {p.name for p in (stage / "bin").iterdir()} == {"ffmpeg", "ffprobe", "aria2c"}
    assert (original / "ffmpeg").read_text() == "keep existing"
    manifest = json.loads((stage / "media-build.json").read_text())
    assert manifest["ffmpeg_version"] == "9.0.2" and manifest["aria2_version"] == "1.37.0"
    assert len(manifest["sources"]) == 2 and len(manifest["binaries"]["ffmpeg"]["sha256"]) == 64
    assert (stage / "licenses/media/ffmpeg-COPYING.GPLv3").is_file()
    assert (stage / "licenses/media/aria2-COPYING").is_file()


@pytest.mark.parametrize("kwargs", [{"nonfree": True}, {"missing_encoder": True}])
def test_incompatible_media_build_never_activates(tmp_path, monkeypatch, kwargs):
    archives = inputs(monkeypatch)
    with pytest.raises(ValueError):
        packaging.prepare(tmp_path / "stage", fetcher=archives.__getitem__, runner=builder(**kwargs))
    assert not (tmp_path / "stage").exists()


def test_corrupt_source_never_executes_build(tmp_path):
    def no_build(*args, **kwargs): pytest.fail("Checksum must precede build execution")
    with pytest.raises(ValueError, match="checksum"):
        packaging.prepare(tmp_path / "stage", fetcher=lambda _: b"corrupt", runner=no_build)
    assert not (tmp_path / "stage").exists()


def test_existing_media_stage_is_preserved(tmp_path):
    stage = tmp_path / "stage"; stage.mkdir(); (stage / "keep").write_text("existing")
    with pytest.raises(FileExistsError): packaging.prepare(stage)
    assert (stage / "keep").read_text() == "existing"


def test_failed_build_preserves_bounded_diagnostics_for_hosted_investigation(capsys):
    with pytest.raises(subprocess.CalledProcessError):
        packaging.run([sys.executable, "-c", "import sys; print('x'*30000+'synthetic-build-tail',file=sys.stderr); sys.exit(1)"])
    error = capsys.readouterr().err
    assert "synthetic-build-tail" in error
    assert len(error) < 20000


@pytest.mark.parametrize("bad_tool,bad_version", [("ffmpeg", "9.0.20"), ("aria2c", "1.37.01")])
def test_media_version_requires_exact_token_not_numeric_prefix(tmp_path, bad_tool, bad_version):
    original = builder()
    def run(command, **kwargs):
        value = original(command, **kwargs)
        if Path(command[0]).name == bad_tool and command[-1] in ("-version", "--version"):
            value.stdout = value.stdout.replace("9.0.2" if bad_tool == "ffmpeg" else "1.37.0", bad_version)
        return value
    with pytest.raises(ValueError): packaging.validate_tools(tmp_path, run)
