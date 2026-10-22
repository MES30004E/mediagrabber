from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from .logging_setup import configure_logging
from .yt_runtime import get_runtime_manager


def main() -> int:
    if "--startup-check" in sys.argv[1:]:
        import argparse
        from pathlib import Path
        from .startup_check import run_startup_check
        parser = argparse.ArgumentParser(description="Launch/render/close the GUI in isolated temporary state; no live account or download checks.")
        parser.add_argument("--startup-check", type=Path, required=True, metavar="REPORT_JSON")
        return run_startup_check(parser.parse_args().startup_check)
    configure_logging()
    runtime_manager = get_runtime_manager()
    runtime_manager.initialize()
    from .ui import MainWindow
    QCoreApplication.setOrganizationName("Morgan")
    QCoreApplication.setApplicationName("Morgan Media Downloader")
    application = QApplication(sys.argv)
    application.setApplicationDisplayName("Morgan Media Downloader")
    window = MainWindow(runtime_manager); window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
