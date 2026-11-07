"""Semantic Qt palettes and restrained shared styling. No theme dependency."""
from PySide6.QtCore import QObject,Qt
from PySide6.QtGui import QColor, QPalette


def _luminance(color: QColor) -> float:
    channels = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                for value in (color.redF(), color.greenF(), color.blueF())]
    return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2]


def status_foreground(tone: str, palette: QPalette) -> QColor:
    """Readable semantic text on an application-window surface, including System."""
    background = _luminance(palette.color(QPalette.ColorRole.Window))
    colors = ({"success": "#6fd38b", "warning": "#efc15b", "error": "#ff8a80", "disabled": "#a3aab5"}
              if background < .3 else
              {"success": "#237a3b", "warning": "#866500", "error": "#b42318", "disabled": "#626c7c"})
    text = palette.color(QPalette.ColorRole.WindowText)
    candidate = QColor(colors[tone]) if tone in colors else text
    minimum = 3.0 if tone == "disabled" else 4.5
    for color in (candidate, text):
        low, high = sorted((background, _luminance(color)))
        if (high + .05) / (low + .05) >= minimum:
            return color
    # Unusual custom palettes can make both their own text and semantic colors
    # unreadable. Keep the status wording and choose the safer neutral contrast.
    return QColor("#000000" if background > .179 else "#ffffff")


def _theme_palette(application, mode):
    palette = application.style().standardPalette()
    if mode in {"Light", "Dark"}:
        dark = mode == "Dark"
        colors = {
            QPalette.ColorRole.Window: "#202226" if dark else "#f7f8fa",
            QPalette.ColorRole.WindowText: "#f0f1f4" if dark else "#242830",
            QPalette.ColorRole.Base: "#292c31" if dark else "#ffffff",
            QPalette.ColorRole.AlternateBase: "#24272b" if dark else "#eef1f5",
            QPalette.ColorRole.Text: "#f0f1f4" if dark else "#242830",
            QPalette.ColorRole.Button: "#32363d" if dark else "#ffffff",
            QPalette.ColorRole.ButtonText: "#f0f1f4" if dark else "#242830",
            QPalette.ColorRole.Highlight: "#276bd2" if dark else "#205fc4",
            QPalette.ColorRole.HighlightedText: "#ffffff",
            QPalette.ColorRole.PlaceholderText: "#a3aab5" if dark else "#626c7c",
            QPalette.ColorRole.Mid: "#545c69" if dark else "#c9d0da",
            QPalette.ColorRole.ToolTipBase: "#292c31" if dark else "#ffffff",
            QPalette.ColorRole.ToolTipText: "#f0f1f4" if dark else "#242830",
        }
        for role, value in colors.items(): palette.setColor(role, QColor(value))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#8c94a1" if dark else "#747e8c"))
    return palette


