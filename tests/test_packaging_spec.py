import json
from pathlib import Path
import runpy
from types import SimpleNamespace


def test_staged_media_bundle_advertises_the_tools_actual_os_floor(tmp_path, monkeypatch):
    stage = tmp_path / "stage"; stage.mkdir(); (stage / "media-build.json").write_text(json.dumps({"deployment_target": "15.0"}))
    monkeypatch.setenv("MORGAN_MEDIA_STAGE", str(stage))
    monkeypatch.delenv("MORGAN_PROVIDER_STAGE", raising=False)
    output = {}
    def analysis(*args, **kwargs):
        if "datas" in kwargs: output.setdefault("inputs", []).extend(kwargs["datas"])
        return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])
    def bundle(*args, **kwargs): output.update(kwargs)
    # Execute the real spec's wiring against inert build-tool boundaries: this
    # does not import PyInstaller, sign, compile or create an application.
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "MorganMediaDownloader.spec"), init_globals={
        "SPECPATH": str(tmp_path), "Analysis": analysis, "PYZ": lambda *a, **kw: None,
        "EXE": lambda *a, **kw: None, "COLLECT": lambda *a, **kw: None, "BUNDLE": bundle})
    assert output["info_plist"]["LSMinimumSystemVersion"] == "15.0"
    assert (str(tmp_path / "resources/bin"), "bin") not in output["inputs"]
