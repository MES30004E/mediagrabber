"""Consumer-level layout/preferences checks; no live accounts or downloads."""
import copy
import pytest
from PySide6.QtCore import QEvent,QTimer,Qt
from PySide6.QtWidgets import QApplication,QLabel

from morgan_media_downloader.models import DownloadJob,DownloadOptions,MediaItem
from morgan_media_downloader.settings import SettingsStore
from morgan_media_downloader.ui import MainWindow
from test_theme_ui import window

APP=QApplication.instance() or QApplication([])


def seed(window,tmp_path):
    jobs=[DownloadJob(MediaItem(f"https://example.test/{i}",f"Synthetic download {i} — a useful long title",source="Fixture"),
        DownloadOptions(download_dir=str(tmp_path/"downloads")),kind="torrent" if i%2 else "media") for i in range(8)]
    window.jobs={job.id:job for job in jobs}; window.database.save_jobs(jobs); window._refresh_queue()
    return jobs


@pytest.mark.parametrize("width,height,view",[(900,650,"Media"),(900,650,"Torrents"),(900,650,"All"),(1180,820,"Media"),(1440,900,"Media")])
def test_default_queue_fits_and_prioritises_titles_with_useful_table_space(window,tmp_path,width,height,view):
    seed(window,tmp_path); window.resize(width,height); window.queue_filter.setCurrentText(view); APP.processEvents()
    assert not window.job_details.isVisible(), "Details must not consume a large empty panel by default"
    assert window.queue_table.height()>=(250 if height==650 else 400)
    assert window.queue_table.horizontalScrollBar().maximum()==0, (
        "Ordinary columns must fit without horizontal scrolling",window.queue_table.viewport().width(),
        [(name,window.queue_table.columnWidth(i)) for i,name in enumerate(window.queue_model.columns) if not window.queue_table.isColumnHidden(i)])
    columns=window.queue_model.columns
    assert window.queue_table.columnWidth(columns.index("Title"))>=160
    visible=[name for column,name in enumerate(columns) if not window.queue_table.isColumnHidden(column)]
    expected={"Media":["Title","Status","Progress","Speed","ETA","Destination"],
        "Torrents":["Title","Status","Progress","Down","ETA","Destination"],
        "All":["Title","Status","Progress","Speed","ETA","Destination"]}
    assert visible==expected[view]


def test_collection_selector_stays_next_to_its_label_in_a_wide_window(window,tmp_path):
    seed(window,tmp_path); window.resize(1440,900); APP.processEvents()
    label=next(label for label in window.collections.findChildren(QLabel) if label.text()=="Collection:")
    assert 0<=window.collections.selector.x()-(label.x()+label.fontMetrics().horizontalAdvance(label.text()))<=20


def test_columns_and_disclosures_persist_without_overwriting_pending_settings(window,tmp_path,monkeypatch):
    from morgan_media_downloader.provider import ProviderStatus
    monkeypatch.setattr("morgan_media_downloader.ui.check_provider",lambda *_:ProviderStatus("available","Synthetic","script"))
    window.settings_panel.theme.setCurrentText("Dark")  # Pending setting, not applied by layout actions.
    window.tabs.sidebar_toggle.click()
    window.queue_details_section.toggle.click()
    window.queue_presentation.column_actions["Source"].trigger()
    APP.processEvents()
    assert window.tabs.isCollapsed() and window.job_details.isVisible()
    assert not window.queue_table.isColumnHidden(window.queue_model.columns.index("Source"))
    assert window.settings.theme=="Light"
    window.settings_panel.apply(); APP.processEvents()
    assert window.settings.theme=="Dark" and window.tabs.isCollapsed() and window.job_details.isVisible()
    assert window.settings.sidebar_collapsed is True and window.settings.queue_details_expanded is True
    assert "Source" in window.settings.queue_visible_columns["Media"]
    from morgan_media_downloader.settings_window import SettingsWindow
    cancelled=SettingsWindow(window.settings,window.managed_tor,window._apply_settings,parent=window,
        runtime_manager=window.runtime_manager,presentation_settings=lambda:window.settings)
    for timer in cancelled.findChildren(QTimer): timer.stop()
    cancelled.theme.setCurrentText("Light"); cancelled.reject()
    assert window.settings.theme=="Dark" and window.tabs.isCollapsed()
    cancelled.deleteLater(); APP.sendPostedEvents(cancelled,QEvent.Type.DeferredDelete)
    window.close(); APP.processEvents()
    saved=SettingsStore().load()
    assert saved.sidebar_collapsed and saved.queue_details_expanded and "Source" in saved.queue_visible_columns["Media"]
    restored=MainWindow(window.runtime_manager)
    for timer in restored.findChildren(QTimer): timer.stop()
    try:
        restored.tabs.setCurrentIndex(1); restored.show(); APP.processEvents()
        assert restored.tabs.isCollapsed() and restored.job_details.isVisible()
        assert not restored.queue_table.isColumnHidden(restored.queue_model.columns.index("Source"))
    finally:
        restored.close(); restored.deleteLater(); APP.sendPostedEvents(restored,QEvent.Type.DeferredDelete)


