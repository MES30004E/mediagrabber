from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from morgan_media_downloader.models import MediaItem, DownloadOptions
from test_ui_diagnostics import _window
from test_playlist_workspace import _populate
from test_media_details import metadata

APP = QApplication.instance() or QApplication([])


def test_explicit_inspection_is_one_authenticated_request_and_choices_reach_only_that_job(tmp_path, monkeypatch):
    from morgan_media_downloader.media_details import details_from_info
    window = _window(tmp_path, monkeypatch); tasks = []; calls = []
    monkeypatch.setattr(window.task_manager, "start", lambda kind, fn, **kw: tasks.append((fn, kw)) if kind == "media-inspection" else None)
    def inspect(*args, **kwargs):
        calls.append((args, kwargs))
        return [MediaItem(args[0], "Inspected", inspection=details_from_info(metadata()))], "None"
    monkeypatch.setattr("morgan_media_downloader.ui.analyse_with_authentication", inspect)
    monkeypatch.setattr(window, "_proxy", lambda: "socks5h://127.0.0.1:9911")
    try:
        window.settings.authentication_mode = "None"
        _populate(window, [MediaItem(f"https://example.test/{i}", f"Track {i}") for i in range(828)])
        window.item_table.setCurrentCell(827, 2)
        assert not tasks and not calls
        window.inspect_button.click(); assert len(tasks) == 1
        fn, callbacks = tasks[-1]; callbacks["on_result"](fn(None, None)); callbacks["on_finished"]()
        assert calls[0][0][0] == "https://example.test/827" and calls[0][0][1].startswith("socks5h:")
        assert calls[0][0][4] == "None" and calls[0][1]["single_video"] is True
        dialog = window.media_details_dialog
        dialog.video_choice.setCurrentIndex(dialog.video_choice.findData("v1080"))
        dialog.audio_choice.setCurrentIndex(dialog.audio_choice.findData("a-ja"))
        dialog.subtitle_source.setCurrentText("Automatic captions only")
        dialog.subtitle_languages.item(0).setCheckState(Qt.CheckState.Checked)
        dialog.write_subtitles.setChecked(True)
        dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
        window._select_items(False)
        for row in (0, 827): window.item_table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        window.enqueue_selected()
        jobs = {job.item.source_url: job for job in window.jobs.values()}
        assert jobs["https://example.test/827"].options.audio_format_id == "a-ja"
        assert jobs["https://example.test/827"].options.video_format_id == "v1080"
        assert jobs["https://example.test/827"].options.subtitle_language == "ja"
        assert jobs["https://example.test/827"].options.write_subtitles
        assert jobs["https://example.test/0"].options.audio_format_id == ""
        assert not jobs["https://example.test/0"].options.write_subtitles
        restored = {job.item.source_url: job for job in window.database.load_jobs()}
        assert restored["https://example.test/827"].options.audio_format_id == "a-ja"
        assert restored["https://example.test/827"].options.subtitle_language == "ja"
    finally: window.close(); APP.processEvents()


def test_old_inspection_result_cannot_attach_to_new_analysis(tmp_path, monkeypatch):
    from morgan_media_downloader.media_details import details_from_info
    window = _window(tmp_path, monkeypatch); tasks = []
    monkeypatch.setattr(window.task_manager, "start", lambda kind, fn, **kw: tasks.append((fn, kw)) if kind == "media-inspection" else None)
    monkeypatch.setattr("morgan_media_downloader.ui.analyse_with_authentication", lambda *args, **kw: ([MediaItem("https://example.test/a", "Old", inspection=details_from_info(metadata()))], "None"))
    try:
        _populate(window, [MediaItem("https://example.test/a", "Old")])
        window.inspect_button.click(); fn, callbacks = tasks[-1]
        _populate(window, [MediaItem("https://example.test/new", "New")])
        callbacks["on_result"](fn(None, None)); callbacks["on_finished"]()
        assert getattr(window, "media_details_dialog", None) is None
        assert window.items[0].inspection == {}
    finally: window.close(); APP.processEvents()


