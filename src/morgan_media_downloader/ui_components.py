"""Small reusable presentation widgets; no downloader or persistence policy."""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QStackedWidget, QToolButton, QStyle,
                               QScrollArea, QFrame, QFormLayout)


class NavigationShell(QWidget):
    """Sidebar navigation retaining the small tab API used by existing actions."""
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        sidebar = QWidget(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(164)
        side = QVBoxLayout(sidebar); side.setContentsMargins(12, 24, 12, 16); side.setSpacing(16)
        brand = QLabel("MORGAN"); brand.setObjectName("brand")
        subtitle = QLabel("Media Downloader"); subtitle.setWordWrap(True); subtitle.setObjectName("muted")
        side.addWidget(brand); side.addWidget(subtitle)
        self.navigation = QListWidget(); self.navigation.setObjectName("navigation"); self.navigation.setAccessibleName("Main sections")
        self.navigation.setFrameShape(QFrame.Shape.NoFrame); side.addWidget(self.navigation, 1)
        hint = QLabel("⌘1–5  Navigate"); hint.setObjectName("muted"); side.addWidget(hint)
        self.stack = QStackedWidget(); self._labels = []; self._shortcuts = []
        layout.addWidget(sidebar); layout.addWidget(self.stack, 1)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self._changed)

    def _changed(self, index):
        self.navigation.setCurrentRow(index); self.currentChanged.emit(index)

    def addTab(self, widget, label):
        index = self.stack.addWidget(widget); self._labels.append(label)
        icons = [QStyle.StandardPixmap.SP_ArrowDown, QStyle.StandardPixmap.SP_FileDialogListView,
                 QStyle.StandardPixmap.SP_FileDialogDetailedView, QStyle.StandardPixmap.SP_ComputerIcon,
                 QStyle.StandardPixmap.SP_FileDialogContentsView]
        item = QListWidgetItem(self.style().standardIcon(icons[min(index, 4)]), label)
        item.setSizeHint(QSize(132, 40)); self.navigation.addItem(item)
        shortcut = QShortcut(QKeySequence(f"Meta+{index + 1}"), self)
        shortcut.activated.connect(lambda i=index: self.setCurrentIndex(i)); self._shortcuts.append(shortcut)
        if index == 0: self.navigation.setCurrentRow(0)
        return index

    def count(self): return self.stack.count()
    def tabText(self, index): return self._labels[index]
    def widget(self, index): return self.stack.widget(index)
    def currentWidget(self): return self.stack.currentWidget()
    def currentIndex(self): return self.stack.currentIndex()
    def setCurrentIndex(self, index): self.stack.setCurrentIndex(index)
    def setCurrentWidget(self, widget): self.stack.setCurrentWidget(widget)


class DisclosureSection(QWidget):
    def __init__(self, title, expanded=False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 4, 0, 4)
        self.toggle = QToolButton(); self.toggle.setText(title); self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.content = QWidget(); layout.addWidget(self.toggle); layout.addWidget(self.content)
        self.toggle.toggled.connect(self.setExpanded); self.setExpanded(expanded)

    def setExpanded(self, expanded):
        self.toggle.setChecked(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)


def settings_page():
    page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(20, 18, 12, 12)
    title = QLabel(); title.setObjectName("pageTitle"); title.setProperty("settingsTitle", True)
    outer.addWidget(title)
    scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
    body = QWidget(); body.setMaximumWidth(820)
    form = QFormLayout(body); form.setContentsMargins(2, 10, 16, 18); form.setSpacing(14)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(body); outer.addWidget(scroll, 1)
    return page, form


def page_heading(layout, title, detail):
    heading = QLabel(title); heading.setObjectName("pageTitle")
    caption = QLabel(detail); caption.setWordWrap(True); caption.setObjectName("muted")
    layout.addWidget(heading); layout.addWidget(caption)


def polish_table(table):
    table.setAlternatingRowColors(True); table.setShowGrid(False)
    table.verticalHeader().hide(); table.verticalHeader().setDefaultSectionSize(40)
    table.setWordWrap(False); table.setTextElideMode(Qt.TextElideMode.ElideRight)
