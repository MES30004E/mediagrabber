import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.check_packaged_media import verify


def bundle(tmp_path):
    app = tmp_path / "App.app"; binaries = app / "Contents/Frameworks/bin"; binaries.mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe", "aria2c"): (binaries / name).write_text("synthetic tool")
    return app


def test_packaged_media_exercises_actual_binary_paths_and_checks_encoded_streams(tmp_path):
    app = bundle(tmp_path); calls = []
    expected = {"source.mp4": ["h264", "aac"], "remux.mkv": ["h264", "aac"], "hevc.mkv": ["hevc"],
        "vp9.mkv": ["vp9"], "av1.mkv": ["av1"], "aac.mka": ["aac"], "mp3.mka": ["mp3"], "opus.mka": ["opus"], "flac.mka": ["flac"]}
    def run(command, **kwargs):
        calls.append(command)
        assert Path(command[0]).is_relative_to(app)
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin"
        if "-version" in command: return SimpleNamespace(stdout=f"{Path(command[0]).name} version 9.0.2\n")
        if "--version" in command: return SimpleNamespace(stdout="aria2 version 1.37.0\n")
        if "-encoders" in command: return SimpleNamespace(stdout=" V..... libx264 libx265 libvpx-vp9 libaom-av1 aac libmp3lame libopus flac")
        output = Path(command[-1])
        if Path(command[0]).name == "ffprobe":
            assert output.is_file() and output.stat().st_size
            return SimpleNamespace(stdout=json.dumps({"streams": [{"codec_name": codec} for codec in expected[output.name]], "format": {"duration": "0.5"}}))
        output.write_bytes(b"synthetic encoded fixture"); return SimpleNamespace(stdout="")
    result = verify(app, runner=run)
    assert result["media_cases"] == 9
    assert len([c for c in calls if Path(c[0]).name == "ffprobe" and "-version" not in c]) == 9
    assert any("copy" in c and c[-1].endswith("remux.mkv") for c in calls)


def test_packaged_media_rejects_missing_tool_without_path_fallback(tmp_path):
    app = bundle(tmp_path); (app / "Contents/Frameworks/bin/ffmpeg").unlink()
    with pytest.raises(RuntimeError, match="missing"):
        verify(app, runner=lambda *args, **kwargs: pytest.fail("No external tool may run"))


def test_packaged_media_rejects_probe_that_does_not_confirm_output_streams(tmp_path):
    app = bundle(tmp_path)
    def run(command, **kwargs):
        if "-version" in command: return SimpleNamespace(stdout=f"{Path(command[0]).name} version 9.0.2\n")
        if "--version" in command: return SimpleNamespace(stdout="aria2 version 1.37.0\n")
        if "-encoders" in command: return SimpleNamespace(stdout="libx264 libx265 libvpx-vp9 libaom-av1 aac libmp3lame libopus flac")
        if Path(command[0]).name == "ffprobe": return SimpleNamespace(stdout='{"streams":[],"format":{"duration":"0.5"}}')
        Path(command[-1]).write_bytes(b"synthetic output"); return SimpleNamespace(stdout="")
    with pytest.raises(RuntimeError, match="streams"): verify(app, runner=run)
