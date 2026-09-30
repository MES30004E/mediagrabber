from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from .logging_setup import configure_logging
from .yt_runtime import get_runtime_manager


def main() -> int:
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
