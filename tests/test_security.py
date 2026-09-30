from morgan_media_downloader.logging_setup import redact_secrets


def test_secret_redaction_covers_proxy_credentials_headers_and_query_tokens():
    message = ("proxy socks5h://alice:super-secret@example.test:1080/path "
               "Authorization: Bearer-secret Cookie=SID-secret "
               "https://example.test/?token=token-secret&safe=yes")
    cleaned = redact_secrets(message)
    for secret in ("super-secret", "Bearer-secret", "SID-secret", "token-secret"):
        assert secret not in cleaned
    assert "alice:[redacted]@" in cleaned
    assert "safe=yes" not in cleaned
    assert "[query redacted]" in cleaned
