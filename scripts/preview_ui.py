"""Preview the unified UI and hand selection with synthetic coordinates only."""
import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from dataclasses import replace
import cv2
from PySide6.QtWidgets import QApplication
from src.app import Controller
from src.core.state import AppState
from src.core.settings import ROOT,Settings
from src.rendering.compositor import Compositor
from src.ui.exhibition_window import owned_image
from src.ui import exhibition_window
from src import app as app_module
from src.core.packets import FramePacket,PosePacket,RenderPacket
from src.core.state import Status
from src.rendering.coordinates import inference_geometry
from scripts.validate_runtime import backdrop,synthetic_pose


def main():
    app=QApplication.instance() or QApplication([])
    state=AppState(replace(Settings(),mirror=False))
    controller=Controller(app,state)
    controller.timer.stop(); controller.stats_timer.stop()
    controller.control.resize(1280,850)
    controller.control.show()
    app.processEvents()
    folder=ROOT/"docs/evidence"
    folder.mkdir(parents=True,exist_ok=True)
    compositor=Compositor()
    view=controller.control.preview
    for mode in ("muscles","bones"):
        state.update(mode=mode)
        rgb,labels,_,_=compositor.render(backdrop(),synthetic_pose(),state.snapshot()[0])
        view.present(owned_image(rgb),labels,points=synthetic_pose(),message="가상 좌표 검증 화면 · 카메라 영상 아님")
        app.processEvents()
        assert controller.control.grab().save(str(folder/f"unified-{mode}.png"))
    state.update(mode="muscles")
    rgb,labels,_,_=compositor.render(backdrop(),synthetic_pose(),state.snapshot()[0])
    image=owned_image(rgb)
    view.present(image,points=synthetic_pose())
    w,h,scale,ox,oy=view.image_geometry()
    center=view.mode_rects()["bones"].center()
    points=synthetic_pose()
    points[15:23,3:]=0
    points[15]=[(center.x()-ox)/scale,(center.y()-oy)/scale,0,1,1]
    old_clock=exhibition_window.now_ms
    try:
        for timestamp in range(1000,1900,100):
            exhibition_window.now_ms=lambda t=timestamp:t
            view.present(image,labels,points,"가상 손 좌표 검증 · 실제 카메라 영상 아님",timestamp)
            app.processEvents()
            if timestamp==1500:
                assert controller.control.grab().save(str(folder/"unified-hand-progress.png"))
        assert state.snapshot()[0].mode=="bones","Hand dwell did not switch mode"
    finally:
        exhibition_window.now_ms=old_clock
    rgb,labels,_,_=compositor.render(backdrop(),synthetic_pose(),state.snapshot()[0])
    view.present(owned_image(rgb),labels,points=synthetic_pose(),message="가상 좌표 검증 화면 · 카메라 영상 아님")
    controller.control.settings_dock.show()
    app.processEvents()
    assert controller.control.grab().save(str(folder/"unified-settings.png"))
    controller.control.settings_dock.hide()
    points=synthetic_pose()
    points[:,:2]=(points[:,:2]-[640,135])*2.6+[640,180]
    points[23:,3:]=0
    bg=backdrop()
    cv2.circle(bg,(640,180),105,(165,185,205),-1)
    cv2.putText(bg,"FACE",(585,190),cv2.FONT_HERSHEY_SIMPLEX,1,(30,40,50),2)
    for mode in ("muscles","bones"):
        state.update(mode=mode)
        rgb,labels,_,_=compositor.render(bg,points,state.snapshot()[0])
        view.present(owned_image(rgb),labels,points=points,message="상체 체험 · 얼굴 보존 / 아래쪽 페이드 · 가상 좌표")
        app.processEvents()
        assert controller.control.grab().save(str(folder/f"closeup-{mode}.png"))
    points=synthetic_pose()
    points[15,:2]=(450,420)
    points[16,:2]=(830,420)
    for mode in ("muscles","bones"):
        state.update(mode=mode)
        rgb,labels,_,_=compositor.render(backdrop(),points,state.snapshot()[0])
        view.present(owned_image(rgb),labels,points=points,message="양팔 교차 · 팔 표시 유지 · 가상 좌표")
        app.processEvents()
        assert controller.control.grab().save(str(folder/f"crossed-arms-{mode}.png"))
    state.update(mode="muscles")
    points=synthetic_pose()
    points[:,:2]=(points[:,:2]-[640,240])*.35+[640,240]
    rgb,labels,_,_=compositor.render(backdrop(),points,state.snapshot()[0])
    view.present(owned_image(rgb),labels,points=points)
    app.processEvents()
    assert controller.control.grab().save(str(folder/"distant-selection.png"))
    bg=backdrop()
    points=synthetic_pose()
    rgb,labels,_,_=compositor.render(bg,points,state.snapshot()[0])
    size,transform=inference_geometry(1280,720,640)
    old_app_clock=app_module.now_ms
    old_view_clock=exhibition_window.now_ms
    try:
        for timestamp in range(10000,13501,100):
            app_module.now_ms=lambda t=timestamp:t
            exhibition_window.now_ms=lambda t=timestamp:t
            frame=FramePacket(timestamp,timestamp,controller.generation,bg,size,transform)
            pose=PosePacket(timestamp,timestamp,controller.generation,points,10,("left",))
            controller.output.put(RenderPacket(frame,pose,rgb,labels,Status.TRACKING,"",state.snapshot()[1]))
            controller.tick()
            app.processEvents()
            if timestamp in (10500,11500,12500):
                assert controller.control.grab().save(str(folder/f"countdown-{view.countdown}.png"))
        assert view.frozen and controller.control.resume_button.isEnabled()
        assert controller.control.grab().save(str(folder/"frozen.png"))
        controller.control.settings_dock.show()
        app.processEvents()
        assert controller.control.grab().save(str(folder/"frozen-controls.png"))
        controller.control.resume_button.click()
        assert not view.frozen
    finally:
        app_module.now_ms=old_app_clock
        exhibition_window.now_ms=old_view_clock
    controller.control.allow_close=True
    controller.control.close()
    print("Minimal UI, hand mode selection, 3-2-1 freeze and control-button resume previews verified.")


if __name__=="__main__": main()
