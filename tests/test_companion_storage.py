"""Synthetic Keychain item only; no Google/browser account access or UI prompts."""
import sys
from uuid import uuid4

import pytest

from morgan_media_downloader.youtube_companion.storage import KeychainSessionStore


def test_native_storage_roundtrip_replacement_and_delete_without_prompts():
    class SyntheticStore(KeychainSessionStore):
        SERVICE = "com.morgan.media-downloader.test." + uuid4().hex
        ACCOUNT = "synthetic-only"
    store = SyntheticStore(interactive=False)
    if sys.platform != "darwin":
        with pytest.raises(ValueError, match="unavailable"): store.load()
        return
    assert store.load() is None
    try:
        store.save({"cookies": [{"value": "synthetic-not-a-session"}]})
        assert store.load() == {"cookies": [{"value": "synthetic-not-a-session"}]}
        store.save({"cookies": [{"value": "synthetic-replacement"}]})
        assert store.load() == {"cookies": [{"value": "synthetic-replacement"}]}
    finally: store.delete()
    assert store.load() is None
