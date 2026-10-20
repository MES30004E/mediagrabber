from pathlib import Path
import sys
from types import SimpleNamespace

from morgan_media_downloader.provider import find_runtime, find_script_home, provider_extractor_args, yt_dlp_javascript_options


def test_frozen_app_uses_bundled_node_and_server_before_external_paths(tmp_path, monkeypatch):
    root = tmp_path / "Contents/Frameworks"
    (root / "bin").mkdir(parents=True); (root / "bin/node").write_text("fixture")
    (root / "provider_server/build").mkdir(parents=True)
    (root / "provider_server/build/generate_once.js").write_text("fixture")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("morgan_media_downloader.provider.shutil.which", lambda _: "/external/node")
    monkeypatch.setattr("morgan_media_downloader.provider.subprocess.run", lambda *args, **kw: SimpleNamespace(stdout="v24.22.0\n"))
    assert find_runtime(for_player=True) == root / "bin/node"
    assert yt_dlp_javascript_options() == {"js_runtimes": {"node": {"path": str(root / "bin/node")}}}
    assert find_script_home() == (root / "provider_server").resolve()
    assert provider_extractor_args("http://127.0.0.1:4416")["youtubepot-bgutilscript"]["server_home"] == [str((root / "provider_server").resolve())]


def test_explicit_provider_configuration_still_takes_precedence(tmp_path, monkeypatch):
    custom = tmp_path / "custom"; (custom / "build").mkdir(parents=True)
    (custom / "build/generate_once.js").write_text("fixture")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    assert find_script_home(str(custom)) == custom.resolve()
