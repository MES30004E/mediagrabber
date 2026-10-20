import json
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import sys

import pytest


def test_install_host_and_launcher_then_ping_and_remove(tmp_path):
    from morgan_media_downloader.youtube_companion.setup import install, remove
    from morgan_media_downloader.youtube_companion.bridge import ORIGIN
    repository = Path(__file__).resolve().parents[1]
    result = install(home=tmp_path, repository=repository, python=Path(sys.executable), launcher=True)
    manifest = json.loads(result["manifest"].read_text())
    assert manifest["allowed_origins"] == ["chrome-extension://cplbbpknliffempndiphmhaolpgipdgn/"]
    assert os.access(manifest["path"], os.X_OK)
    packet = b'{"type":"ping"}'
    process = subprocess.run([manifest["path"], ORIGIN], input=struct.pack("=I", len(packet)) + packet,
                             capture_output=True, timeout=5)
    assert process.returncode == 0 and process.stderr == b""
    length, = struct.unpack("=I", process.stdout[:4])
    assert json.loads(process.stdout[4:4+length]) == {"status": "ready", "protocol": 1}
    info = plistlib.loads((result["launcher"] / "Contents/Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "launch"
    missing = tmp_path / "missing-repository"
    # Reinstallation may update only artifacts identifiable as ours.
    install(home=tmp_path, repository=missing, python=Path(sys.executable), launcher=True)
    launched = subprocess.run([str(result["launcher"] / "Contents/MacOS/launch")],
                              env={**os.environ, "MORGAN_LAUNCHER_NO_DIALOG": "1"}, capture_output=True, timeout=5)
    assert launched.returncode != 0 and b"external drive" in launched.stderr.lower()
    remove(home=tmp_path)
    assert not result["manifest"].exists() and not result["launcher"].exists()


def test_installer_refuses_foreign_launcher_without_overwrite(tmp_path):
    from morgan_media_downloader.youtube_companion.setup import install
    destination = tmp_path / "Desktop/Morgan Media Downloader Dev.app"
    destination.mkdir(parents=True); (destination / "keep").write_text("foreign")
    with pytest.raises(ValueError):
        install(home=tmp_path, repository=tmp_path, python=Path(sys.executable), launcher=True)
    assert (destination / "keep").read_text() == "foreign"


def test_host_only_setup_does_not_inspect_or_replace_foreign_launcher(tmp_path):
    from morgan_media_downloader.youtube_companion.setup import install
    destination = tmp_path / "Desktop/Morgan Media Downloader Dev.app"
    destination.mkdir(parents=True); (destination / "keep").write_text("foreign")
    result = install(home=tmp_path, repository=tmp_path, python=Path(sys.executable), launcher=False)
    assert result["manifest"].is_file() and (destination / "keep").read_text() == "foreign"


def test_fixed_extension_public_key_matches_native_host_identity():
    import base64
    import hashlib
    from morgan_media_downloader.youtube_companion.bridge import EXTENSION_ID
    manifest = json.loads((Path(__file__).resolve().parents[1] / "companion/chrome/manifest.json").read_text())
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(char, 16)) for char in digest) == EXTENSION_ID


def _fake_bundle(tmp_path, monkeypatch):
    bundle = tmp_path / "App with spaces.app/Contents"
    executable = bundle / "MacOS/Morgan Media Downloader"
    executable.parent.mkdir(parents=True); executable.write_text("fixture GUI"); executable.chmod(0o700)
    helper = executable.with_name("MorganNativeHost")
    helper.write_text('#!/bin/sh\nprintf "%s\\n" "$PYINSTALLER_RESET_ENVIRONMENT" "$1"\n')
    helper.chmod(0o700)
    extension = bundle / "Resources/companion/chrome"
    extension.mkdir(parents=True)
    for name in ("manifest.json", "core.mjs", "popup.js", "popup.html", "popup.css"):
        (extension / name).write_text("fixture asset")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle / "Resources"), raising=False)
    return helper


