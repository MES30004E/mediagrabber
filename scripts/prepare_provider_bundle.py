"""Hosted-only Node/provider staging; does not modify the upstream checkout."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

NODE_VERSION = "v24.22.0"
NODE_DIRECTORY = f"node-{NODE_VERSION}-darwin-arm64"
NODE_URL = f"https://nodejs.org/dist/{NODE_VERSION}/{NODE_DIRECTORY}.tar.xz"
NODE_SHA256 = "75ddfb875bbd868ebe57536f4442225f54dd10f6d2178dd439de869a5c648dc3"
PROVIDER_COMMIT = "7608dd51ee813b48cf9a6d68c6e42cb197ce10e0"
PROVIDER_VERSION = "1.3.1"


def download(url):
    if url != NODE_URL: raise ValueError("Unapproved Node source")
    with urllib.request.urlopen(url, timeout=30) as response:
        result = response.read(134_217_729)
    if len(result) > 134_217_728: raise ValueError("Node archive exceeds limit")
    return result


def extract_node(data: bytes, directory: Path):
    if hashlib.sha256(data).hexdigest() != NODE_SHA256: raise ValueError("Node archive checksum mismatch")
    directory.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
        entries = archive.getmembers()
        if len(entries) > 100_000 or sum(max(entry.size, 0) for entry in entries) > 600_000_000:
            raise ValueError("Node archive structure exceeds limit")
        for entry in entries:
            parts = Path(entry.name).parts
            if not parts or parts[0] != NODE_DIRECTORY or ".." in parts or Path(entry.name).is_absolute():
                raise ValueError("Node archive path rejected")
        archive.extractall(directory, filter="data")
    return directory / NODE_DIRECTORY


def run(command, *, cwd=None, env=None):
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                          timeout=600, check=True)


def prepare(destination: Path, project: Path, *, fetcher=download, runner=run):
    destination, project = destination.absolute(), project.resolve()
    if destination.exists() or destination.is_symlink(): raise FileExistsError(destination)
    provider = project / "bgutil-ytdlp-pot-provider"
    if runner(["git", "-C", str(provider), "rev-parse", "HEAD"]).stdout.strip() != PROVIDER_COMMIT:
        raise ValueError("Provider checkout does not match the qualified pin")
    runner(["git", "-C", str(provider), "diff", "--exit-code", "HEAD", "--", "server", "LICENSE"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".morgan-provider-", dir=destination.parent) as temporary:
        work = Path(temporary)
        source = extract_node(fetcher(NODE_URL), work / "node-source")
        output = work / "output"; (output / "bin").mkdir(parents=True)
        node = output / "bin/node"; shutil.copy2(source / "bin/node", node); node.chmod(0o755)
        if runner([str(node), "--version"]).stdout.strip() != NODE_VERSION: raise ValueError("Node version mismatch")
        server = output / "provider_server"; server.mkdir()
        for name in ("package.json", "package-lock.json", "tsconfig.json"):
            shutil.copy2(provider / "server" / name, server / name)
        tracked = runner(["git", "-C", str(provider), "ls-files", "-z", "--", "server/src", "server/types"]).stdout.split("\0")
        if not any(tracked): raise ValueError("Provider tracked sources missing")
        for name in filter(None, tracked):
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts or relative.parts[:2] not in (("server", "src"), ("server", "types")):
                raise ValueError("Provider source path rejected")
            original = provider / relative
            if original.is_symlink() or not original.resolve().is_relative_to(provider.resolve()):
                raise ValueError("Provider source escapes checkout")
            target = server / relative.relative_to("server")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
        shutil.copy2(provider / "LICENSE", server / "LICENSE")
        licenses = output / "licenses"; licenses.mkdir(); shutil.copy2(source / "LICENSE", licenses / "NODE_LICENSE")
        userconfig = work / "npmrc"; userconfig.write_text("")
        environment = dict(os.environ, PATH=str(node.parent) + os.pathsep + os.environ.get("PATH", ""),
            npm_config_userconfig=str(userconfig), npm_config_cache=str(work / "npm-cache"),
            npm_config_build_from_source="true", npm_config_nodedir=str(source),
            npm_config_python=sys.executable, XDG_CACHE_HOME=str(work / "provider-cache"))
        npm = [str(node), str(source / "lib/node_modules/npm/bin/npm-cli.js")]
        runner([*npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=server, env=environment)
        # Only the locked Canvas package's build script is enabled; no unchecked
        # prebuilt native add-on or unrelated npm lifecycle script is accepted.
        runner([*npm, "rebuild", "canvas", "--no-audit", "--no-fund"], cwd=server, env=environment)
        runner([str(node), str(server / "node_modules/typescript/bin/tsc")], cwd=server, env=environment)
        runner([*npm, "prune", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=server, env=environment)
        runner([str(node), "-e", "const c=require('canvas').createCanvas(2,2);if(!c.toBuffer('image/png').length)process.exit(1)"], cwd=server, env=environment)
        version = runner([str(node), str(server / "build/generate_once.js"), "--version"], cwd=server, env=environment).stdout.strip()
        if version != PROVIDER_VERSION: raise ValueError("Provider version mismatch")
        manifest = {"schema": 1, "node_version": NODE_VERSION, "node_url": NODE_URL,
                    "node_sha256": NODE_SHA256, "provider_commit": PROVIDER_COMMIT,
                    "provider_version": version, "package_lock_sha256": hashlib.sha256((server / "package-lock.json").read_bytes()).hexdigest(),
                    "scope": "Build/import checks only; token generation and release qualification remain separate"}
        (output / "provider-build.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if destination.exists() or destination.is_symlink(): raise FileExistsError(destination)
        output.rename(destination)
    return destination


if __name__ == "__main__":
    if os.environ.get("GITHUB_ACTIONS") != "true" or sys.platform != "darwin" or platform.machine() != "arm64":
        raise SystemExit("Provider compilation is restricted to hosted arm64 macOS packaging; no local build is required.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    print(prepare(arguments.destination, arguments.project))
