import subprocess
from pathlib import Path

from morgan_media_downloader.local_converter import analyse_local_video, convert_local_video, default_conversion_output


ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / "resources" / "bin" / "ffmpeg"


def test_local_h264_opus_converts_only_audio_and_preserves_input(tmp_path):
    source = tmp_path / "input.mkv"; output = tmp_path / "Movie - macOS.mp4"
    subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "0.2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "libopus", str(source)], check=True)
    events = []; result = convert_local_video(str(source), str(output), progress=events.append)
    assert source.exists() and output.exists() and result["compatibility"]["verified"]
    assert any("Audio -> AAC" in item for item in result["conversions"])
    assert not any("Video -> H.264" in item for item in result["conversions"])
    assert events[-1] == {"stage": "Completed", "progress": 100}
    assert analyse_local_video(str(output))["compatibility"]["verified"]


def test_default_output_never_selects_input_and_avoids_existing_file(tmp_path):
    source = tmp_path / "Movie.mp4"; source.write_bytes(b"source")
    first = Path(default_conversion_output(str(source))); first.write_bytes(b"existing")
    assert default_conversion_output(str(source)).endswith("Movie - converted 2.mp4")
