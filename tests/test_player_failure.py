from morgan_media_downloader.job_diagnostics import classify_failure


def test_reload_failure_is_player_extraction_not_login_or_format_problem():
    result = classify_failure("[youtube] synthetic: The page needs to be reloaded.", stage="Analysis")
    assert result["code"] == "YouTube player extraction"
    assert result["stage"] == "Analysis"
    assert "runtime" in result["friendly"].lower()
    assert "Retry Without Authentication" not in result["retry_options"]


def test_provider_failure_has_separate_category():
    result = classify_failure("PO-token provider could not generate the required token", stage="Analysis")
    assert result["code"] == "PO-token provider"
    assert "player" not in result["code"].lower()
