"""Small reusable presentation widgets; no downloader or persistence policy."""
from PySide6.QtCore import QEvent,Qt, Signal, QSize
from PySide6.QtGui import QIcon,QPainter,QPalette,QPixmap,QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QStackedWidget, QToolButton, QStyle,
                               QScrollArea, QFrame, QFormLayout, QApplication)
from PySide6.QtWidgets import QTableWidget
from .theme import status_foreground


class StatusLabel(QLabel):
    """Semantic status on a window surface; no backend or persistence policy."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._tone = "neutral"
        self._updating_color = False
        self._refresh_color()

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        self._refresh_color()

    def _refresh_color(self) -> None:
        if getattr(self, "_updating_color", True):
            return
        self._updating_color = True
        try:
            color = status_foreground(self._tone, QApplication.palette())
            stylesheet = f"color: {color.name()}"
            if self.styleSheet() != stylesheet:
                self.setStyleSheet(stylesheet)
        finally:
            self._updating_color = False

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._refresh_color()


class MediaSelectionTable(QTableWidget):
    """Space checks/unchecks the highlighted visible rows as one operation."""
    checksChanged = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            rows = sorted({index.row() for index in self.selectionModel().selectedRows()
                           if not self.isRowHidden(index.row())})
            if rows:
                checked = self.item(rows[0], 0).checkState() != Qt.CheckState.Checked
                previous = self.blockSignals(True)
                try:
                    for row in rows:
                        self.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                finally: self.blockSignals(previous)
                self.checksChanged.emit()
                event.accept(); return
        super().keyPressEvent(event)


class NavigationShell(QWidget):
    """Sidebar navigation retaining the small tab API used by existing actions."""
    currentChanged = Signal(int)
    collapsedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        sidebar = self.sidebar = QWidget(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(164)
        self._collapsed = False
        side = QVBoxLayout(sidebar); side.setContentsMargins(12, 24, 12, 16); side.setSpacing(16)
        brand = QLabel("MORGAN"); brand.setObjectName("brand")
        subtitle = QLabel("Media Downloader"); subtitle.setWordWrap(True); subtitle.setObjectName("muted")
        side.addWidget(brand); side.addWidget(subtitle)
        self.navigation = QListWidget(); self.navigation.setObjectName("navigation"); self.navigation.setAccessibleName("Main sections")
        self.navigation.setFrameShape(QFrame.Shape.NoFrame); side.addWidget(self.navigation, 1)
        hint = QLabel("⌘1–5  Navigate"); hint.setObjectName("muted"); side.addWidget(hint)
        self._captions = (brand, subtitle, hint)
        self.sidebar_toggle = QToolButton(); self.sidebar_toggle.setText("‹")
        self.sidebar_toggle.setAccessibleName("Collapse sidebar"); self.sidebar_toggle.setToolTip("Collapse sidebar")
        self.sidebar_toggle.clicked.connect(lambda: self.setCollapsed(not self._collapsed))
        side.addWidget(self.sidebar_toggle)
        self.stack = QStackedWidget(); self._labels = []; self._shortcuts = []
        layout.addWidget(sidebar); layout.addWidget(self.stack, 1)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self._changed)

    def isCollapsed(self):
        return self._collapsed

    def setCollapsed(self, collapsed):
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.sidebar.setFixedWidth(64 if collapsed else 164)
        for caption in self._captions:
            caption.setVisible(not collapsed)
        for index, label in enumerate(self._labels):
            item = self.navigation.item(index)
            item.setText("" if collapsed else label)
            item.setSizeHint(QSize(28 if collapsed else 132, 40))
        label = "Expand sidebar" if collapsed else "Collapse sidebar"
        self.sidebar_toggle.setText("›" if collapsed else "‹")
        self.sidebar_toggle.setAccessibleName(label); self.sidebar_toggle.setToolTip(label)
        self.collapsedChanged.emit(collapsed)

    def _changed(self, index):
        self.navigation.setCurrentRow(index); self.currentChanged.emit(index)

    def _download_icon(self):
        # Keep the existing standard arrow's shape, but supply explicit readable
        # modes. The Cocoa standard pixmap can stay black after palette changes.
        source=self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown).pixmap(QSize(20,20),self.devicePixelRatioF())
        palette=self.palette(); icon=QIcon()
        for mode,color in ((QIcon.Mode.Normal,palette.color(QPalette.ColorRole.WindowText)),
                (QIcon.Mode.Active,palette.color(QPalette.ColorRole.WindowText)),
                (QIcon.Mode.Selected,palette.color(QPalette.ColorRole.HighlightedText)),
                (QIcon.Mode.Disabled,palette.color(QPalette.ColorGroup.Disabled,QPalette.ColorRole.WindowText))):
            pixmap=QPixmap(source); painter=QPainter(pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(),color); painter.end(); icon.addPixmap(pixmap,mode)
        return icon

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange,QEvent.Type.StyleChange) and hasattr(self,"navigation") and self.navigation.count():
            self.navigation.item(0).setIcon(self._download_icon())

    def addTab(self, widget, label):
        index = self.stack.addWidget(widget); self._labels.append(label)
        icons = [QStyle.StandardPixmap.SP_ArrowDown, QStyle.StandardPixmap.SP_FileDialogListView,
                 QStyle.StandardPixmap.SP_FileDialogDetailedView, QStyle.StandardPixmap.SP_ComputerIcon,
                 QStyle.StandardPixmap.SP_FileDialogContentsView]
        icon=self._download_icon() if index==0 else self.style().standardIcon(icons[min(index,4)])
        item = QListWidgetItem(icon, "" if self._collapsed else label)
        item.setData(Qt.ItemDataRole.AccessibleTextRole, label); item.setToolTip(label)
        item.setSizeHint(QSize(28 if self._collapsed else 132, 40)); self.navigation.addItem(item)
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
