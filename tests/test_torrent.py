from pathlib import Path
from types import SimpleNamespace

import pytest

from morgan_media_downloader.parsing import input_kind
from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem
from morgan_media_downloader.torrent import (
    TORRENT_TOR_ERROR, analyse_torrent, bdecode, build_torrent_command,
    deduplicate_trackers, fetch_magnet_metadata, find_aria2c, parse_aria2_version,
    parse_torrent_progress, public_trackers,
)


def test_magnet_recognition_and_metadata():
    magnet = "magnet:?xt=urn:btih:abc&dn=Lawful%20Dataset&tr=https%3A%2F%2Ftracker.test%2Fa"
    assert input_kind(magnet) == "torrent"
    metadata = analyse_torrent(magnet)
    assert metadata.name == "Lawful Dataset"
    assert metadata.tracker_count == 1
    assert metadata.is_magnet


def test_multifile_torrent_parsing(tmp_path: Path):
    # d4:infod5:filesld6:lengthi3e4:pathl5:a.txteed6:lengthi4e4:pathl5:b.txtee4:name4:testee
    payload = b"d4:infod5:filesld6:lengthi3e4:pathl5:a.txteed6:lengthi4e4:pathl5:b.txteee4:name4:testee"
    path = tmp_path / "sample.torrent"; path.write_bytes(payload)
    metadata = analyse_torrent(str(path))
    assert metadata.name == "test"
    assert metadata.total_size == 7
    assert [item.index for item in metadata.files] == [1, 2]


def test_bdecode_rejects_trailing_data():
    try:
        bdecode(b"i1ee")
    except ValueError as error:
        assert "Trailing" in str(error)
    else:
        raise AssertionError("trailing bencode data was accepted")


def test_private_flag_is_parsed(tmp_path: Path):
    path = tmp_path / "private.torrent"
    path.write_bytes(b"d4:infod6:lengthi1e4:name1:x7:privatei1eee")
    assert analyse_torrent(str(path)).is_private


def _settings(**values):
    defaults = dict(torrent_connection_mode="Direct", torrent_enable_dht=True,
                    torrent_enable_pex=True, torrent_download_limit_kib=0,
                    torrent_upload_limit_kib=0, torrent_continue_seeding=False,
                    torrent_enable_trackers=True)
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _job() -> DownloadJob:
    source = "magnet:?xt=urn:btih:abc&dn=Lawful"
    return DownloadJob(MediaItem(source, "Lawful"), DownloadOptions(download_dir="/tmp/out"),
                       kind="torrent", torrent_source=source, torrent_file_indices=[1, 3])


def test_bundled_binary_precedes_selected_and_path(monkeypatch, tmp_path: Path):
    bundled = tmp_path / "bundle" / "resources" / "bin" / "aria2c"
    selected = tmp_path / "selected-aria2c"
    bundled.parent.mkdir(parents=True); bundled.write_text("bundled"); bundled.chmod(0o755)
    selected.write_text("selected"); selected.chmod(0o755)
    monkeypatch.setattr("morgan_media_downloader.torrent.bundle_root", lambda: tmp_path / "bundle")
    monkeypatch.setattr("morgan_media_downloader.torrent.shutil.which", lambda _: "/path/aria2c")
    assert find_aria2c(str(selected)) == str(bundled.resolve())


def test_aria2_version_parsing():
    assert parse_aria2_version("aria2 version 1.37.0\nCopyright") == "1.37.0"
    assert parse_aria2_version("unrelated") == ""


def test_torrent_command_is_argument_array_and_stops_seeding():
    command = build_torrent_command(_job(), _settings(), "/app/aria2c", Path("/tmp/out"))
    assert command[0] == "/app/aria2c"
    assert "--no-conf=true" in command
    assert command[-1].startswith("magnet:?")
    assert command[command.index("--select-file") + 1] == "1,3"
    assert command[command.index("--seed-time") + 1] == "0"


def test_system_proton_mode_uses_the_system_routing_table_without_proxy_flags():
    command = build_torrent_command(_job(), _settings(torrent_connection_mode="System / Proton VPN"),
                                    "/app/aria2c", Path("/tmp/out"))
    assert not any("proxy" in argument.lower() for argument in command)


@pytest.mark.parametrize("mode", ["Managed Tor", "External Tor", "Custom SOCKS Proxy"])
def test_torrent_rejects_tor_and_proxy_modes(mode: str):
    with pytest.raises(ValueError, match="BitTorrent over Tor") as caught:
        build_torrent_command(_job(), _settings(torrent_connection_mode=mode), "/app/aria2c", Path("/tmp/out"))
    assert str(caught.value) == TORRENT_TOR_ERROR


def test_torrent_progress_parsing():
    progress = parse_torrent_progress("[#abc123 4.0MiB/8.0MiB(50%) CN:7 SD:3 DL:512KiB UL:2KiB ETA:1m2s]")
    assert progress == {"downloaded_bytes": 4 * 1024 ** 2, "total_bytes": 8 * 1024 ** 2,
                        "progress": 50.0, "speed": 512 * 1024, "upload_speed": 2 * 1024,
                        "eta": 62, "peers": 7, "seeds": 3}


def test_private_torrent_disables_public_discovery_and_extra_trackers():
    job = _job(); job.torrent_private = True; job.torrent_trackers = ["https://private.test/announce"]
    settings = _settings(torrent_enable_lpd=True, torrent_extra_public_trackers=True)
    command = build_torrent_command(job, settings, "/app/aria2c", Path("/tmp/out"))
    assert "--enable-dht=false" in command
    assert "--enable-dht6=false" in command
    assert "--enable-peer-exchange=false" in command
    assert "--bt-enable-lpd=false" in command
    assert not any("opentrackr" in part for part in command)


def test_public_tracker_deduplication_and_counts():
    original = ["udp://tracker.test/announce", "udp://tracker.test/announce/"]
    trackers, additional = public_trackers(original, True, False)
    assert deduplicate_trackers(original) == ["udp://tracker.test/announce"]
    assert len(trackers) == 1 + additional
    assert additional > 0


def test_magnet_metadata_fetch_populates_files(monkeypatch, tmp_path: Path):
    executable = tmp_path / "aria2c"; executable.write_text("x"); executable.chmod(0o755)
    monkeypatch.setattr("morgan_media_downloader.torrent.find_aria2c", lambda _: str(executable))

    def fake_run(arguments, **_kwargs):
        destination = Path(arguments[arguments.index("--dir") + 1])
        payload = b"d4:infod5:filesld6:lengthi3e4:pathl5:a.txteed6:lengthi4e4:pathl5:b.txteee4:name4:testee"
        (destination / "metadata.torrent").write_bytes(payload)
        return SimpleNamespace(returncode=0, stdout="Download complete", stderr="")

    monkeypatch.setattr("morgan_media_downloader.torrent.subprocess.run", fake_run)
    magnet = "magnet:?xt=urn:btih:abc&dn=Lawful"
    metadata = fetch_magnet_metadata(magnet)
    assert metadata.is_magnet and metadata.source == magnet
    assert [item.path for item in metadata.files] == ["a.txt", "b.txt"]
