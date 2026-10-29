from pathlib import Path
import shutil

import pytest

from morgan_media_downloader.app_installation import install_verified_app, InstallationError, RecoveryRequired


def app(path, value):
    (path / "Contents").mkdir(parents=True)
    (path / "Contents/version").write_text(value)
    return path


def clone(source, target): shutil.copytree(source, target, symlinks=True)
def stopped(target): pass
def validate(path):
    assert (path / "Contents/version").is_file()


def test_success_validates_copy_before_touching_old_app_and_retains_backup(tmp_path):
    old = app(tmp_path / "Morgan Media Downloader.app", "old")
    source = app(tmp_path / "build/New.app", "new")
    calls = []
    def validator(path):
        calls.append(path)
        if path != old: assert (old / "Contents/version").read_text() == "old"
        validate(path)
    backup = install_verified_app(source, old, validator=validator, cloner=clone, ensure_stopped=stopped)
    assert (old / "Contents/version").read_text() == "new"
    assert (backup / "Contents/version").read_text() == "old"
    assert calls[-1] == old and len(calls) == 2
    assert (source / "Contents/version").read_text() == "new"


def test_invalid_copy_leaves_original_app_untouched(tmp_path):
    old = app(tmp_path / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    def reject(path): raise InstallationError("Synthetic signature failure")
    with pytest.raises(InstallationError):
        install_verified_app(source, old, validator=reject, cloner=clone, ensure_stopped=stopped)
    assert (old / "Contents/version").read_text() == "old"
    assert not list(tmp_path.glob(".morgan-backup-*"))


def test_post_activation_validation_failure_restores_old_app(tmp_path):
    old = app(tmp_path / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    def validator(path):
        if path == old: raise InstallationError("Synthetic post-copy verification failure")
    with pytest.raises(InstallationError):
        install_verified_app(source, old, validator=validator, cloner=clone, ensure_stopped=stopped)
    assert (old / "Contents/version").read_text() == "old"


def test_activation_rename_failure_restores_old_app(tmp_path, monkeypatch):
    from morgan_media_downloader import app_installation as module
    old = app(tmp_path / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    original = module.os.replace
    def replace(source_path, target_path):
        if Path(target_path) == old and ".morgan-candidate-" in str(source_path): raise OSError("Synthetic activation failure")
        return original(source_path, target_path)
    monkeypatch.setattr(module.os, "replace", replace)
    with pytest.raises(OSError):
        install_verified_app(source, old, validator=validate, cloner=clone, ensure_stopped=stopped)
    assert (old / "Contents/version").read_text() == "old"


def test_failed_recovery_preserves_only_old_working_copy_and_reports_location(tmp_path, monkeypatch):
    from morgan_media_downloader import app_installation as module
    old = app(tmp_path / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    original = module.os.replace
    def replace(source_path, target_path):
        if Path(target_path) == old: raise OSError("Synthetic activation and recovery failure")
        return original(source_path, target_path)
    monkeypatch.setattr(module.os, "replace", replace)
    with pytest.raises(RecoveryRequired) as raised:
        install_verified_app(source, old, validator=validate, cloner=clone, ensure_stopped=stopped)
    assert (raised.value.backup / "Contents/version").read_text() == "old"
    assert str(raised.value.backup) in str(raised.value)


def test_unsupported_filesystem_fails_before_copying_or_changing_old_app(tmp_path, monkeypatch):
    from morgan_media_downloader import app_installation as module
    old = app(tmp_path / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    def no_symlinks(*args, **kwargs): raise OSError("Synthetic exFAT symlink rejection")
    monkeypatch.setattr(module.os, "symlink", no_symlinks)
    def no_copy(*args): pytest.fail("Must not copy on an unsupported destination")
    with pytest.raises(InstallationError, match="symlink"):
        install_verified_app(source, old, validator=validate, cloner=no_copy, ensure_stopped=stopped)
    assert (old / "Contents/version").read_text() == "old"


def test_symlink_target_is_never_followed_or_replaced(tmp_path):
    original = app(tmp_path / "Original.app", "old"); target = tmp_path / "Alias.app"; target.symlink_to(original)
    source = app(tmp_path / "new/New.app", "new")
    with pytest.raises(InstallationError):
        install_verified_app(source, target, validator=validate, cloner=clone, ensure_stopped=stopped)
    assert target.is_symlink() and (original / "Contents/version").read_text() == "old"


def test_running_app_refusal_does_not_mutate_installation(tmp_path):
    old = app(tmp_path / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    def running(path): raise InstallationError("Close the app first")
    with pytest.raises(InstallationError, match="Close"):
        install_verified_app(source, old, validator=validate, cloner=clone, ensure_stopped=running)
    assert (old / "Contents/version").read_text() == "old"


def test_first_install_keeps_verified_candidate_and_has_no_fictitious_backup(tmp_path):
    source = app(tmp_path / "new/New.app", "new"); target = tmp_path / "Morgan.app"
    assert install_verified_app(source, target, validator=validate, cloner=clone, ensure_stopped=stopped) is None
    assert (target / "Contents/version").read_text() == "new"


def test_concurrent_installation_is_refused_without_touching_either_candidate(tmp_path):
    old = app(tmp_path / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    def competing_clone(source_path, target_path):
        with pytest.raises(InstallationError, match="in progress"):
            install_verified_app(source, old, validator=validate, cloner=clone, ensure_stopped=stopped)
        clone(source_path, target_path)
    backup = install_verified_app(source, old, validator=validate, cloner=competing_clone, ensure_stopped=stopped)
    assert (backup / "Contents/version").read_text() == "old"
    assert (old / "Contents/version").read_text() == "new"


def test_native_stop_check_rejects_translocated_bundle_processes(tmp_path, monkeypatch):
    from morgan_media_downloader import app_installation as module
    from types import SimpleNamespace
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="12345 /private/tmp/Translocation/Morgan.app/Contents/Frameworks/bin/node\n"))
    with pytest.raises(InstallationError, match="Close"):
        module.require_app_stopped(tmp_path / "Morgan.app")


def test_failed_first_install_cleanup_does_not_claim_a_previous_backup_exists(tmp_path, monkeypatch):
    from morgan_media_downloader import app_installation as module
    source = app(tmp_path / "new/New.app", "new"); target = tmp_path / "Morgan.app"
    original = module.os.replace
    def replace(source_path, target_path):
        if Path(source_path) == target: raise OSError("Synthetic rejection-move failure")
        return original(source_path, target_path)
    monkeypatch.setattr(module.os, "replace", replace)
    def validator(path):
        if path == target: raise InstallationError("Synthetic post-copy rejection")
    with pytest.raises(RecoveryRequired) as raised:
        install_verified_app(source, target, validator=validator, cloner=clone, ensure_stopped=stopped)
    assert raised.value.backup is None
    assert "No previous app existed" in str(raised.value)
    assert str(target) in str(raised.value)


def test_parent_directory_alias_cannot_bypass_installation_lock(tmp_path):
    real = tmp_path / "real"; real.mkdir(); alias = tmp_path / "alias"; alias.symlink_to(real, target_is_directory=True)
    old = app(real / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    def competing_clone(source_path, target_path):
        with pytest.raises(InstallationError, match="in progress"):
            install_verified_app(source, alias / "Morgan.app", validator=validate, cloner=clone, ensure_stopped=stopped)
        clone(source_path, target_path)
    backup = install_verified_app(source, old, validator=validate, cloner=competing_clone, ensure_stopped=stopped)
    assert (backup / "Contents/version").read_text() == "old"


def test_failed_activation_does_not_delete_another_actors_new_target(tmp_path, monkeypatch):
    from morgan_media_downloader import app_installation as module
    old = app(tmp_path / "Morgan.app", "old"); source = app(tmp_path / "new/New.app", "new")
    original = module.os.replace
    def replace(source_path, target_path):
        if Path(target_path) == old and ".morgan-candidate-" in str(source_path):
            app(old, "another actor's app")
            raise OSError("Synthetic target reappeared")
        return original(source_path, target_path)
    monkeypatch.setattr(module.os, "replace", replace)
    with pytest.raises(RecoveryRequired) as raised:
        install_verified_app(source, old, validator=validate, cloner=clone, ensure_stopped=stopped)
    assert (old / "Contents/version").read_text() == "another actor's app"
    assert (raised.value.backup / "Contents/version").read_text() == "old"


def test_post_activation_failure_preserves_foreign_replacement_and_previous_backup(tmp_path):
    from morgan_media_downloader import app_installation as module
    old = app(tmp_path / "Morgan.app", "old")
    source = app(tmp_path / "new/New.app", "new")
    displaced = tmp_path / "displaced-candidate.app"

    def validator(path):
        if path == old:
            module.os.replace(old, displaced)
            app(old, "another actor's app")
            raise InstallationError("Synthetic validation failure after foreign replacement")
        validate(path)

    with pytest.raises(RecoveryRequired) as raised:
        install_verified_app(source, old, validator=validator, cloner=clone, ensure_stopped=stopped)
    assert (old / "Contents/version").read_text() == "another actor's app"
    assert (raised.value.backup / "Contents/version").read_text() == "old"
    assert (displaced / "Contents/version").read_text() == "new"
