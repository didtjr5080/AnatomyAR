from dataclasses import replace
import hashlib
import json
import time
from threading import Event
import numpy as np
from PySide6.QtCore import QThread, Signal
from ..core.packets import FrameMatcher, Latest, PosePacket, RenderPacket, now_ms
from ..core.settings import ROOT
from ..core.state import Status
from ..rendering.coordinates import letterbox, restore_landmarks
from ..rendering.compositor import Compositor
from .smoothing import PoseFilter
from .gesture_tracker import victory_hands


def verify_model(path=None,manifest_name="manifest.json"):
    path = path or ROOT / "models/pose_landmarker_lite.task"
    manifest = json.loads((ROOT / "models" / manifest_name).read_text(encoding="utf-8"))
    if not path.is_file():
        raise FileNotFoundError(f"모델 누락: {path.name} · scripts/fetch_model.py를 실행하세요")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError(f"모델 체크섬 불일치: {path.name}")
    return path


def verify_gesture_model():
    return verify_model(ROOT/"models/gesture_recognizer.task","gesture_manifest.json")


class TrackerWorker(QThread):
    ready = Signal(int)
    failed = Signal(int, str)

    def __init__(self, state, generation, output, metrics):
        super().__init__()
        self.state, self.generation, self.output, self.metrics = state,generation,output,metrics
        self.input, self.results = Latest(),Latest()
        self.matcher = FrameMatcher(generation)
        self.wake = Event()
        self.closing = Event()

    def submit(self, frame):
        # DirectConnection: only this bounded, locked handoff runs on capture's thread.
        if not self.closing.is_set() and frame.generation_id == self.generation:
            self.input.put(frame)
            self.wake.set()

    def stop(self):
        self.closing.set()
        self.requestInterruption()
        self.matcher.close()
        self.wake.set()

    def run(self):
        model = gesture_model = None
        try:
            import mediapipe as mp
            path = verify_model()
            gesture_path = verify_gesture_model()
            compositor = Compositor()
            smoother = PoseFilter()
            def callback(result, image, timestamp):
                if self.closing.is_set():
                    return
                settings,_ = self.state.snapshot()
                frame = self.matcher.match(timestamp,self.generation,now_ms(),settings.max_age_ms)
                if frame is None or self.closing.is_set():
                    return
                points = restore_landmarks(result.pose_landmarks[0],frame) if result.pose_landmarks else np.empty((0,5),np.float32)
                self.results.put((frame,points,now_ms()))
                self.wake.set()
            opts = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(path),delegate=mp.tasks.BaseOptions.Delegate.CPU),
                running_mode=mp.tasks.vision.RunningMode.LIVE_STREAM,num_poses=1,
                output_segmentation_masks=False,result_callback=callback)
            model = mp.tasks.vision.PoseLandmarker.create_from_options(opts)
            gesture_model=mp.tasks.vision.GestureRecognizer.create_from_options(
                mp.tasks.vision.GestureRecognizerOptions(
                    base_options=mp.tasks.BaseOptions(model_asset_path=str(gesture_path),delegate=mp.tasks.BaseOptions.Delegate.CPU),
                    running_mode=mp.tasks.vision.RunningMode.VIDEO,num_hands=2))
            self.ready.emit(self.generation)
            last_submit, last_render, last_version = -1,None,-1
            submitted = {}
            while not self.isInterruptionRequested():
                self.wake.wait(.01)
                self.wake.clear()
                settings,version = self.state.snapshot()
                result = self.results.take()
                if result is not None:
                    frame,points,received = result
                    start_time = submitted.pop(frame.timestamp_ms,received)
                    inference_ms = max(0,received-start_time)
                    filtered,message = smoother.update(points,frame.timestamp_ms,frame.bgr.shape[1],frame.bgr.shape[0],settings.confidence,settings.smoothing_ms)
                    hands=()
                    if now_ms()-frame.timestamp_ms<=settings.max_age_ms:
                        begin=time.perf_counter()
                        rgb=letterbox(frame.bgr,frame.inference_size,frame.transform)
                        gesture_result=gesture_model.recognize_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb),frame.timestamp_ms)
                        hands=victory_hands(gesture_result,frame)
                        self.metrics.sample("gesture_ms",(time.perf_counter()-begin)*1000)
                    pose = PosePacket(frame.frame_id,frame.timestamp_ms,self.generation,filtered,inference_ms,hands)
                    last_render = (frame,pose,message)
                    self.metrics.event("inference")
                    self.metrics.sample("inference_ms",inference_ms)
                if last_render and (result is not None or version != last_version):
                    frame,pose,message = last_render
                    if now_ms()-frame.timestamp_ms <= settings.max_age_ms:
                        begin = time.perf_counter()
                        rgb,labels,limited,count = compositor.render(frame.bgr,pose.landmarks,settings,frame.timestamp_ms)
                        if not len(pose.landmarks):
                            status = Status.WAITING_PERSON
                        elif limited or message or count == 0 and settings.mode != "original":
                            status = Status.DEGRADED
                        else:
                            status = Status.TRACKING
                        self.metrics.sample("composite_ms",(time.perf_counter()-begin)*1000)
                        self.metrics.event("composite")
                        self.output.put(RenderPacket(frame,pose,rgb,labels,status,message or limited,version))
                    else:
                        last_render = None
                        smoother.reset()
                    last_version = version
                frame = self.input.take()
                if frame is not None and frame.timestamp_ms-last_submit >= settings.inference_interval_ms:
                    if now_ms()-frame.timestamp_ms <= settings.max_age_ms:
                        rgb = letterbox(frame.bgr,frame.inference_size,frame.transform)
                        image = mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb)
                        if self.matcher.add(frame):
                            submitted[frame.timestamp_ms] = now_ms()
                            model.detect_async(image,frame.timestamp_ms)
                            last_submit = frame.timestamp_ms
                            submitted = {k:v for k,v in submitted.items() if k >= frame.timestamp_ms-1000}
                elif frame is not None:
                    self.metrics.event("throttled")
        except Exception as exc:
            if not self.closing.is_set():
                self.failed.emit(self.generation,str(exc))
        finally:
            self.closing.set()
            self.matcher.close()
            if model is not None:
                model.close()
            if gesture_model is not None:
                gesture_model.close()
