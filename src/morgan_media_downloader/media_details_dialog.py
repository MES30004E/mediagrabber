"""Per-item stream/subtitle choices from a credential-free inspection summary."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from .subtitle_mux import friendly_language, parse_subtitle_languages


class MediaDetailsDialog(QDialog):
    def __init__(self, title, details, defaults, overrides, on_apply, parent=None):
        super().__init__(parent)
        self.details, self.on_apply = details, on_apply
        self.setWindowTitle("Video formats, audio and subtitles"); self.resize(850, 700)
        outer = QVBoxLayout(self)
        heading = QLabel(title); heading.setTextFormat(Qt.TextFormat.PlainText); heading.setWordWrap(True)
        outer.addWidget(heading)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setTextFormat(Qt.TextFormat.PlainText)
        original = sorted({f["language"] for f in details["formats"] if f["original"] and f["language"]})
        default = sorted({f["language"] for f in details["formats"] if f["default"] and f["language"]})
        describe = lambda codes: ", ".join(friendly_language(code) for code in codes) or "Not reported"
        label = QLabel(f"Reported media language: {describe([details['language']] if details['language'] else [])}\n"
                       f"Original audio: {describe(original)} · Default audio: {describe(default)}\n"
                       "Inspection is a snapshot, not a download guarantee. Selected stream IDs are revalidated before transfer.")
        label.setWordWrap(True); label.setTextFormat(Qt.TextFormat.PlainText); outer.addWidget(label)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); body = QWidget(); content = QVBoxLayout(body)
        self.formats = QTableWidget(len(details["formats"]), 7)
        self.formats.setHorizontalHeaderLabels(["ID", "Media", "Height", "Codecs", "Language", "Extractor labels", "kb/s"])
        self.formats.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.formats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.formats.horizontalHeader().setStretchLastSection(True); self.formats.setMinimumHeight(150); self.formats.setMaximumHeight(230)
        self.video_choice = QComboBox(); self.video_choice.addItem("Follow batch quality / compatibility", "")
        self.audio_choice = QComboBox(); self.audio_choice.addItem("Automatic audio for this video", "")
        self._formats = {f["id"]: f for f in details["formats"]}
        for row, value in enumerate(details["formats"]):
            media = "Video + audio" if value["video"] and value["audio"] else "Video" if value["video"] else "Audio" if value["audio"] else "Unknown"
            if value["extension"]: media += f" · {value['extension']}"
            language = friendly_language(value["language"]) if value["language"] else "Not reported"
            flags = ", ".join(name for key, name in (("original", "Original"), ("default", "Default")) if value[key])
            height = f"{value['height']}p" if value["height"] else "—"
            bitrate = str(value["bitrate"]) if value["bitrate"] is not None else "—"
            for column, text in enumerate((value["id"], media, height, f"{value['video_codec']} / {value['audio_codec']}", language, flags, bitrate)):
                self.formats.setItem(row, column, QTableWidgetItem(text))
            description = f"{value['id']} · {height if value['video'] else value['audio_codec']} · {language} {flags} · {bitrate} kb/s".strip()
            if value["video"]: self.video_choice.addItem(description + (" · includes audio" if value["audio"] else ""), value["id"])
            elif value["audio"]: self.audio_choice.addItem(description, value["id"])
        content.addWidget(self.formats)
        if details.get("formats_truncated"): content.addWidget(QLabel("Only the first 2,000 reported formats are shown; narrow inspection support is limited for this item."))
        form = QFormLayout(); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.subtitle_source = QComboBox(); self.subtitle_source.addItems(["Normal subtitles", "Normal + automatic captions", "Automatic captions only"])
        self.subtitle_source.setCurrentText(overrides.get("subtitle_source", defaults.subtitle_source))
        self.subtitle_languages = QListWidget(); self.subtitle_languages.setMaximumHeight(120)
        self.write_subtitles = QCheckBox("Keep external subtitle files"); self.embed_subtitles = QCheckBox("Embed subtitles")
        self.write_subtitles.setChecked(overrides.get("write_subtitles", defaults.write_subtitles))
        self.embed_subtitles.setChecked(overrides.get("embed_subtitles", defaults.embed_subtitles))
        self._initial_languages = parse_subtitle_languages(overrides.get("subtitle_language", defaults.subtitle_language))
        self._language_choices = {}
        self.subtitle_source.currentTextChanged.connect(self._refresh_languages); self._refresh_languages()
        form.addRow("Video stream", self.video_choice); form.addRow("Audio track / language", self.audio_choice)
        form.addRow("Subtitle source", self.subtitle_source); form.addRow("Reported subtitle languages", self.subtitle_languages)
        form.addRow(self.write_subtitles); form.addRow(self.embed_subtitles); content.addLayout(form)
        for combo, key in ((self.video_choice, "video_format_id"), (self.audio_choice, "audio_format_id")):
            index = combo.findData(overrides.get(key, ""))
            if index < 0:
                combo.insertItem(0, "Previous selection no longer reported — choose again", None); index = 0
            combo.setCurrentIndex(index)
        self.video_choice.currentIndexChanged.connect(self._video_changed); self._video_changed()
        self.video_choice.setEnabled(self.video_choice.count() > 1 and defaults.audio_format == "Original/best audio")
        if defaults.audio_format != "Original/best audio": self.video_choice.setCurrentIndex(0)
        scroll.setWidget(body); outer.addWidget(scroll, 1); outer.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Apply to this item")
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        reset = QPushButton("Use batch defaults"); self.buttons.addButton(reset, QDialogButtonBox.ButtonRole.ResetRole)
        reset.clicked.connect(self._reset); outer.addWidget(self.buttons)

    def _video_changed(self, *_):
        value = self._formats.get(self.video_choice.currentData(), {})
        allowed = not value.get("audio") and self.audio_choice.count() > 1
        if not allowed: self.audio_choice.setCurrentIndex(self.audio_choice.findData(""))
        self.audio_choice.setEnabled(allowed)

    def _refresh_languages(self, *_):
        for index in range(self.subtitle_languages.count()):
            item = self.subtitle_languages.item(index)
            self._language_choices[item.data(Qt.ItemDataRole.UserRole)] = item.checkState() == Qt.CheckState.Checked
        self.subtitle_languages.clear()
        source = self.subtitle_source.currentText()
        languages = set(self.details["manual_subtitles"] if source != "Automatic captions only" else [])
        if source != "Normal subtitles": languages.update(self.details["automatic_subtitles"])
        for code in sorted(languages):
            item = QListWidgetItem(friendly_language(code)); item.setData(Qt.ItemDataRole.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = self._language_choices.get(code, code in self._initial_languages or "all" in self._initial_languages)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.subtitle_languages.addItem(item)
        for control in (self.subtitle_languages, self.embed_subtitles, self.write_subtitles): control.setEnabled(bool(languages))
        if not languages: self.embed_subtitles.setChecked(False); self.write_subtitles.setChecked(False)

    def _save(self):
        if self.video_choice.currentData() is None or self.audio_choice.currentData() is None:
            self.status.setText("A previous stream is no longer reported. Choose a replacement or Use batch defaults."); return
        languages = [self.subtitle_languages.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.subtitle_languages.count())
                     if self.subtitle_languages.item(i).checkState() == Qt.CheckState.Checked]
        if (self.write_subtitles.isChecked() or self.embed_subtitles.isChecked()) and not languages:
            self.status.setText("Select at least one reported subtitle language, or turn subtitle output off."); return
        values = {"video_format_id": self.video_choice.currentData(), "audio_format_id": self.audio_choice.currentData(),
                  "subtitle_source": self.subtitle_source.currentText(), "subtitle_language": ",".join(languages),
                  "write_subtitles": self.write_subtitles.isChecked(), "embed_subtitles": self.embed_subtitles.isChecked()}
        try: self.on_apply(values)
        except ValueError: self.status.setText("The source changed. Inspect the current selection again before applying."); return
        self.accept()

    def _reset(self):
        try: self.on_apply(None)
        except ValueError: self.status.setText("The source changed. Inspect the current selection again before applying."); return
        self.accept()
