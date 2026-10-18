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
    result = install(home=tmp_path, repository=repository, python=Path(sys.executable))
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
    install(home=tmp_path, repository=missing, python=Path(sys.executable))
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
        install(home=tmp_path, repository=tmp_path, python=Path(sys.executable))
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
