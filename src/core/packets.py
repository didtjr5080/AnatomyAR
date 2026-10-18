from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
import time
import numpy as np


def now_ms():
    return time.monotonic_ns() // 1_000_000


class TimestampClock:
    def __init__(self):
        self.last = -1

    def next(self, now=None):
        self.last = max(self.last + 1, now_ms() if now is None else now)
        return self.last


@dataclass(frozen=True)
class FramePacket:
    frame_id: int
    timestamp_ms: int
    generation_id: int
    bgr: np.ndarray
    inference_size: tuple[int, int]
    transform: tuple[float, float, float, float]


@dataclass(frozen=True)
class PosePacket:
    frame_id: int
    timestamp_ms: int
    generation_id: int
    landmarks: np.ndarray
    inference_ms: float
    victory_hands: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderPacket:
    frame: FramePacket
    pose: PosePacket
    rgb: np.ndarray
    labels: tuple
    status: object
    message: str
    version: int


class Latest:
    """One owned packet; signals never carry an unbounded video queue."""
    def __init__(self):
        self.lock = Lock()
        self.value = None
        self.dropped = 0

    def put(self, value):
        with self.lock:
            if self.value is not None:
                self.dropped += 1
            self.value = value

    def take(self):
        with self.lock:
            value, self.value = self.value, None
            return value

    def peek(self):
        with self.lock:
            return self.value


class FrameMatcher:
    def __init__(self, generation, capacity=4):
        self.generation = generation
        self.capacity = capacity
        self.frames = OrderedDict()
        self.last_timestamp = -1
        self.dropped = 0
        self.lock = Lock()
        self.closed = False

    def add(self, frame):
        with self.lock:
            if self.closed or frame.generation_id != self.generation:
                return False
            self.frames[frame.timestamp_ms] = frame
            while len(self.frames) > self.capacity:
                self.frames.popitem(last=False)
                self.dropped += 1
            return True

    def match(self, timestamp, generation, now, max_age):
        with self.lock:
            if self.closed or generation != self.generation:
                return None
            frame = self.frames.pop(timestamp, None)
            if frame is None or timestamp <= self.last_timestamp or not 0 <= now - timestamp <= max_age:
                self.dropped += 1
                return None
            self.last_timestamp = timestamp
            for old in list(self.frames):
                if old < timestamp:
                    del self.frames[old]
                    self.dropped += 1
            return frame

    def close(self):
        with self.lock:
            self.closed = True
            self.frames.clear()
