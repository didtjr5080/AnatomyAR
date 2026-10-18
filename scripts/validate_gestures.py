"""Explicit online validation with Google example images; never saves images or uses a camera."""
import json
import os
import time
import urllib.request
import cv2
import numpy as np
from src.core.settings import ROOT
from src.core.packets import FramePacket,now_ms
from src.rendering.coordinates import inference_geometry,letterbox
from src.tracking.gesture_tracker import victory_hands
from src.tracking.mediapipe_tracker import verify_gesture_model,TrackerWorker


def main():
    import mediapipe as mp
    cv2.setNumThreads(2)
    report={"source":"Google MediaPipe official example images; no webcam; images kept only in memory","samples":{}}
    options=mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(verify_gesture_model())),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,num_hands=2)
    victory_image=None
    with mp.tasks.vision.GestureRecognizer.create_from_options(options) as model:
        for index,name in enumerate(("victory","thumbs_up","pointing_up")):
            url=f"https://storage.googleapis.com/mediapipe-tasks/gesture_recognizer/{name}.jpg"
            with urllib.request.urlopen(url,timeout=30) as response:
                data=response.read(8*1024*1024+1)
            if len(data)>8*1024*1024: raise ValueError("Example image is too large")
            bgr=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
            if bgr is None: raise ValueError("Invalid example image")
            size,transform=inference_geometry(bgr.shape[1],bgr.shape[0],640)
            frame=FramePacket(index,1000+index*100,0,bgr,size,transform)
            image=mp.Image(image_format=mp.ImageFormat.SRGB,data=letterbox(bgr,size,transform))
            begin=time.perf_counter()
            result=model.recognize_for_video(image,frame.timestamp_ms)
            elapsed=(time.perf_counter()-begin)*1000
            hands=victory_hands(result,frame)
            report["samples"][name]={"categories":[{"gesture":items[0].category_name,"score":items[0].score}
                                                    for items in result.gestures if items],
                                     "gesture_ms":elapsed,"victory_hands":hands}
            assert bool(hands)==(name=="victory"),report["samples"][name]
            if name=="victory": victory_image=bgr
    os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
    from PySide6.QtWidgets import QApplication
    from src.app import Controller
    from src.core.state import AppState
    app=QApplication.instance() or QApplication([])
    controller=Controller(app,AppState())
    controller.timer.stop(); controller.stats_timer.stop()
    tracker=TrackerWorker(controller.state,controller.generation,controller.output,controller.metrics)
    errors=[]
    tracker.failed.connect(lambda generation,message:errors.append(message))
    controller.tracker=tracker
    size,transform=inference_geometry(victory_image.shape[1],victory_image.shape[0],640)
    begin=time.monotonic()
    tracker.start()
    try:
        index=0
        observations=[]
        previous=None
        while time.monotonic()-begin<15 and not controller.control.preview.frozen:
            tracker.submit(FramePacket(index,now_ms(),controller.generation,victory_image,size,transform))
            app.processEvents()
            controller.tick()
            if controller.last_display!=previous and controller.current is not None:
                previous=controller.last_display
                current=controller.current
                observations.append({"elapsed":round(time.monotonic()-begin,3),"hands":current.pose.victory_hands,
                                     "age_ms":now_ms()-current.frame.timestamp_ms,"number":controller.countdown.number})
            index+=1
            time.sleep(.033)
        report["pipeline"]={"frozen":controller.control.preview.frozen,"elapsed_seconds":time.monotonic()-begin,
                            "resume_button_enabled":controller.control.resume_button.isEnabled(),
                            "metrics":controller.metrics.snapshot(),"errors":errors,"observations":observations[-100:]}
        (ROOT/"docs/gesture-model-smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        assert controller.control.preview.frozen,"Actual gesture/worker/controller pipeline did not freeze; see docs/gesture-model-smoke.json"
        assert controller.control.resume_button.isEnabled()
        controller.control.resume_button.click()
        assert not controller.control.preview.frozen
        report["pipeline"]["resumed"]=True
    finally:
        tracker.stop()
        assert tracker.wait(5000),"Gesture/pose model shutdown timed out"
        controller.tracker=None
        controller.control.allow_close=True
        controller.control.close()
    (ROOT/"docs/gesture-model-smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__": main()
