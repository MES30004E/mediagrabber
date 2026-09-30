from morgan_media_downloader.models import MediaItem
from morgan_media_downloader.organisation import organised_folder, safe_component


def test_playlist_auto_folder_and_duplicate_prevention():
    items = [MediaItem("u", "One", collection_title="My Playlist", playlist_index=1),
             MediaItem("v", "Two", collection_title="My Playlist", playlist_index=2)]
    assert organised_folder("/tmp/downloads", items, "Auto") == "/tmp/downloads/My Playlist"
    assert organised_folder("/tmp/downloads/My Playlist", items, "Auto") == "/tmp/downloads/My Playlist"


def test_single_media_stays_in_base_and_macos_names_are_sanitised():
    assert organised_folder("/tmp/downloads", [MediaItem("u", "One")], "Auto") == "/tmp/downloads"
    assert safe_component(" Album: A/B \x00 ") == "Album- A-B"
