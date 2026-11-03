from collections import Counter

import pytest
from PySide6.QtCore import QEvent,QObject,QPoint,QTimer,Qt
from PySide6.QtGui import QColor,QIcon,QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel,QLineEdit,QMenu

from morgan_media_downloader.models import DownloadJob,DownloadOptions,MediaItem
from morgan_media_downloader.settings import AppSettings,SettingsStore
from morgan_media_downloader.theme import apply_theme
from morgan_media_downloader.ui import MainWindow
from morgan_media_downloader.yt_runtime import RuntimeSnapshot,YtDlpRuntimeManager

APP=QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path,monkeypatch):
    monkeypatch.setenv("HOME",str(tmp_path))
    for name,child in (("MORGAN_DATA_DIR","data"),("MORGAN_LOG_DIR","logs"),("MORGAN_CACHE_DIR","cache")):
        monkeypatch.setenv(name,str(tmp_path/child))
    previous=QPalette(APP.palette()); stylesheet=APP.styleSheet()
    SettingsStore().save(AppSettings(theme="Light",authentication_mode="None",cookies_file="",browser_profile="",
        download_dir=str(tmp_path/"downloads"),torrent_download_dir=str(tmp_path/"torrents"),converter_output_dir=str(tmp_path/"converted"),
        show_first_run_diagnostics=False,first_run_complete=True,
        clipboard_url_detection=False,yt_dlp_check_updates_on_startup=False,yt_dlp_auto_install_updates=False,
        managed_tor_auto_start=False,connection_mode="Direct / Normal Network"))
    runtime=YtDlpRuntimeManager(tmp_path/"runtime",bundled_loader=lambda:RuntimeSnapshot("synthetic","Fixture",object),provider_checker=lambda:None)
    runtime.initialize(); value=MainWindow(runtime)
    for timer in value.findChildren(QTimer): timer.stop()
    job=DownloadJob(MediaItem("https://example.test/video","Synthetic theme item"),DownloadOptions(download_dir=str(tmp_path)))
    value.database.save_job(job); value.jobs={job.id:job}; value._refresh_queue()
    value.tabs.setCurrentIndex(1); value.show(); APP.processEvents(); value.queue_table.selectRow(0)
    try: yield value
    finally:
        value.close(); APP.processEvents()
        value.deleteLater(); APP.sendPostedEvents(value,QEvent.Type.DeferredDelete)
        apply_theme(APP,"System"); APP.processEvents()
        APP.setStyleSheet(""); APP.setPalette(previous); APP.setStyleSheet(stylesheet); APP.processEvents()


def switch(window,mode):
    window.settings.theme=mode; window._apply_theme(); APP.processEvents()


def sidebar_pixel(window):
    sidebar=window.tabs.navigation.parentWidget()
    image=sidebar.grab().toImage()
    return image.pixelColor(2,image.height()-4).name()


def test_existing_sidebar_table_text_and_details_follow_light_dark_roundtrip(window):
    window.view_job_details(); APP.processEvents()
    for mode,side,base,text in (("Dark","#24272b","#292c31","#f0f1f4"),("Light","#eef1f5","#ffffff","#242830")):
        switch(window,mode)
        assert sidebar_pixel(window)==side
        assert window.queue_table.palette().color(QPalette.ColorRole.Base).name()==base
        assert window.job_details.palette().color(QPalette.ColorRole.Text).name()==text
        assert window.details_dialog_text.palette().color(QPalette.ColorRole.Base).name()==base


def test_dynamic_dialog_and_hidden_settings_controls_use_current_theme(window):
    switch(window,"Dark")
    window.view_job_details(); APP.processEvents()
    assert window.details_dialog_text.palette().color(QPalette.ColorRole.Base).name()=="#292c31"
    fields=window.settings_panel.findChildren(QLineEdit); assert fields
    assert all(field.palette().color(QPalette.ColorRole.Base).name()=="#292c31" for field in fields)
    switch(window,"Light")
    assert window.details_dialog_text.palette().color(QPalette.ColorRole.Base).name()=="#ffffff"


def test_system_roundtrip_repolishes_existing_children_to_current_native_palette(window):
    switch(window,"Dark"); switch(window,"System")
    expected=APP.palette()
    assert sidebar_pixel(window)==expected.color(QPalette.ColorRole.AlternateBase).name()
    assert window.queue_table.palette().color(QPalette.ColorRole.Base)==expected.color(QPalette.ColorRole.Base)