def test_frozen_registration_uses_bundled_helper_without_python_or_desktop_launcher(tmp_path, monkeypatch):
    from morgan_media_downloader.youtube_companion.setup import install, remove
    from morgan_media_downloader.youtube_companion.bridge import ORIGIN
    helper = _fake_bundle(tmp_path, monkeypatch)
    home = tmp_path / "user"
    result = install(home=home)
    assert not result["launcher"].exists()
    assert not (result["host"] / "bootstrap.py").exists()
    assert str(helper) in (result["host"] / "host").read_text()
    manifest = json.loads(result["manifest"].read_text())
    reply = subprocess.run([manifest["path"], ORIGIN], capture_output=True, timeout=5, check=True)
    assert reply.stdout.decode().splitlines() == ["1", ORIGIN]
    assert reply.stderr == b""
    foreign = home / "Desktop/Morgan Media Downloader Dev.app"
    foreign.mkdir(parents=True); (foreign / "keep").write_text("foreign")
    remove(home=home)
    assert not result["manifest"].exists() and (foreign / "keep").read_text() == "foreign"


@pytest.mark.parametrize("broken", ["missing", "not_executable", "symlink", "missing_extension"])
def test_incomplete_bundle_cannot_replace_existing_host(tmp_path, monkeypatch, broken):
    from morgan_media_downloader.youtube_companion.setup import install
    home = tmp_path / "user"
    old = install(home=home, repository=tmp_path, python=Path(sys.executable), launcher=False)
    original = old["manifest"].read_bytes(), (old["host"] / "host").read_bytes()
    helper = _fake_bundle(tmp_path, monkeypatch)
    if broken == "missing": helper.unlink()
    if broken == "not_executable": helper.chmod(0o600)
    if broken == "symlink":
        target = helper.with_name("foreign"); helper.rename(target); helper.symlink_to(target)
    if broken == "missing_extension":
        (helper.parent.parent / "Resources/companion/chrome/manifest.json").unlink()
    with pytest.raises(ValueError): install(home=home)
    assert original == (old["manifest"].read_bytes(), (old["host"] / "host").read_bytes())


def test_native_host_source_entrypoint_has_only_protocol_output(tmp_path):
    from morgan_media_downloader.youtube_companion.bridge import ORIGIN
    root = Path(__file__).resolve().parents[1]
    packet = b'{"type":"ping"}'
    process = subprocess.run([sys.executable, str(root / "native_host_launcher.py"), ORIGIN],
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        input=struct.pack("=I", len(packet)) + packet, capture_output=True, timeout=5)
    assert process.returncode == 0 and process.stderr == b""
    length, = struct.unpack("=I", process.stdout[:4])
    assert len(process.stdout) == length + 4
    assert json.loads(process.stdout[4:]) == {"status": "ready", "protocol": 1}


def test_default_source_setup_and_cli_do_not_create_a_desktop_launcher(tmp_path, monkeypatch, capsys):
    from morgan_media_downloader.youtube_companion import setup
    result = setup.install(home=tmp_path)
    assert not result["launcher"].exists()
    real_install = setup.install
    monkeypatch.setattr(setup, "install", lambda **kwargs: real_install(home=tmp_path, **kwargs))
    monkeypatch.setattr(sys, "argv", ["setup", "install"])
    assert setup.main() == 0
    assert not result["launcher"].exists()
    assert "development launcher installed" not in capsys.readouterr().out.lower()


def test_source_to_frozen_registration_migration_removes_only_owned_bootstrap(tmp_path, monkeypatch):
    from morgan_media_downloader.youtube_companion.setup import install
    home = tmp_path / "user"
    result = install(home=home)
    assert (result["host"] / "bootstrap.py").is_file()
    helper = _fake_bundle(tmp_path, monkeypatch)
    install(home=home)
    assert not (result["host"] / "bootstrap.py").exists()
    assert str(helper) in (result["host"] / "host").read_text()
    assert not result["launcher"].exists()
