from dataclasses import asdict
from enum import Enum
from threading import Lock
from PySide6.QtCore import QObject, Signal
from .settings import Settings, validate


class Status(str, Enum):
    STOPPED = "중지"
    STARTING = "준비 중"
    WAITING_PERSON = "사람 대기"
    TRACKING = "추적 중"
    DEGRADED = "추적 제한"
    CAMERA_ERROR = "카메라 오류"
    MODEL_ERROR = "모델/자산 오류"


class AppState(QObject):
    changed = Signal()
    status_changed = Signal(object, str)

    def __init__(self, settings=None):
        super().__init__()
        self._lock = Lock()
        self._settings = settings or Settings()
        self.version = 0
        self.status = Status.STOPPED
        self.message = ""

    def snapshot(self):
        with self._lock:
            return validate(asdict(self._settings)), self.version

    def update(self, **changes):
        with self._lock:
            self._settings = validate({**asdict(self._settings), **changes})
            self.version += 1
        self.changed.emit()

    def replace(self, settings):
        self.update(**asdict(settings))

    def set_status(self, status, message=""):
        if (status, message) != (self.status, self.message):
            self.status, self.message = status, message
            self.status_changed.emit(status, message)
