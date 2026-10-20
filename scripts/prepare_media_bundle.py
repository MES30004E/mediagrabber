"""Build verified media-tool sources in an isolated hosted macOS stage."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

SOURCES = {
    "ffmpeg": {"directory": "ffmpeg-9.0.2", "url": "https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz",
               "sha256": "8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e"},
    "aria2": {"directory": "aria2-1.37.0", "url": "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0.tar.xz",
              "sha256": "60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b"},
}
CODEC_FORMULAE = ("aom", "lame", "opus", "libvpx", "x264", "x265")
REQUIRED_ENCODERS = ("libx264", "libx265", "libvpx-vp9", "libaom-av1", "aac", "libmp3lame", "libopus", "flac")
FFMPEG_OPTIONS = ("--disable-autodetect", "--disable-debug", "--disable-doc", "--disable-ffplay",
    "--enable-gpl", "--enable-version3", "--enable-libaom", "--enable-libmp3lame",
    "--enable-libopus", "--enable-libvpx", "--enable-libx264", "--enable-libx265",
    "--enable-audiotoolbox", "--enable-videotoolbox", "--enable-securetransport", "--enable-zlib")
ARIA2_OPTIONS = ("--disable-shared", "--enable-static", "--without-gnutls", "--without-openssl", "--with-appletls",
    "--without-libxml2", "--without-libexpat", "--without-sqlite3", "--without-libcares", "--without-libssh2",
    "--without-libgcrypt", "--without-libnettle", "--without-libgmp")


def download(url):
    if url not in {spec["url"] for spec in SOURCES.values()}: raise ValueError("Unapproved media source")
    with urllib.request.urlopen(url, timeout=60) as response: data = response.read(67_108_865)
    if len(data) > 67_108_864: raise ValueError("Media source archive exceeds limit")
    return data


def run(command, *, cwd=None, env=None):
    try:
        return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=1800, check=True)
    except subprocess.CalledProcessError as error:
        # Build logs are otherwise swallowed by capture_output and the hosted
        # traceback reveals only an exit code. Never dump environment variables.
        print((error.stdout or "")[-8000:], file=sys.stderr)
        print((error.stderr or "")[-8000:], file=sys.stderr)
        raise


def extract(data, spec, destination):
    if hashlib.sha256(data).hexdigest() != spec["sha256"]: raise ValueError("Media source checksum mismatch")
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
        entries = archive.getmembers()
        if len(entries) > 100_000 or sum(max(item.size, 0) for item in entries) > 800_000_000:
            raise ValueError("Media source archive structure exceeds limit")
        for entry in entries:
            path = Path(entry.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != spec["directory"]:
                raise ValueError("Media source archive path rejected")
        archive.extractall(destination, filter="data")
    return destination / spec["directory"]


def validate_tools(bin_directory, runner, *, env=None):
    versions = {}
    for name in ("ffmpeg", "ffprobe"):
        listing = runner([str(bin_directory / name), "-version"], env=env).stdout
        if not re.match(rf"{name} version 9\.0\.2(?:\s|$)", listing) or "--enable-nonfree" in listing:
            raise ValueError(f"Unqualified {name} version/configuration")
        versions[name] = listing
    listing = runner([str(bin_directory / "ffmpeg"), "-hide_banner", "-encoders"], env=env).stdout
    if any(not re.search(rf"\b{re.escape(name)}\b", listing) for name in REQUIRED_ENCODERS):
        raise ValueError("Media build lacks an application encoder")
    if not re.match(r"aria2 version 1\.37\.0(?:\s|$)", runner([str(bin_directory / "aria2c"), "--version"], env=env).stdout):
        raise ValueError("Unqualified aria2 version")
    return versions


def prepare(destination: Path, *, fetcher=download, runner=run):
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink(): raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".morgan-media-", dir=destination.parent) as temporary:
        work = Path(temporary)
        sources = {name: extract(fetcher(spec["url"]), spec, work / name) for name, spec in SOURCES.items()}
        prefixes = [runner(["brew", "--prefix", name]).stdout.strip() for name in CODEC_FORMULAE]
        environment = dict(os.environ, PKG_CONFIG_PATH=os.pathsep.join(str(Path(prefix) / "lib/pkgconfig") for prefix in prefixes),
                           MACOSX_DEPLOYMENT_TARGET="15.0")
        jobs = str(min(os.cpu_count() or 2, 8))
        runner(["./configure", *FFMPEG_OPTIONS], cwd=sources["ffmpeg"], env=environment)
        runner(["make", "-j" + jobs, "ffmpeg", "ffprobe"], cwd=sources["ffmpeg"], env=environment)
        runner(["./configure", *ARIA2_OPTIONS], cwd=sources["aria2"], env=environment)
        runner(["make", "-j" + jobs], cwd=sources["aria2"], env=environment)
        output = work / "output"; binaries = output / "bin"; binaries.mkdir(parents=True)
        for name, original in (("ffmpeg", sources["ffmpeg"] / "ffmpeg"), ("ffprobe", sources["ffmpeg"] / "ffprobe"),
                               ("aria2c", sources["aria2"] / "src/aria2c")):
            shutil.copy2(original, binaries / name); (binaries / name).chmod(0o755)
        versions = validate_tools(binaries, runner, env=environment)
        licenses = output / "licenses/media"; licenses.mkdir(parents=True)
        for name, directory in sources.items():
            for license_file in directory.glob("COPYING*"):
                if license_file.is_file(): shutil.copy2(license_file, licenses / f"{name}-{license_file.name}")
        formulae = json.loads(runner(["brew", "info", "--json=v2", *CODEC_FORMULAE]).stdout)
        (licenses / "codec-build-formulae.json").write_text(json.dumps(formulae, indent=2) + "\n")
        manifest = {"schema": 1, "ffmpeg_version": "9.0.2", "aria2_version": "1.37.0", "sources": SOURCES,
            "ffmpeg_options": FFMPEG_OPTIONS, "aria2_options": ARIA2_OPTIONS,
            "versions": versions, "deployment_target": "15.0",
            "binaries": {name: {"sha256": hashlib.sha256((binaries / name).read_bytes()).hexdigest()}
                         for name in ("ffmpeg", "ffprobe", "aria2c")},
            "scope": "Hosted integration only; source-offer, third-party licensing and release approval remain required"}
        (output / "media-build.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if destination.exists() or destination.is_symlink(): raise FileExistsError(destination)
        output.rename(destination)
    return destination


if __name__ == "__main__":
    if os.environ.get("GITHUB_ACTIONS") != "true" or sys.platform != "darwin" or platform.machine() != "arm64":
        raise SystemExit("Media compilation is restricted to hosted arm64 macOS packaging; no local build is required.")
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("destination", type=Path)
    print(prepare(parser.parse_args().destination))