def test_resize_and_sidebar_changes_do_not_scan_jobs_write_sql_or_save_preferences(window,monkeypatch):
    selected=[job.id for job in window._selected_jobs()]
    class NoScanJobs(dict):
        def values(self): raise AssertionError("Resize must not rescan queued downloads")
        def items(self): raise AssertionError("Resize must not rescan queued downloads")
        def __iter__(self): raise AssertionError("Resize must not rescan queued downloads")
    original=window.jobs; window.jobs=NoScanJobs(original)
    statements=[]; window.database._connection.set_trace_callback(statements.append)
    def unexpected(*_args): raise AssertionError("Resize must not persist settings")
    try:
        with monkeypatch.context() as guard:
            guard.setattr(window.settings_store,"save",unexpected)
            for width,height in ((900,650),(1440,900),(1180,820)):
                window.resize(width,height); window.tabs.sidebar_toggle.click(); APP.processEvents()
            assert not statements
            assert [job.id for job in window._selected_jobs()]==selected
    finally:
        window.jobs=original; window.database._connection.set_trace_callback(None)


def test_user_column_width_survives_resize_view_roundtrip_and_row_reorder(window,tmp_path):
    seed(window,tmp_path); window.queue_table.selectRow(0)
    wanted=[job.id for job in window._selected_jobs()]
    window.queue_table.horizontalHeader().resizeSection(0,310)
    window.queue_presentation.column_actions["Source"].trigger()
    window.resize(1440,900); APP.processEvents()
    assert window.queue_table.columnWidth(0)==310, "An explicit user width must not be replaced by automatic fitting"
    window.queue_filter.setCurrentText("Torrents"); APP.processEvents()
    window.queue_presentation.column_actions["Connected peers"].trigger()
    window.queue_filter.setCurrentText("Media"); APP.processEvents()
    window.jobs=dict(reversed(list(window.jobs.items()))); window._refresh_queue(); APP.processEvents()
    assert window.queue_table.columnWidth(0)==310
    assert not window.queue_table.isColumnHidden(window.queue_model.columns.index("Source"))
    assert [job.id for job in window._selected_jobs()]==wanted
    window._persist_settings()
    assert SettingsStore().load().queue_column_widths["Media"]["Title"]==310


def test_reset_columns_restores_only_current_view_defaults_and_keeps_selection(window,tmp_path):
    seed(window,tmp_path); window.queue_table.selectRow(0)
    wanted=[job.id for job in window._selected_jobs()]
    window.queue_presentation.column_actions["Source"].trigger()
    window.queue_table.horizontalHeader().resizeSection(0,310)
    window.queue_filter.setCurrentText("Torrents"); APP.processEvents()
    window.queue_presentation.column_actions["Connected peers"].trigger()
    window.queue_filter.setCurrentText("Media"); APP.processEvents()
    window.queue_presentation.reset_action.trigger(); APP.processEvents()
    assert window.queue_table.isColumnHidden(window.queue_model.columns.index("Source"))
    assert window.queue_table.horizontalScrollBar().maximum()==0
    assert window.queue_table.columnWidth(0)>310 and [job.id for job in window._selected_jobs()]==wanted
    assert "Connected peers" in window.settings.queue_visible_columns["Torrents"]
    assert not window.queue_presentation.column_actions["Title"].isEnabled()


