import json
from types import SimpleNamespace

import pytest

from scripts.check_packaged_provider import verify_payload


def bundle(tmp_path):
    root = tmp_path / "App.app/Contents"
    (root / "Frameworks/bin").mkdir(parents=True)
    (root / "Frameworks/bin/node").write_text("fixture")
    (root / "Resources/provider_server/build").mkdir(parents=True)
    (root / "Resources/provider_server/build/generate_once.js").write_text("fixture")
    (root / "Resources/provider-build.json").write_text(json.dumps({"node_version": "v24.22.0", "provider_version": "1.3.1",
        "provider_commit": "7608dd51ee813b48cf9a6d68c6e42cb197ce10e0"}))
    return root.parent


def test_packaged_provider_probe_requires_expected_versions_and_native_canvas(tmp_path):
    app = bundle(tmp_path); operations = []
    def run(command, **kwargs):
        operations.append(command)
        if command[-1] == "--version": return SimpleNamespace(stdout="v24.22.0\n" if len(command) == 2 else "1.3.1\n")
        return SimpleNamespace(stdout="")
    result = verify_payload(app, runner=run)
    assert result["provider_version"] == "1.3.1"
    assert len(operations) == 3 and any("createCanvas" in str(command) for command in operations)


@pytest.mark.parametrize("version", ["v20.0.0", "", "2.0.2"])
def test_wrong_packaged_runtime_fails_instead_of_using_path_fallback(tmp_path, version):
    with pytest.raises(RuntimeError):
        verify_payload(bundle(tmp_path), runner=lambda *args, **kwargs: SimpleNamespace(stdout=version))


@pytest.mark.parametrize("dependency,accepted", [("@loader_path/libfoo.dylib", True), ("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation", True), ("/opt/homebrew/lib/libfoo.dylib", False)])
def test_native_dependency_gate_rejects_build_machine_libraries(tmp_path, monkeypatch, dependency, accepted):
    from scripts.check_packaged_provider import verify_native_dependencies
    binary = tmp_path / "fixture"; binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    (tmp_path / "libfoo.dylib").write_text("fixture dependency")
    monkeypatch.setattr("scripts.check_packaged_provider.subprocess.run", lambda command, **kw: SimpleNamespace(stdout=f"{binary}:\n\t{dependency} (compatibility version 1.0.0)\n" if "-L" in command else ""))
    if accepted: verify_native_dependencies(tmp_path)
    else:
        with pytest.raises(RuntimeError, match="external"): verify_native_dependencies(tmp_path)


@pytest.mark.parametrize("dependency,rpath", [
    ("@rpath/missing.dylib", "@loader_path"),
    ("@loader_path/missing.dylib", ""),
    ("@loader_path/../../outside.dylib", ""),
    ("@rpath/libfoo.dylib", "/opt/homebrew/lib"),
])
def test_native_gate_requires_existing_contained_dependency_and_rpaths(tmp_path, monkeypatch, dependency, rpath):
    from scripts.check_packaged_provider import verify_native_dependencies
    binary = tmp_path / "fixture"; binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    def run(command, **kwargs):
        if "-L" in command: return SimpleNamespace(stdout=f"{binary}:\n\t{dependency} (compatibility version 1.0.0)\n")
        return SimpleNamespace(stdout=f"Load command 1\n          cmd LC_RPATH\n      cmdsize 32\n         path {rpath} (offset 12)\n" if rpath else "")
    monkeypatch.setattr("scripts.check_packaged_provider.subprocess.run", run)
    with pytest.raises(RuntimeError): verify_native_dependencies(tmp_path)


def test_native_gate_resolves_bundle_rpath(tmp_path, monkeypatch):
    from scripts.check_packaged_provider import verify_native_dependencies
    binary = tmp_path / "fixture"; binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    (tmp_path / "libs").mkdir(); (tmp_path / "libs/libfoo.dylib").write_text("fixture dependency")
    def run(command, **kwargs):
        if "-L" in command: return SimpleNamespace(stdout=f"{binary}:\n\t@rpath/libfoo.dylib (compatibility version 1.0.0)\n")
        return SimpleNamespace(stdout="Load command 1\n          cmd LC_RPATH\n      cmdsize 32\n         path @loader_path/libs (offset 12)\n")
    monkeypatch.setattr("scripts.check_packaged_provider.subprocess.run", run)
    verify_native_dependencies(tmp_path)


def test_native_gate_does_not_treat_dylib_identity_as_loaded_dependency(tmp_path, monkeypatch):
    from scripts.check_packaged_provider import verify_native_dependencies
    binary = tmp_path / "libfoo.dylib"; binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    def run(command, **kwargs):
        if "-L" in command: return SimpleNamespace(stdout=f"{binary}:\n\t@rpath/libfoo.dylib (compatibility version 1.0.0)\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n")
        return SimpleNamespace(stdout="Load command 1\n          cmd LC_ID_DYLIB\n      cmdsize 48\n         name @rpath/libfoo.dylib (offset 24)\n")
    monkeypatch.setattr("scripts.check_packaged_provider.subprocess.run", run)
    verify_native_dependencies(tmp_path)


def test_native_gate_resolves_loader_path_from_real_framework_not_shallow_alias(tmp_path, monkeypatch):
    from scripts.check_packaged_provider import verify_native_dependencies
    binary = tmp_path / "Contents/Frameworks/Qt/libfoo.framework/Versions/A/libfoo"
    (tmp_path / "alias").symlink_to(binary.relative_to(tmp_path))
    binary.parent.mkdir(parents=True); binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    (tmp_path / "Contents/Frameworks/libbar.dylib").write_text("fixture dependency")
    def run(command, **kwargs):
        if "-L" in command: return SimpleNamespace(stdout=f"{binary}:\n\t@rpath/libbar.dylib (compatibility version 1.0.0)\n")
        return SimpleNamespace(stdout="Load command 1\n          cmd LC_RPATH\n      cmdsize 48\n         path @loader_path/../../../.. (offset 12)\n")
    monkeypatch.setattr("scripts.check_packaged_provider.subprocess.run", run)
    verify_native_dependencies(tmp_path)
