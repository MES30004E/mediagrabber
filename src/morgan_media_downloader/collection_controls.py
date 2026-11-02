"""Small native collection presentation; no execution, database or filesystem."""
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMenu, QProgressBar, QToolButton, QVBoxLayout, QWidget

from .collection_model import CollectionListModel


class CollectionControls(QWidget):
    filter_changed = Signal()
    clear_requested = Signal(str, object)
    action_requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model=CollectionListModel(self)
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout(); row.addWidget(QLabel("Collection:"))
        self.selector=QComboBox(); self.selector.setModel(self.model); self.selector.setAccessibleName("Queue collection")
        self.selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.selector.setMinimumContentsLength(18); self.selector.setMinimumWidth(180); self.selector.setMaximumWidth(260)
        self.selector.currentIndexChanged.connect(lambda *_:self.filter_changed.emit()); row.addWidget(self.selector,1)
        self.progress=QProgressBar(); self.progress.setMaximumWidth(165); self.progress.setMinimumWidth(110)
        self.progress.setAccessibleName("Collection average reported job progress")
        self.progress.setToolTip("Equal-weighted reported job progress; not bytes or a success rate."); row.addWidget(self.progress)
        self.actions_button=QToolButton(); self.actions_button.setText("Collection actions")
        self.actions_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.actions_menu=QMenu(self.actions_button); self.actions_button.setMenu(self.actions_menu)
        self.group_actions={}
        for action in ("Pause","Resume","Cancel"):
            item=self.actions_menu.addAction(action+" collection…"); self.group_actions[action]=item
            item.triggered.connect(lambda _checked=False,a=action,item=item:self.action_requested.emit(a,item.data() or self.scope()))
        self.actions_menu.aboutToShow.connect(self._capture_actions); row.addWidget(self.actions_button)
        layout.addLayout(row)
        self.summary_label=QLabel(); self.summary_label.setTextFormat(Qt.TextFormat.PlainText)
        self.summary_label.setWordWrap(True); self.summary_label.setMinimumWidth(0); self.summary_label.setMaximumHeight(42)
        layout.addWidget(self.summary_label)
        self.clear_button=QToolButton(); self.clear_button.setText("Clear entries")
        self.clear_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.clear_menu=QMenu(self.clear_button); self.clear_button.setMenu(self.clear_menu); self.clear_actions={}
        self.clear_heading=self.clear_menu.addSection("Scope")
        for status in ("Completed","Cancelled","Failed","Collection"):
            item=self.clear_menu.addAction(status+" entries…"); self.clear_actions[status]=item
            item.triggered.connect(lambda _checked=False,s=status,item=item:self.clear_requested.emit(s,item.data() or self.scope()))
        self.clear_menu.aboutToShow.connect(self._capture_clear)

    def scope(self):
        key=self.selector.currentData() or ""
        return key,self.model.summary(key).name

    @staticmethod
    def scope_label(scope):
        key,name=scope
        name=" ".join(name.split()); short=name[:80]+("…" if len(name)>80 else "")
        return f'collection "{short}" [{key[-6:]}]' if key else "all collections (entire queue)"

    def sync(self, *, jobs=None, job=None):
        previous=self.scope()[0]; blocker=QSignalBlocker(self.selector)
        try:
            if job is not None: self.model.update_job(job)
            elif jobs is not None: self.model.sync(jobs)
            row=self.model.row_for_id(previous); self.selector.setCurrentIndex(row if row is not None else 0)
        finally: del blocker
        return previous!=self.scope()[0]

    def refresh(self, bulk=None):
        key,_name=self.scope(); summary=self.model.summary(key)
        self.actions_button.setEnabled(bool(key and summary.total and bulk is None))
        self.clear_button.setEnabled(summary.total>0 and bulk is None)
        self.progress.setRange(0,100); self.progress.setEnabled(bulk is None)
        if bulk is not None:
            label=" ".join(str(bulk["label"]).split())[:80]
            self.summary_label.setText(f'Queue batch: {label} — {bulk["completed"]} completed; {bulk["failed"]} failed; {bulk["pending"]} pending. Totals refresh afterward.')
            self.progress.setValue(0); self.progress.setFormat("Totals updating")
        else:
            counts=" · ".join(f"{name}: {count}" for name,count in summary.counts if count)
            self.summary_label.setText(f"{summary.total:,} jobs · {counts}" if counts else f"{summary.total:,} jobs")
            self.progress.setValue(round(summary.progress) if summary.progress is not None else 0)
            self.progress.setFormat(f"Reported {summary.progress:.1f}%" if summary.progress is not None else "Unknown")

    def _capture_actions(self):
        scope=self.scope()
        for item in self.group_actions.values(): item.setData(scope)

    def _capture_clear(self):
        scope=self.scope(); key=scope[0]; counts=dict(self.model.summary(key).counts)
        self.clear_heading.setText("Scope: "+self.scope_label(scope))
        for status,item in self.clear_actions.items():
            total=self.model.summary(key).total if status=="Collection" else counts[status]
            item.setData(scope); item.setText(f'{"Current collection" if status=="Collection" else status+" entries"} ({total:,})…')
            item.setEnabled(bool(total and (status!="Collection" or key)))
