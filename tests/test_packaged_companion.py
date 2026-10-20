import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_packaged_companion import verify_protocol


def test_packaging_checker_exercises_actual_host_without_checkout_import_path(tmp_path):
    # Point Python at the source using an explicit command, not PYTHONPATH: the
    # checker deliberately removes environment paths and changes cwd.
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0,{str(root / 'src')!r}); from morgan_media_downloader.youtube_companion.native_host import main; raise SystemExit(main())"]
    assert verify_protocol(command) == 5


@pytest.mark.parametrize("bad", ["wrong_protocol", "extra_bytes", "stderr"])
def test_packaging_checker_rejects_false_success_and_nonprotocol_output(bad):
    payload = json.dumps({"status": "ready", "protocol": 2 if bad == "wrong_protocol" else 1}).encode()
    code = f"import sys,struct; data={payload!r}; sys.stdout.buffer.write(struct.pack('=I',len(data))+data)"
    if bad == "extra_bytes": code += "; sys.stdout.buffer.write(b'noise')"
    if bad == "stderr": code += "; sys.stderr.write('noise')"
    with pytest.raises(RuntimeError): verify_protocol([sys.executable, "-I", "-c", code])
