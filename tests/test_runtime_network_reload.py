"""A real offline dependency reproduction, isolated from other runtime tests."""
import os
import subprocess
import sys
from pathlib import Path


def test_runtime_reload_preserves_urllib3_regex_interface(tmp_path):
    root = Path(__file__).resolve().parents[1]
    code = '''
from pathlib import Path
import sys
import yt_dlp.networking._requests
import urllib3.util.url as url
from morgan_media_downloader.yt_runtime import YtDlpRuntimeManager
manager = YtDlpRuntimeManager(Path(sys.argv[1]), provider_checker=lambda: None)
for _ in range(3):
    manager._load_bundled()
    assert url.parse_url("https://www.youtube.com/a%2fb").host == "www.youtube.com"
    assert url._PERCENT_RE.sub("X", "%2f") == "X"
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)],
                            env=dict(os.environ, PYTHONPATH=str(root / "src")), capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
