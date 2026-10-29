import pytest

from scripts.check_packaged_archive import verify
from test_app_archives import bundle, validate, COMMIT


def test_archive_probe_launches_only_checked_extraction_and_preserves_source(tmp_path):
    app = bundle(tmp_path / "source"); launched = []
    def launch(extracted):
        assert extracted != app
        validate(extracted); launched.append(extracted)
        return {"result": "passed"}
    report = verify(app, COMMIT, validator=validate, launcher=launch)
    assert report["result"] == "passed" and report["source_unchanged"] is True
    assert report["archive_round_trip"] is True and report["publication_approved"] is False
    assert report["source_commit"] == COMMIT
    assert len(launched) == 1 and not launched[0].exists()
    validate(app)


def test_archive_probe_propagates_extracted_launch_failure(tmp_path):
    app = bundle(tmp_path / "source")
    def fail(extracted): raise RuntimeError("Synthetic extracted GUI failure")
    with pytest.raises(RuntimeError, match="extracted GUI"):
        verify(app, COMMIT, validator=validate, launcher=fail)
    validate(app)


def test_actual_archive_probe_is_refused_outside_hosted_macos(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="hosted"):
        verify(tmp_path / "missing.app", COMMIT)
