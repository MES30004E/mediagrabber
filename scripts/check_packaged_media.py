"""Offline synthetic codec/remux qualification of the actual bundled media tools."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

if __package__:
    from .prepare_media_bundle import validate_tools
else:
    from prepare_media_bundle import validate_tools


def verify(app: Path, *, runner=subprocess.run):
    contents = app.resolve(strict=True) / "Contents"
    binaries = contents / "Frameworks/bin"
    for name in ("ffmpeg", "ffprobe", "aria2c"):
        path = binaries / name
        if not path.is_file(): raise RuntimeError(f"Bundled {name} missing")
        if not path.resolve().is_relative_to(contents): raise RuntimeError("Media tool escapes bundle")
    with tempfile.TemporaryDirectory(prefix="morgan-media-probe-") as temporary:
        work = Path(temporary)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("DYLD_")}
        environment.update(PATH="/usr/bin:/bin", HOME=temporary, XDG_CACHE_HOME=temporary)
        def call(command, *, env=None):
            return runner(command, cwd=temporary, env=environment, capture_output=True, text=True, timeout=90, check=True)
        validate_tools(binaries, call)
        ffmpeg, ffprobe = str(binaries / "ffmpeg"), str(binaries / "ffprobe")
        def encode(arguments, filename, codecs):
            output = work / filename
            call([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", *arguments, str(output)])
            if not output.is_file() or not output.stat().st_size: raise RuntimeError("Media output missing or empty")
            details = json.loads(call([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]).stdout)
            if [stream.get("codec_name") for stream in details.get("streams", [])] != codecs:
                raise RuntimeError(f"Media output streams do not match: {filename}")
            if not 0 < float(details.get("format", {}).get("duration", "0")) < 3:
                raise RuntimeError("Media output duration is invalid")
            return str(output)
        source = encode(["-f", "lavfi", "-i", "color=c=black:s=32x32:r=4", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "0.5", "-c:v", "libx264", "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac"], "source.mp4", ["h264", "aac"])
        encode(["-i", source, "-map", "0", "-c", "copy"], "remux.mkv", ["h264", "aac"])
        for codec, encoder, extra in (("hevc", "libx265", ["-preset", "ultrafast", "-x265-params", "pools=1:frame-threads=1:log-level=error"]),
                                      ("vp9", "libvpx-vp9", ["-deadline", "realtime", "-cpu-used", "8"]),
                                      ("av1", "libaom-av1", ["-cpu-used", "8"])):
            encode(["-i", source, "-an", "-c:v", encoder, "-threads", "2", *extra], codec + ".mkv", [codec])
        for codec, encoder in (("aac", "aac"), ("mp3", "libmp3lame"), ("opus", "libopus"), ("flac", "flac")):
            encode(["-i", source, "-vn", "-c:a", encoder], codec + ".mka", [codec])
    return {"media_cases": 9, "scope": "Synthetic offline codecs/remux only; no torrent transfers or live downloads"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("app", type=Path)
    print(json.dumps(verify(parser.parse_args().app), sort_keys=True))
