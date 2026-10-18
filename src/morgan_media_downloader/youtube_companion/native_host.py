"""Chrome native framing only on stdout. No diagnostic exception output."""
import json
import struct
import sys

MAX_MESSAGE = 131072


def _exact(stream, count):
    result = bytearray()
    while len(result) < count:
        chunk = stream.read(count - len(result))
        if not chunk: raise ValueError("frame.truncated")
        result.extend(chunk)
    return bytes(result)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError("message.duplicate_key")
        result[key] = value
    return result


def read_message(stream):
    length = struct.unpack("=I", _exact(stream, 4))[0]
    if not 0 < length <= MAX_MESSAGE: raise ValueError("frame.limit")
    return json.loads(_exact(stream, length), object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("message.invalid")))


def write_message(stream, message):
    data = json.dumps(message, allow_nan=False, separators=(",", ":")).encode()
    if len(data) > MAX_MESSAGE: raise ValueError("frame.limit")
    stream.write(struct.pack("=I", len(data)) + data); stream.flush()


def main():
    from .bridge import CompanionController, ORIGIN
    try:
        if len(sys.argv) != 2 or sys.argv[1] != ORIGIN: raise ValueError("origin.rejected")
        result = CompanionController().handle(read_message(sys.stdin.buffer), sys.argv[1])
    except Exception:
        result = {"status": "rejected", "message": "Capture rejected. Open Connect in Morgan, approve Incognito access and try again."}
    try: write_message(sys.stdout.buffer, result)
    except Exception: return 1
    return 0


if __name__ == "__main__": raise SystemExit(main())
