from __future__ import annotations

import copy
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt, QUrl, Slot, QEvent
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QToolButton, QVBoxLayout, QWidget, QScrollArea, QLayout,
)

from .database import Database
from .console import ConsoleEvent, ConsoleStore
from .diagnostics import run_checks
from .downloader import analyse_with_authentication, download_job
from .file_ownership import (delete_owned_files, delete_restart_state, owned_paths,
                             prepare_resumable_job, primary_output)
from .keychain import load_proxy_password, save_proxy_password
from .job_diagnostics import diagnostics_text, status_summary
from .local_converter import (
    AUDIO_BITRATES, AUDIO_CODECS, CONTAINERS, FRAME_RATES, PROFILES, QUALITY_LEVELS,
    RESOLUTIONS, SUBTITLE_MODES, VIDEO_CODECS, ConversionOptions, analyse_local_video,
    build_conversion_plan, convert_local_video, default_conversion_output,
    detect_ffmpeg_encoders, format_analysis, output_with_container, preset_options,
)
from .managed_tor import ManagedTor
from .models import DownloadJob, DownloadOptions, JobStatus, MediaItem
from .media_details import language_code
from .network import ProxyConfig, classify_tor_target, detect_tor, managed_tor_health, test_tor_connection, tor_exit_ip
from .network import test_media_connection
from .organisation import organised_folder
from .parsing import input_kind, split_input
from .paths import application_support_dir, logs_dir
from .provider import check_provider
from .settings import AppSettings, SettingsStore
from .settings_window import SettingsWindow
from .tasks import TaskManager
from .thumbnail_cache import fetch_thumbnail
from .subtitle_mux import friendly_language
from .torrent import (TORRENT_TOR_ERROR, TorrentMetadata, analyse_torrent, download_torrent,
                      fetch_magnet_metadata, validate_torrent_connection)
from .yt_runtime import RuntimeSnapshot, YtDlpRuntimeManager, get_runtime_manager
from .ui_components import NavigationShell, page_heading, polish_table, DisclosureSection, MediaSelectionTable
from .theme import apply_theme
from .auth import connection_failure, requires_authentication


def human_bytes(value: float | int) -> str:
    amount = float(value or 0)
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if abs(amount) < 1024 or suffix == "TB":
            return f"{amount:.1f} {suffix}"
        amount /= 1024
    return "0 B"


def human_duration(value: float | int | None) -> str:
    if value is None:
        return "—"
    seconds = int(value)
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02d}"


def reconcile_stuck_job(job: DownloadJob, *, now: float | None = None, timeout: float = 15.0) -> bool:
    """Fail a zero-byte zombie state while leaving genuine extractor/transfer work alone."""
    if job.status != JobStatus.DOWNLOADING: return False
    if job.metadata_success or job.formats_playable or job.downloaded_bytes: return False
    if job.active_extractor_task:
        job.status = JobStatus.ANALYSING; job.postprocessing_stage = "Resolving media"; return True
    if job.active_transfer_task or job.active_postprocess_task: return False
    current = now if now is not None else time.time()
    since = job.last_progress_timestamp or job.last_state_transition or 0.0
    if since and current - since < timeout: return False
    job.status = JobStatus.FAILED; job.failure_stage = "Format resolution"
    job.failure_code = "Extractor returned no media"
    job.error = "No playable media was found and no extractor or transfer task remained active."
    job.postprocessing_stage = "Failed — Extractor returned no media"
    job.active_extractor_task = job.active_transfer_task = job.active_postprocess_task = False
    return True