def test_dialog_exposes_only_reported_subtitle_languages_and_cancel_preserves_defaults(tmp_path):
    from morgan_media_downloader.media_details_dialog import MediaDetailsDialog
    from morgan_media_downloader.media_details import details_from_info
    saved = []
    dialog = MediaDetailsDialog("Synthetic", details_from_info(metadata()), DownloadOptions(subtitle_language="fr"), {}, saved.append)
    try:
        assert dialog.subtitle_languages.count() == 1
        assert dialog.subtitle_languages.item(0).data(Qt.ItemDataRole.UserRole) == "en"
        assert dialog.subtitle_languages.item(0).checkState() == Qt.CheckState.Unchecked
        dialog.audio_choice.setCurrentIndex(dialog.audio_choice.findData("a-ja"))
        dialog.reject()
        assert not saved
    finally: dialog.close(); APP.processEvents()


def test_cleared_subtitle_choices_stay_cleared_across_source_switches():
    from morgan_media_downloader.media_details_dialog import MediaDetailsDialog
    from morgan_media_downloader.media_details import details_from_info
    dialog = MediaDetailsDialog("Synthetic", details_from_info(metadata()), DownloadOptions(subtitle_language="en"), {}, lambda *_: None)
    try:
        dialog.subtitle_languages.item(0).setCheckState(Qt.CheckState.Unchecked)
        dialog.subtitle_source.setCurrentText("Automatic captions only")
        dialog.subtitle_source.setCurrentText("Normal subtitles")
        assert dialog.subtitle_languages.item(0).checkState() == Qt.CheckState.Unchecked
    finally: dialog.close(); APP.processEvents()


def test_unavailable_prior_stream_requires_an_explicit_replacement_or_reset():
    from morgan_media_downloader.media_details_dialog import MediaDetailsDialog
    from morgan_media_downloader.media_details import details_from_info
    saved = []
    dialog = MediaDetailsDialog("Synthetic", details_from_info(metadata()), DownloadOptions(), {"audio_format_id": "gone"}, saved.append)
    try:
        dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
        assert not saved, "A vanished override cannot silently become automatic audio on Apply"
        assert "reported" in dialog.status.text().lower()
        dialog.audio_choice.setCurrentIndex(dialog.audio_choice.findData("a-ja"))
        dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
        assert saved[-1]["audio_format_id"] == "a-ja"
    finally: dialog.close(); APP.processEvents()


def test_open_dialog_cannot_apply_after_runtime_changes(tmp_path, monkeypatch):
    from morgan_media_downloader.media_details import details_from_info
    from morgan_media_downloader.yt_runtime import RuntimeSnapshot
    window = _window(tmp_path, monkeypatch)
    try:
        _populate(window, [MediaItem("https://example.test/a", "Synthetic")])
        item = window.items[0]; runtime = window.runtime_manager.snapshot()
        window._inspection_ready((window._inspection_generation, item, runtime.version, runtime.source, details_from_info(metadata()), "None", ""))
        dialog = window.media_details_dialog
        dialog.audio_choice.setCurrentIndex(dialog.audio_choice.findData("a-ja"))
        monkeypatch.setattr(window.runtime_manager, "snapshot", lambda: RuntimeSnapshot("different", "Bundled", object))
        dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).click()
        assert not window._item_overrides
        assert "changed" in dialog.status.text()
    finally: window.close(); APP.processEvents()


def test_long_stream_identifiers_do_not_force_dialog_off_screen():
    from morgan_media_downloader.media_details_dialog import MediaDetailsDialog
    from morgan_media_downloader.media_details import details_from_info
    value = metadata(); value["formats"][0]["format_id"] = "v" * 128
    dialog = MediaDetailsDialog("Synthetic", details_from_info(value), DownloadOptions(), {}, lambda *_: None)
    try:
        dialog.resize(720, 520); dialog.show(); APP.processEvents()
        assert dialog.width() <= 740
        apply = dialog.buttons.button(QDialogButtonBox.StandardButton.Apply)
        assert apply.mapTo(dialog, apply.rect().bottomRight()).y() < dialog.height()
    finally: dialog.close(); APP.processEvents()


def test_reset_explicitly_returns_item_to_following_batch_defaults():
    from morgan_media_downloader.media_details_dialog import MediaDetailsDialog
    from morgan_media_downloader.media_details import details_from_info
    saved = []
    dialog = MediaDetailsDialog("Synthetic", details_from_info(metadata()), DownloadOptions(), {"audio_format_id": "a-ja"}, saved.append)
    try:
        dialog._reset()
        assert saved == [None]
    finally: dialog.close(); APP.processEvents()
