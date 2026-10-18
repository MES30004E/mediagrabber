"""Security.framework Keychain I/O. Credentials never enter argv or a file."""
import ctypes as C
import json
import sys


class KeychainError(ValueError):
    def __init__(self, code, status):
        super().__init__(code)
        self.os_status = status  # Numeric OS status only; never include credential data.


class KeychainSessionStore:
    SERVICE = "com.morgan.media-downloader.youtube-companion"
    ACCOUNT = "youtube-session-v1"

    def __init__(self, *, interactive=True):
        # Explicit user actions may request Keychain consent. Headless probes
        # can instead require an immediate error rather than displaying OS UI.
        self.interactive = interactive

    def _operation(self, action, data=None):
        if sys.platform != "darwin": raise ValueError("keychain.unavailable")
        cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        sec = C.CDLL("/System/Library/Frameworks/Security.framework/Security")
        pointer = C.c_void_p
        cf.CFStringCreateWithCString.argtypes = [pointer, C.c_char_p, C.c_uint32]; cf.CFStringCreateWithCString.restype = pointer
        cf.CFDataCreate.argtypes = [pointer, pointer, C.c_long]; cf.CFDataCreate.restype = pointer
        cf.CFDictionaryCreate.argtypes = [pointer, pointer, pointer, C.c_long, pointer, pointer]; cf.CFDictionaryCreate.restype = pointer
        cf.CFRelease.argtypes = [pointer]
        cf.CFDataGetLength.argtypes = [pointer]; cf.CFDataGetLength.restype = C.c_long
        cf.CFDataGetBytePtr.argtypes = [pointer]; cf.CFDataGetBytePtr.restype = pointer
        for name in ("SecItemAdd", "SecItemCopyMatching", "SecItemUpdate"):
            getattr(sec, name).argtypes = [pointer, pointer]; getattr(sec, name).restype = C.c_int32
        sec.SecItemDelete.argtypes = [pointer]; sec.SecItemDelete.restype = C.c_int32
        owned = []
        def constant(name): return pointer.in_dll(sec, name).value
        def string(value):
            item = cf.CFStringCreateWithCString(None, value.encode(), 0x08000100); owned.append(item); return item
        def dictionary(values):
            keys = (pointer * len(values))(*values.keys()); vals = (pointer * len(values))(*values.values())
            item = cf.CFDictionaryCreate(None, keys, vals, len(values), None, None); owned.append(item); return item
        try:
            query_values = {constant("kSecClass"): constant("kSecClassGenericPassword"),
                            constant("kSecAttrService"): string(self.SERVICE), constant("kSecAttrAccount"): string(self.ACCOUNT)}
            if not self.interactive:
                query_values[constant("kSecUseAuthenticationUI")] = constant("kSecUseAuthenticationUIFail")
            query = dictionary(query_values)
            if action == "delete":
                status = sec.SecItemDelete(query)
                if status not in (0, -25300): raise ValueError("keychain.delete_failed")
                return
            if action == "load":
                query_values[constant("kSecReturnData")] = pointer.in_dll(cf, "kCFBooleanTrue").value
                query_values[constant("kSecMatchLimit")] = constant("kSecMatchLimitOne")
                output = pointer(); status = sec.SecItemCopyMatching(dictionary(query_values), C.byref(output))
                if status == -25300: return None
                if status != 0: raise ValueError("keychain.read_failed")
                try:
                    length = cf.CFDataGetLength(output)
                    if not 0 < length <= 70000: raise ValueError("keychain.invalid")
                    return json.loads(C.string_at(cf.CFDataGetBytePtr(output), length))
                finally: cf.CFRelease(output)
            encoded = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
            if len(encoded) > 70000: raise ValueError("keychain.limit")
            value = cf.CFDataCreate(None, encoded, len(encoded)); owned.append(value)
            attrs = {constant("kSecValueData"): value}
            status = sec.SecItemUpdate(query, dictionary(attrs))
            if status == -25300:
                attrs.update(query_values)
                attrs[constant("kSecAttrAccessible")] = constant("kSecAttrAccessibleWhenUnlockedThisDeviceOnly")
                status = sec.SecItemAdd(dictionary(attrs), None)
            if status != 0: raise KeychainError("keychain.write_failed", status)
        finally:
            for value in reversed(owned):
                if value: cf.CFRelease(value)

    def load(self): return self._operation("load")
    def save(self, data): self._operation("save", data)
    def delete(self): self._operation("delete")
