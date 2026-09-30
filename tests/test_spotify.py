import io

from morgan_media_downloader.spotify import SpotifyMetadata, fetch_public_metadata, match_confidence, spotify_search_query


def test_spotify_metadata_to_query():
    assert spotify_search_query("Daft Punk", "Instant Crush") == "Daft Punk Instant Crush"


def test_spotify_metadata_uses_supplied_proxy_aware_opener():
    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, size=-1): return io.BytesIO(b'{"title":"Instant Crush","author_name":"Daft Punk"}').read(size)
    result = fetch_public_metadata("https://open.spotify.com/track/123", opener=lambda request: captured.append(request.full_url) or Response())
    assert result[0].search_query == "Daft Punk Instant Crush"
    assert captured and captured[0].startswith("https://open.spotify.com/oembed?")


def test_candidate_confidence_prefers_text_and_duration_match():
    source = SpotifyMetadata("Instant Crush", "Daft Punk", duration=337)
    good = match_confidence(source, {"title": "Daft Punk - Instant Crush", "uploader": "Daft Punk", "duration": 337})
    bad = match_confidence(source, {"title": "Unrelated Song", "uploader": "Other", "duration": 100})
    assert good > bad