class DropInput(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setPlaceholderText("Paste URLs or search terms here — one per line")
        self.setMaximumHeight(92)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
            self._drop_feedback(True)

    def _drop_feedback(self, active):
        self.setProperty("dropActive", active)
        self.style().unpolish(self); self.style().polish(self)

    def dragLeaveEvent(self, event):
        self._drop_feedback(False); event.accept()

    def dropEvent(self, event):
        self._drop_feedback(False)
        urls = [url.toLocalFile() if url.isLocalFile() else url.toString() for url in event.mimeData().urls()]
        self.insertPlainText("\n".join(urls) if urls else event.mimeData().text())
        event.acceptProposedAction()


@dataclass
class AnalysisContext:
    analysis_id: str
    original_input: str
    purpose: str
    options: DownloadOptions
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    input_types: tuple[str, ...] = ()


def _analysis_operation(values: list[str], proxy: str | None, settings: AppSettings,
                        runtime: RuntimeSnapshot, context: AnalysisContext,
                        cancel_event: threading.Event, progress: Callable[[object], None]) -> dict[str, Any]:
    result: list[MediaItem] = []
    torrent = None
    effective_auth: list[str] = []
    for value in values:
        if cancel_event.is_set():
            break
        kind = input_kind(value)
        progress("Fetching torrent metadata…" if kind == "torrent" else
                 "Matching Spotify track…" if kind == "spotify" else
                 "Searching…" if kind == "search" else "Fetching metadata…")
        if kind == "torrent":
            torrent = (fetch_magnet_metadata(value, settings.aria2c_path)
                       if value.lower().startswith("magnet:?") else analyse_torrent(value))
            result.extend(torrent.media_items())
        else:
            items, used_auth = analyse_with_authentication(
                value, proxy, settings.provider_base_url, settings.provider_server_home,
                settings.authentication_mode, settings.cookies_browser, settings.browser_profile,
                settings.cookies_file, runtime, lambda message: progress(message))
            result.extend(items); effective_auth.append(used_auth)
    return {"items": result, "torrent": torrent, "context": context, "authentication": effective_auth}


def _media_download_operation(job: DownloadJob, proxy: str | None, settings: AppSettings,
                              runtime: RuntimeSnapshot, cancel_event: threading.Event,
                              progress: Callable[[object], None], managed_tor: ManagedTor | None = None) -> DownloadJob:
    owned = copy.deepcopy(job)
    circuit = None
    if managed_tor is not None:
        circuit = lambda current, attempt: _rotate_managed_tor(managed_tor, runtime)
    return download_job(owned, proxy, settings.provider_base_url, settings.provider_server_home,
                        lambda value: progress(copy.deepcopy(value)), cancel_event, runtime,
                        lambda category, message, level: progress({"console": (category, message, level),
                                                                   "job_id": owned.id}), circuit)


def _rotate_managed_tor(tor: ManagedTor, runtime: RuntimeSnapshot) -> dict[str, object]:
    health, detail = managed_tor_health(tor, runtime)
    if health != "internet_working": raise RuntimeError(f"Managed Tor health check failed: {detail}")
    previous = tor_exit_ip(tor.proxy_url or "", runtime)
    result = tor.request_new_circuit()
    health, detail = managed_tor_health(tor, runtime)
    if health != "internet_working": raise RuntimeError(f"Managed Tor health check failed after NEWNYM: {detail}")
    current = tor_exit_ip(tor.proxy_url or "", runtime)
    changed = bool(previous and current and previous != current)
    tor.previous_exit_ip = previous; tor.current_exit_ip = current; tor.circuit_changed = changed
    return {**result, "previous_exit_ip": previous, "current_exit_ip": current, "changed": changed}


def _managed_tor_diagnostics(tor: ManagedTor, runtime: RuntimeSnapshot) -> tuple[str, str, str]:
    state, detail = managed_tor_health(tor, runtime)
    address = tor_exit_ip(tor.proxy_url or "", runtime) if state == "internet_working" else ""
    if address: tor.current_exit_ip = address
    return state, detail, address


def _torrent_download_operation(job: DownloadJob, settings: AppSettings,
                                cancel_event: threading.Event,
                                progress: Callable[[object], None]) -> DownloadJob:
    owned = copy.deepcopy(job)
    return download_torrent(owned, settings, lambda value: progress(copy.deepcopy(value)), cancel_event)


def _wait_for_tor_operation(tor: ManagedTor, payload: object, cancel_event: threading.Event,
                            progress: Callable[[object], None]) -> object:
    progress("Waiting for Managed Tor to reach bootstrap 100%…")
    while not cancel_event.wait(0.2):
        if tor.state == "Connected":
            return payload
        if tor.state == "Failed":
            raise ConnectionError(tor.last_error or "Managed Tor failed to start")
    return payload


class SetupDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None, runtime_manager: YtDlpRuntimeManager | None = None,
                 results=None):
        super().__init__(parent)
        self.setWindowTitle("First-run check")
        self.resize(860, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Morgan Media Downloader checked the local components it can use. Optional components may be configured later."))
        table = QTableWidget(0, 3); table.setHorizontalHeaderLabels(["Component", "Status", "Details"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setTextElideMode(Qt.TextElideMode.ElideNone)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for result in (results if results is not None else run_checks(settings, runtime_manager)):
            row = table.rowCount(); table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(result.name))
            status = QTableWidgetItem(result.status or ("Available" if result.available else "Not available"))
            status.setText("● " + status.text()); status.setForeground(Qt.GlobalColor.darkGreen if result.available else Qt.GlobalColor.darkYellow)
            table.setItem(row, 1, status)
            table.setItem(row, 2, QTableWidgetItem(result.detail))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept); layout.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self, runtime_manager: YtDlpRuntimeManager | None = None):
        super().__init__()
        self.runtime_manager = runtime_manager or get_runtime_manager()
        if not self.runtime_manager.initialized: self.runtime_manager.initialize()
        self.settings_store = SettingsStore(); self.settings = self.settings_store.load()
        self.database = Database(); self.items: list[MediaItem] = []
        self._item_overrides: dict[int, dict] = {}
        self._inspection_generation = 0
        self._inspection_busy = False
        self.media_details_dialog = None
        self.torrent_context: TorrentMetadata | None = None
        self.jobs = {job.id: job for job in self.database.load_jobs()}
        self.task_manager = TaskManager(self)
        self.console_store = ConsoleStore(parent=self)
        self.console_job_filter = ""
        self.selected_job_id = ""
        self.details_dialog: QDialog | None = None
        self.details_dialog_text: QPlainTextEdit | None = None
        self.active: dict[str, str] = {}
        self.analysis_task_id = ""
        self.analysis_contexts: dict[str, AnalysisContext] = {}
        self.displayed_input = ""
        self.analysis_stale = False
        self._closing = False
        self.pending_restarts: dict[str, str] = {}
        self.pending_removals: dict[str, bool] = {}
        self.proxy_passwords: dict[str, str] = {}
        self.external_tor_port: int | None = None
        self.tor_internet_state = "unknown"
        self.managed_tor = ManagedTor(self.settings.tor_browser_path)
        self.clean_marker = application_support_dir() / "running.marker"
        self.previous_crash = self.clean_marker.exists()
        self.clean_marker.write_text(str(os.getpid()), encoding="utf-8")
        self.setWindowTitle("Morgan Media Downloader")
        self.setWindowFlag(Qt.WindowType.WindowFullscreenButtonHint, True)
        self.setMinimumSize(900, 650)
        if self.settings.remember_window_size: self.resize(self.settings.window_width, self.settings.window_height)
        else: self.resize(1180, 760)
        if self.settings.remember_window_position and self.settings.window_x is not None and self.settings.window_y is not None:
            self.move(self.settings.window_x, self.settings.window_y)
        self.setAcceptDrops(True)
        self._build_ui(); self._build_menu(); self._apply_theme(); self._refresh_queue(); self._refresh_history()
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._system_appearance_changed)
        self.console_store.append("APP", "Morgan Media Downloader started")
        self.dispatch_timer = QTimer(self); self.dispatch_timer.timeout.connect(self._dispatch); self.dispatch_timer.start(500)
        self.watchdog_timer = QTimer(self); self.watchdog_timer.timeout.connect(self._watchdog_jobs); self.watchdog_timer.start(2000)
        self.connection_timer = QTimer(self); self.connection_timer.timeout.connect(self._refresh_connection_status); self.connection_timer.start(500)
        self.clipboard_timer = QTimer(self); self.clipboard_timer.timeout.connect(self._check_clipboard); self.clipboard_timer.start(1500)
        self.startup_timer = QTimer(self); self.startup_timer.setSingleShot(True); self.startup_timer.timeout.connect(self._start_yt_dlp_update_check)
        if self.settings.yt_dlp_check_updates_on_startup:
            self.startup_timer.start(250)
        self.diagnostics_timer = QTimer(self); self.diagnostics_timer.setSingleShot(True); self.diagnostics_timer.timeout.connect(self._initial_checks); self.diagnostics_timer.start(150)
        if self.settings.connection_mode == "Managed Tor" and self.settings.managed_tor_auto_start:
            self.tor_start_timer = QTimer(self); self.tor_start_timer.setSingleShot(True); self.tor_start_timer.timeout.connect(self.managed_tor.start); self.tor_start_timer.start(300)
        if self.settings_store.last_warning:
            self.settings_warning_timer = QTimer(self); self.settings_warning_timer.setSingleShot(True); self.settings_warning_timer.timeout.connect(self._show_settings_warning); self.settings_warning_timer.start(400)

    def _build_ui(self):
        self.tabs = NavigationShell(); self.setCentralWidget(self.tabs)
        download_tab = QWidget(); outer = QVBoxLayout(download_tab)
        outer.setContentsMargins(22, 14, 22, 12); outer.setSpacing(6)
        self.banner = QWidget(); banner_row = QHBoxLayout(self.banner); banner_row.setContentsMargins(8, 4, 8, 4)
        self.banner_text = QLabel(); self.banner_analyse = QPushButton("Analyse"); self.banner_download = QPushButton("Download"); self.banner_dismiss = QPushButton("Dismiss")
        banner_row.addWidget(self.banner_text, 1); banner_row.addWidget(self.banner_analyse); banner_row.addWidget(self.banner_download); banner_row.addWidget(self.banner_dismiss)
        self.banner_analyse.clicked.connect(self._use_banner_analyse); self.banner_download.clicked.connect(self._use_banner_download); self.banner_dismiss.clicked.connect(self.banner.hide)
        self.banner.setStyleSheet("background: palette(alternate-base); border-radius: 6px;")
        self.banner.hide(); outer.addWidget(self.banner)
        if self.previous_crash:
            self.banner_text.setText("Morgan Media Downloader did not close normally last time.")
            self.banner_analyse.setText("Open Logs"); self.banner_download.hide(); self.banner.show()
        top = QHBoxLayout(); self.input = DropInput(); self.analyse_button = QPushButton("Analyse"); self.download_button = QPushButton("Download")
        self.input.setAccessibleName("Media URLs or search terms"); self.input.setMaximumHeight(54)
        self.input.setToolTip("Paste links or search terms, then Analyse to review playlist entries before downloading.")
        self.download_button.setProperty("primary", True)
        self.download_button.setToolTip("Analyse and download using the current options; review Spotify matches with Analyse first.")
        self.analyse_button.setDefault(True); self.analyse_button.clicked.connect(self.analyse)
        self.download_button.clicked.connect(self.download_input); self.input.textChanged.connect(self._input_changed)
        top.addWidget(self.input, 1); top.addWidget(self.analyse_button); top.addWidget(self.download_button)
        outer.addLayout(top)
        connection_row = QHBoxLayout(); connection_row.addWidget(QLabel("Connection:"))
        self.connection_selector = QComboBox(); self.connection_selector.addItems(["Direct / Normal Network", "System / Proton VPN", "Managed Tor", "External Tor", "Custom HTTP Proxy", "Custom SOCKS5 Proxy"]); self.connection_selector.setCurrentText(self.settings.connection_mode)
        self.connection_selector.setToolTip("Use the Mac's normal network connection.")
        self.connection_selector.currentTextChanged.connect(self._connection_changed)
        self.connection_status = QLabel("● Ready"); self.connection_test = QPushButton("Test"); self.connection_test.clicked.connect(self._test_connection)
        self.account_button = QPushButton("YouTube Account…"); self.account_button.clicked.connect(self.show_youtube_account)
        connection_row.addWidget(self.connection_selector); connection_row.addWidget(self.connection_status); connection_row.addWidget(self.connection_test); connection_row.addStretch(); connection_row.addWidget(self.account_button); outer.addLayout(connection_row)
        self.analysis_progress = QProgressBar(); self.analysis_progress.setRange(0, 0); self.analysis_progress.hide(); outer.addWidget(self.analysis_progress)
        self.summary = QLabel("Enter a supported URL or search terms."); self.summary.setWordWrap(True); outer.addWidget(self.summary)
        self.analysis_diagnostics = QPushButton("View diagnostic details…"); self.analysis_diagnostics.clicked.connect(self._show_analysis_diagnostics)
        self.analysis_diagnostics.hide(); outer.addWidget(self.analysis_diagnostics, 0, Qt.AlignmentFlag.AlignLeft)
        self._analysis_error_details = ""
        self.preview_section = DisclosureSection("Media Preview", self.settings.playlist_preview_expanded)
        preview = self.preview_section
        preview_body = QWidget(); preview_layout = QHBoxLayout(preview_body)
        preview_scroll = QScrollArea(); preview_scroll.setWidgetResizable(True); preview_scroll.setWidget(preview_body)
        preview_scroll.setMinimumHeight(80)
        QVBoxLayout(preview.content).addWidget(preview_scroll)
        self.thumbnail = QLabel("No preview"); self.thumbnail.setFixedSize(160, 90); self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter); self.thumbnail.setStyleSheet("background: palette(midlight); border-radius: 6px;")
        self.preview_details = QLabel("Title\nChannel / artist\nDuration\nSource"); self.preview_details.setWordWrap(True)
        thumbnail_box = QVBoxLayout(); thumbnail_box.addWidget(self.thumbnail)
        self.thumbnail_progress = QProgressBar(); self.thumbnail_progress.setFixedWidth(160); self.thumbnail_progress.hide()
        thumbnail_box.addWidget(self.thumbnail_progress)
        preview_layout.addLayout(thumbnail_box); preview_layout.addWidget(self.preview_details, 1)
        self.playlist_filter = QLineEdit(); self.playlist_filter.setClearButtonEnabled(True)
        self.playlist_filter.setPlaceholderText("Filter analysed titles, artists or sources…")
        self.playlist_filter.setAccessibleName("Filter analysed playlist entries")
        self.playlist_filter.textChanged.connect(self._filter_playlist)
        filter_row = QWidget(); filter_layout = QHBoxLayout(filter_row); filter_layout.setContentsMargins(0, 0, 0, 0)
        self.inspect_button = QPushButton("Inspect Video…"); self.inspect_button.setEnabled(False)
        self.inspect_button.setToolTip("Load formats, audio languages and subtitles for the current row only")
        self.inspect_button.clicked.connect(self._inspect_current_video)
        filter_layout.addWidget(self.playlist_filter, 1); filter_layout.addWidget(self.inspect_button)
        outer.addWidget(filter_row)
        self.playlist_splitter = splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        self.item_table = MediaSelectionTable(0, 7)
        self.item_table.setMinimumHeight(180)
        self.item_table.setHorizontalHeaderLabels(["✓", "#", "Title", "Uploader / artist", "Duration", "Source", "Match"])
        self.item_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 38), (1, 42), (3, 154), (4, 80), (5, 95), (6, 65)):
            self.item_table.setColumnWidth(column, width)
        self.item_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.item_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.item_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.item_table.itemChanged.connect(self._update_selection_count)
        self.item_table.checksChanged.connect(self._update_selection_count)
        self.item_table.currentCellChanged.connect(self._preview_current_item)
        polish_table(self.item_table)
        self.item_table.verticalHeader().setDefaultSectionSize(32)
        splitter.addWidget(self.item_table)
        settings_box = QWidget(); grid = QGridLayout(settings_box)
        grid.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.quality = QComboBox(); self.quality.addItems(["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"]); self.quality.setCurrentText(self.settings.quality)
        self.compatibility = QComboBox(); self.compatibility.addItems(["macOS / QuickTime", "Universal", "Original / Best Available"]); self.compatibility.setCurrentText(self.settings.compatibility)
        self.container = QComboBox(); self.container.addItems(["Auto", "MP4", "MKV", "WebM"]); self.container.setCurrentText(self.settings.container)
        self.audio_format = QComboBox(); self.audio_format.addItems(["Original/best audio", "MP3", "M4A", "OPUS", "FLAC", "WAV"]); self.audio_format.setCurrentText(self.settings.audio_format)
        self.audio_bitrate = QComboBox(); self.audio_bitrate.addItems(["Auto", "128 kbps", "192 kbps", "256 kbps", "320 kbps"]); self.audio_bitrate.setCurrentText(self.settings.audio_bitrate)
        self.audio_language = QComboBox(); self.audio_language.addItem("Automatic / best available", ""); self.audio_language.setEnabled(False)
        self.audio_language.setToolTip("Only languages reported by inspected items appear. Required per video; unavailable languages fail that item. An explicit per-item audio stream overrides this batch requirement.")
        self.embed_thumb = QCheckBox("Embed thumbnail"); self.embed_thumb.setChecked(self.settings.embed_thumbnail)
        self.embed_meta = QCheckBox("Embed metadata"); self.embed_meta.setChecked(self.settings.embed_metadata)
        self.embed_chapters = QCheckBox("Embed chapters"); self.embed_chapters.setChecked(self.settings.embed_chapters)
        self.embed_subtitles = QCheckBox("Embed subtitles"); self.embed_subtitles.setChecked(self.settings.embed_subtitles)
        self.write_subtitles = QCheckBox("Keep external subtitle files"); self.write_subtitles.setChecked(self.settings.write_subtitles)
        self.keep_original = QCheckBox("Keep originals after conversion"); self.keep_original.setChecked(self.settings.keep_original)
        self.subtitle_language = QLineEdit(self.settings.subtitle_languages); self.subtitle_language.setMaximumWidth(120)
        self.subtitle_source = QComboBox(); self.subtitle_source.addItems(["Normal subtitles", "Normal + automatic captions", "Automatic captions only"]); self.subtitle_source.setCurrentText(self.settings.subtitle_source)
        self.verify_postprocessing = QCheckBox("Verify post-processing results"); self.verify_postprocessing.setChecked(self.settings.verify_postprocessing)
        self.folder = QLineEdit(self.settings.download_dir); choose = QPushButton("Choose Folder…"); choose.clicked.connect(self.choose_folder)
        self.template = QComboBox(); self.template.setEditable(True); self.template.addItems(["%(title)s.%(ext)s", "%(uploader)s - %(title)s.%(ext)s", "%(playlist_index)03d - %(title)s.%(ext)s"]); self.template.setCurrentText(self.settings.filename_template)
        grid.addWidget(QLabel("Compatibility"), 0, 0); grid.addWidget(self.compatibility, 0, 1); grid.addWidget(QLabel("Quality"), 0, 2); grid.addWidget(self.quality, 0, 3)
        self.more_options = QWidget(); more_grid = QGridLayout(self.more_options); more_grid.setContentsMargins(0, 0, 0, 0)
        for index, widget in enumerate([self.embed_thumb, self.embed_meta, self.embed_chapters, self.embed_subtitles, self.write_subtitles, self.keep_original]):
            more_grid.addWidget(widget, index // 2, index % 2)
        more_grid.addWidget(QLabel("Subtitle language"), 3, 0); more_grid.addWidget(self.subtitle_language, 3, 1)
        more_grid.addWidget(QLabel("Subtitle source"), 4, 0); more_grid.addWidget(self.subtitle_source, 4, 1)
        more_grid.addWidget(self.verify_postprocessing, 5, 0, 1, 2)
        more_grid.addWidget(QLabel("Filename"), 6, 0); more_grid.addWidget(self.template, 6, 1)
        more_grid.addWidget(QLabel("Container"), 7, 0); more_grid.addWidget(self.container, 7, 1)
        more_grid.addWidget(QLabel("Audio"), 8, 0); more_grid.addWidget(self.audio_format, 8, 1)
        more_grid.addWidget(QLabel("Bitrate"), 9, 0); more_grid.addWidget(self.audio_bitrate, 9, 1)
        more_grid.addWidget(QLabel("Required audio language"), 10, 0); more_grid.addWidget(self.audio_language, 10, 1)
        self.more_options.hide(); self.more_button = QToolButton(); self.more_button.setText("More Options ▾"); self.more_button.clicked.connect(self._toggle_more_options)
        grid.addWidget(QLabel("Folder"), 1, 0); grid.addWidget(self.folder, 1, 1, 1, 2); grid.addWidget(choose, 1, 3)
        grid.addWidget(self.more_button, 2, 0); grid.addWidget(self.more_options, 3, 0, 1, 4)
        self.options_section = DisclosureSection("Download Options · batch defaults", self.settings.playlist_options_expanded)
        options_layout = QVBoxLayout(self.options_section.content); options_layout.setContentsMargins(0, 0, 0, 0)
        options_scroll = QScrollArea(); options_scroll.setWidgetResizable(True); options_scroll.setWidget(settings_box)
        options_scroll.setMinimumHeight(160); options_scroll.setMaximumHeight(260)
        options_layout.addWidget(options_scroll)
        outer.insertWidget(outer.indexOf(filter_row), self.options_section)
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 4); splitter.setStretchFactor(1, 1)
        sizes = self.settings.playlist_panel_sizes
        if not isinstance(sizes, list) or len(sizes) != 2 or any(type(n) is not int or not 0 < n < 100000 for n in sizes):
            sizes = [650, 170]
        self._expanded_preview_sizes = list(sizes)
        splitter.setSizes(sizes)
        self.preview_section.toggle.toggled.connect(self._preview_visibility_changed)
        if not self.preview_section.toggle.isChecked():
            self.preview_section.setMaximumHeight(self.preview_section.sizeHint().height())
        outer.addWidget(splitter, 1)
        buttons = QHBoxLayout()
        select_all = QPushButton("Select All Visible"); select_none = QPushButton("Select None"); invert = QPushButton("Invert Visible")
        select_all.clicked.connect(lambda: self._select_items(True)); select_none.clicked.connect(lambda: self._select_items(False)); invert.clicked.connect(self._invert_items)
        self.add_button = QPushButton("Download Selected"); self.add_button.clicked.connect(self.enqueue_selected); self.add_button.setEnabled(False)
        self.add_button.setProperty("primary", True)
        buttons.addWidget(select_all); buttons.addWidget(select_none); buttons.addWidget(invert); buttons.addStretch(); buttons.addWidget(self.add_button)
        self.selection_count = QLabel("0 selected · 0 visible · 0 total"); self.selection_count.setWordWrap(True)
        outer.addLayout(buttons)
        self.activity_label = QLabel("Current activity: No active downloads"); outer.addWidget(self.activity_label)
        # Preserve control size hints rather than crushing the options inside a
        # vertical splitter on smaller screens. Selection actions stay in view.
        outer.removeItem(buttons); outer.removeWidget(self.activity_label)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        download_page = QWidget(); download_layout = QVBoxLayout(download_page); download_layout.setContentsMargins(0, 0, 0, 0)
        download_scroll = QScrollArea(); download_scroll.setWidgetResizable(True); download_scroll.setWidget(download_tab)
        download_layout.addWidget(download_scroll, 1)
        footer = QWidget(); footer_layout = QVBoxLayout(footer); footer_layout.setContentsMargins(22, 4, 22, 12)
        footer_layout.addWidget(self.selection_count); footer_layout.addLayout(buttons); footer_layout.addWidget(self.activity_label); download_layout.addWidget(footer)
        self.tabs.addTab(download_page, "Download")
        self.tabs.addTab(self._queue_tab(), "Queue"); self.tabs.addTab(self._history_tab(), "History")
        self.console_tab = self._console_tab(); self.tabs.addTab(self.console_tab, "Console")
        self.settings_panel = SettingsWindow(self.settings, self.managed_tor, self._apply_settings, self,
                                             self.runtime_manager, self.task_manager, embedded=True,
                                             account_callback=self._apply_account_choice)
        self.tabs.addTab(self.settings_panel, "Settings")
        self.provider_label = QLabel(); self.runtime_label = QLabel(); self.connection_bar_label = QLabel()
        self.statusBar().addPermanentWidget(self.provider_label); self.statusBar().addPermanentWidget(self.runtime_label); self.statusBar().addPermanentWidget(self.connection_bar_label)
        self.provider_label.setText("● PO provider: checking"); self.runtime_label.setText(f"● yt-dlp {self.runtime_manager.snapshot().version}"); self._refresh_connection_status()
        self.provider_check_timer = QTimer(self); self.provider_check_timer.setSingleShot(True); self.provider_check_timer.timeout.connect(self._update_provider_status); self.provider_check_timer.start(20)
        if self.settings.connection_mode == "External Tor":
            self.external_probe_timer = QTimer(self); self.external_probe_timer.setSingleShot(True); self.external_probe_timer.timeout.connect(self._probe_external_tor); self.external_probe_timer.start(30)

    def _queue_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget)
        layout.setContentsMargins(22, 18, 22, 16); layout.setSpacing(10)
        page_heading(layout, "Queue", "Track transfers, review warnings and manage retained downloads.")
        self.queue_empty = QLabel("No downloads yet. Add a URL on Download to get started."); self.queue_empty.setObjectName("muted"); self.queue_empty.setWordWrap(True); layout.addWidget(self.queue_empty)
        filter_row = QHBoxLayout(); filter_row.addWidget(QLabel("View:"))
        self.queue_filter = QComboBox(); self.queue_filter.addItems(["Media", "Torrents", "All"])
        self.queue_filter.currentTextChanged.connect(self._refresh_queue); filter_row.addWidget(self.queue_filter); filter_row.addStretch()
        layout.addLayout(filter_row)
        self.job_banner = QWidget(); banner_layout = QVBoxLayout(self.job_banner); banner_layout.setContentsMargins(8, 8, 8, 8)
        self.job_banner_text = QLabel(); self.job_banner_text.setWordWrap(True); banner_layout.addWidget(self.job_banner_text)
        banner_actions = QHBoxLayout(); banner_layout.addLayout(banner_actions)
        for text, callback in [("Retry", self.retry_banner_job), ("View Details", self.view_job_details),
                               ("Open Console", self.view_job_console), ("Dismiss", self.job_banner.hide)]:
            button = QPushButton(text); button.clicked.connect(callback); banner_actions.addWidget(button)
        self.job_account_button = QPushButton("Account settings…"); self.job_account_button.clicked.connect(self.show_youtube_account)
        self.job_account_button.hide(); banner_actions.addWidget(self.job_account_button); banner_actions.addStretch()
        self.job_banner.setStyleSheet("background: palette(alternate-base); border-radius: 6px;")
        self.job_banner.hide(); layout.addWidget(self.job_banner)
        self.queue_table = QTableWidget(0, 0)
        polish_table(self.queue_table)
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.queue_table.customContextMenuRequested.connect(self._queue_context_menu)
        self.queue_table.itemSelectionChanged.connect(self._queue_selection_changed)
        layout.addWidget(self.queue_table)
        self.job_details = QPlainTextEdit(); self.job_details.setReadOnly(True); self.job_details.setMaximumHeight(155)
        self.job_details.setPlaceholderText("Select a job to view details"); layout.addWidget(self.job_details)
        actions = QHBoxLayout()
        for text, callback in [("Pause", self.pause_selected), ("Resume", self.resume_selected), ("Cancel", self.cancel_selected), ("Retry", self.retry_selected), ("Clear Completed", self.clear_completed)]:
            button = QPushButton(text); button.clicked.connect(callback); actions.addWidget(button)
        actions.addStretch(); layout.addLayout(actions); return widget

    def _queue_context_menu(self, position):
        menu = QMenu(self.queue_table)
        for text, callback in [("Pause", self.pause_selected), ("Resume", self.resume_selected),
                               ("Cancel", self.cancel_selected), ("Retry", self.retry_selected),
                               ("Restart from Beginning", self.restart_selected),
                               ("View Details", self.view_job_details), ("View Warnings", self.view_job_warnings),
                               ("View Console", self.view_job_console), ("Copy Diagnostics", self.copy_job_diagnostics),
                               ("Open", self.open_selected), ("Reveal in Finder", self.reveal_selected),
                               ("Remove", self.remove_selected), ("Copy Magnet", self.copy_magnet),
                               ("Stop Seeding", self.stop_seeding)]:
            menu.addAction(text, callback)
        selected = self._selected_or_banner_job()
        if selected and selected.effective_connection == "Managed Tor":
            menu.addSeparator(); menu.addAction("New Tor Circuit", self.new_tor_circuit)
            menu.addAction("Retry with New Tor Circuit", self.retry_with_new_tor_circuit)
        if selected and selected.output_file and Path(selected.output_file).is_file():
            menu.addAction("Convert for macOS / QuickTime", self.convert_selected_for_macos)
            menu.addAction("Convert As…", lambda: self.open_video_converter(selected.output_file))
        menu.exec(self.queue_table.viewport().mapToGlobal(position))

    def _console_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); controls = QHBoxLayout()
        layout.setContentsMargins(22, 18, 22, 16); layout.setSpacing(10)
        page_heading(layout, "Console", "Local, redacted diagnostics. Filter by source or inspect a selected job.")
        self.console_filter = QComboBox(); self.console_filter.addItems(
            ["All", "App", "yt-dlp", "ffmpeg", "Subtitles", "Thumbnail", "aria2", "Tor", "Warnings", "Errors"])
        self.console_filter.currentTextChanged.connect(self._refresh_console)
        self.console_job_label = QLabel("All jobs")
        self.console_job_label.setWordWrap(True); self.console_job_label.setMaximumWidth(240)
        all_jobs = QPushButton("All Jobs"); all_jobs.clicked.connect(self.clear_console_job_filter)
        self.console_autoscroll = QCheckBox("Auto-scroll"); self.console_autoscroll.setChecked(True)
        clear = QPushButton("Clear"); clear.clicked.connect(self.console_store.clear)
        copy_button = QPushButton("Copy"); copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(self.console_view.toPlainText()))
        save = QPushButton("Save Console…"); save.clicked.connect(self._save_console)
        open_logs = QPushButton("Open Logs Folder"); open_logs.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir()))))
        controls.addWidget(QLabel("Filter:")); controls.addWidget(self.console_filter); controls.addWidget(self.console_job_label); controls.addWidget(all_jobs); controls.addStretch()
        controls.addWidget(self.console_autoscroll)
        layout.addLayout(controls)
        actions = QHBoxLayout()
        for control in (clear, copy_button, save, open_logs): actions.addWidget(control)
        actions.addStretch(); layout.addLayout(actions)
        self.console_view = QPlainTextEdit(); self.console_view.setReadOnly(True)
        self.console_view.document().setMaximumBlockCount(10_000)
        self.console_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)); layout.addWidget(self.console_view)
        self.console_store.event_added.connect(self._console_event_added)
        self.console_store.cleared.connect(self.console_view.clear)
        return widget

    def _console_event_added(self, event: ConsoleEvent):
        if event not in self.console_store.events(self.console_filter.currentText(), self.console_job_filter): return
        self.console_view.appendPlainText(event.line)
        if self.console_autoscroll.isChecked():
            bar = self.console_view.verticalScrollBar(); bar.setValue(bar.maximum())

    def _refresh_console(self, *_):
        self.console_view.setPlainText(self.console_store.text(self.console_filter.currentText(), self.console_job_filter))

    def _save_console(self):
        target = QFileDialog.getSaveFileName(self, "Save Console", "Morgan Media Downloader Console.txt", "Text files (*.txt)")[0]
        if target: Path(target).write_text(self.console_view.toPlainText() + "\n", encoding="utf-8")

    def _history_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); filters = QHBoxLayout()
        layout.setContentsMargins(22, 18, 22, 16); layout.setSpacing(10)
        page_heading(layout, "History", "Find completed work and review output details from your local history.")
        self.history_search = QLineEdit(); self.history_search.setPlaceholderText("Search local history")
        self.history_filter = QComboBox(); self.history_filter.addItems(["All"] + [s.value for s in JobStatus])
        self.history_search.textChanged.connect(self._refresh_history); self.history_filter.currentTextChanged.connect(self._refresh_history)
        filters.addWidget(self.history_search); filters.addWidget(self.history_filter); layout.addLayout(filters)
        self.history_table = QTableWidget(0, 7); self.history_table.setHorizontalHeaderLabels(["Date", "Title", "Original URL", "Downloaded source", "Output file", "Format", "Status"])
        polish_table(self.history_table)
        self.history_empty = QLabel("No history yet."); self.history_empty.setObjectName("muted"); layout.addWidget(self.history_empty)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.history_table.customContextMenuRequested.connect(self._history_context_menu)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch); layout.addWidget(self.history_table)
        return widget

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")
        new = QAction("New Download", self); new.setShortcut("Meta+N"); new.triggered.connect(lambda: (self.tabs.setCurrentIndex(0), self.input.setFocus()))
        open_torrent = QAction("Open Torrent…", self); open_torrent.triggered.connect(self.open_torrent)
        convert_video = QAction("Convert Media…", self); convert_video.triggered.connect(self.open_video_converter)
        folder = QAction("Open Downloads Folder", self); folder.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.folder.text())))
        quit_action = QAction("Quit", self); quit_action.setShortcut("Meta+Q"); quit_action.triggered.connect(self.close)
        file_menu.addActions([new, open_torrent, convert_video, folder]); file_menu.addSeparator(); file_menu.addAction(quit_action)
        edit = self.menuBar().addMenu("Edit"); preferences = QAction("Settings…", self); preferences.setShortcut("Meta+,"); preferences.setMenuRole(QAction.MenuRole.PreferencesRole); preferences.triggered.connect(self.show_preferences); edit.addAction(preferences)
        view = self.menuBar().addMenu("View")
        self.fullscreen_action = QAction("Full Screen", self); self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.setShortcut("Ctrl+Meta+F" if sys.platform == "darwin" else "F11")
        self.fullscreen_action.triggered.connect(lambda enabled: self.showFullScreen() if enabled else self.showNormal())
        view.addAction(self.fullscreen_action)
        downloads = self.menuBar().addMenu("Downloads")
        pause_all = QAction("Pause All", self); pause_all.triggered.connect(self.pause_all)
        resume_all = QAction("Resume All", self); resume_all.triggered.connect(self.resume_all)
        clear = QAction("Clear Completed", self); clear.triggered.connect(self.clear_completed); downloads.addActions([pause_all, resume_all, clear])
        help_menu = self.menuBar().addMenu("Help")
        about = QAction("About", self); about.triggered.connect(lambda: QMessageBox.about(self, "About", "Morgan Media Downloader 0.1\nDownloads media the user is authorised to save.\nSpotify links are matched to supported sources; Spotify audio is never decrypted."))
        versions = QAction("Component Status", self); versions.triggered.connect(self.show_component_status)
        provider = QAction("bgutil Provider Status", self); provider.triggered.connect(self.show_provider_status)
        logs = QAction("Open Logs Folder", self); logs.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir()))))
        help_menu.addActions([about, versions, provider, logs])

    def show_provider_status(self):
        QMessageBox.information(self, "PO-token provider", self.provider_label.toolTip() or self.provider_label.text())

    def _toggle_more_options(self):
        visible = not self.more_options.isVisible()
        self.more_options.setVisible(visible)
        self.more_button.setText("More Options ▴" if visible else "More Options ▾")

    def _input_changed(self):
        self._inspection_generation += 1
        self.analysis_diagnostics.hide(); self._analysis_error_details = ""
        count = len(split_input(self.input.toPlainText()))
        if not self.analysis_task_id:
            self.analyse_button.setText("Analyse All" if count > 1 else "Analyse")
        self.download_button.setText("Download All" if count > 1 else "Download")
        current = self.input.toPlainText().strip()
        if self.displayed_input and current != self.displayed_input:
            self.analysis_stale = True
            self.add_button.setEnabled(False)
            self.inspect_button.setEnabled(False)
            self.summary.setText("Input changed — analyse the new URL.")

    def _connection_changed(self, mode: str):
        self._inspection_generation += 1
        self.settings.connection_mode = mode
        if hasattr(self, "settings_panel"):
            self.settings_panel.working.connection_mode = mode
            self.settings_panel.connection.blockSignals(True); self.settings_panel.connection.setCurrentText(mode); self.settings_panel.connection.blockSignals(False)
        self.settings_store.save(self.settings)
        if mode == "Managed Tor" and self.settings.managed_tor_auto_start and self.managed_tor.state in {"Stopped", "Failed"}:
            self.managed_tor.start()
        if mode == "External Tor":
            self._probe_external_tor()
        tooltips = {
            "Direct / Normal Network": "Use the Mac's normal network connection.",
            "System / Proton VPN": "Use macOS networking. If Proton VPN is connected, downloads use that VPN.",
        }
        self.connection_selector.setToolTip(tooltips.get(mode, "Use the selected proxy connection for new media jobs."))
        self._refresh_connection_status()

    def _refresh_connection_status(self):
        if not hasattr(self, "connection_status"):
            return
        mode = self.settings.connection_mode
        if mode == "Managed Tor":
            for message in self.managed_tor.drain_logs():
                self.console_store.append("TOR", message)
            state = self.managed_tor.state
            text = f"Managed Tor • {state}"
            if self.managed_tor.port: text += f" • SOCKS 127.0.0.1:{self.managed_tor.port}"
            if self.managed_tor.control_port: text += f" • Control 127.0.0.1:{self.managed_tor.control_port}"
            if self.managed_tor.bootstrap_percent: text += f" • Bootstrap {self.managed_tor.bootstrap_percent}%"
            good = state == "Connected"
            unknown = state.startswith("Bootstrapping") or state == "Starting"
            if good and not self.managed_tor.current_exit_ip and not self.task_manager.active_ids("tor-exit-probe"):
                runtime = self.runtime_manager.snapshot()
                self.task_manager.start("tor-exit-probe", lambda _cancel, _progress, t=self.managed_tor, r=runtime: _managed_tor_diagnostics(t, r),
                                        on_result=self._connection_test_ready)
        elif mode == "External Tor":
            text, good, unknown = ((f"External Tor • Connected • {self.external_tor_port}", True, False)
                                   if self.external_tor_port else ("External Tor • Not running / not tested", False, True))
        elif mode == "System / Proton VPN":
            text, good, unknown = "System network", True, False
        elif mode == "Direct / Normal Network":
            text, good, unknown = "Ready", True, False
        else:
            configured = bool((self.settings.http_proxy_host and self.settings.http_proxy_port)
                              if mode == "Custom HTTP Proxy" else
                              (self.settings.socks_proxy_host and self.settings.socks_proxy_port))
            text, good, unknown = ("Configured" if configured else "Proxy details required"), configured, not configured
        color = "#2e9b45" if good else "#c28a00" if unknown else "#c0392b"
        self.connection_status.setText(f"● {text}"); self.connection_status.setStyleSheet(f"color: {color}")
        compact = f"Tor {self.managed_tor.port}" if mode == "Managed Tor" and self.managed_tor.port else mode.replace(" / Normal Network", "")
        self.connection_bar_label.setText(f"● {compact}")
        tor_state = f"{mode}:{text}"
        if mode in {"Managed Tor", "External Tor"} and tor_state != getattr(self, "_last_tor_console_state", ""):
            self._last_tor_console_state = tor_state; self.console_store.append("TOR", text)

    def _test_connection(self):
        if self.settings.connection_mode == "External Tor" and not self.external_tor_port:
            self._probe_external_tor(); return
        try:
            proxy = self._proxy()
        except (ValueError, ConnectionError) as error:
            self._connection_test_ready(("unavailable", str(error))); return
        runtime = self.runtime_manager.snapshot()
        self.connection_test.setEnabled(False); self.connection_status.setText("● Testing…")
        operation = (lambda _cancel, _progress, t=self.managed_tor, r=runtime: _managed_tor_diagnostics(t, r)) if self.settings.connection_mode == "Managed Tor" else (
            lambda _cancel, _progress, p=proxy, r=runtime: test_media_connection(p, r))
        self.task_manager.start("connection-test", operation,
                                on_result=self._connection_test_ready, on_error=self._connection_test_error,
                                on_finished=self._connection_test_finished)

    def _connection_test_ready(self, result: object):
        state, detail, *extra = result
        if extra and extra[0]: self.managed_tor.current_exit_ip = str(extra[0])
        good = state in {"available", "internet_working"}
        if self.settings.connection_mode == "Managed Tor": self.tor_internet_state = state
        self.connection_status.setText(f"● {'Connected' if good else 'Failed'} — {detail}")
        self.connection_status.setStyleSheet(f"color: {'#2e9b45' if good else '#c0392b'}")
        self.console_store.append("TOR" if self.settings.connection_mode in {"Managed Tor", "External Tor"} else "APP",
                                  detail, level="info" if good else "warning")

    def _connection_test_error(self, message: str, _details: str):
        self._connection_test_ready(("unavailable", message))

    def _connection_test_finished(self, _task_id: str):
        self.connection_test.setEnabled(True)

    def new_tor_circuit(self):
        if self.settings.connection_mode != "Managed Tor" or not self.managed_tor.proxy_url:
            QMessageBox.warning(self, "New Tor Circuit", "Managed Tor must be connected first."); return
        self.console_store.append("TOR", "Requesting NEWNYM")
        runtime = self.runtime_manager.snapshot()
        self.task_manager.start("tor-circuit", lambda _cancel, _progress, t=self.managed_tor, r=runtime: _rotate_managed_tor(t, r),
                                on_result=self._tor_circuit_ready, on_error=self._tor_circuit_error)

    def retry_with_new_tor_circuit(self):
        job = self._selected_or_banner_job()
        if not job: return
        self._pending_circuit_retry_job = job.id
        self.new_tor_circuit()

    def _tor_circuit_ready(self, result: object):
        if not isinstance(result, dict): return
        previous, current = str(result.get("previous_exit_ip") or ""), str(result.get("current_exit_ip") or "")
        changed = result.get("changed")
        self.console_store.append("TOR", f"Previous exit: {previous or 'Unknown'}; new exit: {current or 'Unknown'}; "
                                  f"changed: {'Yes' if changed else 'No' if changed is False else 'Unknown'}")
        if job_id := getattr(self, "_pending_circuit_retry_job", ""):
            self._pending_circuit_retry_job = ""
            if job := self.jobs.get(job_id):
                job.tor_previous_exit_ip = previous; job.tor_current_exit_ip = current
                job.tor_circuit_changed = changed if isinstance(changed, bool) else None
                job.tor_last_circuit_change = str(result.get("last_circuit_change") or "")
                self._resume([job])
        self._refresh_selected_job_details()

    def _tor_circuit_error(self, message: str, _details: str):
        self._pending_circuit_retry_job = ""
        self.console_store.append("TOR", f"NEWNYM failed: {message}", level="error")
        QMessageBox.warning(self, "New Tor Circuit", message)

    def _probe_external_tor(self):
        self.connection_status.setText("● External Tor • Detecting…")
        self.task_manager.start("connection-test", lambda _cancel, _progress: detect_tor(),
                                on_result=self._external_tor_ready)

    def _external_tor_ready(self, result):
        available, port = result
        self.external_tor_port = port if available else None
        text = f"External Tor • Connected • {port}" if available else "External Tor • Not running"
        self.connection_status.setText(f"● {text}")
        self.connection_status.setStyleSheet(f"color: {'#2e9b45' if available else '#c0392b'}")

    def _use_banner_analyse(self):
        if self.previous_crash and "did not close" in self.banner_text.text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir()))); return
        if getattr(self, "_banner_url", ""):
            self.input.setPlainText(self._banner_url); self.banner.hide(); self.analyse()

    def _use_banner_download(self):
        if getattr(self, "_banner_url", ""):
            self.input.setPlainText(self._banner_url); self.banner.hide(); self.download_input()

    def _check_clipboard(self):
        if not self.settings.clipboard_url_detection or self.previous_crash and self.banner.isVisible():
            return
        value = QApplication.clipboard().text().strip()
        if value == getattr(self, "_last_clipboard", ""):
            return
        self._last_clipboard = value
        if value.startswith("magnet:?") or value.startswith(("http://", "https://")):
            self._banner_url = value
            self.banner_text.setText(f"{input_kind(value).replace('_', ' ').title()} link detected")
            self.banner_analyse.setText("Analyse"); self.banner_download.show(); self.banner.show()

    def _show_settings_warning(self):
        QMessageBox.warning(self, "Settings recovered", self.settings_store.last_warning)

    def _refresh_activity(self):
        if not hasattr(self, "activity_label"):
            return
        media = sum(1 for job_id in self.active if self.jobs.get(job_id) and self.jobs[job_id].kind == "media")
        torrents = sum(1 for job_id in self.active if self.jobs.get(job_id) and self.jobs[job_id].kind == "torrent")
        self.activity_label.setText(f"Current activity: {media} media download(s), {torrents} torrent(s)" if media or torrents else "Current activity: No active downloads")

    def _proxy(self) -> str | None:
        mode = self.settings.connection_mode
        if mode == "Custom HTTP Proxy":
            host, port, username, kind = self.settings.http_proxy_host, self.settings.http_proxy_port, self.settings.http_proxy_username, "http"
        elif mode == "Custom SOCKS5 Proxy":
            host, port, username, kind = self.settings.socks_proxy_host, self.settings.socks_proxy_port, self.settings.socks_proxy_username, "socks"
        else:
            host, port, username, kind = self.settings.proxy_host, self.settings.proxy_port, self.settings.proxy_username, "legacy"
        if self.settings.connection_mode == "External Tor":
            port = self.external_tor_port or 9150
            if not self.external_tor_port:
                raise ConnectionError("External Tor is not running on 127.0.0.1:9150 or :9050.")
            host = host or "127.0.0.1"
        elif self.settings.connection_mode == "Managed Tor":
            if not self.managed_tor.proxy_url:
                if self.settings.managed_tor_auto_start and self.managed_tor.state in {"Stopped", "Failed"}:
                    self.managed_tor.start()
                raise ConnectionError(f"Managed Tor is {self.managed_tor.state}. Wait until bootstrap reaches 100%.")
            host, port = "127.0.0.1", self.managed_tor.port
        password = ""
        if username:
            account = f"{kind}:{username}"
            if account not in self.proxy_passwords:
                self.proxy_passwords[account] = load_proxy_password(account) or load_proxy_password(username)
            password = self.proxy_passwords[account]
        return ProxyConfig(self.settings.connection_mode, host, port, username, password).url()

    @Slot()
    def analyse(self):
        if self.analysis_task_id:
            self.task_manager.cancel(self.analysis_task_id)
            self.analyse_button.setText("Cancelling…")
            return
        values = split_input(self.input.toPlainText())
        if not values:
            QMessageBox.information(self, "Analyse", "Enter at least one URL or search term."); return
        self._start_analysis(values, "preview", self._current_options())

    def download_input(self):
        values = split_input(self.input.toPlainText())
        if not values:
            QMessageBox.information(self, "Download", "Enter at least one URL or search term."); return
        current = self.input.toPlainText().strip()
        if self.items and not self.analysis_stale and self.displayed_input == current:
            self.enqueue_selected(); return
        options = self._current_options()
        for value in values:
            self._start_analysis([value], "download", copy.deepcopy(options))

    def _start_analysis(self, values: list[str], purpose: str, options: DownloadOptions):
        if (any(input_kind(value) != "torrent" for value in values)
                and self.settings.connection_mode == "Managed Tor" and not self.managed_tor.proxy_url):
            if self.managed_tor.state in {"Stopped", "Failed"}:
                self.managed_tor.start()
            wait_id = f"analysis-{uuid4()}"
            context = AnalysisContext(wait_id, "\n".join(values), purpose, options,
                                      input_types=tuple(input_kind(value) for value in values))
            self.analysis_contexts[wait_id] = context
            if purpose == "preview":
                self.analysis_task_id = wait_id; self.analyse_button.setText("Cancel Analysis"); self.analysis_progress.show()
            tor = self.managed_tor; payload = (list(values), purpose, copy.deepcopy(options))
            operation = lambda cancel, progress, t=tor, p=payload: _wait_for_tor_operation(t, p, cancel, progress)
            self.task_manager.start("analysis", operation, task_id=wait_id,
                                    on_result=self._tor_analysis_ready, on_error=self._show_worker_error,
                                    on_progress=self._analysis_progress, on_finished=self._analysis_finished)
            return
        try: proxy = None if all(input_kind(value) == "torrent" for value in values) else self._proxy()
        except (ValueError, ConnectionError) as error: QMessageBox.warning(self, "Connection", str(error)); return
        analysis_id = f"analysis-{uuid4()}"
        original = "\n".join(values)
        context = AnalysisContext(analysis_id, original, purpose, options,
                                  input_types=tuple(input_kind(value) for value in values))
        settings = copy.deepcopy(self.settings); runtime = self.runtime_manager.snapshot()
        operation = lambda cancel, progress, v=list(values), p=proxy, s=settings, r=runtime, c=context: _analysis_operation(v, p, s, r, c, cancel, progress)
        self.analysis_contexts[analysis_id] = context
        if purpose == "preview":
            self.analysis_task_id = analysis_id
            self.items = []; self.torrent_context = None; self.item_table.setRowCount(0)
            self.analyse_button.setText("Cancel Analysis"); self.analysis_progress.show(); self.summary.setText("Connecting…")
        self.task_manager.start("analysis", operation, task_id=analysis_id,
                                on_result=self._analysis_ready, on_error=self._show_worker_error,
                                on_progress=self._analysis_progress, on_finished=self._analysis_finished)

    def _tor_analysis_ready(self, payload: object):
        values, purpose, options = payload
        self._start_analysis(values, purpose, options)

    def _analysis_progress(self, status: object):
        self.summary.setText(str(status))
        self.console_store.append("APP", str(status))

    def _analysis_finished(self, task_id: str):
        self.analysis_contexts.pop(task_id, None)
        if self.analysis_task_id == task_id:
            self.analysis_task_id = ""
            self.analyse_button.setText("Analyse All" if len(split_input(self.input.toPlainText())) > 1 else "Analyse")
            self.analysis_progress.hide()

    def _analysis_ready(self, payload):
        context: AnalysisContext = payload["context"]
        items = payload["items"]
        if context.purpose == "download":
            self._enqueue_payload(items, payload.get("torrent"), context.options)
            return
        if self.input.toPlainText().strip() != context.original_input.strip():
            self.summary.setText("Input changed — analyse the new URL.")
            return
        self.displayed_input = context.original_input.strip(); self.analysis_stale = False
        self._inspection_generation += 1; self._item_overrides.clear()
        self.torrent_context = payload.get("torrent")
        self.items = items
        self._refresh_audio_languages(preserve_missing=False)
        self.item_table.blockSignals(True)
        self.item_table.clearContents(); self.item_table.setRowCount(len(items))
        if self.torrent_context:
            self.item_table.setHorizontalHeaderLabels(["✓", "#", "Filename", "Path", "Size", "Source", "Match"])
        else:
            self.item_table.setHorizontalHeaderLabels(["✓", "#", "Title", "Uploader / artist", "Duration", "Source", "Match"])
        for row, item in enumerate(items):
            check = QTableWidgetItem(); check.setFlags(check.flags() | Qt.ItemFlag.ItemIsUserCheckable); check.setCheckState(Qt.CheckState.Checked if item.selected else Qt.CheckState.Unchecked)
            measure = human_bytes(item.file_size) if self.torrent_context else human_duration(item.duration)
            cells = [check, QTableWidgetItem(str(item.playlist_index or row + 1)), QTableWidgetItem(item.title), QTableWidgetItem(item.uploader), QTableWidgetItem(measure), QTableWidgetItem(item.source), QTableWidgetItem(f"{item.confidence:.0f}%" if item.confidence is not None else "—")]
            for column, cell in enumerate(cells): self.item_table.setItem(row, column, cell)
        self.item_table.blockSignals(False)
        self._filter_playlist()
        if self.torrent_context:
            privacy = "Private" if self.torrent_context.is_private else "Public"
            self.summary.setText(f"{self.torrent_context.name} — {human_bytes(self.torrent_context.total_size)}, {len(self.torrent_context.files)} file(s), {self.torrent_context.tracker_count} tracker(s), {privacy}. BitTorrent uses Direct or System / Proton VPN only.")
            self.add_button.setText("Download Selected Torrent Files")
        else:
            source_count = len({item.source for item in items})
            self.summary.setText(f"Found {len(items)} item{'s' if len(items) != 1 else ''} from {source_count} source{'s' if source_count != 1 else ''}. Review matches, then download selected items.")
            self.add_button.setText("Download Selected Matches")
        authentication = payload.get("authentication") or []
        fallback = next((value for value in authentication if value.endswith("-> None") and not value.startswith("Auto")), "")
        if fallback:
            self.statusBar().showMessage(f"Authentication fallback: {fallback}", 10_000)
        self._update_selection_count()
        if items:
            self._preview_current_item(0)
        else:
            self._clear_thumbnail_preview(); self.preview_details.setText("No analysed items")

    def _preview_current_item(self, row: int, *_):
        if not 0 <= row < len(self.items): return
        item = self.items[row]
        self._preview_item_row = row
        self.preview_details.setText(
            f"{item.title}\n{item.uploader or 'Unknown channel / artist'}\n{human_duration(item.duration)}\n"
            f"{item.source or 'Unknown source'}\n"
            f"Subtitles reported: {', '.join(friendly_language(code) for code in item.available_subtitles) or 'Not reported'}\n"
            f"Automatic captions reported: {', '.join(friendly_language(code) for code in item.automatic_captions) or 'Not reported'}")
        self._clear_thumbnail_preview()
        if item.thumbnail and self.preview_section.toggle.isChecked(): self._start_thumbnail_preview(item)

    def _preview_visibility_changed(self, expanded: bool):
        if expanded:
            self.preview_section.setMaximumHeight(16777215)
            self.playlist_splitter.setSizes(getattr(self, "_expanded_preview_sizes", [650, 170]))
            self._preview_current_item(getattr(self, "_preview_item_row", 0))
        else:
            self._expanded_preview_sizes = self.playlist_splitter.sizes()
            self.preview_section.setMaximumHeight(self.preview_section.sizeHint().height())
            self._clear_thumbnail_preview()

    def _clear_thumbnail_preview(self):
        previous = getattr(self, "_thumbnail_worker_id", "")
        self.thumbnail_task_id = ""
        self._pending_thumbnail_item = None
        if previous: self.task_manager.cancel(previous)
        self.thumbnail.setPixmap(QPixmap()); self.thumbnail.setText("No thumbnail")
        self.thumbnail_progress.hide()

    def _filter_playlist(self, *_):
        query = self.playlist_filter.text().strip().casefold()
        for row, item in enumerate(self.items):
            text = " ".join((item.title, item.uploader, item.source, str(item.playlist_index or row + 1))).casefold()
            self.item_table.setRowHidden(row, bool(query and query not in text))
        self._update_selection_count()

    def _update_selection_count(self, *_):
        selected = visible = 0
        for row, item in enumerate(self.items):
            cell = self.item_table.item(row, 0)
            if cell is None: continue
            item.selected = cell.checkState() == Qt.CheckState.Checked
            selected += item.selected
            visible += not self.item_table.isRowHidden(row)
        self.selection_count.setText(f"{selected} selected · {visible} visible · {len(self.items)} total")
        if self._item_overrides: self.selection_count.setText(self.selection_count.text() + f" · {len(self._item_overrides)} item override(s)")
        self.add_button.setEnabled(bool(selected) and not self.analysis_stale)
        self.inspect_button.setEnabled(bool(visible) and not self.torrent_context and not self.analysis_stale and not self._inspection_busy)

    def _inspect_current_video(self):
        if self._inspection_busy or self.analysis_stale or self.torrent_context: return
        row = self.item_table.currentRow()
        if row < 0 or self.item_table.isRowHidden(row):
            row = next((r for r in range(len(self.items)) if not self.item_table.isRowHidden(r)), -1)
        if row < 0: return
        item = self.items[row]
        try: proxy = self._proxy()
        except (ValueError, ConnectionError):
            self.statusBar().showMessage("Inspection unavailable — selected connection is not ready. Test Network and retry.", 15000); return
        settings, runtime = copy.deepcopy(self.settings), self.runtime_manager.snapshot()
        generation = self._inspection_generation
        self._inspection_busy = True; self.inspect_button.setEnabled(False)
        self.statusBar().showMessage("Inspecting one video with the selected authentication and connection…")
        def inspect(_cancel, _progress):
            try:
                items, effective = analyse_with_authentication(item.source_url, proxy, settings.provider_base_url,
                    settings.provider_server_home, settings.authentication_mode, settings.cookies_browser,
                    settings.browser_profile, settings.cookies_file, runtime, single_video=True)
                if len(items) != 1: raise ValueError("No playable formats")
                return generation, item, runtime.version, runtime.source, items[0].inspection, effective, ""
            except Exception as error:
                from .job_diagnostics import classify_failure
                return generation, item, runtime.version, runtime.source, None, "", classify_failure(error)["code"]
        self.task_manager.start("media-inspection", inspect, on_result=self._inspection_ready, on_finished=self._inspection_finished)

    def _inspection_ready(self, payload):
        generation, item, version, source, details, effective, error = payload
        runtime = self.runtime_manager.snapshot()
        if generation != self._inspection_generation or (version, source) != (runtime.version, runtime.source) or not any(current is item for current in self.items):
            self.statusBar().showMessage("Inspection discarded — input, authentication, connection or runtime changed. Inspect again.", 15000); return
        if details is None:
            self.statusBar().showMessage(f"Inspection failed — {error}. Check authentication, runtime and provider, then retry.", 15000); return
        from .media_details_dialog import MediaDetailsDialog
        item.inspection = details
        self._refresh_audio_languages()
        if self.media_details_dialog is not None: self.media_details_dialog.close()
        def apply(values):
            active_runtime = self.runtime_manager.snapshot()
            if generation != self._inspection_generation or (version, source) != (active_runtime.version, active_runtime.source) or self.analysis_stale or not any(current is item for current in self.items):
                raise ValueError("Source changed")
            if values is None: self._item_overrides.pop(id(item), None)
            else: self._item_overrides[id(item)] = dict(values)
            self._update_selection_count()
        self.media_details_dialog = MediaDetailsDialog(item.title, details, self._current_options(),
            self._item_overrides.get(id(item), {}), apply, self)
        self.media_details_dialog.status.setText(f"Inspected {datetime.now(timezone.utc).isoformat(timespec='seconds')} · yt-dlp {version} · Authentication: {effective}. Not a sign-in or transfer guarantee.")
        self.media_details_dialog.show()
        self.statusBar().showMessage("Inspection ready — review formats and apply choices to this item, or keep batch defaults.", 15000)

    def _inspection_finished(self, *_):
        self._inspection_busy = False
        self._update_selection_count()

    def _start_thumbnail_preview(self, item: MediaItem):
        previous = getattr(self, "_thumbnail_worker_id", "")
        if previous:
            self.task_manager.cancel(previous)
            self.thumbnail_task_id = ""
            self._pending_thumbnail_item = copy.deepcopy(item)
            self.thumbnail.setText("Waiting for previous thumbnail request to stop…")
            self.thumbnail_progress.setRange(0, 0); self.thumbnail_progress.show()
            return
        task_id = f"thumbnail-preview-{uuid4()}"; self.thumbnail_task_id = task_id
        self.thumbnail.setPixmap(QPixmap()); self.thumbnail.setText("Loading thumbnail…")
        self.thumbnail_progress.setRange(0, 0); self.thumbnail_progress.show()
        self.console_store.append("THUMBNAIL", "Loading preview thumbnail")
        try: proxy = self._proxy()
        except (ValueError, ConnectionError):
            self.thumbnail_task_id = ""; self.thumbnail_progress.hide()
            self._thumbnail_error("Selected connection unavailable; thumbnail was not fetched.", "")
            return
        runtime = self.runtime_manager.snapshot()
        def operation(_cancel, report, u=item.thumbnail, h=dict(item.thumbnail_headers), p=proxy, r=runtime, identity=task_id):
            try:
                path = fetch_thumbnail(u, h, lambda value: report({"thumbnail_progress": value, "thumbnail_task_id": identity}), p, r,
                                       cancel_event=_cancel)
            except Exception:
                path = None
            return identity, path
        self._thumbnail_worker_id = task_id
        self.task_manager.start("thumbnail-preview", operation, task_id=task_id,
                                on_result=self._thumbnail_delivered, on_progress=self._thumbnail_progress_ready,
                                on_finished=self._thumbnail_finished)

    def _thumbnail_delivered(self, payload):
        task_id, path = payload
        if task_id != getattr(self, "thumbnail_task_id", ""): return
        if path is None: self._thumbnail_error("Thumbnail could not be loaded; retry the selected item.", "")
        else: self._thumbnail_ready(path)

    def _thumbnail_progress_ready(self, payload: object):
        if not isinstance(payload, dict) or "thumbnail_progress" not in payload: return
        if payload.get("thumbnail_task_id", getattr(self, "thumbnail_task_id", "")) != getattr(self, "thumbnail_task_id", ""): return
        value = payload["thumbnail_progress"]
        if value is None: self.thumbnail_progress.setRange(0, 0)
        else:
            self.thumbnail_progress.setRange(0, 100); self.thumbnail_progress.setValue(int(value))
            self.thumbnail.setText(f"Loading thumbnail…\n{int(value)}%")

    def _thumbnail_ready(self, path: object):
        pixmap = QPixmap(str(path))
        if pixmap.isNull(): self._thumbnail_error("Thumbnail image could not be decoded", ""); return
        self.thumbnail.setText(""); self.thumbnail.setPixmap(
            pixmap.scaled(self.thumbnail.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.console_store.append("THUMBNAIL", "Preview thumbnail loaded")

    def _thumbnail_error(self, message: str, _details: str):
        self.thumbnail.setPixmap(QPixmap()); self.thumbnail.setText("Thumbnail\nunavailable")
        self.console_store.append("THUMBNAIL", message, level="warning")

    def _thumbnail_finished(self, task_id: str):
        if getattr(self, "_thumbnail_worker_id", "") == task_id:
            self._thumbnail_worker_id = ""
        if getattr(self, "thumbnail_task_id", "") == task_id:
            self.thumbnail_task_id = ""; self.thumbnail_progress.hide()
        pending = getattr(self, "_pending_thumbnail_item", None)
        self._pending_thumbnail_item = None
        if pending is not None and not self._closing and self.preview_section.toggle.isChecked():
            self._start_thumbnail_preview(pending)

    def _show_worker_error(self, message: str, details: str):
        from .logging_setup import redact_secrets
        message, details = redact_secrets(message), redact_secrets(details)
        if requires_authentication(message):
            result = connection_failure(message)
            self.summary.setText(result.message)
            youtube = any("youtube.com" in value or "youtu.be" in value or value == ":ytwatchlater" for value in split_input(self.input.toPlainText()))
            self.account_button.setText("Reconnect YouTube…" if youtube else "Authentication settings…")
            self._analysis_error_details = re.sub(r"(?im)^.*(?:cookie|authorization|password|token|signature).*$", "[Sensitive diagnostic line omitted]", message + "\n\n" + details)
            self.analysis_diagnostics.show()
            self.console_store.append("ERROR", result.message, level="error")
            return  # Never offer an unauthenticated format retry for private errors.
        self.console_store.append("ERROR", message, level="error")
        self.summary.setText("Analysis failed")
        if "format" in message.casefold() and any(term in message.casefold() for term in ("not available", "compatible")):
            box = QMessageBox(QMessageBox.Icon.Warning, "No compatible format",
                              "No compatible format was found with the current settings.", parent=self)
            best = box.addButton("Try Best Available", QMessageBox.ButtonRole.AcceptRole)
            no_auth = None
            if self.settings.authentication_mode not in {"None", "Auto"}:
                no_auth = box.addButton("Retry Without Authentication", QMessageBox.ButtonRole.ActionRole)
            box.addButton("Show Technical Details", QMessageBox.ButtonRole.HelpRole)
            box.addButton(QMessageBox.StandardButton.Cancel); box.setDetailedText(details); box.exec()
            if box.clickedButton() is best:
                self.quality.setCurrentText("Best"); QTimer.singleShot(0, self.analyse)
            elif no_auth is not None and box.clickedButton() is no_auth:
                QTimer.singleShot(0, self._retry_analysis_without_authentication)
            return
        if self.settings.authentication_mode == "None" and any(term in message.lower() for term in ("private", "sign in", "age", "unavailable", "bot")):
            message += "\n\nTry authenticated browser cookies in Settings → Accounts."
        box = QMessageBox(QMessageBox.Icon.Critical, "Unable to analyse", message, parent=self); box.setDetailedText(details); box.exec()

    def _show_analysis_diagnostics(self):
        box = QMessageBox(QMessageBox.Icon.Information, "Analysis diagnostics", self.summary.text(), parent=self)
        box.setDetailedText(self._analysis_error_details); box.exec()

    def _retry_analysis_without_authentication(self):
        previous = self.settings.authentication_mode; self.settings.authentication_mode = "None"
        try: self.analyse()
        finally: self.settings.authentication_mode = previous

    def _select_items(self, selected: bool):
        self.item_table.blockSignals(True)
        for row in range(self.item_table.rowCount()):
            if selected and self.item_table.isRowHidden(row): continue
            self.item_table.item(row, 0).setCheckState(Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
        self.item_table.blockSignals(False)
        self._update_selection_count()

    def _invert_items(self):
        self.item_table.blockSignals(True)
        for row in range(self.item_table.rowCount()):
            if self.item_table.isRowHidden(row): continue
            item = self.item_table.item(row, 0); item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)
        self.item_table.blockSignals(False)
        self._update_selection_count()

    def _refresh_audio_languages(self, *, preserve_missing=True):
        selected = self.audio_language.currentData()
        formats = [value for item in self.items for value in item.inspection.get("formats", []) if value.get("audio")]
        languages = sorted({language_code(value.get("language")) for value in formats} - {""})
        self.audio_language.clear(); self.audio_language.addItem("Automatic / best available", "")
        if any(value.get("original") for value in formats): self.audio_language.addItem("Original (where explicitly reported)", "@original")
        for code in languages: self.audio_language.addItem(f"{friendly_language(code)} ({code})", code)
        index = self.audio_language.findData(selected)
        if selected and index < 0 and preserve_missing:
            label = "Original" if selected == "@original" else selected
            self.audio_language.addItem(f"Unavailable in inspected metadata — still required: {label}", selected)
            index = self.audio_language.count() - 1
        self.audio_language.setCurrentIndex(max(0, index))
        self.audio_language.setEnabled(self.audio_language.count() > 1)

    def _current_options(self) -> DownloadOptions:
        return DownloadOptions(
            compatibility=self.compatibility.currentText(), quality=self.quality.currentText(), container=self.container.currentText(),
            audio_format=self.audio_format.currentText(), audio_bitrate=self.audio_bitrate.currentText(),
            audio_language=self.audio_language.currentData() or "",
            embed_thumbnail=self.embed_thumb.isChecked(), embed_metadata=self.embed_meta.isChecked(),
            embed_chapters=self.embed_chapters.isChecked(), embed_subtitles=self.embed_subtitles.isChecked(),
            write_subtitles=self.write_subtitles.isChecked(), keep_original=self.keep_original.isChecked(),
            subtitle_language=self.subtitle_language.text().strip(), subtitle_source=self.subtitle_source.currentText(),
            verify_postprocessing=self.verify_postprocessing.isChecked(), filename_template=self.template.currentText(),
            download_dir=self.folder.text().strip(), cookies_browser=self.settings.cookies_browser,
            authentication_mode=self.settings.authentication_mode, browser_profile=self.settings.browser_profile,
            cookies_file=self.settings.cookies_file,
        )

    def enqueue_selected(self):
        if self.analysis_stale: return
        selected = [item for row, item in enumerate(self.items) if self.item_table.item(row, 0).checkState() == Qt.CheckState.Checked]
        if not selected: QMessageBox.information(self, "Queue", "Select at least one item."); return
        self._enqueue_payload(selected, self.torrent_context, self._current_options())

    def _enqueue_payload(self, selected: list[MediaItem], torrent_context: TorrentMetadata | None,
                         options: DownloadOptions):
        if not selected:
            return
        if torrent_context:
            try:
                validate_torrent_connection(self.settings.torrent_connection_mode)
            except ValueError:
                QMessageBox.warning(self, "Torrent connection", TORRENT_TOR_ERROR); return
            indices = [item.playlist_index for item in selected if item.playlist_index]
            item = MediaItem(torrent_context.source, torrent_context.name, source="Torrent",
                             original_url=torrent_context.source, file_size=sum(i.file_size for i in selected))
            torrent_options = DownloadOptions(download_dir=self.settings.torrent_download_dir)
            job = DownloadJob(item=item, options=options, kind="torrent", effective_connection=self.settings.torrent_connection_mode,
                              total_bytes=item.file_size, torrent_source=torrent_context.source,
                              torrent_file_indices=indices, torrent_private=torrent_context.is_private,
                              torrent_file_paths=[str(Path(media.uploader) / media.title) if media.uploader else media.title for media in selected],
                              torrent_trackers=list(torrent_context.trackers))
            job.options = torrent_options
            self.jobs[job.id] = job; self.database.save_job(job)
            self._refresh_queue(); self._refresh_history(); self.tabs.setCurrentIndex(1); return
        organised = organised_folder(options.download_dir, selected, self.settings.create_subfolders)
        created_directory = organised if Path(organised) != Path(options.download_dir) and not Path(organised).exists() else ""
        for item in selected:
            item_options = copy.deepcopy(options)
            for key, value in self._item_overrides.get(id(item), {}).items(): setattr(item_options, key, value)
            item_options.download_dir = organised
            if len(selected) > 1 and "playlist_index" not in item_options.filename_template and item.playlist_index:
                item_options.filename_template = "%(playlist_index)03d - " + item_options.filename_template
            job = DownloadJob(item=item, options=item_options, created_job_directory=created_directory,
                              effective_connection=self.settings.connection_mode); self.jobs[job.id] = job; self.database.save_job(job)
        self._persist_settings(); self._refresh_queue(); self._refresh_history(); self.tabs.setCurrentIndex(1)

    def _dispatch(self):
        active_media = sum(1 for job_id in self.active if self.jobs.get(job_id) and self.jobs[job_id].kind == "media")
        active_torrents = sum(1 for job_id in self.active if self.jobs.get(job_id) and self.jobs[job_id].kind == "torrent")
        media_slots = max(0, self.settings.concurrent_downloads - active_media)
        torrent_slots = max(0, self.settings.torrent_max_active - active_torrents)
        waiting = [job for job in self.jobs.values() if job.status == JobStatus.WAITING]
        for job in waiting:
            settings = copy.deepcopy(self.settings)
            if job.kind == "torrent":
                if not torrent_slots: continue
                operation = lambda cancel, progress, j=copy.deepcopy(job), s=settings: _torrent_download_operation(j, s, cancel, progress)
                torrent_slots -= 1
                job.status = JobStatus.FETCHING_METADATA if job.torrent_source.startswith("magnet:?") else JobStatus.DOWNLOADING
            else:
                if not media_slots: continue
                try: proxy = self._proxy()
                except (ValueError, ConnectionError): continue
                runtime = self.runtime_manager.snapshot()
                job.status = JobStatus.ANALYSING; job.postprocessing_stage = "Resolving media"
                job.active_extractor_task = True; job.active_transfer_task = False; job.active_postprocess_task = False
                job.last_state_transition = job.last_progress_timestamp = time.time()
                tor = self.managed_tor if settings.connection_mode == "Managed Tor" else None
                if tor:
                    job.tor_process_state = "Running" if tor.process and tor.process.poll() is None else "Not running"
                    job.tor_bootstrap = tor.bootstrap_percent
                    job.tor_socks_state = "Connected" if tor.proxy_url else "Failed"
                    job.tor_socks_endpoint = f"127.0.0.1:{tor.port}" if tor.port else ""
                    job.tor_control_endpoint = f"127.0.0.1:{tor.control_port}" if tor.control_port else ""
                    job.tor_internet_state = self.tor_internet_state
                    job.tor_current_exit_ip = tor.current_exit_ip; job.tor_previous_exit_ip = tor.previous_exit_ip
                    job.tor_last_circuit_change = tor.last_circuit_change
                operation = lambda cancel, progress, j=copy.deepcopy(job), p=proxy, s=settings, r=runtime, t=tor: _media_download_operation(j, p, s, r, cancel, progress, t)
                media_slots -= 1
            task_id = f"job-{job.id}"
            self.active[job.id] = task_id; self.database.save_job(job)
            self.task_manager.start(f"download-{job.kind}", operation, task_id=task_id,
                                    on_result=self._job_changed, on_progress=self._job_progress,
                                    on_error=self._job_error, on_finished=self._job_finished)
        self._refresh_activity()

    def _watchdog_jobs(self):
        changed = False
        for job in self.jobs.values():
            if reconcile_stuck_job(job):
                changed = True; self.database.save_job(job)
                if job.status == JobStatus.FAILED and job.id in self.active:
                    self.task_manager.cancel(self.active[job.id])
                    self.console_store.append("ERROR", job.error, job.id, "error")
        if changed: self._refresh_queue(); self._refresh_selected_job_details()

    def _job_progress(self, payload: object):
        if isinstance(payload, DownloadJob): self._job_changed(payload)
        elif isinstance(payload, dict) and "console" in payload:
            category, message, level = payload["console"]
            self.console_store.append(category, message, str(payload.get("job_id") or ""), level)

    def _job_changed(self, job: DownloadJob):
        current = self.jobs.get(job.id)
        if current and current.status == JobStatus.CANCELLED and job.status == JobStatus.PAUSED:
            job.status = JobStatus.CANCELLED
        if job.effective_connection == "Managed Tor" and not job.tor_current_exit_ip:
            job.tor_current_exit_ip = self.managed_tor.current_exit_ip
        if job.status == JobStatus.FAILED and job.failure_code == "HTTP 403" and job.effective_connection == "Managed Tor":
            state, message = classify_tor_target(self.tor_internet_state, job.error)
            if state == "target_rejected":
                job.failure_code = "Target rejected Tor"; job.error = message
        job.updated_at = datetime.now(timezone.utc).isoformat(); self.jobs[job.id] = job; self.database.save_job(job); self._refresh_queue(); self._refresh_history()
        if job.kind == "torrent":
            marker = (job.status.value, int(job.progress))
            if marker != getattr(self, "_last_aria_console", {}).get(job.id):
                if not hasattr(self, "_last_aria_console"): self._last_aria_console = {}
                self._last_aria_console[job.id] = marker
                self.console_store.append("ARIA2", f"{job.status.value} • {job.progress:.1f}% • {human_bytes(job.speed)}/s", job.id)
        if job.status == JobStatus.FAILED:
            self._show_job_banner(job, f"Download failed: {job.failure_code or job.error}")
            self.console_store.append("ERROR", job.error or job.failure_code, job.id, "error")
        elif job.status == JobStatus.COMPLETED_WARNINGS:
            self._show_job_banner(job, "Completed with warnings — view details")
            for warning in job.warnings: self.console_store.append("WARNING", warning, job.id, "warning")

    def _job_error(self, message: str, details: str):
        from .logging_setup import redact_secrets
        safe = redact_secrets(message); self.statusBar().showMessage(f"Background job failed: {safe}", 8000)
        self.console_store.append("ERROR", safe, level="error")

    def _job_finished(self, task_id: str):
        job_id = task_id.removeprefix("job-")
        self.active.pop(job_id, None)
        if job_id in self.pending_restarts:
            choice = self.pending_restarts.pop(job_id)
            if job := self.jobs.get(job_id): self._restart_job(job, choice)
        if job_id in self.pending_removals:
            delete_files = self.pending_removals.pop(job_id)
            if job := self.jobs.get(job_id): self._remove_job(job, delete_files)
        self._refresh_queue(); self._refresh_history(); self._refresh_activity()

    def _selected_jobs(self) -> list[DownloadJob]:
        ids = []
        for index in self.queue_table.selectionModel().selectedRows():
            value = self.queue_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            if value: ids.append(value)
        return [self.jobs[value] for value in ids if value in self.jobs]

    def pause_selected(self): self._pause(self._selected_jobs())
    def pause_all(self): self._pause(list(self.jobs.values()))
    def _pause(self, jobs):
        for job in jobs:
            if job.id in self.active:
                job.status = JobStatus.PAUSED; self.task_manager.cancel(self.active[job.id])
            elif job.status == JobStatus.WAITING: job.status = JobStatus.PAUSED
            self.database.save_job(job)
        self._refresh_queue()
    def resume_selected(self): self._resume(self._selected_jobs())
    def resume_all(self): self._resume(list(self.jobs.values()))
    def _resume(self, jobs):
        for job in jobs:
            if job.status in {JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.INTERRUPTED}:
                if job.kind == "media" and job.status == JobStatus.FAILED and (
                        requires_authentication(job.error) or job.failure_code.startswith("auth.")):
                    # An explicit retry after reconnect uses the applied account
                    # choice, preserving all unrelated captured download options.
                    for name in ("authentication_mode", "cookies_browser", "browser_profile", "cookies_file"):
                        setattr(job.options, name, getattr(self.settings, name))
                prepare_resumable_job(job); self.database.save_job(job)
        self._refresh_queue()
    def cancel_selected(self):
        for job in self._selected_jobs():
            job.status = JobStatus.CANCELLED
            if job.id in self.active: self.task_manager.cancel(self.active[job.id])
            self.database.save_job(job)
        self._refresh_queue()
    def retry_selected(self): self._resume(self._selected_jobs())
    def restart_selected(self):
        for job in self._selected_jobs():
            choice = self._confirm_restart(job)
            if choice == "cancel": continue
            job.technical_details = "Restarting from the beginning…"
            if job.id in self.active:
                self.pending_restarts[job.id] = choice; self.task_manager.cancel(self.active[job.id])
            else:
                self._restart_job(job, choice)
        self._refresh_queue()

    def _confirm_restart(self, job: DownloadJob) -> str:
        final_exists = any(Path(path).exists() for path in job.final_files)
        if final_exists:
            box = QMessageBox(QMessageBox.Icon.Question, "Restart download", "An output file already exists.", parent=self)
            keep = box.addButton("Keep existing and create a new file", QMessageBox.ButtonRole.AcceptRole)
            replace = box.addButton("Replace existing", QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(QMessageBox.StandardButton.Cancel); box.exec()
            return "keep" if box.clickedButton() is keep else "replace" if box.clickedButton() is replace else "cancel"
        partial_exists = any(Path(path).exists() for path in owned_paths(job, include_final=False))
        if partial_exists and QMessageBox.question(
                self, "Restart download", "Restart this download from the beginning?\n\nExisting partial download data for this job will be deleted.",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Ok:
            return "cancel"
        return "restart"

    def _restart_job(self, job: DownloadJob, choice: str):
        replace = choice == "replace"
        keep = choice == "keep"
        delete_restart_state(job, delete_final=replace)
        if keep:
            job.options.filename_template = "%(title)s (new).%(ext)s"
            job.output_file = ""; job.final_files.clear()
        job.status = JobStatus.WAITING
        self.database.save_job(job)

    def remove_selected(self):
        selected = self._selected_jobs()
        if not selected: return
        selected_ids = [job.id for job in selected]
        choice = self._confirm_remove(selected)
        if choice == "cancel": return
        delete_files = choice == "delete"
        removed = pending = 0
        for job_id in selected_ids:
            # The modal dialog processes worker results; use the current
            # inventory, not a job object replaced while confirmation was open.
            job = self.jobs.get(job_id)
            if job is None: continue
            if job.id in self.active:
                self.pending_removals[job.id] = delete_files; self.task_manager.cancel(self.active[job.id])
                pending += 1
            else:
                self._remove_job(job, delete_files); removed += 1
        self._refresh_queue(); self._refresh_history()
        self.statusBar().showMessage(f"Removed {removed} queue entries; {pending} waiting for active tasks to stop. "
            + ("Verified job-owned files selected for removal." if delete_files else "Downloaded files kept."), 10000)

    def _confirm_remove(self, jobs: list[DownloadJob]) -> str:
        active = sum(job.id in self.active for job in jobs)
        completed = sum(job.status in {JobStatus.COMPLETED, JobStatus.COMPLETED_WARNINGS} for job in jobs)
        box = QMessageBox(QMessageBox.Icon.Question, "Remove selected jobs",
            f"Remove {len(jobs)} selected jobs?\n\n{active} active; {completed} completed.\n"
            "Active tasks must stop before their entries or files are removed.", parent=self)
        keep = box.addButton("Remove queue entries only, keep files", QMessageBox.ButtonRole.AcceptRole)
        delete = box.addButton("Remove entries and verified job-owned files", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(keep); box.setEscapeButton(QMessageBox.StandardButton.Cancel); box.exec()
        return "list" if box.clickedButton() is keep else "delete" if box.clickedButton() is delete else "cancel"

    def _remove_job(self, job: DownloadJob, delete_files: bool):
        if delete_files: delete_owned_files(job)
        self.jobs.pop(job.id, None); self.database.remove_job(job.id)

    def _selected_or_banner_job(self) -> DownloadJob | None:
        selected = self._selected_jobs()
        if selected: return selected[0]
        if self.selected_job_id in self.jobs: return self.jobs[self.selected_job_id]
        return self.jobs.get(getattr(self, "_banner_job_id", ""))

    def _show_job_banner(self, job: DownloadJob, message: str):
        self.job_account_button.setVisible(job.kind == "media" and (requires_authentication(job.error) or job.failure_code.startswith("auth.")))
        self._banner_job_id = job.id; self.job_banner_text.setText(message); self.job_banner.show()

    def retry_banner_job(self):
        if job := self._selected_or_banner_job(): self._resume([job]); self.job_banner.hide()

    def _job_details_text(self, job: DownloadJob) -> str:
        size = f"{human_bytes(job.downloaded_bytes)} / {human_bytes(job.total_bytes)}"
        subtitles = job.verification.get("subtitles") or job.subtitle_details.get("languages") or []
        warning_text = "\n  - ".join(job.warnings) if job.warnings else "None"
        compatibility = job.compatibility_details
        compatibility_text = (
            f"Compatibility profile: {compatibility.get('profile') or job.options.compatibility}\n"
            f"Final container: {compatibility.get('container') or 'Not verified'}\n"
            f"Video codec: {compatibility.get('video_codec') or 'Not verified'}\n"
            f"Audio codec: {compatibility.get('audio_codec') or 'Not verified'}\n"
            f"Subtitle codec: {compatibility.get('subtitle_codec') or 'Not verified'}\n"
            f"Output compatibility: {'Verified' if compatibility.get('verified') else 'Not verified'}\n")
        tor_text = ""
        if job.effective_connection == "Managed Tor":
            changed = "Yes" if job.tor_circuit_changed else "No" if job.tor_circuit_changed is False else "Unknown"
            tor_text = (f"Tor process: {job.tor_process_state}\nBootstrap: {job.tor_bootstrap}%\n"
                        f"SOCKS: {job.tor_socks_state} — {job.tor_socks_endpoint or 'Unknown'}\n"
                        f"Control: {job.tor_control_endpoint or 'Unknown'}\nTor Internet: {job.tor_internet_state}\n"
                        f"Current exit: {job.tor_current_exit_ip or 'Unknown'}\nPrevious exit: {job.tor_previous_exit_ip or 'Unknown'}\n"
                        f"Circuit changed: {changed}\nCircuit retry: {job.tor_circuit_retry}/{job.tor_circuit_retry_limit}\n"
                        f"Target result: {job.tor_target_result}\nLast circuit change: {job.tor_last_circuit_change or 'Never'}\n")
        return (
            f"Title: {job.item.title}\nSource: {job.item.original_url or job.item.source_url}\n"
            f"Extractor: {job.extractor_key or job.item.source or 'Unknown'}\nStatus: {status_summary(job)}\n"
            f"Failure stage: {job.failure_stage or 'None'}\nMetadata: {'Success' if job.metadata_success else 'Not confirmed'}\n"
            f"Formats: {job.formats_playable} playable / {job.formats_total} total\n"
            f"Authentication: {job.effective_authentication or job.options.authentication_mode}\n"
            f"Connection: {job.effective_connection or 'Unknown'}\nQuality: {job.options.quality}\n"
            f"Container: {job.options.container}\nDestination: {job.output_file or job.options.download_dir}\n"
            f"Current stage: {job.postprocessing_stage or job.status.value}\nProgress: {job.progress:.1f}%\n"
            f"Downloaded: {size}\nSpeed: {human_bytes(job.speed)}/s\nETA: {human_duration(job.eta)}\n"
            f"Embedded subtitles: {', '.join(map(str, subtitles)) if subtitles else 'No'}\n"
            f"Embedded thumbnail: {job.verification.get('thumbnail', 'Not verified')}\n"
            f"{compatibility_text}{tor_text}"
            f"Warnings: {warning_text}\nError: {job.error or 'None'}\nTechnical details: {job.technical_details or 'None'}")

    def _queue_selection_changed(self):
        selected = self._selected_jobs()
        if selected: self.selected_job_id = selected[0].id
        self._refresh_selected_job_details()

    def _refresh_selected_job_details(self):
        job = self.jobs.get(self.selected_job_id)
        text = self._job_details_text(job) if job else ""
        self.job_details.setPlainText(text)
        if self.details_dialog_text is not None:
            self.details_dialog_text.setPlainText(text)
        if not job and self.details_dialog is not None:
            self.details_dialog.setWindowTitle("Download Details — job removed")

    def view_job_details(self):
        if not (job := self._selected_or_banner_job()): return
        self.selected_job_id = job.id
        if self.details_dialog is None:
            dialog = QDialog(self); dialog.setWindowTitle("Download Details"); dialog.resize(650, 520)
            layout = QVBoxLayout(dialog); self.details_dialog_text = QPlainTextEdit(dialog)
            self.details_dialog_text.setReadOnly(True); layout.addWidget(self.details_dialog_text)
            close = QPushButton("Close", dialog); close.clicked.connect(dialog.hide); layout.addWidget(close)
            self.details_dialog = dialog
        self.details_dialog.setWindowTitle(f"Download Details — {job.item.title}")
        self._refresh_selected_job_details(); self.details_dialog.show(); self.details_dialog.raise_()

    def view_job_warnings(self):
        if not (job := self._selected_or_banner_job()): return
        QMessageBox.information(self, "Job Warnings", self._warning_details_text(job))

    def _warning_details_text(self, job: DownloadJob) -> str:
        lines = []
        if job.verification.get("video"): lines.append("✓ Video downloaded")
        if job.verification.get("audio"): lines.append("✓ Audio downloaded")
        if job.verification.get("video") and job.verification.get("audio"): lines.append("✓ Video/audio merged")
        for subtitle in job.verification.get("subtitles") or []: lines.append(f"✓ Subtitle embedded: {subtitle}")
        if job.verification.get("thumbnail") is True: lines.append("✓ Thumbnail embedded")
        if job.verification.get("metadata"): lines.append("✓ Metadata written")
        compatibility = job.compatibility_details
        if compatibility.get("verified"):
            lines.append(f"✓ {compatibility.get('container', 'MP4')} container")
            lines.append(f"✓ Video: {compatibility.get('video_codec', 'verified')}")
            lines.append(f"✓ Audio: {compatibility.get('audio_codec', 'verified')}")
            if job.verification.get("subtitle_count"):
                lines.append(f"✓ Subtitles: {compatibility.get('subtitle_codec', 'mov_text')}")
            if job.verification.get("thumbnail"):
                lines.append("✓ QuickTime-compatible artwork")
            if job.verification.get("faststart"):
                lines.append("✓ MP4 fast start")
        else:
            lines.extend(f"⚠ {risk}" for risk in compatibility.get("risks") or [])
        lines.extend(f"⚠ {warning}" for warning in job.warnings)
        return "\n".join(lines) or "No warnings were recorded."

    def view_job_console(self):
        if not (job := self._selected_or_banner_job()): return
        self.console_job_filter = job.id; self.console_job_label.setText(f"Job: {job.item.title}")
        self.tabs.setCurrentWidget(self.console_tab); self._refresh_console()

    def clear_console_job_filter(self):
        self.console_job_filter = ""; self.console_job_label.setText("All jobs"); self._refresh_console()

    def copy_job_diagnostics(self):
        if job := self._selected_or_banner_job():
            QApplication.clipboard().setText(diagnostics_text(
                job, yt_dlp_version=self.runtime_manager.snapshot().version))
    def open_selected(self):
        for job in self._selected_jobs():
            target = primary_output(job)
            if target and Path(target).exists(): QDesktopServices.openUrl(QUrl.fromLocalFile(target))
    def reveal_selected(self):
        for job in self._selected_jobs():
            target = primary_output(job)
            if target: subprocess.Popen(["open", "-R", target])
    def copy_magnet(self):
        magnets = [job.torrent_source for job in self._selected_jobs() if job.torrent_source.startswith("magnet:?")]
        if magnets: QApplication.clipboard().setText("\n".join(magnets))
    def stop_seeding(self):
        for job in self._selected_jobs():
            if job.kind == "torrent" and job.status == JobStatus.SEEDING:
                job.status = JobStatus.COMPLETED
                if job.id in self.active: self.task_manager.cancel(self.active[job.id])
                self.database.save_job(job)
        self._refresh_queue()
    def clear_completed(self):
        self.database.clear_completed(); self.jobs = {key: job for key, job in self.jobs.items() if job.status not in {JobStatus.COMPLETED, JobStatus.COMPLETED_WARNINGS}}; self._refresh_queue(); self._refresh_history()

    def convert_selected_for_macos(self):
        job = self._selected_or_banner_job()
        if job and job.output_file: self.open_video_converter(job.output_file, quicktime=True)

    def open_video_converter(self, path: object = "", quicktime: bool = False):
        selected_path = path if isinstance(path, str) else ""
        if not hasattr(self, "converter_dialog"):
            dialog = QDialog(self); dialog.setWindowTitle("Convert Media"); dialog.resize(790, 720)
            layout = QFormLayout(dialog)
            self.converter_input = QLineEdit(); choose_in = QPushButton("Choose…")
            choose_in.clicked.connect(self._choose_converter_input); input_row = QHBoxLayout(); input_row.addWidget(self.converter_input); input_row.addWidget(choose_in)
            self.converter_output = QLineEdit(); choose_out = QPushButton("Save As…")
            choose_out.clicked.connect(self._choose_converter_output); output_row = QHBoxLayout(); output_row.addWidget(self.converter_output); output_row.addWidget(choose_out)
            self.converter_profile = QComboBox(); self.converter_profile.addItems(list(PROFILES))
            self.converter_format = QComboBox(); self.converter_format.addItems(list(CONTAINERS))
            self.converter_video = QComboBox(); self.converter_video.addItems(list(VIDEO_CODECS))
            self.converter_audio = QComboBox(); self.converter_audio.addItems(list(AUDIO_CODECS))
            self.converter_quality = QComboBox(); self.converter_quality.addItems(list(QUALITY_LEVELS))
            self.converter_crf = QSpinBox(); self.converter_crf.setRange(0, 51); self.converter_crf.setValue(22)
            quality_row = QHBoxLayout(); quality_row.addWidget(self.converter_quality); quality_row.addWidget(QLabel("CRF")); quality_row.addWidget(self.converter_crf)
            self.converter_resolution = QComboBox(); self.converter_resolution.addItems(list(RESOLUTIONS))
            self.converter_height = QSpinBox(); self.converter_height.setRange(144, 8640); self.converter_height.setValue(1080); self.converter_height.setSuffix(" px high")
            resolution_row = QHBoxLayout(); resolution_row.addWidget(self.converter_resolution); resolution_row.addWidget(self.converter_height)
            self.converter_upscale = QCheckBox("Allow upscaling")
            self.converter_framerate = QComboBox(); self.converter_framerate.addItems(list(FRAME_RATES))
            self.converter_bitrate = QComboBox(); self.converter_bitrate.addItems(list(AUDIO_BITRATES))
            self.converter_subtitles = QComboBox(); self.converter_subtitles.addItems(list(SUBTITLE_MODES))
            self.converter_metadata = QCheckBox("Preserve metadata"); self.converter_chapters = QCheckBox("Preserve chapters"); self.converter_artwork = QCheckBox("Preserve artwork")
            preservation = QHBoxLayout(); preservation.addWidget(self.converter_metadata); preservation.addWidget(self.converter_chapters); preservation.addWidget(self.converter_artwork)
            self.converter_output_mode = QComboBox(); self.converter_output_mode.addItems(["Create new file", "Replace Original"])
            self.converter_result = QPlainTextEdit(); self.converter_result.setReadOnly(True)
            self.converter_progress = QProgressBar(); self.converter_progress.setRange(0, 100)
            controls = QHBoxLayout(); analyse = QPushButton("Analyse"); self.converter_convert = QPushButton("Convert"); close = QPushButton("Close")
            self.converter_convert.setEnabled(False)
            details_button = QPushButton("View Details"); details_button.clicked.connect(self._converter_view_details)
            console_button = QPushButton("Open Console"); console_button.clicked.connect(lambda: self.tabs.setCurrentWidget(self.console_tab))
            analyse.clicked.connect(self._analyse_converter); self.converter_convert.clicked.connect(self._convert_video); close.clicked.connect(dialog.hide)
            controls.addWidget(analyse); controls.addWidget(self.converter_convert); controls.addWidget(details_button); controls.addWidget(console_button); controls.addStretch(); controls.addWidget(close)
            layout.addRow("Input", input_row); layout.addRow("Output", output_row); layout.addRow("Output mode", self.converter_output_mode); layout.addRow("Profile", self.converter_profile)
            layout.addRow("Output Format", self.converter_format); layout.addRow("Video Codec", self.converter_video); layout.addRow("Audio Codec", self.converter_audio)
            layout.addRow("Video Quality", quality_row); layout.addRow("Resolution", resolution_row); layout.addRow("", self.converter_upscale)
            layout.addRow("Frame Rate", self.converter_framerate); layout.addRow("Audio Bitrate", self.converter_bitrate); layout.addRow("Subtitles", self.converter_subtitles)
            layout.addRow("Preservation", preservation)
            layout.addRow("Analysis", self.converter_result); layout.addRow("Progress", self.converter_progress); layout.addRow(controls)
            self.converter_dialog = dialog
            self._converter_updating = False; self._converter_details = None
            self._converter_last_error_details = ""
            self.converter_input.textChanged.connect(self._converter_input_changed)
            self.converter_profile.currentTextChanged.connect(self._converter_profile_changed)
            for widget in (self.converter_format, self.converter_video, self.converter_audio, self.converter_quality,
                           self.converter_resolution, self.converter_framerate, self.converter_bitrate, self.converter_subtitles):
                widget.currentTextChanged.connect(self._converter_manual_changed)
            for widget in (self.converter_crf, self.converter_height): widget.valueChanged.connect(self._converter_manual_changed)
            for widget in (self.converter_upscale, self.converter_metadata, self.converter_chapters, self.converter_artwork): widget.toggled.connect(self._converter_manual_changed)
            self.converter_output_mode.currentTextChanged.connect(self._converter_manual_changed)
            self._converter_apply_options(ConversionOptions(
                profile=self.settings.converter_profile, container=self.settings.converter_container,
                video_codec=self.settings.converter_video_codec, audio_codec=self.settings.converter_audio_codec,
                subtitle_mode=self.settings.converter_subtitle_mode, quality=self.settings.converter_quality,
                resolution=self.settings.converter_resolution, frame_rate=self.settings.converter_frame_rate,
                audio_bitrate=self.settings.converter_audio_bitrate))
        if quicktime:
            self._converter_apply_options(preset_options("macOS / QuickTime"))
        if selected_path:
            self.converter_input.setText(selected_path)
            self.converter_output.setText(default_conversion_output(selected_path, self.converter_format.currentText()))
        self.converter_dialog.show(); self.converter_dialog.raise_()

    def _converter_options(self) -> ConversionOptions:
        return ConversionOptions(
            profile=self.converter_profile.currentText(), container=self.converter_format.currentText(),
            video_codec=self.converter_video.currentText(), audio_codec=self.converter_audio.currentText(),
            subtitle_mode=self.converter_subtitles.currentText(), quality=self.converter_quality.currentText(),
            custom_crf=self.converter_crf.value(), resolution=self.converter_resolution.currentText(),
            custom_height=self.converter_height.value(), allow_upscaling=self.converter_upscale.isChecked(),
            frame_rate=self.converter_framerate.currentText(), audio_bitrate=self.converter_bitrate.currentText(),
            preserve_metadata=self.converter_metadata.isChecked(), preserve_chapters=self.converter_chapters.isChecked(),
            preserve_artwork=self.converter_artwork.isChecked(), replace_original=self.converter_output_mode.currentText() == "Replace Original")

    def _converter_apply_options(self, options: ConversionOptions):
        self._converter_updating = True
        try:
            for widget, value in ((self.converter_profile, options.profile), (self.converter_format, options.container),
                                  (self.converter_video, options.video_codec), (self.converter_audio, options.audio_codec),
                                  (self.converter_subtitles, options.subtitle_mode), (self.converter_quality, options.quality),
                                  (self.converter_resolution, options.resolution), (self.converter_framerate, options.frame_rate),
                                  (self.converter_bitrate, options.audio_bitrate)): widget.setCurrentText(value)
            self.converter_crf.setValue(options.custom_crf); self.converter_height.setValue(options.custom_height)
            self.converter_upscale.setChecked(options.allow_upscaling); self.converter_metadata.setChecked(options.preserve_metadata)
            self.converter_chapters.setChecked(options.preserve_chapters); self.converter_artwork.setChecked(options.preserve_artwork)
            self.converter_output_mode.setCurrentText("Replace Original" if options.replace_original else "Create new file")
        finally: self._converter_updating = False
        if self.converter_output.text():
            self.converter_output.setText(output_with_container(self.converter_output.text(), options.container))
        self._converter_update_controls()

    def _converter_input_changed(self, *_):
        self._converter_details = None
        if hasattr(self, "converter_convert"): self.converter_convert.setEnabled(False)

    def _converter_profile_changed(self, profile: str):
        if self._converter_updating or profile == "Custom": return
        self._converter_apply_options(preset_options(profile, self._converter_options()))
        self._converter_refresh_plan()

    def _converter_manual_changed(self, *_):
        if self._converter_updating: return
        if self.sender() is not self.converter_profile and self.converter_profile.currentText() != "Custom":
            self._converter_updating = True; self.converter_profile.setCurrentText("Custom"); self._converter_updating = False
        if self.sender() is self.converter_format and self.converter_output.text():
            self.converter_output.setText(output_with_container(self.converter_output.text(), self.converter_format.currentText()))
        self._converter_update_controls(); self._converter_refresh_plan()

    def _converter_update_controls(self):
        custom_quality = self.converter_quality.currentText() == "Custom CRF"
        self.converter_crf.setEnabled(custom_quality)
        self.converter_height.setEnabled(self.converter_resolution.currentText() == "Custom")
        self.converter_bitrate.setEnabled(self.converter_audio.currentText() not in {"Copy", "FLAC"})
        available = detect_ffmpeg_encoders()
        for combo, names in ((self.converter_video, VIDEO_CODECS), (self.converter_audio, AUDIO_CODECS)):
            for index, name in enumerate(names):
                if name not in {"Auto", "Copy"}: combo.model().item(index).setEnabled(available.get(name, False))

    def _converter_refresh_plan(self):
        if not self._converter_details: return
        plan = build_conversion_plan(self._converter_details, self._converter_options(), detect_ffmpeg_encoders())
        self.converter_result.setPlainText(format_analysis(self._converter_details, plan))
        self.converter_convert.setEnabled(plan.valid)

    def _choose_converter_input(self):
        chosen = QFileDialog.getOpenFileName(self, "Choose Media", self.settings.converter_output_dir, "Media files (*.mp4 *.mov *.m4v *.mkv *.webm *.avi);;All files (*)")[0]
        if chosen: self.converter_input.setText(chosen); self.converter_output.setText(default_conversion_output(chosen, self.converter_format.currentText()))

    def _choose_converter_output(self):
        extension = {"MP4": "mp4", "MOV": "mov", "M4V": "m4v", "MKV": "mkv", "WebM": "webm"}[self.converter_format.currentText()]
        chosen = QFileDialog.getSaveFileName(self, "Save Converted Media", self.converter_output.text(), f"{self.converter_format.currentText()} media (*.{extension})")[0]
        if chosen: self.converter_output.setText(output_with_container(chosen, self.converter_format.currentText()))

    def _analyse_converter(self):
        path, options = self.converter_input.text().strip(), self._converter_options()
        if not path: return
        self.converter_progress.setValue(0); self.converter_result.setPlainText("Analysing…")
        self.console_store.append("CONVERT", "Analysing local file")
        self.task_manager.start("local-converter-analysis", lambda _cancel, _progress, p=path, o=options: analyse_local_video(p, o),
                                on_result=self._converter_analysis_ready, on_error=self._converter_error)

    def _converter_analysis_ready(self, result: object):
        if not isinstance(result, dict): return
        self._converter_details = result["details"]; self.converter_result.setPlainText(str(result["analysis_text"]))
        self.converter_convert.setEnabled(bool(result["plan"]["valid"])); self.converter_progress.setValue(10)
        self.console_store.append("PLAN", f"{result['plan']['mode']} — {self.converter_format.currentText()}")

    def _convert_video(self):
        source, output, options = self.converter_input.text().strip(), self.converter_output.text().strip(), self._converter_options()
        if not source or not output: return
        if not self._converter_details:
            self.converter_result.setPlainText("Analyse the input before converting."); self.converter_convert.setEnabled(False); return
        plan = build_conversion_plan(self._converter_details, options, detect_ffmpeg_encoders())
        if not plan.valid:
            self.converter_result.setPlainText(format_analysis(self._converter_details, plan)); self.converter_convert.setEnabled(False); return
        self.settings.converter_profile = options.profile; self.settings.converter_container = options.container
        self.settings.converter_video_codec = options.video_codec; self.settings.converter_audio_codec = options.audio_codec
        self.settings.converter_subtitle_mode = options.subtitle_mode; self.settings.converter_quality = options.quality
        self.settings.converter_resolution = options.resolution; self.settings.converter_frame_rate = options.frame_rate
        self.settings.converter_audio_bitrate = options.audio_bitrate; self.settings.converter_output_dir = str(Path(output).parent)
        self.settings_store.save(self.settings)
        self.console_store.append("FFMPEG", "Starting conversion")
        self.converter_convert.setEnabled(False)
        self.task_manager.start("local-converter", lambda _cancel, report, s=source, o=output, p=options: convert_local_video(s, o, p, report),
                                on_result=self._converter_ready, on_progress=self._converter_progress_ready, on_error=self._converter_error)

    def _converter_progress_ready(self, payload: object):
        if isinstance(payload, dict):
            value = int(payload.get("progress") or 0); self.converter_progress.setValue(value)
            extras = []
            if payload.get("elapsed") is not None: extras.append(f"Elapsed {human_duration(float(payload['elapsed']))}")
            if payload.get("fps"): extras.append(f"{payload['fps']} fps")
            if payload.get("eta") is not None: extras.append(f"ETA {human_duration(float(payload['eta']))}")
            if payload.get("speed"): extras.append(str(payload["speed"]))
            self.converter_progress.setFormat(f"{value}%" + (" • " + " • ".join(extras) if extras else ""))
            self.console_store.append("CONVERT", str(payload.get("stage") or "Converting"))

    def _converter_ready(self, result: object):
        if not isinstance(result, dict): return
        conversions = "; ".join(result.get("conversions") or ["Remuxed"])
        self.converter_result.appendPlainText(f"\nCompleted: {result['output']}\n{conversions}\nFinal size: {human_bytes(result.get('final_size', 0))}\nffprobe verification: Passed")
        self.converter_progress.setValue(100); self.converter_convert.setEnabled(True)
        self.console_store.append("VERIFY", f"{self.converter_format.currentText()} output valid")
        self.console_store.append("COMPLETE", f"Converted media: {result['output']}")

    def _converter_error(self, message: str, _details: str):
        self._converter_last_error_details = _details
        self.converter_result.appendPlainText(f"\nFailed: {message}\nUse View Details or open Console for diagnostics.")
        if hasattr(self, "converter_convert"): self.converter_convert.setEnabled(True)
        self.console_store.append("CONVERT", message, level="error")

    def _converter_view_details(self):
        text = self._converter_last_error_details or self.converter_result.toPlainText() or "No conversion details are available yet."
        box = QMessageBox(QMessageBox.Icon.Information, "Conversion Details", "Converter diagnostics", parent=self)
        box.setDetailedText(text); box.exec()

    def _history_selected_job(self) -> DownloadJob | None:
        rows = self.history_table.selectionModel().selectedRows()
        if not rows: return None
        item = self.history_table.item(rows[0].row(), 0); job_id = item.data(Qt.ItemDataRole.UserRole) if item else ""
        return self.jobs.get(job_id) or next((j for j in self.database.search_history() if j.id == job_id), None)

    def _history_context_menu(self, position):
        job = self._history_selected_job()
        if not job: return
        menu = QMenu(self.history_table)
        def select(): self.selected_job_id = job.id; self.jobs.setdefault(job.id, job)
        menu.addAction("Open File", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(job.output_file)))
        menu.addAction("Reveal in Finder", lambda: subprocess.Popen(["open", "-R", job.output_file]))
        menu.addAction("View Details", lambda: (select(), self.view_job_details()))
        menu.addAction("View Warnings", lambda: (select(), self.view_job_warnings()))
        menu.addAction("View Console", lambda: (select(), self.view_job_console()))
        menu.addAction("Convert for macOS / QuickTime", lambda: self.open_video_converter(job.output_file, quicktime=True))
        menu.addAction("Convert As…", lambda: self.open_video_converter(job.output_file))
        menu.exec(self.history_table.viewport().mapToGlobal(position))

    def _refresh_queue(self, *_):
        if not hasattr(self, "queue_table"): return
        view = self.queue_filter.currentText() if hasattr(self, "queue_filter") else "Media"
        columns = {
            "Media": ["Title", "Source", "Status", "Progress", "Downloaded / Total", "Speed", "ETA", "Format", "Destination"],
            "Torrents": ["Title", "Status", "Progress", "Downloaded / Total", "Down", "Up", "Connected peers", "Connected seeders", "ETA", "Destination"],
            "All": ["Title", "Type", "Status", "Progress", "Speed", "ETA", "Destination"],
        }[view]
        jobs = [job for job in self.jobs.values() if view == "All" or (view == "Torrents") == (job.kind == "torrent")]
        self.queue_empty.setVisible(not jobs)
        old_ids = [self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                   for row in range(self.queue_table.rowCount()) if self.queue_table.item(row, 0)]
        old_columns = [self.queue_table.horizontalHeaderItem(i).text()
                       for i in range(self.queue_table.columnCount()) if self.queue_table.horizontalHeaderItem(i)]
        structural = old_columns != columns or old_ids != [job.id for job in jobs]
        vertical = self.queue_table.verticalScrollBar().value()
        horizontal = self.queue_table.horizontalScrollBar().value()
        focus = QApplication.focusWidget()
        self.queue_table.blockSignals(True)
        if structural:
            self.queue_table.clear(); self.queue_table.setColumnCount(len(columns)); self.queue_table.setHorizontalHeaderLabels(columns)
            self.queue_table.setRowCount(len(jobs)); header = self.queue_table.horizontalHeader()
            # Continuous ResizeToContents re-measures every row for each changed
            # status cell, producing quadratic synchronous work on large queues.
            for index in range(len(columns)): header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            if "Destination" in columns: header.setSectionResizeMode(columns.index("Destination"), QHeaderView.ResizeMode.Stretch)
        for row, job in enumerate(jobs):
            size = f"{human_bytes(job.downloaded_bytes)} / {human_bytes(job.total_bytes)}" if job.total_bytes else human_bytes(job.downloaded_bytes)
            format_name = "BitTorrent" if job.kind == "torrent" else (job.options.audio_format if job.options.audio_format != "Original/best audio" else f"{job.options.quality} / {job.options.container}")
            if job.status == JobStatus.FAILED:
                retained = f" • {job.progress:.1f}% • {human_bytes(job.downloaded_bytes)} retained" if job.downloaded_bytes else ""
                status_text = status_summary(job) + retained
            elif job.status == JobStatus.COMPLETED_WARNINGS: status_text = "Completed with warnings ⚠"
            elif job.status in {JobStatus.DOWNLOADING, JobStatus.CONVERTING} and job.postprocessing_stage: status_text = job.postprocessing_stage
            else: status_text = job.status.value
            values = {
                "Title": job.item.title, "Source": job.item.source, "Type": "Torrent" if job.kind == "torrent" else "Media",
                "Status": status_text, "Downloaded / Total": size,
                "Speed": f"{human_bytes(job.speed)}/s" if job.speed else "—",
                "Down": f"{human_bytes(job.speed)}/s" if job.speed else "—",
                "Up": f"{human_bytes(job.upload_speed)}/s" if job.upload_speed else "—",
                "Connected peers": str(job.peers), "Connected seeders": str(job.seeds),
                "ETA": human_duration(job.eta), "Format": format_name,
                "Destination": job.output_file or job.options.download_dir,
            }
            for column, name in enumerate(columns):
                if name == "Progress":
                    bar = self.queue_table.cellWidget(row, column)
                    if not isinstance(bar, QProgressBar):
                        bar = QProgressBar(); bar.setRange(0, 1000); self.queue_table.setCellWidget(row, column, bar)
                    bar.setValue(int(job.progress * 10)); bar.setFormat(f"{job.progress:.1f}%"); continue
                item = self.queue_table.item(row, column)
                if item is None:
                    item = QTableWidgetItem(); self.queue_table.setItem(row, column, item)
                item.setText(values[name])
                if column == 0: item.setData(Qt.ItemDataRole.UserRole, job.id)
            first = self.queue_table.item(row, 0)
            if job.kind == "torrent":
                discovery = (f"Peer Discovery\nTrackers: {job.original_tracker_count} original + "
                             f"{job.additional_tracker_count} additional\n"
                             f"DHT/PEX/Local Discovery: {'Disabled (private torrent)' if job.torrent_private else 'Configured in Settings'}")
                first.setToolTip(discovery)
            else:
                subtitle = f"Embed {job.options.subtitle_language}" if job.options.embed_subtitles else "Off"
                thumbnail = "Embed" if job.options.embed_thumbnail else "Off"
                effective = job.effective_authentication or job.options.authentication_mode
                verification = ""
                if job.verification:
                    verification = (f"\nVerified video: {job.verification.get('video')}"
                                    f"\nVerified audio: {job.verification.get('audio')}"
                                    f"\nEmbedded subtitles: {job.verification.get('subtitle_count')}"
                                    f"\nEmbedded thumbnail: {job.verification.get('thumbnail')}"
                                    f"\nMetadata: {job.verification.get('metadata')}")
                first.setToolTip(
                    f"Quality: {job.options.quality}\nContainer: {job.options.container}"
                    f"\nAuthentication: {effective}\nConnection: {self.settings.connection_mode}"
                    f"\nThumbnail: {thumbnail}\nSubtitles: {subtitle}{verification}")
        if structural:
            for column, name in enumerate(columns):
                if name not in {"Title", "Destination"}: self.queue_table.resizeColumnToContents(column)
        if self.selected_job_id:
            selected_row = next((row for row, job in enumerate(jobs) if job.id == self.selected_job_id), -1)
            if selected_row >= 0 and not self.queue_table.selectionModel().isRowSelected(
                    selected_row, self.queue_table.rootIndex()):
                self.queue_table.selectRow(selected_row)
        self.queue_table.blockSignals(False)
        self.queue_table.verticalScrollBar().setValue(vertical)
        self.queue_table.horizontalScrollBar().setValue(horizontal)
        if focus is not None and structural: focus.setFocus()
        if self.selected_job_id and self.selected_job_id not in self.jobs:
            self.selected_job_id = ""
        self._refresh_selected_job_details()

    def _refresh_history(self, *_):
        if not hasattr(self, "history_table"): return
        jobs = self.database.search_history(self.history_search.text(), self.history_filter.currentText())
        self.history_empty.setVisible(not jobs)
        self.history_empty.setText("No matching history. Try another search or status filter." if self.history_search.text() or self.history_filter.currentText() != "All" else "No history yet. Completed downloads will appear here.")
        self.history_table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            values = [job.created_at[:19].replace("T", " "), job.item.title, job.item.original_url, job.item.source_url, job.output_file, job.options.audio_format if job.options.audio_format != "Original/best audio" else job.options.quality, job.status.value]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0: item.setData(Qt.ItemDataRole.UserRole, job.id)
                self.history_table.setItem(row, column, item)

    def choose_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose download folder", self.folder.text())
        if chosen: self.folder.setText(chosen); self._persist_settings()

    def open_torrent(self):
        chosen = QFileDialog.getOpenFileName(self, "Open Torrent", self.settings.torrent_download_dir, "Torrent files (*.torrent)")[0]
        if chosen:
            self.tabs.setCurrentIndex(0); self.input.setPlainText(chosen); self.analyse()

    def show_preferences(self):
        self.tabs.setCurrentWidget(self.settings_panel)

    def show_youtube_account(self):
        self.show_preferences()
        self.settings_panel.sidebar.setCurrentRow(list(self.settings_panel.pages).index("Accounts"))
        self.settings_panel.connect_youtube.setFocus()

    def _apply_account_choice(self, mode: str) -> AppSettings:
        if mode not in {"YouTube Companion", "None"}: raise ValueError("Unsupported account action")
        updated = copy.deepcopy(self.settings)
        updated.authentication_mode = mode; updated.cookies_file = ""
        # Persist first: failure must not be described as an activated choice.
        self.settings_store.save(updated)
        self.settings = updated
        self._inspection_generation += 1
        return copy.deepcopy(updated)

    def _apply_settings(self, settings: AppSettings, proxy_passwords: object):
        self._inspection_generation += 1
        self.settings = settings
        supplied = proxy_passwords if isinstance(proxy_passwords, dict) else {"legacy": str(proxy_passwords or "")}
        for kind, username in (("http", settings.http_proxy_username), ("socks", settings.socks_proxy_username)):
            password = str(supplied.get(kind) or "")
            account = f"{kind}:{username}" if username else ""
            if password and account:
                save_proxy_password(account, password); self.proxy_passwords[account] = password
        self.managed_tor.browser_path = settings.tor_browser_path
        self.folder.setText(settings.download_dir); self.template.setCurrentText(settings.filename_template)
        self.compatibility.setCurrentText(settings.compatibility); self.quality.setCurrentText(settings.quality); self.container.setCurrentText(settings.container)
        self.audio_format.setCurrentText(settings.audio_format); self.audio_bitrate.setCurrentText(settings.audio_bitrate)
        self.embed_thumb.setChecked(settings.embed_thumbnail); self.embed_meta.setChecked(settings.embed_metadata)
        self.embed_chapters.setChecked(settings.embed_chapters); self.embed_subtitles.setChecked(settings.embed_subtitles)
        self.write_subtitles.setChecked(settings.write_subtitles); self.keep_original.setChecked(settings.keep_original)
        self.subtitle_language.setText(settings.subtitle_languages); self.subtitle_source.setCurrentText(settings.subtitle_source)
        self.verify_postprocessing.setChecked(settings.verify_postprocessing)
        self.connection_selector.blockSignals(True); self.connection_selector.setCurrentText(settings.connection_mode); self.connection_selector.blockSignals(False)
        self.settings_store.save(settings); self._apply_theme(); self._update_provider_status()
        if settings.yt_dlp_check_updates_on_startup:
            if not self.startup_timer.isActive(): self.startup_timer.start(250)
        else:
            self.startup_timer.stop()
        self._refresh_connection_status()
        if settings.connection_mode == "Managed Tor" and settings.managed_tor_auto_start and self.managed_tor.state == "Stopped":
            self.managed_tor.start()

    def _update_provider_status(self):
        base_url, server_home = self.settings.provider_base_url, self.settings.provider_server_home
        self.task_manager.start("provider-check", lambda _cancel, _progress, u=base_url, h=server_home: check_provider(u, h),
                                on_result=self._provider_status_ready)

    def _provider_status_ready(self, result):
        color = {"available": "#2e9b45", "not_running": "#c28a00", "error": "#c0392b"}.get(result.state, "#777")
        self.provider_label.setText(f"● PO provider: {result.mode or result.state}"); self.provider_label.setStyleSheet(f"color: {color}"); self.provider_label.setToolTip(result.detail)
        if hasattr(self, "runtime_label"):
            self.runtime_label.setText(f"● yt-dlp {self.runtime_manager.snapshot().version}")
        self.console_store.append("APP", f"PO-token provider: {result.mode or result.state} — {result.detail}",
                                  level="info" if result.state == "available" else "warning")

    def _start_yt_dlp_update_check(self):
        if not self.settings.yt_dlp_check_updates_on_startup:
            self.startup_timer.stop()
            return
        self.startup_timer.start(3_600_000)
        auto_install = self.settings.yt_dlp_auto_install_updates
        manager = self.runtime_manager
        self.task_manager.start("yt-runtime", lambda _cancel, _progress, m=manager: m.check_and_update(auto_install, automatic=True),
                                on_result=self._yt_update_ready)
        self.settings_panel._refresh_components(check=True, automatic=True)

    def _yt_update_ready(self, _result: object):
        self._update_provider_status()
        self.settings_panel._refresh_runtime_status()
        self.runtime_label.setText(f"● yt-dlp {self.runtime_manager.snapshot().version}")
        self.console_store.append("APP", f"yt-dlp runtime ready: {self.runtime_manager.snapshot().version}")

    def _persist_settings(self):
        self.settings.download_dir = self.folder.text().strip(); self.settings.compatibility = self.compatibility.currentText(); self.settings.quality = self.quality.currentText(); self.settings.container = self.container.currentText(); self.settings.audio_format = self.audio_format.currentText(); self.settings.audio_bitrate = self.audio_bitrate.currentText(); self.settings.filename_template = self.template.currentText()
        self.settings.embed_thumbnail = self.embed_thumb.isChecked(); self.settings.embed_metadata = self.embed_meta.isChecked(); self.settings.embed_chapters = self.embed_chapters.isChecked(); self.settings.embed_subtitles = self.embed_subtitles.isChecked(); self.settings.write_subtitles = self.write_subtitles.isChecked(); self.settings.keep_original = self.keep_original.isChecked(); self.settings.subtitle_languages = self.subtitle_language.text().strip(); self.settings.subtitle_source = self.subtitle_source.currentText(); self.settings.verify_postprocessing = self.verify_postprocessing.isChecked()
        self.settings.playlist_panel_sizes = (self.playlist_splitter.sizes() if self.preview_section.toggle.isChecked()
                                               else list(self._expanded_preview_sizes))
        self.settings.playlist_options_expanded = self.options_section.toggle.isChecked()
        self.settings.playlist_preview_expanded = self.preview_section.toggle.isChecked()
        geometry = self.normalGeometry() if self.isFullScreen() or self.isMaximized() else self.geometry()
        if self.settings.remember_window_size:
            self.settings.window_width = geometry.width(); self.settings.window_height = geometry.height()
        if self.settings.remember_window_position:
            self.settings.window_x = geometry.x(); self.settings.window_y = geometry.y()
        self.settings_store.save(self.settings)

    def _apply_theme(self):
        apply_theme(QApplication.instance(), self.settings.theme)

    def _system_appearance_changed(self, *_):
        if self.isVisible() and self.settings.theme == "System": self._apply_theme()

    def _initial_checks(self):
        if self.settings.show_first_run_diagnostics and not self.settings.first_run_complete:
            self._start_diagnostics(True)

    def show_component_status(self):
        self._start_diagnostics(False)

    def _start_diagnostics(self, first_run: bool):
        settings, manager = copy.deepcopy(self.settings), self.runtime_manager
        self.task_manager.start("diagnostics", lambda _cancel, _progress, s=settings, m=manager: run_checks(s, m),
                                on_result=self._first_run_diagnostics_ready if first_run else self._diagnostics_ready)

    def _diagnostics_ready(self, results):
        SetupDialog(self.settings, self, self.runtime_manager, results).exec()

    def _first_run_diagnostics_ready(self, results):
        self._diagnostics_ready(results)
        self.settings.first_run_complete = True; self.settings_store.save(self.settings)

    def closeEvent(self, event):
        if not self._closing:
            self._closing = True
            self._persist_settings()
            for timer in self.findChildren(QTimer):
                timer.stop()
            for job_id in list(self.active):
                job = self.jobs.get(job_id)
                if job:
                    job.status = JobStatus.INTERRUPTED
                    self.database.save_job(job)
            if self.settings.managed_tor_stop_on_exit:
                self.managed_tor.stop()
        if not self.task_manager.shutdown(10_000):
            event.ignore()
            self.statusBar().showMessage("Waiting for background tasks to stop safely…")
            if not hasattr(self, "shutdown_retry_timer"):
                self.shutdown_retry_timer = QTimer(self); self.shutdown_retry_timer.setSingleShot(True); self.shutdown_retry_timer.timeout.connect(self.close)
            self.shutdown_retry_timer.start(250)
            return
        self.database.close()
        try: self.clean_marker.unlink(missing_ok=True)
        except OSError: pass
        event.accept()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "fullscreen_action"):
            self.fullscreen_action.setChecked(self.isFullScreen())