@pytest.mark.parametrize("hidden",[False,True])
def test_system_appearance_uses_palette_that_arrives_after_scheme_notification(window,hidden):
    switch(window,"System")
    if hidden: window.hide()
    window._system_appearance_changed()  # Qt documents that the old palette is still current here.
    native=QPalette(APP.palette()); native.setColor(QPalette.ColorRole.Window,QColor("#102030"))
    native.setColor(QPalette.ColorRole.AlternateBase,QColor("#203040")); native.setColor(QPalette.ColorRole.Base,QColor("#304050"))
    APP.setPalette(native); APP.processEvents()
    assert sidebar_pixel(window)=="#203040"
    assert window.queue_table.palette().color(QPalette.ColorRole.Base).name()=="#304050"


class StyleEvents(QObject):
    def __init__(self): super().__init__(); self.events=[]
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.StyleChange,QEvent.Type.PaletteChange): self.events.append(event.type())
        return False


def test_unchanged_theme_does_not_repolish_or_write_settings(window,monkeypatch):
    switch(window,"Dark"); watcher=StyleEvents(); window.installEventFilter(watcher)
    original=window.settings_store.save
    def unexpected(*_args): raise AssertionError("An unchanged theme must not save preferences")
    monkeypatch.setattr(window.settings_store,"save",unexpected)
    try:
        switch(window,"Dark")
        assert not watcher.events
    finally:
        window.removeEventFilter(watcher); monkeypatch.setattr(window.settings_store,"save",original)


def luminance(color):
    values=[value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4 for value in (color.redF(),color.greenF(),color.blueF())]
    return .2126*values[0]+.7152*values[1]+.0722*values[2]


def contrast(first,second):
    if first.alphaF()<1:
        first=QColor.fromRgbF(*(foreground*first.alphaF()+background*(1-first.alphaF())
            for foreground,background in zip((first.redF(),first.greenF(),first.blueF()),(second.redF(),second.greenF(),second.blueF()))))
    a,b=sorted((luminance(first),luminance(second)))
    return (b+.05)/(a+.05)


@pytest.mark.parametrize("mode,background",[(QIcon.Mode.Normal,"#24272b"),(QIcon.Mode.Selected,"#276bd2")])
def test_download_navigation_arrow_stays_readable_in_dark_and_selected_states(window,mode,background):
    switch(window,"Dark")
    image=window.tabs.navigation.item(0).icon().pixmap(20,20,mode).toImage()
    colors=Counter(image.pixelColor(x,y).rgb() for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x,y).alpha()>245)
    assert colors
    foreground=QColor.fromRgb(colors.most_common(1)[0][0])
    assert contrast(foreground,QColor(background))>=4.5


