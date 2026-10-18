import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from src.app import Controller
from src import app as app_module
from src.ui import exhibition_window
from src.core.state import AppState,Status
from src.core.packets import PosePacket,RenderPacket
from test_core import frame,person


@pytest.fixture
def scene(monkeypatch):
    app=QApplication.instance() or QApplication([])
    controller=Controller(app,AppState())
    controller.timer.stop(); controller.stats_timer.stop()
    clock=[1000]
    monkeypatch.setattr(app_module,"now_ms",lambda:clock[0])
    monkeypatch.setattr(exhibition_window,"now_ms",lambda:clock[0])
    def send(t,value=200,hands=(),composed=True):
        clock[0]=t
        f=frame(fid=t,ts=t,generation=controller.generation)
        pose=PosePacket(t,t,controller.generation,person(),30,hands)
        labels=((500,300,"anatomy"),) if composed else ()
        status=Status.TRACKING if composed else Status.WAITING_PERSON
        packet=RenderPacket(f,pose,np.full((720,1280,3),value,np.uint8),labels,status,"",controller.state.snapshot()[1])
        controller.output.put(packet)
        controller.tick()
    try:
        yield controller,clock,send
    finally:
        controller.control.allow_close=True
        controller.control.close()


def test_small_render_gap_keeps_complete_image_instead_of_flashing_raw(scene):
    controller,clock,send=scene
    send(1000,value=200)
    view=controller.control.preview
    for t in (1201,1300,1450):
        clock[0]=t
        controller.preview.put(frame(ts=t,generation=controller.generation))
        controller.tick()
        assert view.image.pixelColor(0,0).red()==200
        assert not view.hand_cursors
    send(1480,value=210)
    assert view.image.pixelColor(0,0).red()==210
    clock[0]=2000
    controller.preview.put(frame(ts=2000,generation=controller.generation))
    controller.tick()
    assert view.image.pixelColor(0,0).red()==0


def test_brief_missing_pose_holds_complete_frame_but_long_loss_releases_it(scene):
    controller,clock,send=scene
    send(1000,value=200)
    send(1250,value=50,composed=False)
    assert controller.control.preview.image.pixelColor(0,0).red()==200
    send(1600,value=50,composed=False)
    assert controller.control.preview.image.pixelColor(0,0).red()==50


def test_countdown_latches_and_photo_uses_last_good_composite(scene):
    controller,clock,send=scene
    for t in range(1000,1600,100): send(t,hands=("left",))
    assert controller.control.preview.countdown==3
    send(1700,value=210,hands=())
    for t in range(1800,4501,100):
        send(t,value=50,hands=(),composed=False)
        assert controller.control.preview.image.pixelColor(0,0).red()==210
    view=controller.control.preview
    assert view.frozen and view.countdown is None
    assert view.image.pixelColor(0,0).red()==210
    held=view.image.copy()
    for t in range(4600,7000,100): send(t,value=20,composed=False)
    assert view.image==held
    assert controller.control.resume_button.isEnabled()


def test_countdown_completes_on_gui_clock_even_if_model_stops_delivering(scene):
    controller,clock,send=scene
    for t in range(1000,1600,100): send(t,hands=("left",))
    for t,number in ((2500,2),(3500,1),(4500,None)):
        clock[0]=t
        controller.tick()
        assert controller.control.preview.countdown==number
    assert controller.control.preview.frozen


def test_setting_change_does_not_reuse_previous_modes_composite(scene):
    controller,clock,send=scene
    send(1000,value=200)
    controller.state.update(mode="bones")
    send(1100,value=50,composed=False)
    assert controller.control.preview.image.pixelColor(0,0).red()==50


def test_delayed_result_stream_never_alternates_anatomy_with_raw(scene):
    controller,clock,send=scene
    view=controller.control.preview
    for step in range(625):
        now=1000+step*16
        clock[0]=now
        controller.preview.put(frame(fid=now,ts=now,generation=controller.generation))
        if step%10==0:
            captured=now-170
            f=frame(fid=now,ts=captured,generation=controller.generation)
            pose=PosePacket(now,captured,controller.generation,person(),100)
            rgb=np.full((720,1280,3),200,np.uint8)
            controller.output.put(RenderPacket(f,pose,rgb,((500,300,"anatomy"),),Status.TRACKING,"",0))
        controller.tick()
        assert view.image.pixelColor(0,0).red()==200
