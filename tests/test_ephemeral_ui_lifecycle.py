"""Closed one-shot windows/menus must release their captured media and jobs."""
import gc
import weakref

import pytest
from PySide6.QtCore import QEvent, QPoint, QTimer
from PySide6.QtWidgets import QDialogButtonBox, QMenu

from morgan_media_downloader.media_details import details_from_info
from morgan_media_downloader.media_details_dialog import MediaDetailsDialog
from morgan_media_downloader.models import DownloadJob, DownloadOptions, MediaItem
from test_history_deferred import APP, window
from test_media_details import metadata
from test_playlist_workspace import _populate


def drain_deletes():
    APP.processEvents()
    APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()


def inspect_item(window, number):
    item = MediaItem(f"https://example.test/{number}", f"Synthetic {number}")
    _populate(window, [item])
    runtime = window.runtime_manager.snapshot()
    window._inspection_ready((window._inspection_generation, item, runtime.version, runtime.source,
                              details_from_info(metadata()), "None", ""))
    return weakref.ref(item)


@pytest.mark.parametrize("action", ["close", "cancel", "apply", "reset"])
def test_repeated_finished_inspections_release_dialogs_and_old_items(window, action):
    references = []
    for number in range(5):
        references.append(inspect_item(window, number))
        dialog = window.media_details_dialog
        if action == "close": dialog.close()
        elif action == "cancel": dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        elif action == "apply": dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
        else: dialog._reset()
        del dialog
        drain_deletes()
        assert window.media_details_dialog is None
        assert not window.findChildren(MediaDetailsDialog)
    _populate(window, [])
    drain_deletes()
    assert all(reference() is None for reference in references)


def test_replacement_releases_old_inspection_without_clearing_new_owner(window):
    previous = inspect_item(window, 0)
    inspect_item(window, 1)
    current = window.media_details_dialog
    drain_deletes()
    assert window.media_details_dialog is current and current.isVisible()
    assert window.findChildren(MediaDetailsDialog) == [current]
    assert previous() is None


def test_window_close_disposes_the_active_inspection(window):
    inspect_item(window, 0)
    window.close(); drain_deletes()
    assert window.media_details_dialog is None
    assert not window.findChildren(MediaDetailsDialog)


@pytest.mark.parametrize("page", ["queue", "history"])
@pytest.mark.parametrize("activate", [False, True])
def test_context_menu_completion_releases_menus_and_captured_jobs(window, tmp_path, monkeypatch, page, activate):
    references = []
    conversions = []
    monkeypatch.setattr(window, "open_video_converter", lambda path: conversions.append(path))
    output = tmp_path / "synthetic.mp4"; output.write_bytes(b"not real media")
    for number in range(3):
        job = DownloadJob(MediaItem(f"https://example.test/{number}", f"Synthetic {number}"),
                          DownloadOptions(authentication_mode="None"), output_file=str(output))
        references.append(weakref.ref(job))
        window.jobs = {job.id: job}; window.database.save_job(job)
        window._refresh_queue(); window._refresh_history()
        table = window.queue_table if page == "queue" else window.history_table
        window.tabs.setCurrentIndex(1) if page == "queue" else window.tabs.setCurrentWidget(window.history_page)
        table.selectRow(0)
        errors = []
        def dismiss():
            # Native Cocoa menus need not be QApplication.activePopupWidget().
            # Inspect the actual menu created by this table's handler instead.
            menus = table.findChildren(QMenu)
            menu = menus[-1] if menus else None
            try:
                assert isinstance(menu, QMenu)
                action = next(action for action in menu.actions() if action.text() == "Convert As…")
                if activate: action.trigger()
            except BaseException as error: errors.append(error)
            finally:
                if menu is not None: menu.close()
        QTimer.singleShot(0, dismiss)
        if page == "queue": window._queue_context_menu(QPoint(5, 5))
        else: window._history_context_menu(QPoint(5, 5))
        if errors: raise errors[0]
        drain_deletes()
        assert not table.findChildren(QMenu)
        window.database.remove_job(job.id); window.jobs.clear()
        window._refresh_queue(); window._refresh_history()
        del job
    drain_deletes()
    assert conversions == ([str(output)] * 3 if activate else [])
    assert all(reference() is None for reference in references)
