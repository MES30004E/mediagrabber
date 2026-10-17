"""Semantic Qt palettes and restrained shared styling. No theme dependency."""
from PySide6.QtGui import QColor, QPalette


def apply_theme(application, mode):
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
    if application.palette() != palette: application.setPalette(palette)
    stylesheet = """QWidget { font-size: 13px; }
QLabel#pageTitle { font-size: 23px; font-weight: 600; padding: 2px 0px; }
QLabel#brand { font-size: 17px; font-weight: 700; }
QLabel#muted { color: palette(placeholder-text); }
QWidget#sidebar { background: palette(alternate-base); border-right: 1px solid palette(mid); }
QListWidget#navigation { background: transparent; outline: none; }
QListWidget#navigation::item { border-radius: 7px; padding: 3px 8px; margin: 2px 0px; }
QListWidget#navigation::item:selected { background: palette(highlight); color: palette(highlighted-text); }
QListWidget#navigation::item:focus { border: 1px solid palette(text); }
QPushButton { padding: 6px 12px; border: 1px solid palette(mid); border-radius: 6px; background: palette(button); }
QPushButton:hover { border-color: palette(highlight); }
QPushButton:focus, QToolButton:focus { border: 2px solid palette(highlight); }
QPushButton:pressed { background: palette(alternate-base); }
QPushButton[primary="true"] { background: palette(highlight); color: palette(highlighted-text); border-color: palette(highlight); font-weight: 600; }
QPushButton:disabled { color: palette(mid); background: palette(window); }
QToolButton { padding: 5px 8px; border: 1px solid transparent; border-radius: 5px; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { padding: 6px; border: 1px solid palette(mid); border-radius: 6px; background: palette(base); selection-background-color: palette(highlight); }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: palette(highlight); }
QPlainTextEdit[dropActive="true"] { border: 2px solid palette(highlight); background: palette(alternate-base); }
QGroupBox { font-weight: 600; border: 1px solid palette(mid); border-radius: 8px; margin-top: 18px; padding: 14px 10px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0px 5px; }
QTableWidget { border: 1px solid palette(mid); border-radius: 6px; background: palette(base); alternate-background-color: palette(alternate-base); }
QHeaderView::section { background: palette(window); color: palette(placeholder-text); border: none; border-bottom: 1px solid palette(mid); padding: 9px 6px; font-weight: 600; }
QTableWidget::item { padding: 4px 6px; }
QProgressBar { border: none; border-radius: 4px; background: palette(alternate-base); text-align: center; min-height: 16px; }
QProgressBar::chunk { background: palette(highlight); border-radius: 4px; }
QScrollArea { border: none; }
QStatusBar { border-top: 1px solid palette(mid); }
"""
    if application.styleSheet() != stylesheet: application.setStyleSheet(stylesheet)
