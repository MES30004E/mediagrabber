"""Consent-bound control files contain NO cookies; Keychain owns session data."""
import fcntl
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import time
from uuid import uuid4
from contextlib import contextmanager

from .session import validate_cookies

EXTENSION_ID = "cplbbpknliffempndiphmhaolpgipdgn"
HOST = "com.morgan.media_downloader.youtube"
ORIGIN = f"chrome-extension://{EXTENSION_ID}/"


def control_root():
    return Path.home() / "Library/Application Support/Morgan Media Downloader/companion"


class CompanionController:
    def __init__(self, root=None, store=None):
        self.root = Path(root) if root is not None else control_root()
        if store is None:
            from .storage import KeychainSessionStore
            store = KeychainSessionStore()
        self.store = store

    @contextmanager
    def _lock(self):
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("control.permissions")
        fd = os.open(self.root / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ValueError("control.permissions")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally: os.close(fd)

    def _read(self, name):
        try: fd = os.open(self.root / name, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError: return None
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > 8192:
                raise ValueError("control.permissions")
            return json.load(stream)

    def _write(self, name, data):
        temporary = self.root / ("." + name + "." + uuid4().hex)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.root / name)
        finally: temporary.unlink(missing_ok=True)

    def begin(self):
        with self._lock():
            operation = str(uuid4())
            self._write("pending.json", {"operation_id": operation, "nonce": secrets.token_hex(32), "expires": time.time() + 300})
            return operation

    def cancel(self, operation_id=None):
        with self._lock():
            pending = self._read("pending.json")
            if pending and (operation_id is None or pending.get("operation_id") == operation_id):
                (self.root / "pending.json").unlink(missing_ok=True)

    def receipt(self):
        try:
            with self._lock(): return self._read("receipt.json")
        except BlockingIOError:
            return None  # Native host may be awaiting Keychain approval; don't freeze Qt.

    def poll_status(self, operation_id, *, expire=False):
        """Reconcile completion and expiry atomically with the capture writer.

        A Keychain prompt can outlive the authorization deadline. While its
        writer owns the lock, defer rather than losing a later success receipt.
        """
        try:
            with self._lock():
                receipt = self._read("receipt.json")
                if receipt and receipt.get("operation_id") == operation_id:
                    return {"receipt": receipt}
                pending = self._read("pending.json")
                if not pending or pending.get("operation_id") != operation_id:
                    return {"expired": True} if expire else None
                if expire or time.time() >= pending["expires"]:
                    (self.root / "pending.json").unlink()
                    return {"expired": True}
                return {"operation_id": operation_id, "extension_ready": pending.get("extension_ready"),
                        "reported_at": pending.get("reported_at")}
        except BlockingIOError:
            return {"busy": True}

    def disconnect(self):
        with self._lock():
            self.store.delete()  # Failure must not claim that the session was deleted.
            (self.root / "pending.json").unlink(missing_ok=True)
            (self.root / "receipt.json").unlink(missing_ok=True)

    def handle(self, message, origin):
        if origin != ORIGIN or not isinstance(message, dict): raise ValueError("origin.rejected")
        kind = message.get("type")
        if kind == "ping" and set(message) == {"type"}: return {"status": "ready", "protocol": 1}
        if kind == "ping":
            if set(message) != {"type", "incognito", "incognito_allowed"} or any(
                    type(message[key]) is not bool for key in ("incognito", "incognito_allowed")):
                raise ValueError("message.invalid")
            try:
                with self._lock():
                    pending = self._read("pending.json")
                    if pending and time.time() < pending["expires"]:
                        pending["extension_ready"] = message["incognito"] and message["incognito_allowed"]
                        pending["reported_at"] = time.time()
                        self._write("pending.json", pending)
            except BlockingIOError:
                pass  # Host is reachable even while an approved capture stores its session.
            return {"status": "ready", "protocol": 1}
        with self._lock():
            pending = self._read("pending.json")
            if not pending or time.time() >= pending["expires"]: raise ValueError("operation.missing_or_expired")
            if kind == "hello" and set(message) == {"type"}:
                return {"status": "pending", **pending}
            if set(message) != {"type", "operation_id", "nonce", "consent", "incognito", "store_id", "cookies"} or kind != "capture":
                raise ValueError("message.invalid")
            if message["operation_id"] != pending["operation_id"] or not isinstance(message["nonce"], str) or not hmac.compare_digest(message["nonce"], pending["nonce"]):
                raise ValueError("operation.rejected")
            if message["consent"] is not True or message["incognito"] is not True: raise ValueError("consent.required")
            cookies = validate_cookies(message["cookies"], message["store_id"])
            (self.root / "pending.json").unlink()  # Consume before storage, never retry a transfer automatically.
            try:
                self.store.save({"version": 1, "cookies": cookies})
                result = {"status": "imported", "operation_id": pending["operation_id"], "cookie_count": len(cookies), "imported_at": time.time()}
            except Exception:
                result = {"status": "storage_failed", "operation_id": pending["operation_id"]}
            self._write("receipt.json", result)
            return result
