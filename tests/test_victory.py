import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from types import SimpleNamespace
from dataclasses import replace
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication,QLabel
from src.ui.victory_countdown import VictoryCountdown
from src.tracking.gesture_tracker import victory_hands
from src.tracking.mediapipe_tracker import verify_gesture_model
from src.core.packets import PosePacket,RenderPacket
from src.core.state import AppState,Status
from src.app import Controller
from src import app as app_module
from src.ui import exhibition_window
from test_core import frame,person


def test_countdown_requires_continuous_fresh_victory_and_release_after_resume():
    timer=VictoryCountdown()
    seen=[]
    for t in range(1000,4501,100):
        triggered=timer.update(("left",),t,t,200)
        if t in (1500,2500,3500): seen.append(timer.number)
        assert triggered==(t==4500)
    assert seen==[3,2,1]
    for t in range(4600,9000,100):
        assert not timer.update(("left",),t,t,200)
        assert timer.number is None
    timer.update((),9000,9000,200)
    timer.update(("left",),9100,9100,200)
    assert not timer.wait_release and timer.since==9100


@pytest.mark.parametrize("interruption",["loss","swap","gap","stale"])
def test_victory_arming_cancels_on_loss_hand_swap_or_stale_input(interruption):
    timer=VictoryCountdown()
    for t in range(1000,1400,100): timer.update(("left",),t,t,200)
    assert timer.number is None
    if interruption=="loss": timer.update((),1400,1400,200)
    if interruption=="swap": timer.update(("right",),1400,1400,200)
    if interruption=="gap": timer.update(("left",),1700,1700,200)
    if interruption=="stale": timer.update(("left",),1400,1701,200)
    assert timer.number is None


def test_repeated_pose_cannot_advance_countdown():
    timer=VictoryCountdown()
    timer.update(("left",),1000,1000,200)
    assert not timer.update(("left",),1000,1190,200)
    assert timer.since==1000 and timer.number is None
    assert not timer.update(("left",),1000,4500,200)
    assert timer.since is None


def test_victory_classifier_uses_hands_without_body_pose_and_rejects_other_signs():
    f=frame(); p=person(); sx,sy,px,py=f.transform; iw,ih=f.inference_size
    wrist=SimpleNamespace(x=(p[15,0]*sx+px)/iw,y=(p[15,1]*sy+py)/ih)
    category=SimpleNamespace(category_name="Victory",score=.9)
    result=SimpleNamespace(gestures=[[category]],hand_landmarks=[[wrist]*21],
                           handedness=[[SimpleNamespace(category_name="Left",score=.9)]])
    assert victory_hands(result,f)==("left",)
    category.category_name="Open_Palm"
    assert not victory_hands(result,f)
    category.category_name="Victory"; category.score=.4
    assert not victory_hands(result,f)
    category.score=.9; wrist.x=-.5
    assert not victory_hands(result,f)
    wrist.x=(p[15,0]*sx+px)/iw; result.handedness[0][0].score=.2
    assert not victory_hands(result,f)


def test_real_gesture_model_video_inference_and_close():
    import mediapipe as mp
    options=mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(verify_gesture_model())),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,num_hands=2)
    with mp.tasks.vision.GestureRecognizer.create_from_options(options) as model:
        image=mp.Image(image_format=mp.ImageFormat.SRGB,data=np.zeros((256,256,3),np.uint8))
        for timestamp in (100,200):
            assert not model.recognize_for_video(image,timestamp).gestures


def test_controller_freezes_until_resume_and_discards_buffered_frames(monkeypatch):
    app=QApplication.instance() or QApplication([])
    state=AppState(); controller=Controller(app,state)
    controller.timer.stop(); controller.stats_timer.stop()
    clock=[1000]
    monkeypatch.setattr(app_module,"now_ms",lambda:clock[0])
    monkeypatch.setattr(exhibition_window,"now_ms",lambda:clock[0])
    view=controller.control.preview
    def send(t,hands=("left",),value=80):
        clock[0]=t
        f=frame(fid=t,ts=t,generation=controller.generation)
        pose=PosePacket(t,t,controller.generation,person(),10,hands)
        rgb=np.full((720,1280,3),value,np.uint8)
        controller.output.put(RenderPacket(f,pose,rgb,(),Status.TRACKING,"",state.snapshot()[1]))
        controller.tick()
    try:
        controller.control.show(); app.processEvents()
        assert not controller.control.settings_dock.isVisible()
        assert not any(label.isVisible() for label in controller.control.findChildren(QLabel))
        for t in range(1000,4501,100): send(t)
        assert view.frozen and controller.control.resume_button.isEnabled()
        assert view.countdown is None and not view.hand_cursors
        held=view.image.copy()
        state.update(mode="bones",mirror=False,standby=True)
        send(6000,value=200)
        assert view.image==held and view.frozen_settings.mode=="muscles"
        assert not view.frozen_settings.standby
        controller.stop(); controller.tick()
        assert view.frozen and view.image==held
        clock[0]=7000
        controller.control.resume_button.click()
        assert not view.frozen and view.image.isNull()
        assert not controller.control.resume_button.isEnabled()
        state.update(standby=False)
        send(6900,value=200)
        assert view.image.isNull()
        send(7100,value=120)
        assert view.image.pixelColor(0,0).red()==120
        assert controller.countdown.wait_release
        send(7200,hands=())
        assert not controller.countdown.wait_release
    finally:
        controller.control.allow_close=True
        controller.control.close()


def test_inference_latency_does_not_repeatedly_cancel_fresh_countdown(monkeypatch):
    app=QApplication.instance() or QApplication([])
    controller=Controller(app,AppState())
    controller.timer.stop(); controller.stats_timer.stop()
    clock=[1000]
    monkeypatch.setattr(app_module,"now_ms",lambda:clock[0])
    monkeypatch.setattr(exhibition_window,"now_ms",lambda:clock[0])
    try:
        for received in range(1000,4501,100):
            clock[0]=received
            captured=received-130
            f=frame(fid=received,ts=captured,generation=controller.generation)
            pose=PosePacket(received,captured,controller.generation,person(),50,("left",))
            rgb=np.full((720,1280,3),80,np.uint8)
            controller.output.put(RenderPacket(f,pose,rgb,(),Status.TRACKING,"",0))
            controller.tick()
        assert controller.control.preview.frozen
    finally:
        controller.control.allow_close=True
        controller.control.close()
