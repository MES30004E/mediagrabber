import json
from types import SimpleNamespace

import pytest

from scripts.check_packaged_app import verify


def bundle(tmp_path):
    app = tmp_path / "App.app"; (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/MacOS/Morgan Media Downloader").write_text("synthetic executable")
    return app


def test_packaged_gui_probe_requires_cocoa_frozen_render_and_clean_shutdown(tmp_path):
    app = bundle(tmp_path)
    def run(command, **kwargs):
        assert command[0] == str(app / "Contents/MacOS/Morgan Media Downloader")
        assert kwargs["env"]["QT_QPA_PLATFORM"] == "cocoa" and kwargs["env"]["PATH"] == "/usr/bin:/bin"
        assert "PYTHONPATH" not in kwargs["env"] and "DYLD_LIBRARY_PATH" not in kwargs["env"]
        from pathlib import Path
        Path(command[-1]).write_text(json.dumps({"schema": 1, "result": "passed", "qt_platform": "cocoa", "frozen": True,
            "rendered": True, "closed_cleanly": True, "bundled_dependency_discovery": True,
            "tabs": ["Download", "Queue", "History", "Console", "Settings"]}))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    assert verify(app, runner=run)["qt_platform"] == "cocoa"


@pytest.mark.parametrize("bad_field,bad_value", [("frozen", False), ("qt_platform", "offscreen"), ("rendered", False),
    ("closed_cleanly", False), ("bundled_dependency_discovery", False)])
def test_packaged_gui_probe_never_accepts_source_headless_or_partial_success(tmp_path, bad_field, bad_value):
    app = bundle(tmp_path)
    def run(command, **kwargs):
        from pathlib import Path
        data = {"schema": 1, "result": "passed", "qt_platform": "cocoa", "frozen": True,
            "rendered": True, "closed_cleanly": True, "bundled_dependency_discovery": True,
            "tabs": ["Download", "Queue", "History", "Console", "Settings"]}
        data[bad_field] = bad_value; Path(command[-1]).write_text(json.dumps(data))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    with pytest.raises(RuntimeError): verify(app, runner=run)


def test_failed_startup_report_preserves_redacted_diagnostic(tmp_path):
    app = bundle(tmp_path)
    def run(command, **kwargs):
        from pathlib import Path
        Path(command[-1]).write_text(json.dumps({"result": "failed", "error_type": "RuntimeError", "error": "synthetic startup failure cookie=[redacted]"}))
        return SimpleNamespace(returncode=2, stdout="", stderr="")
    with pytest.raises(RuntimeError, match="synthetic startup failure"):
        verify(app, runner=run)
