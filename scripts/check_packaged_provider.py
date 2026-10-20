"""Offline provider/Node and native-dependency checks; never generates a token."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def verify_payload(app: Path, *, runner=subprocess.run):
    contents = app.resolve(strict=True) / "Contents"
    node = contents / "Frameworks/bin/node"
    server = contents / "Resources/provider_server"
    entry = server / "build/generate_once.js"
    manifest = json.loads((contents / "Resources/provider-build.json").read_text())
    if manifest.get("provider_commit") != "7608dd51ee813b48cf9a6d68c6e42cb197ce10e0":
        raise RuntimeError("Packaged provider pin mismatch")
    if not node.is_file() or not entry.is_file(): raise RuntimeError("Packaged provider/runtime missing")
    for resource in (node, entry):
        if not resource.resolve().is_relative_to(contents): raise RuntimeError("Packaged provider path escapes bundle")
    with tempfile.TemporaryDirectory(prefix="morgan-provider-probe-") as temporary:
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"NODE_PATH", "NODE_OPTIONS", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "PYTHONPATH", "VIRTUAL_ENV"}}
        environment.update(PATH="/usr/bin:/bin", XDG_CACHE_HOME=temporary)
        def call(arguments):
            return runner([str(node), *arguments], cwd=temporary, env=environment,
                          capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        version = call(["--version"])
        provider = call([str(entry), "--version"])
        if version != "v24.22.0" or version != manifest.get("node_version") or provider != "1.3.1" or provider != manifest.get("provider_version"):
            raise RuntimeError("Packaged Node/provider version mismatch")
        call(["-e", "const {createRequire}=require('module');const c=createRequire(process.argv[1])('canvas').createCanvas(2,2);if(!c.toBuffer('image/png').length)process.exit(1)", str(entry)])
    return {"node_version": version, "provider_version": provider, "canvas": "native PNG buffer generated",
            "scope": "Offline build/import only; PO-token generation/live download not tested"}


def verify_native_dependencies(app: Path):
    app = app.resolve(strict=True)
    magic = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf"}
    seen = set()
    for path in app.rglob("*"):
        if not path.is_file(): continue
        resolved = path.resolve()
        if not resolved.is_relative_to(app): raise RuntimeError("Packaged file escapes bundle")
        if resolved in seen: continue
        seen.add(resolved)
        path = resolved  # dyld resolves a framework's real location, not its shallow alias.
        with path.open("rb") as stream:
            if stream.read(4) not in magic: continue
        executable = (app / "Contents/MacOS") if (app / "Contents/MacOS").is_dir() else path.parent
        if path.name == "node": executable = path.parent
        def relative_location(value):
            for prefix, base in (("@loader_path", path.parent), ("@executable_path", executable)):
                if value == prefix or value.startswith(prefix + "/"):
                    location = (base / value[len(prefix):].lstrip("/")).resolve()
                    if location.is_relative_to(app): return location
            raise RuntimeError(f"Packaged Mach-O {path.relative_to(app)} retains an external path: {value}")
        commands = subprocess.run(["/usr/bin/otool", "-l", str(path)], capture_output=True, text=True, timeout=15, check=True).stdout
        rpaths = []
        load_command = ""
        identity = None
        for line in commands.splitlines():
            stripped = line.strip()
            if stripped.startswith("cmd "): load_command = stripped[4:]
            elif load_command == "LC_RPATH" and stripped.startswith("path "):
                rpaths.append(relative_location(stripped[5:].split(" (offset", 1)[0]))
            elif load_command == "LC_ID_DYLIB" and stripped.startswith("name "):
                identity = stripped[5:].split(" (offset", 1)[0]
        listing = subprocess.run(["/usr/bin/otool", "-L", str(path)], capture_output=True, text=True, timeout=15, check=True).stdout
        for line in listing.splitlines()[1:]:
            dependency = line.strip().split(" (", 1)[0]
            if dependency == identity: continue  # Install name is not a loaded dependency.
            if dependency.startswith(("/usr/lib/", "/System/Library/")): continue
            if dependency.startswith("@rpath/"):
                candidates = [(base / dependency[len("@rpath/"):]).resolve() for base in rpaths]
            else:
                candidates = [relative_location(dependency)]
            if not any(candidate.is_relative_to(app) and candidate.is_file() for candidate in candidates):
                raise RuntimeError(f"Packaged Mach-O {path.relative_to(app)} dependency missing or external: {dependency}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("app", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(verify_payload(arguments.app), sort_keys=True))
    verify_native_dependencies(arguments.app)
    print("Mach-O dependencies resolve inside the bundle or to Apple system paths; external rpaths rejected.")
