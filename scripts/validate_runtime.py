"""Synthetic evidence only. Never reads or records a camera."""
import argparse
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import platform
import threading
import time
import cv2
import numpy as np
from src.core.settings import Settings,ROOT
from src.rendering.compositor import Compositor
from src.tracking.mediapipe_tracker import verify_model


def synthetic_pose(phase=0,scene="front"):
    p=np.zeros((33,5),np.float32)
    p[:,3:]=1
    coords={0:(640,135),2:(660,125),5:(620,125),7:(685,140),8:(595,140),
        11:(745,235),12:(535,235),13:(790,345),14:(490,345),15:(810,450),16:(470,450),
        23:(710,430),24:(570,430),25:(710,550),26:(570,550),27:(720,680),28:(560,680)}
    if scene=="raise":
        coords.update({13:(855,215),15:(925,135),14:(425,215),16:(355,135)})
    elif scene=="elbow":
        coords.update({15:(865,275),16:(395,275)})
    elif scene=="knee":
        coords.update({25:(790,515),27:(825,630)})
    elif scene=="turn":
        coords.update({11:(725,240),12:(555,230),23:(700,435),24:(580,425)})
        p[11,2]=35; p[12,2]=-35
    if phase:
        coords[15]=(810+55*math.sin(phase),395+55*math.cos(phase))
        coords[16]=(470-55*math.sin(phase),395+55*math.cos(phase))
    for index,xy in coords.items(): p[index,:2]=xy
    return p


def backdrop():
    bg=np.full((720,1280,3),(32,25,18),np.uint8)
    for x in range(0,1280,80): cv2.line(bg,(x,0),(x,720),(46,38,29),1)
    for y in range(0,720,80): cv2.line(bg,(0,y),(1280,y),(46,38,29),1)
    cv2.putText(bg,"SYNTHETIC POSE / NOT CAMERA",(30,690),cv2.FONT_HERSHEY_SIMPLEX,.65,(150,165,180),1,cv2.LINE_AA)
    return bg


def model_check():
    import mediapipe as mp
    event=threading.Event(); observed=[]
    def callback(result,image,timestamp):
        observed.append({"timestamp":timestamp,"poses":len(result.pose_landmarks)})
        event.set()
    options=mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(verify_model()),delegate=mp.tasks.BaseOptions.Delegate.CPU),
        running_mode=mp.tasks.vision.RunningMode.LIVE_STREAM,result_callback=callback)
    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as model:
        image=mp.Image(image_format=mp.ImageFormat.SRGB,data=np.zeros((256,256,3),np.uint8))
        model.detect_async(image,100)
        assert event.wait(10),"LIVE_STREAM callback timed out"
        assert observed[0]=={"timestamp":100,"poses":0}
    return observed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence",action="store_true")
    parser.add_argument("--frames",type=int,default=120)
    args=parser.parse_args()
    cv2.setNumThreads(2)
    folder=ROOT/"docs/evidence"
    folder.mkdir(parents=True,exist_ok=True)
    report={"environment":"development PC; NOT Galaxy Book2", "python":platform.python_version(),
            "model_async_blank_frame":model_check(),"frames_per_mode":args.frames,
            "input":"synthetic landmarks; no camera capture", "modes":{}}
    compositor=Compositor(); bg=backdrop()
    for mode in ("bones","muscles"):
        settings=replace(Settings(),mode=mode)
        timings=[]
        for i in range(args.frames+5):
            start=time.perf_counter()
            image,labels,message,count=compositor.render(bg,synthetic_pose(i*.07),settings,1000+i*33)
            elapsed=(time.perf_counter()-start)*1000
            if i>=5: timings.append(elapsed)
        report["modes"][mode]={"composite_mean_ms":float(np.mean(timings)),"composite_p95_ms":float(np.percentile(timings,95)),
            "composite_capacity_fps":float(1000/np.mean(timings)),"parts":count}
        if args.evidence:
            for scene in ("front","raise","elbow","knee","turn"):
                compositor.flex.reset()
                for settle in range(20):
                    image,_,_,_=compositor.render(bg,synthetic_pose(scene=scene),settings,1000+settle*33)
                cv2.imwrite(str(folder/f"{mode}-{scene}.png"),cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
            compositor.flex.reset()
            image,_,_,_=compositor.render(bg,synthetic_pose(),settings)
            cv2.imwrite(str(folder/f"{mode}-detail.png"),cv2.cvtColor(image[65:480,480:820],cv2.COLOR_RGB2BGR))
            video=cv2.VideoWriter(str(folder/f"{mode}-synthetic-motion.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),24,(1280,720))
            assert video.isOpened()
            compositor.flex.reset()
            try:
                for i in range(120):
                    image,_,_,_=compositor.render(bg,synthetic_pose(i*.06),settings,1000+i*42)
                    video.write(cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
            finally: video.release()
    if args.evidence:
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication
        from src.core.state import AppState
        from src.app import Controller
        from src.ui.exhibition_window import owned_image
        app=QApplication.instance() or QApplication([])
        state=AppState(replace(Settings(),mirror=False))
        controller=Controller(app,state)
        controller.timer.stop(); controller.stats_timer.stop()
        controller.control.resize(1920,1080)
        controller.control.show()
        for mode in ("bones","muscles"):
            state.update(mode=mode)
            image,labels,_,_=compositor.render(bg,synthetic_pose(),state.snapshot()[0])
            qimage=owned_image(image)
            controller.control.preview.present(qimage,labels,synthetic_pose(),"가상 좌표 검증 화면 · 카메라 영상 아님")
            app.processEvents()
            controller.control.grab().save(str(folder/f"unified-{mode}-1080.png"))
        controller.control.allow_close=True; controller.control.close()
    (ROOT/"docs/synthetic-performance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__": main()
