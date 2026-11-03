"""Bounded header/viewport presentation; never scans jobs, persists or owns work."""
from PySide6.QtCore import QEvent,QObject
from PySide6.QtWidgets import QHeaderView,QMenu,QToolButton


DEFAULT_COLUMNS = {
    "Media": ("Title","Status","Progress","Speed","ETA","Destination"),
    "Torrents": ("Title","Status","Progress","Down","ETA","Destination"),
    "All": ("Title","Status","Progress","Speed","ETA","Destination"),
}
REQUIRED_COLUMNS = frozenset(("Title","Status","Progress"))


class QueuePresentation(QObject):
    def __init__(self,table,model,settings):
        super().__init__(table)
        self.table=table; self.model=model; self.settings=settings
        self._view=None; self._configuring=False
        self.columns_button=QToolButton(); self.columns_button.setText("Columns")
        self.columns_button.setAccessibleName("Choose queue columns")
        self.columns_button.setToolTip("Choose columns. Extra technical columns may need horizontal scrolling.")
        self.columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu=QMenu(self.columns_button); self.columns_button.setMenu(self.menu)
        self.column_actions={}
        table.horizontalHeader().sectionResized.connect(self._record_resize)
        table.viewport().installEventFilter(self); table.installEventFilter(self)
        self.configure(model.view)

    def _widths(self):
        values=self.settings().queue_column_widths
        values=values.get(self._view,{}) if isinstance(values,dict) else {}
        return values if isinstance(values,dict) else {}

    def _default_width(self,name):
        if name=="Status":
            return self.table.fontMetrics().horizontalAdvance("Completed with warnings ⚠")+12
        if name in {"Speed","Down","Up"}:
            return self.table.fontMetrics().horizontalAdvance("1023.9 KB/s")+12
        if name=="ETA":
            return self.table.fontMetrics().horizontalAdvance("999:59:59")+12
        return {"Progress":100,"Destination":80,
            "Type":48,"Source":100,"Downloaded / Total":140,
            "Format":150,"Connected peers":120,"Connected seeders":130}.get(name,160)

    def configure(self,view,*,force=False):
        if self._configuring or view!=self.model.view or (view==self._view and not force):
            return
        self._view=view; self._configuring=True
        try:
            root=self.settings().queue_visible_columns
            saved=root.get(view) if isinstance(root,dict) else None
            visible={name for name in saved if isinstance(name,str)} if isinstance(saved,list) else set(DEFAULT_COLUMNS[view])
            visible|=REQUIRED_COLUMNS
            header=self.table.horizontalHeader(); header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(40)
            widths=self._widths()
            for column,name in enumerate(self.model.columns):
                self.table.setColumnHidden(column,name not in visible)
                size=widths.get(name)
                if type(size) is not int or not 40<=size<=2000:
                    size=self._default_width(name)
                header.resizeSection(column,size)
            self.menu.clear(); self.column_actions={}
            for name in self.model.columns:
                action=self.menu.addAction(name); action.setCheckable(True); action.setChecked(name in visible)
                action.setEnabled(name not in REQUIRED_COLUMNS)
                action.triggered.connect(lambda checked,v=view,n=name:self._set_visible(v,n,checked))
                self.column_actions[name]=action
            self.menu.addSeparator()
            self.reset_action=self.menu.addAction("Reset columns to defaults",lambda _checked=False,v=view:self._reset_view(v))
        finally:
            self._configuring=False
        self._fit_title()

    def _set_visible(self,view,name,visible):
        if view!=self._view or view!=self.model.view or name in REQUIRED_COLUMNS:
            return
        self.table.setColumnHidden(self.model.columns.index(name),not visible)
        settings=self.settings()
        if not isinstance(settings.queue_visible_columns,dict): settings.queue_visible_columns={}
        settings.queue_visible_columns[view]=[field for column,field in enumerate(self.model.columns) if not self.table.isColumnHidden(column)]
        self._fit_title()

    def _fit_title(self):
        if self._configuring or self._view!=self.model.view or "Title" in self._widths():
            return
        self._configuring=True
        try:
            title=self.model.columns.index("Title")
            occupied=sum(self.table.columnWidth(column) for column in range(len(self.model.columns))
                if column!=title and not self.table.isColumnHidden(column))
            self.table.horizontalHeader().resizeSection(title,max(160,self.table.viewport().width()-occupied))
        finally:
            self._configuring=False

    def _record_resize(self,column,_old,width):
        if (self._configuring or self._view!=self.model.view or not 0<=column<len(self.model.columns)
                or not 40<=width<=2000):
            return
        settings=self.settings()
        if not isinstance(settings.queue_column_widths,dict):
            settings.queue_column_widths={}
        values=settings.queue_column_widths.get(self._view)
        if not isinstance(values,dict):
            values={}; settings.queue_column_widths[self._view]=values
        field=self.model.columns[column]; values[field]=width
        if field!="Title": self._fit_title()

    def _reset_view(self,view):
        if view!=self._view or view!=self.model.view:
            return
        settings=self.settings()
        for values in (settings.queue_visible_columns,settings.queue_column_widths):
            if isinstance(values,dict): values.pop(view,None)
        self.configure(view,force=True)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Resize and watched is self.table.viewport():
            self._fit_title()
        elif event.type()==QEvent.Type.FontChange and watched is self.table:
            self.configure(self.model.view,force=True)
        return False
