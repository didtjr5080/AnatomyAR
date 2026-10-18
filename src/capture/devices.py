"""Discover cameras with the same backend/index pairs used for capture."""
from contextlib import contextmanager
import ctypes
import os
import cv2
from PySide6.QtCore import QThread, Signal

BACKENDS = ((cv2.CAP_DSHOW, "DirectShow"), (cv2.CAP_MSMF, "Media Foundation"))
SCAN_COUNT = 6


@contextmanager
def camera_apartment():
    result = ctypes.windll.ole32.CoInitializeEx(None, 0) if os.name == "nt" else None
    try:
        yield
    finally:
        if result in (0, 1):
            ctypes.windll.ole32.CoUninitialize()


def open_camera(index, settings=None, cancelled=lambda: False):
    """Return a camera only after a real frame is read; caller owns release()."""
    for backend, name in BACKENDS:
        if cancelled():
            return None
        camera = cv2.VideoCapture()
        keep = False
        try:
            if not camera.open(index, backend):
                continue
            if settings is not None:
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, settings.capture_width)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.capture_height)
                camera.set(cv2.CAP_PROP_FPS, settings.capture_fps)
            for _ in range(3):
                if cancelled():
                    return None
                ok, frame = camera.read()
                if ok and frame is not None and frame.size:
                    info = {"index": index, "backend": name, "width": frame.shape[1],
                            "height": frame.shape[0], "fps": camera.get(cv2.CAP_PROP_FPS)}
                    keep = True
                    return camera, frame, info
        except cv2.error:
            pass
        finally:
            if not keep:
                camera.release()
    return None


def select_camera(index, settings, cancelled=lambda: False):
    # Old settings used 0 as the only default; recover from that unavailable entry.
    indices = list(range(SCAN_COUNT)) if index in (-1, 0) else [index]
    for candidate in indices:
        if cancelled():
            return None
        opened = open_camera(candidate, settings, cancelled)
        if opened is not None:
            return opened
    return None


class CameraScanner(QThread):
    discovered = Signal(object)

    def run(self):
        devices = []
        with camera_apartment():
            for index in range(SCAN_COUNT):
                if self.isInterruptionRequested():
                    return
                opened = open_camera(index, cancelled=self.isInterruptionRequested)
                if opened is not None:
                    camera, frame, info = opened
                    camera.release()
                    devices.append(info)
        if not self.isInterruptionRequested():
            self.discovered.emit(devices)