def test_collapsed_navigation_keeps_keyboard_routes_and_accessible_names(window):
    from PySide6.QtTest import QTest
    window.tabs.sidebar_toggle.click(); APP.processEvents()
    assert window.tabs.isCollapsed() and window.tabs.sidebar.width()==64
    assert window.tabs.navigation.item(0).data(Qt.ItemDataRole.AccessibleTextRole)=="Download"
    assert window.tabs.sidebar_toggle.accessibleName()=="Expand sidebar"
    APP.setActiveWindow(window)
    QTest.keyClick(window,Qt.Key.Key_5,Qt.KeyboardModifier.MetaModifier); APP.processEvents()
    assert window.tabs.currentWidget() is window.settings_panel
    APP.setActiveWindow(window)
    QTest.keyClick(window,Qt.Key.Key_2,Qt.KeyboardModifier.MetaModifier); APP.processEvents()
    assert window.tabs.currentIndex()==1 and window.tabs.isCollapsed()


def test_preferences_getter_merges_only_ui_state_not_unrelated_captured_choices(window):
    from morgan_media_downloader.settings_window import SettingsWindow
    current=copy.deepcopy(window.settings)
    current.sidebar_collapsed=True; current.queue_details_expanded=True
    current.queue_visible_columns={"Media":["Title","Status","Progress","Source"]}
    current.authentication_mode="Browser Cookies"; current.cookies_file="/synthetic/not-a-real-cookie-file"
    current.converter_container="MKV"
    dialog=SettingsWindow(window.settings,window.managed_tor,lambda *_:None,parent=window,
        runtime_manager=window.runtime_manager,presentation_settings=lambda:current)
    for timer in dialog.findChildren(QTimer): timer.stop()
    try:
        dialog.theme.setCurrentText("Dark")
        result=dialog._collect()
        assert result.sidebar_collapsed and result.queue_details_expanded
        assert result.theme=="Dark" and result.authentication_mode=="None" and result.cookies_file==""
        assert result.converter_container=="MP4" and window.settings.theme=="Light"
        result.queue_visible_columns["Media"].append("Format")
        assert current.queue_visible_columns["Media"]==["Title","Status","Progress","Source"]
    finally:
        dialog.reject(); dialog.deleteLater(); APP.sendPostedEvents(dialog,QEvent.Type.DeferredDelete)