class _ThemeState(QObject):
    """One application-owned theme observer, never one per window or job."""
    def __init__(self,application):
        super().__init__(application)
        self.application=application; self.mode=None; self._busy=False
        self._stylesheet=""; self._template=""; self._last_palette=None
        application.paletteChanged.connect(self._palette_changed)

    def _render_stylesheet(self):
        # Native System placeholder/disabled text can be translucent with <2:1
        # contrast. Use an opaque semantic color without overriding the native
        # application palette; regenerate it when the actual palette arrives.
        palette=self.application.palette()
        color=status_foreground("disabled",palette)
        sidebar="palette(alternate-base)"
        if self.mode=="System":
            background=palette.color(QPalette.ColorRole.AlternateBase)
            for role in (QPalette.ColorRole.WindowText,QPalette.ColorRole.Text):
                foreground=palette.color(role); alpha=foreground.alphaF()
                painted=QColor.fromRgbF(*(fg*alpha+bg*(1-alpha) for fg,bg in zip(
                    (foreground.redF(),foreground.greenF(),foreground.blueF()),
                    (background.redF(),background.greenF(),background.blueF()))))
                low,high=sorted((_luminance(background),_luminance(painted)))
                if (high+.05)/(low+.05)<4.5:
                    # Cocoa dark AlternateBase can be light gray behind white
                    # labels. Reuse its window surface, not a manual OS palette.
                    sidebar="palette(window)"
                    break
        return self._template.replace("@disabled-text@",color.name()).replace("@sidebar-background@",sidebar)

    def _palette_changed(self,*_args):
        # colorSchemeChanged precedes the native palette. React to the actual
        # new palette, including for hidden pages/windows, without freezing a
        # System palette into application-specific overrides.
        app=self.application
        if self.mode!="System" or self._busy or app.styleSheet()!=self._stylesheet: return
        if self._last_palette==app.palette(): return
        self._busy=True
        try:
            self._stylesheet=self._render_stylesheet()
            app.setStyleSheet(self._stylesheet)
            self._last_palette=QPalette(app.palette())
        finally: self._busy=False

    def apply(self,mode,stylesheet):
        if self._busy: return
        mode=mode if mode in {"Light","Dark"} else "System"
        app=self.application; changed=mode!=self.mode; before=QPalette(app.palette())
        self._busy=True; self.mode=mode; self._template=stylesheet
        try:
            hints=app.styleHints()
            if changed and hasattr(hints,"setColorScheme"):
                # Qt6.8+ can also theme native controls; Qt6.7 keeps the palette/
                # stylesheet path. This is only a platform hint, not a promise.
                hints.setColorScheme({"Light":Qt.ColorScheme.Light,"Dark":Qt.ColorScheme.Dark}.get(mode,Qt.ColorScheme.Unknown))
            if mode=="System":
                if changed: app.setPalette(QPalette())  # Release manual palette overrides once.
            else:
                palette=_theme_palette(app,mode)
                if app.palette()!=palette: app.setPalette(palette)
            self._stylesheet=self._render_stylesheet()
            if changed or before!=app.palette() or self._last_palette!=app.palette() or app.styleSheet()!=self._stylesheet:
                app.setStyleSheet(self._stylesheet)
                self._last_palette=QPalette(app.palette())
        finally: self._busy=False


def apply_theme(application, mode):
    stylesheet = """QWidget { font-size: 13px; }
QLabel#pageTitle { font-size: 23px; font-weight: 600; padding: 2px 0px; }
QLabel#brand { font-size: 17px; font-weight: 700; }
QLabel#muted { color: palette(window-text); }
QWidget#sidebar { background: @sidebar-background@; border-right: 1px solid palette(mid); }
QListWidget#navigation { background: transparent; outline: none; }
QListWidget#navigation::item { border-radius: 7px; padding: 3px 8px; margin: 2px 0px; }
QListWidget#navigation::item:selected { background: palette(highlight); color: palette(highlighted-text); }
QListWidget#navigation::item:focus { border: 1px solid palette(text); }
QPushButton { padding: 6px 12px; border: 1px solid palette(mid); border-radius: 6px; background: palette(button); }
QPushButton:hover { border-color: palette(highlight); }
QPushButton:focus, QToolButton:focus { border: 2px solid palette(highlight); }
QPushButton:pressed { background: palette(alternate-base); }
QPushButton[primary="true"] { background: palette(highlight); color: palette(highlighted-text); border-color: palette(highlight); font-weight: 600; }
QPushButton:disabled { color: @disabled-text@; background: palette(window); }
QMenu::item:disabled { color: @disabled-text@; }
QToolButton { padding: 5px 8px; border: 1px solid transparent; border-radius: 5px; }
QToolButton:disabled { color: @disabled-text@; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { padding: 6px; border: 1px solid palette(mid); border-radius: 6px; background: palette(base); selection-background-color: palette(highlight); }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: palette(highlight); }
QPlainTextEdit[dropActive="true"] { border: 2px solid palette(highlight); background: palette(alternate-base); }
QGroupBox { font-weight: 600; border: 1px solid palette(mid); border-radius: 8px; margin-top: 18px; padding: 14px 10px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0px 5px; }
QTableWidget { border: 1px solid palette(mid); border-radius: 6px; background: palette(base); alternate-background-color: palette(alternate-base); }
QHeaderView::section { background: palette(window); color: palette(window-text); border: none; border-bottom: 1px solid palette(mid); padding: 9px 6px; font-weight: 600; }
QTableWidget::item { padding: 4px 6px; }
QProgressBar { border: none; border-radius: 4px; background: palette(alternate-base); text-align: center; min-height: 16px; }
QProgressBar::chunk { background: palette(highlight); border-radius: 4px; }
QScrollArea { border: none; }
QStatusBar { border-top: 1px solid palette(mid); }
"""
    state=getattr(application,"_morgan_theme_state",None)
    if state is None:
        state=_ThemeState(application); application._morgan_theme_state=state
    state.apply(mode,stylesheet)
