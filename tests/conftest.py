"""Dispose accepted, drained test windows; importing backend tests stays Qt-free."""
import sys

import pytest


@pytest.fixture(autouse=True)
def dispose_closed_test_windows():
    widgets = sys.modules.get("PySide6.QtWidgets")
    app = widgets.QApplication.instance() if widgets else None
    if app:
        from PySide6.QtCore import QEvent
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    previous = set(app.topLevelWidgets()) if app else set()
    yield
    widgets = sys.modules.get("PySide6.QtWidgets")
    ui = sys.modules.get("morgan_media_downloader.ui")
    app = widgets.QApplication.instance() if widgets else None
    if app is None or ui is None:
        return
    from PySide6.QtCore import QEvent
    for window in app.topLevelWidgets():
        if (window not in previous and isinstance(window, ui.MainWindow)
                and window._closing and not window.isVisible()
                and window.task_manager.active_count == 0):
            # close() accepts shutdown but does not destroy parented C++ widgets.
            # Only this test's already-closed/drained windows are ours to dispose;
            # never close a live owner or a pre-existing/global fixture here.
            window.deleteLater()
            app.sendPostedEvents(window, QEvent.Type.DeferredDelete)
    # Settings/dialog fixtures already request deleteLater(). processEvents()
    # outside an event loop does not necessarily deliver those queued deletes.
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
