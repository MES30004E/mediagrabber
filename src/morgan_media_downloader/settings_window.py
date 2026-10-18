from __future__ import annotations

import copy
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer, QUrl, QSize
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
from .provider import check_provider, find_runtime
from .settings import AppSettings
from .tasks import TaskManager
from .torrent import format_aria2_diagnostic, inspect_aria2c
from .yt_runtime import YtDlpRuntimeManager, get_runtime_manager
from .ui_components import settings_page, DisclosureSection


def _combo(values: list[str], current: str) -> QComboBox:
    widget = QComboBox(); widget.addItems(values); widget.setCurrentText(current); return widget


class SettingsWindow(QDialog):
    def __init__(self, settings: AppSettings, tor: ManagedTor, apply_callback: Callable[[AppSettings, object], None],
                 parent=None, runtime_manager: YtDlpRuntimeManager | None = None,
                 task_manager: TaskManager | None = None, embedded: bool = False, companion_controller=None,
                 account_callback: Callable[[str], AppSettings] | None = None):
        super().__init__(parent)
        self.original = settings; self.working = copy.deepcopy(settings); self.tor = tor; self.apply_callback = apply_callback
        self.runtime_manager = runtime_manager or get_runtime_manager()
        self.task_manager = task_manager or TaskManager(self)
        self.embedded = embedded
        self.account_callback = account_callback
        from .youtube_companion.bridge import CompanionController
        self.companion = companion_controller or CompanionController()
        self._pending_companion = None
        self._companion_busy = False
        self._companion_deadline = 0
        if not self.runtime_manager.initialized: self.runtime_manager.initialize()
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle("Settings"); self.resize(790, 610)
        outer = QVBoxLayout(self); body = QHBoxLayout(); self.sidebar = QListWidget(); self.sidebar.setObjectName("navigation"); self.sidebar.setAccessibleName("Settings sections"); self.sidebar.setFixedWidth(138)
        self.stack = QStackedWidget(); body.addWidget(self.sidebar); body.addWidget(self.stack, 1); outer.addLayout(body, 1)
        self.pages = {}
        for name, builder in [("General", self._general), ("Downloads", self._downloads), ("Network", self._network),
                              ("Accounts", self._authentication), ("Torrents", self._torrents), ("Advanced", self._advanced)]:
            self.sidebar.addItem(name); page = builder(); self.pages[name] = page; self.stack.addWidget(page)
            self.sidebar.item(self.sidebar.count() - 1).setSizeHint(QSize(120, 36))
            for label in page.findChildren(QLabel):
                if label.property("settingsTitle"): label.setText(name)
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex); self.sidebar.setCurrentRow(0)
        standard = QDialogButtonBox.StandardButton.Apply if embedded else (
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Ok)
        self.buttons = QDialogButtonBox(standard)
        if not embedded: self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        if not embedded: self.buttons.accepted.connect(self._ok)
        outer.addWidget(self.buttons)
        self.timer = QTimer(self); self.timer.timeout.connect(self._refresh_tor_state); self.timer.start(250)
        self.timer.timeout.connect(self._poll_companion)
        self.finished.connect(self._cancel_companion)

    @staticmethod
    def _page() -> tuple[QWidget, QFormLayout]:
        return settings_page()

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
        self._verified_at = ""
        self._readiness_busy = False
        self._account_stages = {
            "Extension / native host": "Not checked — Connect, then open the extension in Incognito",
            "Capture": "Not authorized",
            "Transfer": "No session transferred in this window",
            "Keychain": "Not checked",
            "Verification": "Not yet verified",
            "Downloader / provider": "Not checked — separate from sign-in",
        }
        page, form = self._page(); self.auth_mode = _combo(["YouTube Companion", "Auto", "None", "Browser Cookies", "Imported cookies.txt"], self.working.authentication_mode)
        self.browser = _combo(["Chrome", "Chromium", "Firefox", "Safari", "Edge"], self.working.cookies_browser)
        self.profile = QComboBox(); self.profile.setEditable(True)
        self.cookies_file = QLineEdit(self.working.cookies_file)
        self.cookies_choose = QPushButton("Choose cookies.txt…"); self.cookies_choose.clicked.connect(self._choose_cookies); file_row = QHBoxLayout(); file_row.addWidget(self.cookies_file); file_row.addWidget(self.cookies_choose)
        self.auth_test = QPushButton("Verify Session"); self.auth_test.clicked.connect(self._test_auth)
        self.connect_youtube = QPushButton("Connect YouTube with Chrome Incognito"); self.connect_youtube.setProperty("primary", True); self.connect_youtube.clicked.connect(self._connect_youtube)
        self.readiness_check = QPushButton("Check downloader/provider"); self.readiness_check.clicked.connect(self._check_account_readiness)
        self.companion_setup = QPushButton("Companion setup instructions…"); self.companion_setup.clicked.connect(self._show_companion_setup)
        self.connect_browser = QPushButton("Use ordinary browser-profile cookies"); self.connect_browser.clicked.connect(self._connect_browser)
        self.auth_status = QLabel("Not verified — connect a browser to get started."); self.auth_status.setWordWrap(True)
        self.auth_progress = QLabel(); self.auth_progress.setWordWrap(True)
        self.auth_progress.setTextFormat(Qt.TextFormat.PlainText)
        self.auth_progress.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.auth_status.setTextFormat(Qt.TextFormat.PlainText)
        self.disconnect_youtube = QPushButton("Disconnect"); self.disconnect_youtube.clicked.connect(self._disconnect_youtube)
        self.sign_in = QPushButton("Sign in using browser…"); self.sign_in.clicked.connect(self._open_youtube_browser)
        self.refresh_browsers = QPushButton("Detect Browsers"); self.refresh_browsers.clicked.connect(self._detect_browsers)
        self.browser_status = QLabel(); self.browser_status.setWordWrap(True)
        account = QGroupBox("YouTube"); account_layout = QVBoxLayout(account)
        account_layout.addWidget(self.auth_status)
        account_layout.addWidget(self.auth_progress)
        account_layout.addWidget(self.connect_youtube)
        actions = QHBoxLayout(); actions.addWidget(self.auth_test); actions.addWidget(self.disconnect_youtube)
        account_layout.addLayout(actions); account_layout.addWidget(self.companion_setup)
        account_layout.addWidget(self.readiness_check)
        form.addRow(account)
        reset = QPushButton("Reset Authentication Settings"); reset.clicked.connect(self._reset_authentication)
        guide = QPushButton("Create YouTube cookies.txt guide"); guide.clicked.connect(self._show_cookies_guide)
        open_robots = QPushButton("Open YouTube robots.txt"); open_robots.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(YOUTUBE_ROBOTS_URL)))
        helper_row = QHBoxLayout(); helper_row.addWidget(guide); helper_row.addWidget(open_robots)
        privacy = QLabel("Connect → Sign in → Capture Session in the extension → close Incognito → Verify. Captured cookies stay in macOS Keychain and are supplied to yt-dlp in memory. Successful import activates only YouTube Companion for future tasks; Cancel still discards unrelated edits. Import is not proof of private-content permission. Disconnect immediately deletes the captured session and disables authentication, even if you later Cancel. Other connection methods still require Apply."); privacy.setWordWrap(True)
        self.advanced_auth = DisclosureSection("Advanced authentication · browser profiles and manual import", self.working.authentication_mode in {"Imported cookies.txt", "Browser Cookies"})
        advanced = QFormLayout(self.advanced_auth.content); advanced.setContentsMargins(0, 12, 0, 12); advanced.setSpacing(12)
        advanced.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        advanced.addRow("Connection method", self.auth_mode); advanced.addRow("cookies.txt", file_row); advanced.addRow(reset); advanced.addRow(helper_row)
        advanced.addRow(self.connect_browser); advanced.addRow("Browser", self.browser); advanced.addRow("Profile", self.profile)
        advanced.addRow(self.sign_in); advanced.addRow(self.browser_status); advanced.addRow(self.refresh_browsers)
        form.addRow(self.advanced_auth); form.addRow(privacy)
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
        if imported: self.advanced_auth.setExpanded(True)
        self._invalidate_auth()

    def _invalidate_auth(self, *_):
        self._auth_generation += 1
        self.auth_status.setText("Not verified — verify again after changing the connection.")
        self.auth_status.setToolTip("")
        self._account_stages["Verification"] = "Needs verification — connection or source changed"
        self._account_stages["Downloader / provider"] = "Not checked — connection or source changed"
        self._render_account_stages()

    def _render_account_stages(self):
        self.auth_progress.setText("\n".join([
            f"Active authentication: {self.original.authentication_mode}",
            f"Selected method: {self.auth_mode.currentText()} (Apply needed if different)",
            *(f"{name}: {value}" for name, value in self._account_stages.items()),
            f"Last verification attempt (this window): {self._verified_at or 'Never'}",
            "Sign-in is not proof of private-content access or a successful download.",
        ]))
        self.connect_youtube.setText("Reconnect YouTube with Chrome Incognito" if self.original.authentication_mode == "YouTube Companion"
                                     else "Connect YouTube with Chrome Incognito")

    def _check_account_readiness(self):
        if self._readiness_busy: return
        generation = self._auth_generation
        base_url, home = self.provider_url.text().strip(), self.provider_home.text().strip()
        version = self.runtime_manager.snapshot().version
        self._readiness_busy = True; self.readiness_check.setEnabled(False)
        self._account_stages["Downloader / provider"] = "Checking prerequisites; download not tested"
        self._render_account_stages()
        def check(_cancel, _progress):
            # Do not relay provider.detail: it can contain private paths or URL credentials.
            try:
                status = check_provider(base_url, home)
                engine = find_runtime(for_player=True)
            except Exception:
                return generation, "Check failed — verify component settings and retry; download not tested"
            provider = ("HTTP provider responding" if status.mode == "http" and status.state == "available" else
                        "Script discovered; token generation not tested" if status.mode == "script" and status.state == "available" else
                        "Provider unavailable — check Advanced settings and Node/Deno")
            javascript = "Player JavaScript engine detected" if engine else "Player JavaScript engine missing — install Node 22+ or Deno 2.3+"
            return generation, f"yt-dlp {version}; {javascript}; {provider}; download not tested"
        self.task_manager.start("account-readiness", check, on_result=self._account_readiness_ready,
                                on_finished=self._account_readiness_finished)

    def _account_readiness_ready(self, payload):
        generation, status = payload
        if generation == self._auth_generation:
            self._account_stages["Downloader / provider"] = status
            self._render_account_stages()

    def _account_readiness_finished(self, *_):
        self._readiness_busy = False; self.readiness_check.setEnabled(True)

    def _detect_browsers(self):
        sources = discover_browsers()
        names = {source.name for source in sources}
        for index in range(self.browser.count()):
            name = self.browser.itemText(index)
            self.browser.setItemData(index, "Detected locally" if name in names else "Not detected — select only if available", Qt.ItemDataRole.ToolTipRole)
        self.browser_status.setText("Detected: " + ", ".join(source.name for source in sources) if sources else "No supported browser detected. Install/sign in with a supported browser, or import cookies.txt.")
        self._refresh_profiles()

    def _connect_youtube(self):
        self._invalidate_auth()
        source = next((source for source in discover_browsers() if source.name == "Chrome" and source.application), None)
        if source is None:
            self.auth_status.setText("Google Chrome was not detected. Install it or use an Advanced authentication fallback; no ordinary cookies were captured."); return
        try:
            from .youtube_companion.setup import install
            install(launcher=False)
            self._pending_companion = self.companion.begin()
            self._companion_deadline = time.monotonic() + 300
            self._account_stages.update({"Extension / native host": "Host registered; Chrome extension readiness not yet reported",
                                         "Capture": "Authorized for one transfer (5 minutes)", "Transfer": "Waiting for explicit Capture Session",
                                         "Verification": "Not yet verified"})
            self._render_account_stages()
            subprocess.Popen(["/usr/bin/open", "-a", str(source.application), "--args", "--incognito", "https://www.youtube.com/"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            self._cancel_companion()
            self._account_stages["Capture"] = "Not authorized — preparation failed; retry Connect"
            self._account_stages["Extension / native host"] = "Not confirmed — check setup and user-folder permissions"
            self._render_account_stages()
            self.auth_status.setText("Could not prepare the companion. Check user-folder permissions and setup instructions; no ordinary-profile fallback was used."); return
        self.auth_status.setText("Waiting for Capture Session (5 minutes). First time: load the companion extension, enable Allow in Incognito and pin it using Setup instructions. Sign in in the Incognito YouTube tab, then explicitly approve Capture in the extension. No session has been verified yet.")

    def _show_companion_setup(self):
        from .youtube_companion.bridge import EXTENSION_ID
        extension = Path(__file__).resolve().parents[2] / "companion/chrome"
        QMessageBox.information(self, "Chrome Incognito companion setup",
            f"1. Open chrome://extensions in Google Chrome. Enable Developer mode, then Load unpacked:\n{extension}\n\n"
            f"2. Confirm extension ID: {EXTENSION_ID}. Open Details → Allow in Incognito. Pin the extension.\n\n"
            "3. Click Connect/Reconnect here (registers the local host and authorizes one capture for 5 minutes).\n"
            "4. Use one Incognito YouTube tab, sign in, open the extension, check consent and Capture Session. Close Incognito promptly.\n"
            "5. Successful capture activates Companion automatically. Return here and Verify Session. Unrelated settings still need Apply. No private library is enumerated. See docs/YOUTUBE_COOKIE_COMPANION.md for removal and security limits.")

    def _poll_companion(self):
        if self._pending_companion is None or self._companion_busy: return
        try:
            pending = self.companion.poll_status(self._pending_companion, expire=time.monotonic() >= self._companion_deadline)
            if pending and pending.get("busy"):
                self.auth_status.setText("Native host busy — Keychain completion is not yet confirmed. Complete any Keychain prompt, or Reconnect to recover after the host finishes.")
                return
            if pending and pending.get("expired"):
                self._pending_companion = None
                self.auth_status.setText("Capture request expired. Reconnect to approve a new capture.")
                self._account_stages["Capture"] = "Expired — Reconnect to authorize again"; self._render_account_stages(); return
            if pending and pending.get("extension_ready") is not None:
                self._account_stages["Extension / native host"] = ("Chrome reported Incognito readiness; native host responding" if pending["extension_ready"] else
                    "Native host responding; open extension in Incognito and enable Allow in Incognito")
                self._render_account_stages()
            receipt = pending.get("receipt") if pending else None
        except Exception:
            self._cancel_companion(); self.auth_status.setText("Companion status could not be read safely. Check local permissions and Reconnect.")
            self._account_stages["Capture"] = "Status unreadable — Reconnect after checking local permissions"
            self._render_account_stages(); return
        if not receipt or receipt.get("operation_id") != self._pending_companion: return
        self._pending_companion = None
        if receipt.get("status") == "imported":
            self.cookies_file.clear(); self.auth_mode.setCurrentText("YouTube Companion")
            self._invalidate_auth()
            self._account_stages.update({"Capture": "Completed (single-use authorization consumed)", "Transfer": "Session transferred",
                                         "Keychain": "Stored", "Verification": "Not yet verified"})
            self._render_account_stages()
            try: self._persist_account_choice("YouTube Companion")
            except Exception:
                self.auth_status.setText("Session imported and stored in Keychain, but activation could not be saved. Check settings-folder permissions, then retry Apply or Reconnect. Unrelated pending edits were not saved.")
                return
            self.auth_status.setText("Session imported securely into Keychain and activated for future tasks — not yet verified. Close Incognito, then Verify Session. Unrelated settings edits remain unsaved.")
        else:
            self._account_stages.update({"Capture": "Consumed — Reconnect to retry", "Transfer": "Session received",
                                         "Keychain": "Storage failed — check Keychain access; no plaintext fallback"})
            self._render_account_stages()
            self.auth_status.setText("Secure session storage failed. Check Keychain access, then Reconnect. No plaintext fallback was saved.")

    def _cancel_companion(self, *_):
        if self._pending_companion is not None:
            try: self.companion.cancel(self._pending_companion)
            except Exception: pass  # Pending authorization still expires after five minutes.
            self._pending_companion = None

    def _persist_account_choice(self, mode: str):
        """Commit only the explicit managed-account action, not the form copy."""
        if mode not in {"YouTube Companion", "None"}: raise ValueError("Unsupported account action")
        if self.account_callback is not None:
            applied = self.account_callback(mode)
        else:
            applied = copy.deepcopy(self.original)
            applied.authentication_mode = mode; applied.cookies_file = ""
            self.apply_callback(copy.deepcopy(applied), {})
        self.original = copy.deepcopy(applied)
        self.working.authentication_mode = mode; self.working.cookies_file = ""
        self._render_account_stages()

    def _connect_browser(self):
        sources = discover_browsers()
        if sources and self.browser.currentText() not in {source.name for source in sources}: self.browser.setCurrentText(sources[0].name)
        self.cookies_file.clear(); self.auth_mode.setCurrentText("Browser Cookies")
        self._refresh_profiles(); self.profile.setFocus()
        self.auth_status.setText("Choose the profile signed in to YouTube, then Verify Connection. Apply saves this choice for analysis and downloads.")

    def _disconnect_youtube(self):
        if self._companion_busy: return
        self._companion_busy = True
        self._invalidate_auth()
        for control in (self.connect_youtube, self.disconnect_youtube, self.auth_test): control.setEnabled(False)
        self.auth_status.setText("Deleting the captured session from Keychain…")
        def disconnect(_cancel, _progress):
            self.companion.disconnect()
            return True
        self.task_manager.start("youtube-disconnect", disconnect, on_result=self._companion_disconnected,
                                on_error=self._companion_disconnect_error, on_finished=self._companion_disconnect_finished)

    def _companion_disconnect_error(self, *_):
        self.auth_status.setText("Disconnect failed: Keychain session deletion was not confirmed. Check Keychain access and retry.")

    def _companion_disconnect_finished(self, *_):
        self._companion_busy = False
        for control in (self.connect_youtube, self.disconnect_youtube): control.setEnabled(True)
        self.auth_test.setEnabled(not self._auth_busy)

    def _companion_disconnected(self, *_):
        self._pending_companion = None
        self.auth_mode.setCurrentText("None"); self.cookies_file.clear()
        self.profile.setCurrentIndex(-1); self.profile.setEditText("")
        self._invalidate_auth()
        self._account_stages.update({"Capture": "Not authorized", "Keychain": "Deleted", "Transfer": "No active captured session"})
        self._render_account_stages()
        try: self._persist_account_choice("None")
        except Exception:
            self.auth_status.setText("Captured session deleted, but authentication-disabled settings could not be saved. Check settings permissions and Apply; already-running snapshots are unchanged.")
            return
        self.auth_status.setText("Captured Keychain session deleted and authentication disabled for future tasks. Unrelated settings edits remain unsaved; browser sign-in and running task snapshots are unchanged.")

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
        self.provider_url.textChanged.connect(self._invalidate_auth)
        self.provider_home.textChanged.connect(self._invalidate_auth)
        self.console_detail = _combo(["Normal", "Verbose", "Debug"], self.working.console_detail)
        form.addRow("Console detail", self.console_detail)
        self.yt_check_startup = QCheckBox(); self.yt_check_startup.setChecked(self.working.yt_dlp_check_updates_on_startup)
        self.yt_auto_install = QCheckBox(); self.yt_auto_install.setChecked(self.working.yt_dlp_auto_install_updates)
        self.yt_runtime_status = QLabel(); self.yt_runtime_status.setWordWrap(True); self.yt_runtime_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.runtime_channel = QComboBox()
        self.runtime_channel.addItem("Stable (automatic checks)", "stable")
        self.runtime_channel.addItem("Nightly (explicit opt-in; rollback available)", "nightly")
        runtime_buttons = QHBoxLayout(); self.runtime_action_buttons = []
        manager = self.runtime_manager
        for text, action in [("Check Now", None),
                             ("Update Now", None),
                             ("Roll Back", manager.rollback),
                             ("Use Bundled Version", manager.use_bundled)]:
            button = QPushButton(text); button.clicked.connect(lambda _checked=False, label=text, fn=action: self._select_runtime_action(label, fn)); runtime_buttons.addWidget(button); self.runtime_action_buttons.append(button)
        self._refresh_runtime_status()
        form.addRow("yt-dlp Updates", QLabel("Official release assets: checksum, structure, import and provider compatibility checks before activation. Nightly is not a live download guarantee."))
        form.addRow("Manual update channel", self.runtime_channel)
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
        self._verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._account_stages["Verification"] = "Attempting session verification"
        self._render_account_stages()
        self.auth_status.setText("Verifying cookie access and YouTube session…")
        def verify(_cancel, _progress):
            try: result = verify_youtube_connection(*values)
            except Exception: result = None  # Never publish unsanitized exception details or obsolete evidence.
            return generation, result
        self.task_manager.start("authentication-test", verify,
                                on_result=self._auth_test_delivered, on_finished=self._auth_test_finished)

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
        if generation == self._auth_generation:
            if result is None: self._auth_test_error()
            else: self._auth_test_ready(result)

    def _auth_test_ready(self, result: YouTubeConnection):
        self._verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._account_stages["Verification"] = ("Signed-in status confirmed — account identity not confirmed" if result.authenticated else
                                                "Signed-in status unconfirmed — check the selected source and retry")
        if self.auth_mode.currentText() == "YouTube Companion" and result.cookies_readable:
            self._account_stages["Keychain"] = "Stored session readable"
        self._render_account_stages()
        self.auth_status.setText(result.message)
        self.auth_status.setToolTip(f"Verification: {result.state}. Cookie source readable: {result.cookies_readable}. This is not a download/provider or private-content entitlement test.")

    def _auth_test_error(self, *_):
        self._account_stages["Verification"] = "Failed to complete — check connection and retry"
        self._render_account_stages()
        self.auth_status.setText("Verification could not complete. Check the connection and retry.")

    def _auth_test_finished(self, *_):
        self._auth_busy = False; self.auth_test.setEnabled(not self._companion_busy)
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
            f"Latest nightly: {info.get('latest_nightly', 'Not checked')}\nActive channel: {info.get('active_channel', 'bundled')}\n"
            f"Last update: {info['last_update']}\nRuntime source: {info['source']}\nStatus: {info['status']}{compatibility}\nLast error: {info.get('last_error') or 'None'}")

    def _select_runtime_action(self, label, action):
        if action is None:
            channel = self.runtime_channel.currentData()
            install = label == "Update Now"
            manager = self.runtime_manager
            action = lambda: manager.check_and_update(install, install, channel=channel)
        self._run_runtime_action(action)

    def _run_runtime_action(self, action: Callable[[], object]):
        for button in self.runtime_action_buttons: button.setEnabled(False)
        self.task_manager.start("yt-runtime", lambda _cancel, _progress: action(),
                                on_finished=self._runtime_action_finished)

    def _runtime_action_finished(self, _task_id: str = ""):
        self._refresh_runtime_status()
        self._invalidate_auth()
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
        self.original = copy.deepcopy(self.working)
        self._render_account_stages()
    def _ok(self): self.apply(); self.accept()
