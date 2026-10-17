from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox, QStackedWidget, QGroupBox,
    QVBoxLayout, QWidget,
)

from .auth import YOUTUBE_ROBOTS_URL, browser_profiles, discover_browsers, verify_youtube_connection, YouTubeConnection
from .network import ProxyConfig, detect_tor
from .keychain import load_proxy_password
from .managed_tor import ManagedTor, tor_executable
from .network import test_tor_proxy
from .paths import find_binary, logs_dir
from .provider import check_provider
from .settings import AppSettings
from .tasks import TaskManager
from .torrent import format_aria2_diagnostic, inspect_aria2c
from .yt_runtime import YtDlpRuntimeManager, get_runtime_manager


def _combo(values: list[str], current: str) -> QComboBox:
    widget = QComboBox(); widget.addItems(values); widget.setCurrentText(current); return widget


class SettingsWindow(QDialog):
    def __init__(self, settings: AppSettings, tor: ManagedTor, apply_callback: Callable[[AppSettings, object], None],
                 parent=None, runtime_manager: YtDlpRuntimeManager | None = None,
                 task_manager: TaskManager | None = None, embedded: bool = False):
        super().__init__(parent)
        self.original = settings; self.working = copy.deepcopy(settings); self.tor = tor; self.apply_callback = apply_callback
        self.runtime_manager = runtime_manager or get_runtime_manager()
        self.task_manager = task_manager or TaskManager(self)
        self.embedded = embedded
        if not self.runtime_manager.initialized: self.runtime_manager.initialize()
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle("Settings"); self.resize(790, 610)
        outer = QVBoxLayout(self); body = QHBoxLayout(); self.sidebar = QListWidget(); self.sidebar.setFixedWidth(150)
        self.stack = QStackedWidget(); body.addWidget(self.sidebar); body.addWidget(self.stack, 1); outer.addLayout(body, 1)
        self.pages = {}
        for name, builder in [("General", self._general), ("Downloads", self._downloads), ("Network", self._network),
                              ("Accounts", self._authentication), ("Torrents", self._torrents), ("Advanced", self._advanced)]:
            self.sidebar.addItem(name); page = builder(); self.pages[name] = page; self.stack.addWidget(page)
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex); self.sidebar.setCurrentRow(0)
        standard = QDialogButtonBox.StandardButton.Apply if embedded else (
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Ok)
        self.buttons = QDialogButtonBox(standard)
        if not embedded: self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        if not embedded: self.buttons.accepted.connect(self._ok)
        outer.addWidget(self.buttons)
        self.timer = QTimer(self); self.timer.timeout.connect(self._refresh_tor_state); self.timer.start(250)

    @staticmethod
    def _page() -> tuple[QWidget, QFormLayout]:
        page = QWidget(); form = QFormLayout(page); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); return page, form

    def _general(self):
        page, form = self._page(); self.theme = _combo(["System", "Light", "Dark"], self.working.theme)
        self.remember_size = QCheckBox(); self.remember_size.setChecked(self.working.remember_window_size)
        self.remember_position = QCheckBox(); self.remember_position.setChecked(self.working.remember_window_position)
        self.show_diagnostics = QCheckBox(); self.show_diagnostics.setChecked(self.working.show_first_run_diagnostics)
        self.clipboard_detection = QCheckBox(); self.clipboard_detection.setChecked(self.working.clipboard_url_detection)
        form.addRow("Theme", self.theme); form.addRow("Detect supported URLs copied to clipboard", self.clipboard_detection); form.addRow("Remember window size", self.remember_size); form.addRow("Remember window position", self.remember_position); form.addRow("Show first-run diagnostics on startup", self.show_diagnostics)
        return page

    def _downloads(self):
        page, form = self._page(); self.download_dir = QLineEdit(self.working.download_dir); choose = QPushButton("Choose…"); choose.clicked.connect(lambda: self._choose_directory(self.download_dir))
        row = QHBoxLayout(); row.addWidget(self.download_dir); row.addWidget(choose)
        self.filename = QLineEdit(self.working.filename_template); self.quality = _combo(["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"], self.working.quality)
        self.compatibility = _combo(["macOS / QuickTime", "Universal", "Original / Best Available"], self.working.compatibility)
        self.container = _combo(["Auto", "MP4", "MKV", "WebM"], self.working.container); self.audio_format = _combo(["Original/best audio", "MP3", "M4A", "OPUS", "FLAC", "WAV"], self.working.audio_format)
        self.audio_bitrate = _combo(["Auto", "128 kbps", "192 kbps", "256 kbps", "320 kbps"], self.working.audio_bitrate)
        self.concurrency = QSpinBox(); self.concurrency.setRange(1, 4); self.concurrency.setValue(self.working.concurrent_downloads)
        self.subfolders = _combo(["Never", "Auto", "Always for multi-file jobs"], self.working.create_subfolders)
        form.addRow("Default download folder", row); form.addRow("Create subfolders", self.subfolders); form.addRow("Filename template", self.filename); form.addRow("Compatibility", self.compatibility); form.addRow("Video quality", self.quality); form.addRow("Container", self.container); form.addRow("Audio format", self.audio_format); form.addRow("Audio bitrate", self.audio_bitrate); form.addRow("Concurrent downloads", self.concurrency)
        self.embed_thumbnail, self.embed_metadata, self.embed_chapters = QCheckBox(), QCheckBox(), QCheckBox()
        self.embed_subtitles, self.write_subtitles, self.keep_original = QCheckBox(), QCheckBox(), QCheckBox()
        for widget, value, label in [(self.embed_thumbnail, self.working.embed_thumbnail, "Embed thumbnail"), (self.embed_metadata, self.working.embed_metadata, "Embed metadata"), (self.embed_chapters, self.working.embed_chapters, "Embed chapters"), (self.embed_subtitles, self.working.embed_subtitles, "Embed subtitles"), (self.write_subtitles, self.working.write_subtitles, "Keep external subtitle files"), (self.keep_original, self.working.keep_original, "Keep temporary/original files")]:
            widget.setChecked(value); form.addRow(label, widget)
        self.languages = QLineEdit(self.working.subtitle_languages); form.addRow("Subtitle languages", self.languages)
        self.subtitle_source = _combo(["Normal subtitles", "Normal + automatic captions", "Automatic captions only"], self.working.subtitle_source)
        self.verify_postprocessing = QCheckBox(); self.verify_postprocessing.setChecked(self.working.verify_postprocessing)
        form.addRow("Subtitle source", self.subtitle_source); form.addRow("Verify post-processing results", self.verify_postprocessing)
        return page

    def _network(self):
        page, form = self._page(); self.connection = _combo(["Direct / Normal Network", "System / Proton VPN", "Managed Tor", "External Tor", "Custom HTTP Proxy", "Custom SOCKS5 Proxy"], self.working.connection_mode)
        self.tor_path = QLineEdit(self.working.tor_browser_path); choose = QPushButton("Choose Tor Browser…"); choose.clicked.connect(self._choose_tor)
        tor_row = QHBoxLayout(); tor_row.addWidget(self.tor_path); tor_row.addWidget(choose)
        self.tor_auto = QCheckBox(); self.tor_auto.setChecked(self.working.managed_tor_auto_start); self.tor_stop = QCheckBox(); self.tor_stop.setChecked(self.working.managed_tor_stop_on_exit)
        self.tor_state = QLabel(); controls = QHBoxLayout()
        for text, callback in [("Start Tor", self._start_tor), ("Stop Tor", self.tor.stop), ("Restart Tor", self.tor.restart), ("New Tor Circuit", self._new_tor_circuit), ("Test", self._test_tor)]:
            button = QPushButton(text); button.clicked.connect(callback); controls.addWidget(button)
        self.http_proxy_host = QLineEdit(self.working.http_proxy_host or self.working.proxy_host); self.http_proxy_port = QSpinBox(); self.http_proxy_port.setRange(0, 65535); self.http_proxy_port.setValue(self.working.http_proxy_port or self.working.proxy_port)
        self.http_proxy_username = QLineEdit(self.working.http_proxy_username or self.working.proxy_username); self.http_proxy_password = QLineEdit(); self.http_proxy_password.setPlaceholderText("Leave blank to keep Keychain password"); self.http_proxy_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.socks_proxy_host = QLineEdit(self.working.socks_proxy_host or self.working.proxy_host); self.socks_proxy_port = QSpinBox(); self.socks_proxy_port.setRange(0, 65535); self.socks_proxy_port.setValue(self.working.socks_proxy_port or self.working.proxy_port)
        self.socks_proxy_username = QLineEdit(self.working.socks_proxy_username or self.working.proxy_username); self.socks_proxy_password = QLineEdit(); self.socks_proxy_password.setPlaceholderText("Leave blank to keep Keychain password"); self.socks_proxy_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Default connection", self.connection); form.addRow("Managed Tor Browser path", tor_row); form.addRow("Automatically start Managed Tor", self.tor_auto); form.addRow("Stop Managed Tor when app closes", self.tor_stop); form.addRow("Managed Tor state", self.tor_state); form.addRow("", controls)
        form.addRow("Custom HTTP host", self.http_proxy_host); form.addRow("Custom HTTP port", self.http_proxy_port); form.addRow("Custom HTTP username", self.http_proxy_username); form.addRow("Custom HTTP password (Keychain)", self.http_proxy_password)
        form.addRow("Custom SOCKS5 host", self.socks_proxy_host); form.addRow("Custom SOCKS5 port", self.socks_proxy_port); form.addRow("Custom SOCKS5 username", self.socks_proxy_username); form.addRow("Custom SOCKS5 password (Keychain)", self.socks_proxy_password)
        self._refresh_tor_state(); return page

    def _authentication(self):
        self._auth_generation = 0
        self._auth_busy = False
        page, form = self._page(); self.auth_mode = _combo(["Auto", "None", "Browser Cookies", "Imported cookies.txt"], self.working.authentication_mode)
        self.browser = _combo(["Chrome", "Chromium", "Firefox", "Safari", "Edge"], self.working.cookies_browser)
        self.profile = QComboBox(); self.profile.setEditable(True)
        self.cookies_file = QLineEdit(self.working.cookies_file)
        self.cookies_choose = QPushButton("Choose cookies.txt…"); self.cookies_choose.clicked.connect(self._choose_cookies); file_row = QHBoxLayout(); file_row.addWidget(self.cookies_file); file_row.addWidget(self.cookies_choose)
        self.auth_test = QPushButton("Verify Connection"); self.auth_test.clicked.connect(self._test_auth)
        self.auth_status = QLabel("Not verified — connect a browser to get started."); self.auth_status.setWordWrap(True)
        self.connect_youtube = QPushButton("Connect YouTube"); self.connect_youtube.clicked.connect(self._connect_youtube)
        self.disconnect_youtube = QPushButton("Disconnect"); self.disconnect_youtube.clicked.connect(self._disconnect_youtube)
        self.sign_in = QPushButton("Sign in using browser…"); self.sign_in.clicked.connect(self._open_youtube_browser)
        self.refresh_browsers = QPushButton("Detect Browsers"); self.refresh_browsers.clicked.connect(self._detect_browsers)
        self.browser_status = QLabel(); self.browser_status.setWordWrap(True)
        account = QGroupBox("YouTube"); account_layout = QVBoxLayout(account)
        account_layout.addWidget(self.auth_status)
        actions = QHBoxLayout(); actions.addWidget(self.connect_youtube); actions.addWidget(self.auth_test); actions.addWidget(self.disconnect_youtube)
        account_layout.addLayout(actions); account_layout.addWidget(self.sign_in); account_layout.addWidget(self.browser_status); account_layout.addWidget(self.refresh_browsers)
        form.addRow(account)
        reset = QPushButton("Reset Authentication Settings"); reset.clicked.connect(self._reset_authentication)
        guide = QPushButton("Create YouTube cookies.txt guide"); guide.clicked.connect(self._show_cookies_guide)
        open_robots = QPushButton("Open YouTube robots.txt"); open_robots.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(YOUTUBE_ROBOTS_URL)))
        helper_row = QHBoxLayout(); helper_row.addWidget(guide); helper_row.addWidget(open_robots)
        privacy = QLabel("Browser cookies are read locally by yt-dlp from the selected browser profile. Morgan Media Downloader does not upload your cookies."); privacy.setWordWrap(True)
        form.addRow("Connection method", self.auth_mode); form.addRow("Browser", self.browser); form.addRow("Profile", self.profile); form.addRow("Manual cookies.txt fallback", file_row); form.addRow("", reset); form.addRow("", helper_row); form.addRow(privacy)
        self.browser.currentTextChanged.connect(self._refresh_profiles); self.auth_mode.currentTextChanged.connect(self._refresh_auth_controls)
        self.profile.currentTextChanged.connect(self._invalidate_auth)
        self.cookies_file.textChanged.connect(self._invalidate_auth)
        for control in (self.connection, self.http_proxy_host, self.socks_proxy_host, self.http_proxy_username, self.socks_proxy_username, self.http_proxy_password, self.socks_proxy_password, self.tor_path):
            (control.currentTextChanged if isinstance(control, QComboBox) else control.textChanged).connect(self._invalidate_auth)
        for control in (self.http_proxy_port, self.socks_proxy_port): control.valueChanged.connect(self._invalidate_auth)
        self._refresh_profiles(); self._refresh_auth_controls()
        self._detect_browsers()
        return page

    def _refresh_profiles(self, *_):
        current_browser = self.browser.currentText()
        selected = self.working.browser_profile if not hasattr(self, "_profile_browser") else self._selected_profile()
        if hasattr(self, "_profile_browser") and self._profile_browser != current_browser: selected = ""
        self._profile_browser = current_browser
        self.profile.blockSignals(True); self.profile.clear()
        for label, value in browser_profiles(self.browser.currentText()): self.profile.addItem(label, value)
        index = next((i for i in range(self.profile.count()) if self.profile.itemData(i) == selected), -1)
        if index >= 0: self.profile.setCurrentIndex(index)
        elif selected: self.profile.setEditText(selected)
        self.profile.blockSignals(False)
        self._invalidate_auth()

    def _refresh_auth_controls(self, *_):
        browser = self.auth_mode.currentText() == "Browser Cookies"
        imported = self.auth_mode.currentText() == "Imported cookies.txt"
        self.browser.setEnabled(browser); self.profile.setEnabled(browser)
        self.cookies_file.setEnabled(imported); self.cookies_choose.setEnabled(imported)
        self._invalidate_auth()

    def _invalidate_auth(self, *_):
        self._auth_generation += 1
        self.auth_status.setText("Not verified — verify again after changing the connection.")

    def _detect_browsers(self):
        sources = discover_browsers()
        names = {source.name for source in sources}
        for index in range(self.browser.count()):
            name = self.browser.itemText(index)
            self.browser.setItemData(index, "Detected locally" if name in names else "Not detected — select only if available", Qt.ItemDataRole.ToolTipRole)
        self.browser_status.setText("Detected: " + ", ".join(source.name for source in sources) if sources else "No supported browser detected. Install/sign in with a supported browser, or import cookies.txt.")
        self._refresh_profiles()

    def _connect_youtube(self):
        sources = discover_browsers()
        if sources and self.browser.currentText() not in {source.name for source in sources}: self.browser.setCurrentText(sources[0].name)
        self.cookies_file.clear(); self.auth_mode.setCurrentText("Browser Cookies")
        self._refresh_profiles(); self.profile.setFocus()
        self.auth_status.setText("Choose the profile signed in to YouTube, then Verify Connection. Apply saves this choice for analysis and downloads.")

    def _disconnect_youtube(self):
        self.auth_mode.setCurrentText("None"); self.cookies_file.clear()
        self.profile.setCurrentIndex(-1); self.profile.setEditText("")
        self._invalidate_auth()
        self.auth_status.setText("Disconnected in this settings copy. Apply to stop using cookies in future tasks. Browser sign-in and existing tasks are unchanged.")

    def _open_youtube_browser(self):
        source = next((source for source in discover_browsers() if source.name == self.browser.currentText()), None)
        if not source or not source.application:
            self.auth_status.setText("Selected browser is not installed. Choose a detected browser or import cookies.txt."); return
        arguments = ["/usr/bin/open", "-a", str(source.application), "https://www.youtube.com/"]
        # No guest/incognito session or cookie export. Profile switching remains
        # visible and under browser control; opening a URL is not login evidence.
        try: subprocess.Popen(arguments)
        except OSError:
            self.auth_status.setText("Could not open the selected browser. Open it manually and sign in to YouTube."); return
        self.auth_status.setText("In the browser, select the same profile shown here and sign in to YouTube. Return here and Verify Connection.")

    def _selected_profile(self) -> str:
        value = self.profile.currentData()
        # Editable combo data can still refer to the formerly selected item.
        return str(value if value is not None and self.profile.currentText() == self.profile.itemText(self.profile.currentIndex()) else self.profile.currentText()).strip()

    def _reset_authentication(self):
        self.auth_mode.setCurrentText("Auto"); self.browser.setCurrentText("Chrome")
        self._refresh_profiles(); self.profile.setCurrentIndex(0); self.cookies_file.clear()
        self._invalidate_auth()

    def _show_cookies_guide(self):
        QMessageBox.information(
            self, "Create YouTube cookies.txt",
            "1. Open a new Chrome Incognito window.\n"
            "2. Sign into the YouTube account.\n"
            f"3. In the same tab navigate to:\n{YOUTUBE_ROBOTS_URL}\n"
            "4. Export youtube.com cookies in Netscape cookies.txt format.\n"
            "5. Close the Incognito window immediately.\n"
            "6. Select the resulting cookies.txt file here.")

    def _torrents(self):
        page, form = self._page(); self.torrent_dir = QLineEdit(self.working.torrent_download_dir); choose = QPushButton("Choose…"); choose.clicked.connect(lambda: self._choose_directory(self.torrent_dir)); folder_row = QHBoxLayout(); folder_row.addWidget(self.torrent_dir); folder_row.addWidget(choose)
        self.torrent_max = QSpinBox(); self.torrent_max.setRange(1, 8); self.torrent_max.setValue(self.working.torrent_max_active)
        self.upload_limit = QSpinBox(); self.upload_limit.setRange(0, 1_000_000); self.upload_limit.setValue(self.working.torrent_upload_limit_kib); self.upload_limit.setSuffix(" KiB/s (0 unlimited)")
        self.download_limit = QSpinBox(); self.download_limit.setRange(0, 1_000_000); self.download_limit.setValue(self.working.torrent_download_limit_kib); self.download_limit.setSuffix(" KiB/s (0 unlimited)")
        self.dht, self.pex, self.lpd, self.trackers, self.extra_trackers, self.seeding = QCheckBox(), QCheckBox(), QCheckBox(), QCheckBox(), QCheckBox(), QCheckBox()
        for widget, value in [(self.dht, self.working.torrent_enable_dht), (self.pex, self.working.torrent_enable_pex), (self.lpd, self.working.torrent_enable_lpd), (self.trackers, self.working.torrent_enable_trackers), (self.extra_trackers, self.working.torrent_extra_public_trackers), (self.seeding, self.working.torrent_continue_seeding)]: widget.setChecked(value)
        self.torrent_connection = _combo(["Direct / Normal Network", "System / Proton VPN"], self.working.torrent_connection_mode)
        self.aria = QLineEdit(self.working.aria2c_path); aria_choose = QPushButton("Choose aria2c…"); aria_choose.clicked.connect(self._choose_aria); aria_row = QHBoxLayout(); aria_row.addWidget(self.aria); aria_row.addWidget(aria_choose)
        self.aria_status = QLabel("Not tested"); self.aria_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); self.aria.textChanged.connect(lambda: self.aria_status.setText("Not tested"))
        self.aria_test = QPushButton("Test Torrent Engine"); self.aria_test.clicked.connect(self._test_aria)
        form.addRow("Default torrent folder", folder_row); form.addRow("Maximum active torrents", self.torrent_max); form.addRow("Upload limit", self.upload_limit); form.addRow("Download limit", self.download_limit); form.addRow("Enable DHT", self.dht); form.addRow("Enable PEX", self.pex); form.addRow("Enable Local Peer Discovery", self.lpd); form.addRow("Enable tracker communication", self.trackers); form.addRow("Add extra public trackers to public torrents", self.extra_trackers); form.addRow("Continue seeding after download", self.seeding); form.addRow("Torrent connection", self.torrent_connection); form.addRow("aria2c location", aria_row); form.addRow("Torrent engine", self.aria_status); form.addRow("", self.aria_test)
        return page

    def _advanced(self):
        page, form = self._page(); self.safe_options = QLineEdit(self.working.yt_dlp_safe_options); self.provider_url = QLineEdit(self.working.provider_base_url); self.provider_home = QLineEdit(self.working.provider_server_home)
        self.console_detail = _combo(["Normal", "Verbose", "Debug"], self.working.console_detail)
        form.addRow("Console detail", self.console_detail)
        self.yt_check_startup = QCheckBox(); self.yt_check_startup.setChecked(self.working.yt_dlp_check_updates_on_startup)
        self.yt_auto_install = QCheckBox(); self.yt_auto_install.setChecked(self.working.yt_dlp_auto_install_updates)
        self.yt_runtime_status = QLabel(); self.yt_runtime_status.setWordWrap(True); self.yt_runtime_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        runtime_buttons = QHBoxLayout(); self.runtime_action_buttons = []
        manager = self.runtime_manager
        for text, action in [("Check Now", lambda m=manager: m.check_and_update(False)),
                             ("Update Now", lambda m=manager: m.check_and_update(True, True)),
                             ("Roll Back", manager.rollback),
                             ("Use Bundled Version", manager.use_bundled)]:
            button = QPushButton(text); button.clicked.connect(lambda _checked=False, fn=action: self._run_runtime_action(fn)); runtime_buttons.addWidget(button); self.runtime_action_buttons.append(button)
        self._refresh_runtime_status()
        form.addRow("yt-dlp Updates", QLabel("Verified stable releases from the official yt-dlp GitHub repository"))
        form.addRow("Check for updates on startup", self.yt_check_startup); form.addRow("Automatically install stable updates", self.yt_auto_install)
        form.addRow("yt-dlp", self.yt_runtime_status); form.addRow("", runtime_buttons)
        open_logs = QPushButton("Open Logs Folder"); open_logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir()))))
        form.addRow("yt-dlp extra safe options", self.safe_options); form.addRow("ffmpeg", QLabel(find_binary("ffmpeg") or "Not available")); form.addRow("ffprobe", QLabel(find_binary("ffprobe") or "Not available")); form.addRow("aria2", QLabel("See Torrents → Test Torrent Engine")); form.addRow("PO-token provider", QLabel("Live status is shown in the main status bar")); form.addRow("", open_logs)
        reset = QPushButton("Reset all settings…"); reset.clicked.connect(self._reset); form.addRow("", reset); return page

    def _choose_directory(self, target: QLineEdit):
        if chosen := QFileDialog.getExistingDirectory(self, "Choose folder", target.text()): target.setText(chosen)
    def _choose_tor(self):
        if chosen := QFileDialog.getExistingDirectory(self, "Choose Tor Browser.app", str(Path(self.tor_path.text()).parent)): self.tor_path.setText(chosen)
    def _choose_cookies(self):
        if chosen := QFileDialog.getOpenFileName(self, "Choose Netscape cookies.txt", self.cookies_file.text(), "Cookie files (*.txt);;All files (*)")[0]: self.cookies_file.setText(chosen)
    def _choose_aria(self):
        if chosen := QFileDialog.getOpenFileName(self, "Choose aria2c", self.aria.text())[0]: self.aria.setText(chosen)
    def _refresh_aria(self): self.aria_status.setText(format_aria2_diagnostic(inspect_aria2c(self.aria.text())))
    def _test_aria(self):
        path = self.aria.text(); self.aria_test.setEnabled(False); self.aria_status.setText("Testing…")
        self.task_manager.start("diagnostic", lambda _cancel, _progress, p=path: inspect_aria2c(p),
                                on_result=self._aria_test_ready, on_finished=self._aria_test_finished)
    def _aria_test_ready(self, info):
        self.aria_status.setText(format_aria2_diagnostic(info))
        (QMessageBox.information if info.available else QMessageBox.warning)(self, "Torrent Engine", format_aria2_diagnostic(info))
    def _aria_test_finished(self, _task_id): self.aria_test.setEnabled(True)
    def _refresh_tor_state(self):
        lines = [self.tor.state]
        if self.tor.port: lines.append(f"SOCKS: 127.0.0.1:{self.tor.port}")
        if self.tor.control_port: lines.append(f"Control: 127.0.0.1:{self.tor.control_port}")
        lines.append(f"Bootstrap: {self.tor.bootstrap_percent}%")
        if self.tor.state == "Failed" and self.tor.last_error: lines.append(self.tor.last_error)
        self.tor_state.setText("\n".join(lines))
    def _start_tor(self): self.tor.browser_path = self.tor_path.text().strip(); self.tor.start()
    def _new_tor_circuit(self):
        try:
            result = self.tor.request_new_circuit()
            QMessageBox.information(self, "Managed Tor", f"NEWNYM requested. Cooldown waited: {float(result['cooldown_waited']):.1f}s")
        except RuntimeError as error: QMessageBox.warning(self, "Managed Tor", str(error))
    def _test_tor(self):
        if not self.tor.proxy_url:
            QMessageBox.warning(self, "Managed Tor", f"Managed Tor is {self.tor.state}. Start it and wait for Connected."); return
        proxy, runtime = self.tor.proxy_url, self.runtime_manager.snapshot()
        self.task_manager.start("connection-test", lambda _cancel, _progress, p=proxy, r=runtime: test_tor_proxy(p, r),
                                on_result=self._tor_test_ready)
    def _tor_test_ready(self, result):
        state, detail = result
        (QMessageBox.information if state == "available" else QMessageBox.warning)(self, "Managed Tor", detail)
    def _test_auth(self):
        if self._auth_busy: return
        profile = self._selected_profile()
        try: proxy = self._authentication_proxy()
        except (ValueError, ConnectionError):
            self.auth_status.setText("Selected connection is unavailable. Check Network settings before verifying."); return
        values = (self.auth_mode.currentText(), self.browser.currentText(), profile, self.cookies_file.text().strip(), proxy, self.runtime_manager.snapshot())
        generation = self._auth_generation
        self._auth_busy = True; self.auth_test.setEnabled(False)
        self.auth_status.setText("Verifying cookie access and YouTube session…")
        self.task_manager.start("authentication-test", lambda _cancel, _progress, v=values, g=generation: (g, verify_youtube_connection(*v)),
                                on_result=self._auth_test_delivered, on_error=self._auth_test_error, on_finished=self._auth_test_finished)

    def _authentication_proxy(self):
        mode = self.connection.currentText()
        if mode == "Managed Tor":
            if not self.tor.proxy_url: raise ConnectionError("Managed Tor unavailable")
            return self.tor.proxy_url
        if mode == "External Tor":
            available, port = detect_tor()
            if not available: raise ConnectionError("External Tor unavailable")
            return ProxyConfig(mode, "127.0.0.1", port).url()
        if mode in {"Custom HTTP Proxy", "Custom SOCKS5 Proxy"}:
            kind = "http" if mode == "Custom HTTP Proxy" else "socks"
            username = getattr(self, kind + "_proxy_username").text().strip()
            password = getattr(self, kind + "_proxy_password").text()
            if username and not password: password = load_proxy_password(f"{kind}:{username}") or ""
            return ProxyConfig(mode, getattr(self, kind + "_proxy_host").text().strip(),
                               getattr(self, kind + "_proxy_port").value(), username, password).url()
        return None

    def _auth_test_delivered(self, payload):
        generation, result = payload
        if generation == self._auth_generation: self._auth_test_ready(result)

    def _auth_test_ready(self, result):
        self.auth_status.setText(result.message)
        self.auth_status.setToolTip(f"Verification: {result.state}. Cookie source readable: {result.cookies_readable}. This is not a download/provider or private-content entitlement test.")

    def _auth_test_error(self, *_):
        self.auth_status.setText("Verification could not complete. Check the connection and retry.")

    def _auth_test_finished(self, *_):
        self._auth_busy = False; self.auth_test.setEnabled(True)
    def _reset(self):
        if QMessageBox.question(self, "Reset settings", "Reset every setting to its default value?") == QMessageBox.StandardButton.Yes:
            self.working = AppSettings(); self.apply_callback(copy.deepcopy(self.working), "")
            QMessageBox.information(self, "Reset settings", "Defaults were restored.")
            self.accept()

    def _refresh_runtime_status(self):
        info = self.runtime_manager.describe()
        compatibility = f"\nCompatibility: {info['compatibility_error']}" if info["compatibility_error"] else ""
        self.yt_runtime_status.setText(
            f"Current version: {info['active_version']}\nBundled version: {info['bundled_version']}\n"
            f"Latest stable: {info['latest_stable']}\nLast checked: {info['last_checked']}\n"
            f"Last update: {info['last_update']}\nRuntime source: {info['source']}\nStatus: {info['status']}{compatibility}")

    def _run_runtime_action(self, action: Callable[[], object]):
        for button in self.runtime_action_buttons: button.setEnabled(False)
        self.task_manager.start("yt-runtime", lambda _cancel, _progress: action(),
                                on_finished=self._runtime_action_finished)

    def _runtime_action_finished(self, _task_id: str = ""):
        self._refresh_runtime_status()
        for button in self.runtime_action_buttons: button.setEnabled(True)

    def _collect(self) -> AppSettings:
        s = copy.deepcopy(self.working)
        s.theme = self.theme.currentText(); s.clipboard_url_detection = self.clipboard_detection.isChecked(); s.remember_window_size = self.remember_size.isChecked(); s.remember_window_position = self.remember_position.isChecked(); s.show_first_run_diagnostics = self.show_diagnostics.isChecked()
        s.download_dir = self.download_dir.text().strip(); s.create_subfolders = self.subfolders.currentText(); s.filename_template = self.filename.text(); s.compatibility = self.compatibility.currentText(); s.quality = self.quality.currentText(); s.container = self.container.currentText(); s.audio_format = self.audio_format.currentText(); s.audio_bitrate = self.audio_bitrate.currentText(); s.concurrent_downloads = self.concurrency.value()
        s.embed_thumbnail = self.embed_thumbnail.isChecked(); s.embed_metadata = self.embed_metadata.isChecked(); s.embed_chapters = self.embed_chapters.isChecked(); s.embed_subtitles = self.embed_subtitles.isChecked(); s.write_subtitles = self.write_subtitles.isChecked(); s.keep_original = self.keep_original.isChecked(); s.subtitle_languages = self.languages.text().strip(); s.subtitle_source = self.subtitle_source.currentText(); s.verify_postprocessing = self.verify_postprocessing.isChecked()
        s.connection_mode = self.connection.currentText(); s.tor_browser_path = self.tor_path.text().strip(); s.managed_tor_auto_start = self.tor_auto.isChecked(); s.managed_tor_stop_on_exit = self.tor_stop.isChecked()
        s.http_proxy_host = self.http_proxy_host.text().strip(); s.http_proxy_port = self.http_proxy_port.value(); s.http_proxy_username = self.http_proxy_username.text().strip()
        s.socks_proxy_host = self.socks_proxy_host.text().strip(); s.socks_proxy_port = self.socks_proxy_port.value(); s.socks_proxy_username = self.socks_proxy_username.text().strip()
        s.authentication_mode = self.auth_mode.currentText(); s.cookies_browser = self.browser.currentText(); s.browser_profile = self._selected_profile(); s.cookies_file = self.cookies_file.text().strip()
        s.torrent_download_dir = self.torrent_dir.text().strip(); s.torrent_max_active = self.torrent_max.value(); s.torrent_upload_limit_kib = self.upload_limit.value(); s.torrent_download_limit_kib = self.download_limit.value(); s.torrent_enable_dht = self.dht.isChecked(); s.torrent_enable_pex = self.pex.isChecked(); s.torrent_enable_lpd = self.lpd.isChecked(); s.torrent_enable_trackers = self.trackers.isChecked(); s.torrent_extra_public_trackers = self.extra_trackers.isChecked(); s.torrent_continue_seeding = self.seeding.isChecked(); s.torrent_connection_mode = self.torrent_connection.currentText(); s.aria2c_path = self.aria.text().strip()
        s.yt_dlp_safe_options = self.safe_options.text().strip(); s.provider_base_url = self.provider_url.text().strip(); s.provider_server_home = self.provider_home.text().strip()
        s.yt_dlp_check_updates_on_startup = self.yt_check_startup.isChecked(); s.yt_dlp_auto_install_updates = self.yt_auto_install.isChecked()
        s.console_detail = self.console_detail.currentText()
        return s

    def apply(self):
        self.working = self._collect(); self.apply_callback(copy.deepcopy(self.working), {
            "http": self.http_proxy_password.text(), "socks": self.socks_proxy_password.text()})
    def _ok(self): self.apply(); self.accept()
