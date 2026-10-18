import time
import cv2
from PySide6.QtCore import QThread, Signal
from ..core.packets import FramePacket, TimestampClock
from ..rendering.coordinates import inference_geometry
from .devices import camera_apartment,select_camera


class CameraWorker(QThread):
    frame_ready = Signal(object)
    opened = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, settings, generation, preview, metrics):
        super().__init__()
        self.settings, self.generation = settings, generation
        self.preview, self.metrics = preview, metrics

    def run(self):
        with camera_apartment():
            self.capture()

    def capture(self):
        s = self.settings
        camera = None
        clock = TimestampClock()
        try:
            opened = select_camera(s.camera_index,s,self.isInterruptionRequested)
            if opened is None:
                if self.isInterruptionRequested(): return
                raise RuntimeError("카메라 영상을 열지 못했습니다. 장치가 없는 뜻은 아닙니다. 자동 선택·재검색, Windows 카메라 권한과 다른 앱 점유를 확인하세요.")
            camera,first_frame,info = opened
            self.opened.emit(self.generation,info)
            frame_id, failures = 0, 0
            while not self.isInterruptionRequested():
                start = time.perf_counter()
                if first_frame is not None:
                    ok,bgr = True,first_frame
                    first_frame = None
                else:
                    ok,bgr = camera.read()
                self.metrics.sample("capture_ms",(time.perf_counter()-start)*1000)
                if not ok or bgr is None or bgr.size == 0:
                    failures += 1
                    if failures >= 5:
                        raise RuntimeError("카메라 읽기 실패: 연결을 확인한 뒤 다시 시작하세요")
                    self.msleep(100)
                    continue
                failures = 0
                image = bgr.copy()
                image.setflags(write=False)
                size,transform = inference_geometry(image.shape[1],image.shape[0],s.inference_size)
                frame = FramePacket(frame_id,clock.next(),self.generation,image,size,transform)
                self.preview.put(frame)
                self.frame_ready.emit(frame)
                self.metrics.event("capture")
                frame_id += 1
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(self.generation,str(exc))
        finally:
            if camera is not None: camera.release()
