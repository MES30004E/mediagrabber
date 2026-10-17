"""Exercise the normal Python entry point with an isolated offscreen event loop."""
import os
import subprocess
import sys
from pathlib import Path


def test_normal_python_entry_point_launches_and_closes_cleanly(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1",
                       PYTHONPATH=str(root / "src"), MORGAN_DATA_DIR=str(tmp_path / "data"),
                       MORGAN_LOG_DIR=str(tmp_path / "logs"), MORGAN_CACHE_DIR=str(tmp_path / "cache"))
    script = '''
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from morgan_media_downloader.settings import AppSettings, SettingsStore
from morgan_media_downloader.provider import ProviderStatus
from morgan_media_downloader import app, ui
SettingsStore().save(AppSettings(show_first_run_diagnostics=False, yt_dlp_check_updates_on_startup=False))
execute = QApplication.exec
def timed(application):
    QTimer.singleShot(250, application.closeAllWindows)
    return execute()
with patch.object(QApplication, "exec", timed), patch.object(ui, "check_provider", return_value=ProviderStatus("unchecked", "Offline launch smoke", "")), patch("morgan_media_downloader.settings_window.browser_profiles", return_value=[("Default", "")]), patch("morgan_media_downloader.settings_window.discover_browsers", return_value=[]):
    raise SystemExit(app.main())
'''
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=root, env=environment,
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "data/running.marker").exists()
