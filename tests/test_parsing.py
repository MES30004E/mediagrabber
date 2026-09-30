import pytest

from morgan_media_downloader.parsing import as_yt_dlp_target, input_kind, sanitize_filename, split_input


def test_split_input_ignores_blank_lines():
    assert split_input("https://example.com/a\n\n search phrase \n") == ["https://example.com/a", "search phrase"]


def test_input_classification():
    assert input_kind("https://open.spotify.com/track/123") == "spotify"
    assert input_kind("https://music.youtube.com/watch?v=1") == "youtube_music"
    assert input_kind("artist track") == "search"


def test_search_becomes_ytsearch_target():
    assert as_yt_dlp_target("Daft Punk Instant Crush") == "ytsearch10:Daft Punk Instant Crush"


def test_watch_later_keyword_reaches_extractor_instead_of_search():
    assert input_kind(":ytwatchlater") == "url"
    assert as_yt_dlp_target(":ytwatchlater") == ":ytwatchlater"


@pytest.mark.parametrize("value", [
    "https://www.youtube.com/playlist?list=WL",
    "http://youtube.com/playlist?list=WL&feature=share",
    "https://m.youtube.com/playlist?feature=share&list=WL#top",
    "https://music.youtube.com/playlist?list=WL",
    "https://www.youtube.com/feed/watch_later",
    "https://www.youtube.com/feed/watch_later/",
    "youtube.com/playlist?list=WL",
    "www.youtube.com/feed/watch_later",
])
def test_watch_later_urls_use_canonical_private_playlist(value):
    assert input_kind(value) == "url"
    assert as_yt_dlp_target(value) == "https://www.youtube.com/playlist?list=WL"


@pytest.mark.parametrize("value", [
    "https://www.youtube.com/playlist?list=PLfixture&feature=share",
    "https://www.youtube.com/watch?v=fixture&list=WL",
    "https://example.com/playlist?list=WL",
    "https://youtube.com.example.com/feed/watch_later",
    "https://www.youtube.com/playlist?list=WLother",
])
def test_other_urls_are_not_rewritten_as_watch_later(value):
    assert as_yt_dlp_target(value) == value


@pytest.mark.parametrize("value", ["Watch Later", "artist track", ":ytwatchlater extra", "youtube.com is a website"])
def test_ordinary_text_search_still_uses_requested_result_count(value):
    assert input_kind(value) == "search"
    assert as_yt_dlp_target(value, result_count=3) == f"ytsearch3:{value}"


def test_filename_sanitation():
    assert sanitize_filename('A/B: C? <live>') == "A_B_ C_ _live_"
    assert sanitize_filename("...") == "download"