def test_explicit_reset_uses_fresh_defaults_not_presentation_getter(window,monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from morgan_media_downloader.settings_window import SettingsWindow
    current=copy.deepcopy(window.settings); current.sidebar_collapsed=True; current.queue_details_expanded=True
    current.queue_visible_columns={"Media":["Title","Source"]}; current.queue_column_widths={"Media":{"Title":310}}
    captured=[]
    dialog=SettingsWindow(window.settings,window.managed_tor,lambda value,_:captured.append(value),parent=window,
        runtime_manager=window.runtime_manager,presentation_settings=lambda:current)
    for timer in dialog.findChildren(QTimer): timer.stop()
    monkeypatch.setattr(QMessageBox,"question",lambda *_:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox,"information",lambda *_:QMessageBox.StandardButton.Ok)
    try:
        dialog._reset()
        assert len(captured)==1 and not captured[0].sidebar_collapsed and not captured[0].queue_details_expanded
        assert captured[0].queue_visible_columns==captured[0].queue_column_widths=={}
    finally:
        dialog.deleteLater(); APP.sendPostedEvents(dialog,QEvent.Type.DeferredDelete)


def test_default_completed_warning_status_is_not_elided_in_actual_cell_pixels(window):
    from PySide6.QtCore import QRect
    from morgan_media_downloader.models import JobStatus
    job=next(iter(window.jobs.values())); job.status=JobStatus.COMPLETED_WARNINGS
    window._refresh_queue(); window.queue_table.clearSelection(); APP.processEvents()
    column=window.queue_model.columns.index("Status"); index=window.queue_table.model().index(0,column)
    width=window.queue_table.columnWidth(column)
    def cell_image():
        APP.processEvents(); image=window.queue_table.viewport().grab().toImage()
        rect=window.queue_table.visualRect(index); scale=image.devicePixelRatio()
        return image.copy(QRect(round(rect.x()*scale),round(rect.y()*scale),round(rect.width()*scale),round(rect.height()*scale)))
    current=cell_image()
    window.queue_table.horizontalHeader().resizeSection(column,350)
    try:
        reference=cell_image(); border=round(4*current.devicePixelRatio())
        common=QRect(border,border,current.width()-2*border,current.height()-2*border)
        assert current.copy(common)==reference.copy(common), (
            f"Default status elides actual warning text: width={width}, font={window.queue_table.fontMetrics().horizontalAdvance(str(index.data()))}")
    finally: window.queue_table.horizontalHeader().resizeSection(column,width)


def test_long_connection_result_wraps_without_pushing_account_actions_outside_compact_window(window):
    window.tabs.setCurrentIndex(0); window.resize(900,650)
    window._connection_test_ready(("unavailable","Synthetic proxy connection unavailable — verify the selected connection and try again. "*3))
    APP.processEvents()
    assert window.width()==900
    assert window.connection_status.wordWrap()
    assert window.connection_status.textFormat()==Qt.TextFormat.PlainText
    for control in (window.connection_selector,window.connection_status,window.connection_test,window.account_button):
        assert control.isVisible()
        assert window.rect().contains(control.mapTo(window,control.rect().bottomRight()))


@pytest.mark.parametrize("progress",[4.0,37.5,100.0])
@pytest.mark.parametrize("view",["Media","Torrents","All"])
def test_compact_progress_percentage_is_complete_against_wide_actual_cell(window,progress,view):
    from PySide6.QtCore import QRect
    job=next(iter(window.jobs.values())); job.progress=progress; job.kind="torrent" if view=="Torrents" else "media"
    window._refresh_queue(); window.queue_filter.setCurrentText(view)
    window.resize(900,650); window.queue_table.clearSelection(); APP.processEvents()
    column=window.queue_model.columns.index("Progress"); index=window.queue_table.model().index(0,column)
    width=window.queue_table.columnWidth(column)
    def label_image():
        APP.processEvents(); image=window.queue_table.viewport().grab().toImage()
        rect=window.queue_table.visualRect(index); scale=image.devicePixelRatio()
        label_width=window.queue_table.fontMetrics().horizontalAdvance("100.0%")
        return image.copy(QRect(round((rect.right()-label_width-3)*scale),round((rect.y()+4)*scale),round(label_width*scale),round((rect.height()-8)*scale)))
    current=label_image(); window.queue_table.horizontalHeader().resizeSection(column,220)
    try: assert current==label_image(),"Compact progress must preserve the full percentage, not an elided label"
    finally: window.queue_table.horizontalHeader().resizeSection(column,width)


@pytest.mark.parametrize("view,fields",[("Media",("Speed","ETA")),("Torrents",("Down","Up","ETA")),("All",("Speed","ETA"))])
def test_running_transfer_units_and_long_eta_are_not_elided_in_actual_cell_pixels(window,view,fields):
    from PySide6.QtCore import QRect
    from morgan_media_downloader.models import JobStatus
    job=next(iter(window.jobs.values())); job.kind="torrent" if view=="Torrents" else "media"
    job.status=JobStatus.DOWNLOADING; job.speed=12.4*1024**2; job.upload_speed=1023.8*1024; job.eta=124*3600+61
    window._refresh_queue(); window.queue_filter.setCurrentText(view); window.resize(900,650)
    window.queue_table.clearSelection(); APP.processEvents()
    assert window.width()==900 and window.queue_table.horizontalScrollBar().maximum()==0
    for field in fields:
        if field=="Up":
            window.queue_presentation.column_actions["Up"].trigger(); APP.processEvents()
        column=window.queue_model.columns.index(field); index=window.queue_table.model().index(0,column)
        window.queue_table.scrollTo(index); APP.processEvents()
        width=window.queue_table.columnWidth(column)
        def cell_image():
            APP.processEvents(); image=window.queue_table.viewport().grab().toImage()
            rect=window.queue_table.visualRect(index); scale=image.devicePixelRatio()
            return image.copy(QRect(round(rect.x()*scale),round(rect.y()*scale),round(rect.width()*scale),round(rect.height()*scale)))
        current=cell_image(); window.queue_table.horizontalHeader().resizeSection(column,220)
        try:
            reference=cell_image(); border=round(4*current.devicePixelRatio())
            common=QRect(border,border,current.width()-2*border,current.height()-2*border)
            assert current.copy(common)==reference.copy(common),f"{view} {field} elides {index.data()!r} at {width}px"
        finally: window.queue_table.horizontalHeader().resizeSection(column,width)
