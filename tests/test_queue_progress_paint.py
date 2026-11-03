"""Actual QWidget painting: native Cocoa cannot draw NSViews into a bare QImage."""
import pytest
from PySide6.QtCore import QEvent,QIdentityProxyModel,QRect,Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QStyle,QStyleOptionViewItem,QWidget

from morgan_media_downloader.models import DownloadJob,DownloadOptions,MediaItem
from morgan_media_downloader.queue_model import PROGRESS_ROLE,QueueProgressDelegate,QueueTableModel

APP=QApplication.instance() or QApplication([])
BACKGROUND=QColor("#102030")


class DisplayProxy(QIdentityProxyModel):
    label=None
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if self.label is not None and role==Qt.ItemDataRole.DisplayRole and index.column()==3:
            return self.label
        return super().data(index,role)


class ProgressScene(QWidget):
    cell=QRect(360,80,220,40)
    def __init__(self):
        super().__init__()
        self.setFixedSize(800,240)
        self.model=QueueTableModel()
        self.job=DownloadJob(MediaItem("https://example.test/progress","Synthetic progress"),DownloadOptions(authentication_mode="None"))
        self.model.sync([self.job],"Media","Direct")
        self.proxy=DisplayProxy(self); self.proxy.setSourceModel(self.model)
        self.delegate=QueueProgressDelegate(self)
        self.direction=Qt.LayoutDirection.LeftToRight
        self.state=QStyle.StateFlag.State_Enabled|QStyle.StateFlag.State_Active
        self.painter_preserved=False

    def paintEvent(self,event):
        painter=QPainter(self)
        try:
            painter.fillRect(self.rect(),BACKGROUND)
            painter.setClipRect(self.rect())
            before=(painter.transform(),painter.clipRegion(),painter.pen(),painter.brush(),painter.font())
            option=QStyleOptionViewItem(); option.widget=self; option.palette=self.palette(); option.rect=self.cell
            option.state=self.state; option.direction=self.direction
            self.delegate.paint(painter,option,self.proxy.index(0,3))
            self.painter_preserved=before==(painter.transform(),painter.clipRegion(),painter.pen(),painter.brush(),painter.font())
        finally: painter.end()

    def frame(self,progress):
        self.job.progress=progress; self.model.update_job(self.job,"Direct")
        self.update(); APP.processEvents()
        return self.grab().toImage()


@pytest.fixture
def scene():
    value=ProgressScene(); value.show(); APP.processEvents()
    try: yield value
    finally:
        value.close(); value.deleteLater(); APP.sendPostedEvents(value,QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("progress,direction,state",[
    (0,Qt.LayoutDirection.LeftToRight,QStyle.StateFlag.State_Enabled),
    (25,Qt.LayoutDirection.LeftToRight,QStyle.StateFlag.State_Enabled),
    (100,Qt.LayoutDirection.LeftToRight,QStyle.StateFlag.State_Enabled),
    (25,Qt.LayoutDirection.RightToLeft,QStyle.StateFlag.State_Enabled),
    (25,Qt.LayoutDirection.LeftToRight,QStyle.StateFlag.State_Enabled|QStyle.StateFlag.State_Selected),
    (25,Qt.LayoutDirection.LeftToRight,QStyle.StateFlag.State_None),
    (float("nan"),Qt.LayoutDirection.LeftToRight,QStyle.StateFlag.State_Enabled),
])
def test_actual_progress_paint_stays_in_offset_cell_and_restores_painter(scene,progress,direction,state):
    scene.direction=direction; scene.state=state|QStyle.StateFlag.State_Active
    image=scene.frame(progress); scale=image.devicePixelRatio()
    points=[(x,y) for y in range(image.height()) for x in range(image.width()) if image.pixelColor(x,y)!=BACKGROUND]
    assert points, "Known progress or unknown text must actually paint"
    outside=[(x,y) for x,y in points if not scene.cell.contains(int(x/scale),int(y/scale))]
    assert not outside, f"Paint escaped the progress cell: {len(outside)} pixels; first={outside[0] if outside else None}"
    assert scene.painter_preserved


@pytest.mark.parametrize("direction",[Qt.LayoutDirection.LeftToRight,Qt.LayoutDirection.RightToLeft])
def test_offset_progress_fill_tracks_zero_quarter_full_in_both_directions(scene,direction):
    scene.direction=direction
    empty,quarter,full=(scene.frame(progress) for progress in (0,25,100))
    scale=empty.devicePixelRatio()
    left,right=((380,100),(509,100)) if direction==Qt.LayoutDirection.LeftToRight else ((430,100),(560,100))
    def pixel(image,point): return image.pixelColor(int(point[0]*scale),int(point[1]*scale))
    assert (pixel(quarter,left)!=pixel(empty,left))==(direction==Qt.LayoutDirection.LeftToRight)
    assert (pixel(quarter,right)!=pixel(empty,right))==(direction==Qt.LayoutDirection.RightToLeft)
    assert pixel(full,left)!=pixel(empty,left) and pixel(full,right)!=pixel(empty,right)


def test_visible_percentage_uses_display_role_even_when_native_style_ignores_bar_text(scene):
    scene.proxy.label="25.0%"; first=scene.frame(25)
    scene.proxy.label="75.0%"; second=scene.frame(25)
    assert scene.proxy.index(0,3).data(PROGRESS_ROLE)==25
    scale=first.devicePixelRatio()
    # Literal right-hand label area, separate from the native track. Only the
    # DisplayRole changed: the extractor progress/track is identical.
    differences=sum(first.pixelColor(x,y)!=second.pixelColor(x,y)
        for x in range(int(520*scale),int(578*scale))
        for y in range(int(85*scale),int(115*scale)))
    assert differences>0, "The native style must not silently drop percentage text"
