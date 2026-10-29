import shutil

import pytest

from morgan_media_downloader.app_installation import install_verified_app
from scripts.check_packaged_replacement import verify


def test_replacement_probe_preserves_source_and_old_bundle_and_launches_new_copy(tmp_path):
    source = tmp_path / "Source.app"
    (source / "Contents/MacOS").mkdir(parents=True)
    (source / "Contents/MacOS/Morgan Media Downloader").write_bytes(b"synthetic")
    launches = []

    def install(candidate, target):
        return install_verified_app(candidate, target, validator=lambda path: None,
                                  cloner=lambda a, b: shutil.copytree(a, b, symlinks=True),
                                  ensure_stopped=lambda path: None)

    def launch(target):
        assert target != source
        assert (target / "Contents/MacOS/Morgan Media Downloader").read_bytes() == b"synthetic"
        launches.append(target)
        return {"result": "passed"}

    report = verify(source, installer=install, launcher=launch)
    assert report == {"result": "passed", "first_install": True, "backup_retained": True,
                      "source_unchanged": True, "replacement_launch": True}
    assert len(launches) == 1
    assert (source / "Contents/MacOS/Morgan Media Downloader").read_bytes() == b"synthetic"
    assert not launches[0].exists()  # Runner-owned fixture cleaned, never source.


def test_replacement_probe_does_not_claim_success_when_launch_fails(tmp_path):
    source = tmp_path / "Source.app"
    source.mkdir()
    def install(candidate, target):
        return install_verified_app(candidate, target, validator=lambda path: None,
                                  cloner=lambda a, b: shutil.copytree(a, b, symlinks=True),
                                  ensure_stopped=lambda path: None)
    def fail(target):
        raise RuntimeError("Synthetic frozen launch failure")
    with pytest.raises(RuntimeError, match="launch failure"):
        verify(source, installer=install, launcher=fail)
    assert source.is_dir()