@pytest.mark.parametrize("theme",["Light","Dark","System"])
def test_disabled_primary_controls_remain_legible(window,theme):
    switch(window,theme)
    button=window.stop_queue_batch; assert not button.isEnabled()
    image=button.grab().toImage(); bounds=button.fontMetrics().boundingRect(button.text())
    background=APP.palette().color(QPalette.ColorRole.Window)
    assert image.pixelColor(8,image.height()//2)==background
    center=image.rect().center(); width=min(bounds.width()*image.devicePixelRatio(),image.width()-20)
    height=min(bounds.height()*image.devicePixelRatio(),image.height()-12)
    colors=[image.pixelColor(x,y) for x in range(int(center.x()-width/2),int(center.x()+width/2))
            for y in range(int(center.y()-height/2),int(center.y()+height/2))]
    assert max(contrast(color,background) for color in colors)>=3


def test_system_muted_captions_remain_readable(window):
    switch(window,"System")
    labels=window.tabs.findChildren(QLabel,"muted"); assert labels
    background=APP.palette().color(QPalette.ColorRole.Window)
    assert all(contrast(label.palette().color(QPalette.ColorRole.WindowText),background)>=4.5 for label in labels)


def test_system_table_header_text_is_painted_with_readable_contrast(window):
    switch(window,"System")
    header=window.queue_table.horizontalHeader(); image=header.grab().toImage()
    scale=image.devicePixelRatio(); width=int(header.sectionSize(0)*scale)
    background=APP.palette().color(QPalette.ColorRole.Window)
    # Interior of the first title section: excludes the bottom/right border,
    # selection outlines and sorting arrows, not the actual title glyphs.
    colors=[image.pixelColor(x,y) for x in range(12,width-16)
        for y in range(6,image.height()-10)]
    assert max(contrast(color,background) for color in colors)>=4.5


def test_older_qt_without_native_scheme_setter_keeps_working_palette_theme(window,monkeypatch):
    from types import SimpleNamespace
    original=APP.styleHints
    monkeypatch.setattr(APP,"styleHints",lambda:SimpleNamespace())
    try:
        switch(window,"Dark")
        assert sidebar_pixel(window)=="#24272b"
        assert window.queue_table.palette().color(QPalette.ColorRole.Base).name()=="#292c31"
    finally: monkeypatch.setattr(APP,"styleHints",original)


def test_existing_and_new_popup_menus_are_dark_and_restore_light(window):
    existing=QMenu(window); existing.addAction("Synthetic action"); existing.addAction("Unavailable").setEnabled(False)
    switch(window,"Dark"); fresh=QMenu(window); fresh.addAction("Synthetic action")
    try:
        for menu in (existing,fresh):
            menu.setMinimumWidth(240); menu.popup(window.mapToGlobal(QPoint(200,100))); APP.processEvents()
            image=menu.grab().toImage()
            assert luminance(image.pixelColor(image.width()-12,image.height()//2))<.2
            assert contrast(menu.palette().color(QPalette.ColorRole.Text),menu.palette().color(QPalette.ColorRole.Window))>=4.5
            menu.hide()
        switch(window,"Light")
        assert contrast(existing.palette().color(QPalette.ColorRole.Text),existing.palette().color(QPalette.ColorRole.Window))>=4.5
    finally: existing.close(); fresh.close()


def test_theme_switch_preserves_uuid_selection_focus_and_navigation_shortcuts(window):
    selected=[job.id for job in window._selected_jobs()]; assert len(selected)==1
    # Synthetic key delivery needs Qt's active-window context, not permission to
    # bring this test process ahead of the user's foreground macOS application.
    APP.setActiveWindow(window)
    window.queue_search.setFocus(); APP.processEvents()
    assert window.focusWidget() is window.queue_search
    switch(window,"Dark")
    assert [job.id for job in window._selected_jobs()]==selected
    assert window.focusWidget() is window.queue_search
    APP.setActiveWindow(window)
    QTest.keyClick(window,Qt.Key.Key_5,Qt.KeyboardModifier.MetaModifier); APP.processEvents()
    assert window.tabs.currentWidget() is window.settings_panel
    switch(window,"Light")
    APP.setActiveWindow(window)
    QTest.keyClick(window,Qt.Key.Key_2,Qt.KeyboardModifier.MetaModifier); APP.processEvents()
    assert window.tabs.currentIndex()==1 and [job.id for job in window._selected_jobs()]==selected


def test_status_messages_keep_meaning_and_readable_colors_through_theme_changes(window):
    from morgan_media_downloader.provider import ProviderStatus
    cases=[(window.connection_status,lambda:window._connection_test_ready(("available","Synthetic ready")),"success"),
        (window.connection_status,lambda:window._connection_test_ready(("unavailable","Synthetic failure")),"error"),
        (window.provider_label,lambda:window._provider_status_ready(ProviderStatus("available","Synthetic available","script")),"success"),
        (window.provider_label,lambda:window._provider_status_ready(ProviderStatus("not_running","Synthetic missing","http")),"warning"),
        (window.provider_label,lambda:window._provider_status_ready(ProviderStatus("error","Synthetic failure","http")),"error")]
    for label,update,tone in cases:
        update(); APP.processEvents(); text=label.text(); detail=label.toolTip()
        for mode in ("Light","Dark","System"):
            switch(window,mode)
            foreground=label.palette().color(QPalette.ColorRole.WindowText); background=APP.palette().color(QPalette.ColorRole.Window)
            assert contrast(foreground,background)>=4.5
            if tone=="success": assert foreground.green()>foreground.red()
            elif tone=="error": assert foreground.red()>foreground.green()
            else: assert foreground.red()>=foreground.green()>foreground.blue()
            assert label.text()==text and label.toolTip()==detail and window.task_manager.active_count==0


def test_status_labels_follow_late_custom_system_palette_with_contrast_fallback(window):
    switch(window,"System")
    for background in ("#808080","#102030","#ffffff"):
        native=QPalette(APP.palette())
        native.setColor(QPalette.ColorRole.Window,QColor(background))
        native.setColor(QPalette.ColorRole.WindowText,QColor(background))  # Deliberately unreadable custom text.
        window._connection_test_ready(("unavailable","Synthetic connection failure"))
        APP.setPalette(native); APP.processEvents()
        assert "Synthetic connection failure" in window.connection_status.text()
        assert contrast(window.connection_status.palette().color(QPalette.ColorRole.WindowText),QColor(background))>=4.5
        disabled=window.stop_queue_batch.palette().color(QPalette.ColorGroup.Disabled,QPalette.ColorRole.ButtonText)
        assert contrast(disabled,QColor(background))>=3
