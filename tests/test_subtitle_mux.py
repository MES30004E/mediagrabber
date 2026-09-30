import shutil
import subprocess
from pathlib import Path

import pytest

from morgan_media_downloader.media_verification import inspect_media
from morgan_media_downloader.subtitle_mux import (
    mux_subtitles_atomically, parse_subtitle_languages, subtitle_download_flags,
)


ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / "resources" / "bin" / "ffmpeg"
FFPROBE = ROOT / "resources" / "bin" / "ffprobe"


def _media(path: Path):
    subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=320x180:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)], check=True)


def test_subtitle_language_parsing_and_source_modes():
    assert parse_subtitle_languages(" en, zh-Hans,ja,en ") == ["en", "zh-Hans", "ja"]
    assert subtitle_download_flags("Normal subtitles") == (True, False)
    assert subtitle_download_flags("Normal + automatic captions") == (True, True)
    assert subtitle_download_flags("Automatic captions only") == (False, True)


@pytest.mark.parametrize("suffix,codec", [(".mp4", "mov_text"), (".mkv", "subrip")])
def test_real_ffmpeg_mux_is_atomic_and_ffprobe_verifies_two_languages(tmp_path: Path, suffix: str, codec: str):
    media = tmp_path / f"result{suffix}"; _media(media)
    en = tmp_path / "result.en.vtt"; ja = tmp_path / "result.ja.srt"
    en_text = "WEBVTT\n\n00:00:00.250 --> 00:00:01.250\nEnglish cue\n"
    ja_text = "1\n00:00:00,500 --> 00:00:01,500\nJapanese cue\n"
    en.write_text(en_text, encoding="utf-8"); ja.write_text(ja_text, encoding="utf-8")
    details = mux_subtitles_atomically(str(media), [
        {"language": "en", "name": "English", "filepath": str(en)},
        {"language": "ja", "name": "Japanese", "filepath": str(ja)},
    ], ffmpeg=str(FFMPEG), ffprobe=str(FFPROBE))
    verified = inspect_media(str(media), str(FFPROBE))
    assert details["verified"] and verified["subtitle_count"] == 2
    assert {stream["language"] for stream in verified["subtitle_streams"]} == {"eng", "jpn"}
    assert all(stream["codec"] == codec for stream in verified["subtitle_streams"])
    if suffix == ".mp4": assert verified["faststart"] is True
    assert en.read_text(encoding="utf-8") == en_text and ja.read_text(encoding="utf-8") == ja_text
    assert not list(tmp_path.glob(".*.subtitle-mux-*"))


def test_mux_failure_preserves_only_valid_media(tmp_path: Path):
    media = tmp_path / "valid.mp4"; media.write_bytes(b"original-valid-media")
    subtitle = tmp_path / "valid.en.vtt"; subtitle.write_text("WEBVTT\n", encoding="utf-8")
    def fail(*_args, **_kwargs): return subprocess.CompletedProcess([], 1, "", "mux failed")
    with pytest.raises(RuntimeError, match="could not mux"):
        mux_subtitles_atomically(str(media), [{"language": "en", "filepath": str(subtitle)}],
                                 ffmpeg="/fake/ffmpeg", runner=fail)
    assert media.read_bytes() == b"original-valid-media"
    assert subtitle.exists()
