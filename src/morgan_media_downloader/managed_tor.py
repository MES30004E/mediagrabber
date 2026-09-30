from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
import fcntl
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from .paths import application_support_dir

BOOTSTRAP = re.compile(r"Bootstrapped\s+(\d+)%")
PORT_COLLISION = re.compile(r"address already in use|failed to bind|cannot bind listener", re.IGNORECASE)
MANAGED_TOR_FORBIDDEN_PORTS = frozenset({9050, 9051, 9150, 9151})
MAX_LAUNCH_ATTEMPTS = 3


def tor_executable(browser_path: str) -> Path | None:
    root = Path(browser_path).expanduser()
    primary = root / "Contents" / "MacOS" / "Tor" / "tor"
    backup = root / "Contents.bak" / "MacOS" / "Tor" / "tor"
    for candidate in (primary, backup):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _reserved_local_port() -> tuple[int, socket.socket]:
    """Reserve an OS-selected loopback port until immediately before Tor launch."""
    for _ in range(32):
        reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            reservation.bind(("127.0.0.1", 0))
            port = int(reservation.getsockname()[1])
            if port not in MANAGED_TOR_FORBIDDEN_PORTS:
                return port, reservation
        except OSError:
            pass
        reservation.close()
    raise OSError("Could not reserve an isolated localhost port for Managed Tor")


def reserve_runtime_ports() -> tuple[int, int, tuple[socket.socket, socket.socket]]:
    socks_port, socks_reservation = _reserved_local_port()
    try:
        control_port, control_reservation = _reserved_local_port()
    except BaseException:
        socks_reservation.close()
        raise
    return socks_port, control_port, (socks_reservation, control_reservation)


def free_socks_port(preferred: int = 0) -> int:
    """Compatibility helper: Managed Tor always receives an ephemeral safe port."""
    del preferred
    port, reservation = _reserved_local_port()
    reservation.close()
    return port


def _control_command(port: int, cookie: bytes, command: str,
                     connector=socket.create_connection) -> list[str]:
    """Authenticate to the app-owned Tor control port and issue one command."""
    with connector(("127.0.0.1", port), timeout=5) as connection:
        stream = connection.makefile("rwb", buffering=0)
        stream.write(f"AUTHENTICATE {cookie.hex()}\r\n".encode("ascii"))
        auth = stream.readline().decode("utf-8", "replace").strip()
        if not auth.startswith("250"):
            raise RuntimeError("Managed Tor control authentication failed")
        stream.write((command + "\r\n").encode("ascii"))
        lines = []
        while True:
            line = stream.readline().decode("utf-8", "replace").strip()
            if not line:
                raise RuntimeError("Managed Tor control connection closed unexpectedly")
            lines.append(line)
            if line.startswith("250 ") or line == "250 OK":
                return lines
            if line[:3].isdigit() and not line.startswith(("250-", "250+")):
                raise RuntimeError("Managed Tor control request failed")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


