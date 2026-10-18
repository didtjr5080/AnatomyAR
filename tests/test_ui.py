import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from src.app import Controller
from src.core.state import AppState,Status
from src.core.settings import Settings
from src.core.packets import PosePacket,RenderPacket,now_ms
from src.ui.exhibition_window import owned_image,match_screen
from test_core import frame,person


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_qimage_owns_memory(app):
    rgb=np.full((10,10,3),127,np.uint8)
    image=owned_image(rgb)
    rgb[:]=0
    assert image.pixelColor(5,5).red()==127


def test_mode_change_keeps_workers_in_single_window(app):
    state=AppState(); controller=Controller(app,state)
    marker=object(); controller.camera=marker; controller.tracker=marker
    state.update(mode="bones",opacity=.8,mirror=False)
    assert controller.camera is marker and controller.tracker is marker
    assert controller.control.preview.state is state
    assert not hasattr(controller,"exhibition")
    assert not controller.control.preview.isWindow()
    assert state.snapshot()[0].mode=="bones"
    controller.camera=controller.tracker=None
    controller.timer.stop(); controller.stats_timer.stop()
    controller.control.allow_close=True; controller.control.close()


def test_stale_and_wrong_generation_never_display_overlay(app):
    state=AppState(); controller=Controller(app,state)
    f=frame(ts=now_ms()-250,generation=0)
    pose=PosePacket(0,f.timestamp_ms,0,person(),10)
    render=RenderPacket(f,pose,np.ones((720,1280,3),np.uint8),((10,10,"old"),),Status.TRACKING,"",0)
    controller.current=render
    controller.preview.put(frame(ts=now_ms(),generation=0))
    controller.tick()
    assert controller.control.preview.labels==()
    controller.output.put(replace(render,frame=replace(f,generation_id=999)))
    controller.tick()
    assert controller.control.preview.labels==()
    controller.timer.stop(); controller.stats_timer.stop()
    controller.control.allow_close=True; controller.control.close()


def test_duplicate_monitor_names_require_unambiguous_match():
    class Screen:
        def __init__(self,x): self.x=x
        def name(self): return "duplicate"
        def serialNumber(self): return ""
        def manufacturer(self): return "test"
        def model(self): return "test"
        def geometry(self):
            return SimpleNamespace(x=lambda:self.x,y=lambda:0,width=lambda:1920,height=lambda:1080)
    a,b=Screen(-1920),Screen(0)
    saved={"name":"duplicate","serial":"","manufacturer":"test","model":"test"}
    assert match_screen(saved,[a,b]) is None
    saved["geometry"]="-1920,0,1920,1080"
    assert match_screen(saved,[b,a]) is a
