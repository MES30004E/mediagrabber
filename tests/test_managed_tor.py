import json
import os
import socket
import fcntl
from pathlib import Path

from morgan_media_downloader.managed_tor import (
    BOOTSTRAP, MANAGED_TOR_FORBIDDEN_PORTS, MAX_LAUNCH_ATTEMPTS, ManagedTor,
    free_socks_port, reserve_runtime_ports, tor_executable,
)


def test_bootstrap_progress_parser():
    assert BOOTSTRAP.search("Bootstrapped 35% (loading)").group(1) == "35"


def test_primary_tor_path_precedes_backup(tmp_path: Path):
    primary = tmp_path / "Contents" / "MacOS" / "Tor" / "tor"
    backup = tmp_path / "Contents.bak" / "MacOS" / "Tor" / "tor"
    primary.parent.mkdir(parents=True); backup.parent.mkdir(parents=True)
    primary.write_text(""); backup.write_text(""); primary.chmod(0o700); backup.chmod(0o700)
    assert tor_executable(str(tmp_path)) == primary


def test_dynamic_socks_port_is_local_and_available():
    port = free_socks_port(9150)
    assert 1 <= port <= 65535
    assert port not in MANAGED_TOR_FORBIDDEN_PORTS


def test_runtime_port_pair_is_distinct_reserved_and_leaves_browser_ports_alone():
    socks, control, reservations = reserve_runtime_ports()
    browser_sockets = []
    try:
        assert socks != control
        assert {socks, control}.isdisjoint(MANAGED_TOR_FORBIDDEN_PORTS)
        for port in (9150, 9151):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", port)); browser_sockets.append(listener)
    finally:
        for reservation in reservations: reservation.close()
        for listener in browser_sockets: listener.close()


def test_browser_ports_can_be_occupied_before_runtime_selection():
    listeners = []
    try:
        for port in (9150, 9151):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", port)); listeners.append(listener)
        socks, control, reservations = reserve_runtime_ports()
        assert {socks, control}.isdisjoint({9050, 9051, 9150, 9151})
        for reservation in reservations: reservation.close()
    finally:
        for listener in listeners: listener.close()


def test_newnym_uses_app_cookie_and_honours_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path))
    tor = ManagedTor("unused"); tor.state = "Connected"; tor.control_port = 19051
    tor.cookie_path.parent.mkdir(parents=True); tor.cookie_path.write_bytes(b"x" * 32)
    calls, sleeps = [], []
    tor.last_newnym_monotonic = 95.0
    result = tor.request_new_circuit(cooldown=10, clock=lambda: 100.0, sleeper=sleeps.append,
                                     command=lambda port, cookie, command: calls.append((port, cookie, command)))
    assert calls == [(19051, b"x" * 32, "SIGNAL NEWNYM")]
    assert sleeps == [5.0] and result["cooldown_waited"] == 5.0
    assert "x" * 16 not in str(result)


class _CollisionProcess:
    def __init__(self):
        self.stdout = iter(["[warn] Failed to bind one of the listener ports.\n"])
    def wait(self, timeout=None): return 1
    def poll(self): return 1


def test_collision_reselects_ports_until_third_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path))
    tor = ManagedTor("unused")
    process = _CollisionProcess(); tor.process = process; tor.state = "Starting"
    retries = []
    monkeypatch.setattr(tor, "_launch_attempt", lambda executable, attempt: retries.append(attempt) or True)
    tor._read_output(process, Path("/fake/tor"), 1)
    assert retries == [2]
    assert tor.last_error == "Managed Tor port collision"


def test_collision_stops_after_maximum_three_attempts(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path))
    tor = ManagedTor("unused")
    process = _CollisionProcess(); tor.process = process; tor.state = "Starting"
    tor._read_output(process, Path("/fake/tor"), MAX_LAUNCH_ATTEMPTS)
    assert tor.state == "Failed"
    assert "3 launch attempts" in tor.last_error


def test_runtime_state_persists_actual_ports_and_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path))
    tor = ManagedTor("unused"); tor.port = 49172; tor.control_port = 49173
    tor.launch_timestamp = "2026-08-30T00:00:00+00:00"; tor.bootstrap_percent = 42
    tor.data_dir.mkdir(parents=True); tor._set_state("Bootstrapping 42%")
    payload = json.loads(tor.runtime_path.read_text())
    assert payload["socks_host"] == payload["control_host"] == "127.0.0.1"
    assert (payload["socks_port"], payload["control_port"]) == (49172, 49173)
    assert payload["owner_pid"] == os.getpid() and payload["bootstrap_percent"] == 42


def test_stale_lock_is_removed_only_in_morgan_data_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path))
    tor = ManagedTor("unused"); tor.data_dir.mkdir(parents=True)
    lock = tor.data_dir / "lock"; lock.write_text("stale")
    tor._recover_stale_instance(Path("/fake/tor"))
    assert not lock.exists()
    assert "stale Managed Tor" in " ".join(tor.drain_logs())


def test_active_morgan_lock_is_not_deleted(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path))
    tor = ManagedTor("unused"); tor.data_dir.mkdir(parents=True)
    lock = tor.data_dir / "lock"
    with lock.open("w") as owner:
        fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            tor._recover_stale_instance(Path("/fake/tor"))
        except RuntimeError as error:
            assert "lock is active" in str(error)
        else:
            raise AssertionError("active lock should not be removed")
        assert lock.exists()


def test_foreign_tor_process_is_never_terminated(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_DATA_DIR", str(tmp_path))
    tor = ManagedTor("unused"); tor.data_dir.mkdir(parents=True)
    tor.runtime_path.write_text(json.dumps({"pid": 43210, "owner_pid": 0}))
    monkeypatch.setattr("morgan_media_downloader.managed_tor._pid_alive", lambda pid: pid == 43210)
    monkeypatch.setattr(tor, "_owned_command", lambda *_: False)
    killed = []; monkeypatch.setattr(os, "kill", lambda *args: killed.append(args))
    try:
        tor._recover_stale_instance(Path("/fake/tor"))
    except RuntimeError as error:
        assert "unverified" in str(error)
    else:
        raise AssertionError("unverified Tor process should be rejected")
    assert killed == []