class ManagedTor:
    def __init__(self, browser_path: str):
        self.browser_path = browser_path
        # State is deliberately polled by a main-thread QTimer. Calling an arbitrary
        # UI callback from Tor's stdout reader thread caused unsafe QObject access.
        self.process: subprocess.Popen[str] | None = None
        self.port: int | None = None
        self.control_port: int | None = None
        self.bootstrap_percent = 0
        self.launch_timestamp = ""
        self.launch_attempt = 0
        self.last_circuit_change = ""
        self.last_newnym_monotonic = 0.0
        self.current_exit_ip = ""
        self.previous_exit_ip = ""
        self.circuit_changed: bool | None = None
        self.state = "Stopped"
        self.last_error = ""
        self._connected = threading.Event()
        self._lock = threading.RLock()
        self._log_messages: deque[str] = deque()

    @property
    def data_dir(self) -> Path:
        return application_support_dir() / "tor"

    @property
    def runtime_path(self) -> Path:
        return self.data_dir / "managed_runtime.json"

    @property
    def cookie_path(self) -> Path:
        return self.data_dir / "control_auth_cookie"

    @property
    def available(self) -> bool:
        return tor_executable(self.browser_path) is not None

    @property
    def proxy_url(self) -> str | None:
        return f"socks5h://127.0.0.1:{self.port}" if self.state == "Connected" and self.port else None

    @property
    def runtime_state(self) -> dict[str, object]:
        process = self.process
        return {
            "pid": process.pid if process and process.poll() is None else None,
            "owner_pid": os.getpid(),
            "socks_host": "127.0.0.1",
            "socks_port": self.port,
            "control_host": "127.0.0.1",
            "control_port": self.control_port,
            "data_directory": str(self.data_dir),
            "launch_timestamp": self.launch_timestamp,
            "bootstrap_percent": self.bootstrap_percent,
            "state": self.state,
        }

    def drain_logs(self) -> list[str]:
        with self._lock:
            messages = list(self._log_messages)
            self._log_messages.clear()
            return messages

    def _log(self, message: str) -> None:
        self._log_messages.append(message)

    def _set_state(self, value: str) -> None:
        self.state = value
        self._persist_runtime()

    def _persist_runtime(self) -> None:
        if not self.data_dir.exists():
            return
        temporary = self.runtime_path.with_name(f".{self.runtime_path.name}.tmp-{os.getpid()}")
        try:
            temporary.write_text(json.dumps(self.runtime_state, indent=2) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(self.runtime_path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _owned_command(self, pid: int, executable: Path) -> bool:
        try:
            result = subprocess.run(
                ["/bin/ps", "-p", str(pid), "-o", "command="], capture_output=True,
                text=True, timeout=3, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        command = result.stdout.strip()
        return (result.returncode == 0 and str(executable) in command
                and f"--DataDirectory {self.data_dir}" in command)

    def _recover_stale_instance(self, executable: Path) -> None:
        runtime: dict[str, object] = {}
        try:
            loaded = json.loads(self.runtime_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                runtime = loaded
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        tor_pid = int(runtime.get("pid") or 0)
        owner_pid = int(runtime.get("owner_pid") or 0)
        if tor_pid and _pid_alive(tor_pid):
            if owner_pid and owner_pid != os.getpid() and _pid_alive(owner_pid):
                raise RuntimeError("Managed Tor is owned by another running Morgan Media Downloader instance")
            if not self._owned_command(tor_pid, executable):
                raise RuntimeError("Refusing to terminate an unverified Tor process")
            self._log(f"Recovering stale Morgan-owned Tor process {tor_pid}")
            os.kill(tor_pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while _pid_alive(tor_pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            if _pid_alive(tor_pid):
                raise RuntimeError("Stale Morgan-owned Tor process did not stop")
        # This directory belongs only to Morgan. A lock is stale once its recorded
        # process is gone; Tor Browser uses a completely separate DataDirectory.
        lock_path = self.data_dir / "lock"
        if lock_path.exists():
            with lock_path.open("a+") as lock_stream:
                try:
                    fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise RuntimeError("Managed Tor data-directory lock is active") from error
                lock_path.unlink()
                self._log("Removed stale Managed Tor data-directory lock")
        self.runtime_path.unlink(missing_ok=True)

    def start(self) -> bool:
        with self._lock:
            if self.process and self.process.poll() is None:
                return True
            executable = tor_executable(self.browser_path)
            if not executable:
                self.last_error = "Tor executable not found"
                self._set_state("Failed")
                return False
            self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.data_dir, 0o700)
            try:
                self._recover_stale_instance(executable)
            except (OSError, RuntimeError) as error:
                self.last_error = str(error)
                self._set_state("Failed")
                return False
            self.last_error = ""
            self.bootstrap_percent = 0
            self._connected.clear()
            return self._launch_attempt(executable, 1)

    def _launch_attempt(self, executable: Path, attempt: int) -> bool:
        self.launch_attempt = attempt
        self.last_error = ""
        self._log("Selecting isolated runtime ports")
        try:
            socks_port, control_port, reservations = reserve_runtime_ports()
        except OSError as error:
            self.last_error = str(error)
            self._set_state("Failed")
            return False
        self.port, self.control_port = socks_port, control_port
        self._log(f"SOCKS port selected: {socks_port}")
        self._log(f"Control port selected: {control_port}")
        arguments = [
            str(executable), "--DataDirectory", str(self.data_dir),
            "--SocksPort", f"127.0.0.1:{socks_port}",
            "--ClientOnly", "1", "--AvoidDiskWrites", "1",
            "--ControlPort", f"127.0.0.1:{control_port}",
            "--CookieAuthentication", "1", "--CookieAuthFile", str(self.cookie_path),
            "--Log", "notice stdout",
        ]
        # Keep both endpoints reserved until the final moment before Tor is spawned.
        for reservation in reservations:
            reservation.close()
        self._log(f"Launching Managed Tor (attempt {attempt}/{MAX_LAUNCH_ATTEMPTS})")
        try:
            owned_process = subprocess.Popen(
                arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True,
            )
        except OSError as error:
            self.last_error = str(error)
            self._set_state("Failed")
            return False
        self.process = owned_process
        self.launch_timestamp = datetime.now(timezone.utc).isoformat()
        self._set_state("Starting")
        threading.Thread(target=self._read_output, args=(owned_process, executable, attempt), daemon=True).start()
        threading.Thread(target=self._watch_timeout, args=(owned_process,), daemon=True).start()
        return True

    @staticmethod
    def _endpoint_ready(port: int | None) -> bool:
        if not port:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            return False

    def _read_output(self, owned_process: subprocess.Popen[str], executable: Path, attempt: int) -> None:
        assert owned_process.stdout is not None
        collision = False
        for line in owned_process.stdout:
            if PORT_COLLISION.search(line):
                collision = True
                self.last_error = "Managed Tor port collision"
                self._log("Managed Tor port collision detected")
            if match := BOOTSTRAP.search(line):
                percent = int(match.group(1))
                self.bootstrap_percent = percent
                self._persist_runtime()
                if percent >= 100:
                    if self._endpoint_ready(self.port) and self._endpoint_ready(self.control_port):
                        self._set_state("Connected")
                        self._log("Bootstrapped 100%")
                        self._log("SOCKS ready")
                        self._log("Control interface ready")
                        self._connected.set()
                    else:
                        self.last_error = "Tor reported bootstrap 100%, but a runtime endpoint is unavailable"
                else:
                    self._set_state(f"Bootstrapping {percent}%")
            if "[err]" in line.lower():
                self.last_error = line.strip()
        return_code = owned_process.wait()
        retry = False
        with self._lock:
            if self.process is not owned_process:
                return
            self.process = None
            if collision and attempt < MAX_LAUNCH_ATTEMPTS and self.state != "Stopped":
                retry = True
                self._connected.clear()
                self.bootstrap_percent = 0
                self._set_state("Starting")
                self._log("Selecting a new port pair after collision")
            elif self.state != "Stopped":
                if collision:
                    self.last_error = f"Managed Tor port collision after {MAX_LAUNCH_ATTEMPTS} launch attempts"
                elif not self.last_error:
                    self.last_error = f"Tor exited with status {return_code}"
                self._set_state("Failed")
        if retry:
            with self._lock:
                self._launch_attempt(executable, attempt + 1)

    def _watch_timeout(self, owned_process: subprocess.Popen[str]) -> None:
        if not self._connected.wait(90) and owned_process.poll() is None:
            with self._lock:
                if self.process is not owned_process:
                    return
                self.last_error = "Tor bootstrap timed out after 90 seconds"
                self._set_state("Failed")
                owned_process.terminate()

    def wait_until_connected(self, timeout: float = 90) -> bool:
        return self._connected.wait(timeout)

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def request_new_circuit(self, *, cooldown: float = 10.0,
                            clock=time.monotonic, sleeper=time.sleep,
                            command=_control_command) -> dict[str, object]:
        with self._lock:
            if self.state != "Connected" or not self.control_port:
                raise RuntimeError("Managed Tor is not connected")
            try:
                cookie = self.cookie_path.read_bytes()
            except OSError as error:
                raise RuntimeError("Managed Tor control cookie is unavailable") from error
            if len(cookie) != 32:
                raise RuntimeError("Managed Tor control cookie is invalid")
            remaining = max(0.0, cooldown - (clock() - self.last_newnym_monotonic)) if self.last_newnym_monotonic else 0.0
            if remaining:
                sleeper(remaining)
            command(self.control_port, cookie, "SIGNAL NEWNYM")
            self.last_newnym_monotonic = clock()
            self.last_circuit_change = datetime.now(timezone.utc).isoformat()
            return {"requested": True, "cooldown_waited": remaining,
                    "last_circuit_change": self.last_circuit_change}

    def stop(self) -> None:
        with self._lock:
            owned_process = self.process
            # Only the exact Popen object created by this instance is terminated.
            if owned_process and owned_process.poll() is None:
                owned_process.terminate()
                try:
                    owned_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    owned_process.kill()
                    owned_process.wait(timeout=3)
            if self.process is owned_process:
                self.process = None
            self._connected.clear()
            self.bootstrap_percent = 0
            self.port = None
            self.control_port = None
            self._set_state("Stopped")
            self.runtime_path.unlink(missing_ok=True)
