import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from dataclasses import replace
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from src.core.state import AppState
from src.core.settings import Settings
from src.ui.hand_selector import DwellSelector,palm_points
from src.ui.exhibition_window import VideoView,owned_image
from src.ui import exhibition_window


def test_dwell_requires_fresh_samples_and_leaving_to_rearm():
    selector=DwellSelector(800)
    hit=[("left","bones")]
    assert selector.update(hit,1000,1000,200,"muscles") is None
    assert selector.update(hit,1000,1190,200,"muscles") is None
    for timestamp in range(1100,1800,100):
        assert selector.update(hit,timestamp,timestamp,200,"muscles") is None
    assert selector.update(hit,1800,1800,200,"muscles")=="bones"
    assert selector.update([("left","muscles")],1900,1900,200,"bones") is None
    assert selector.latched
    selector.update([],2000,2000,200,"bones")
    assert not selector.latched


def test_loss_conflict_hand_swap_and_stale_cancel_progress():
    selector=DwellSelector(800)
    selector.update([("left","bones")],1000,1000,200,"muscles")
    selector.update([("left","bones")],1150,1150,200,"muscles")
    assert selector.progress>0
    selector.update([("right","bones")],1200,1200,200,"muscles")
    assert selector.progress==0
    selector.update([("left","bones"),("right","muscles")],1300,1300,200,"muscles")
    assert selector.target is None
    selector.update([("left","bones")],1400,1700,200,"muscles")
    assert selector.target is None
    selector.update([("left","bones")],1800,1800,200,"muscles")
    selector.update([("left","bones")],2200,2200,200,"muscles")
    assert selector.progress==0


def test_unreliable_or_outside_hands_hidden():
    p=np.zeros((33,5),np.float32)
    p[15]=[100,150,0,1,1]
    assert palm_points(p,640,480,.6)==[("left",100.,150.)]
    p[15,0]=np.nan
    assert palm_points(p,640,480,.6)==[]
    p[15]=[1000,150,0,1,1]
    assert palm_points(p,640,480,.6)==[]


@pytest.mark.parametrize("mirror",[False,True])
@pytest.mark.parametrize("fit",["fit","fill"])
def test_hand_hits_the_visible_button_with_mirror_and_fit(monkeypatch,mirror,fit):
    app=QApplication.instance() or QApplication([])
    state=AppState(replace(Settings(),mirror=mirror,fit=fit))
    view=VideoView(state); view.resize(900,850)
    image=owned_image(np.zeros((720,1280,3),np.uint8))
    view.present(image)
    rect=view.mode_rects()["bones"]
    w,h,scale,ox,oy=view.image_geometry()
    x=(rect.center().x()-ox)/scale
    if mirror: x=w-1-x
    y=(rect.center().y()-oy)/scale
    points=np.zeros((33,5),np.float32)
    points[15]=[x,y,0,1,1]
    clock=[1000]
    monkeypatch.setattr(exhibition_window,"now_ms",lambda:clock[0])
    for t in range(1000,1900,100):
        clock[0]=t
        view.present(image,points=points,timestamp_ms=t)
    assert state.snapshot()[0].mode=="bones"
    assert view.hand_cursors[0][1].x()==pytest.approx(rect.center().x(),abs=.01)
    view.update_hands(2201)
    assert not view.hand_cursors and view.selector.target is None
    QTest.mouseClick(view,Qt.MouseButton.LeftButton,pos=view.mode_rects()["muscles"].center().toPoint())
    assert state.snapshot()[0].mode=="muscles"
    view.close()
