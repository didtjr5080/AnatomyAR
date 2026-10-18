from collections import defaultdict, deque
from threading import Lock
import time
import ctypes
import os
import numpy as np


def process_memory():
    if os.name!="nt":
        return {}
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)] + [(name,ctypes.c_size_t) for name in (
            "PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage","PrivateUsage")]
    counters=Counters(); counters.cb=ctypes.sizeof(counters)
    get=ctypes.windll.psapi.GetProcessMemoryInfo
    get.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if get(wintypes.HANDLE(-1),ctypes.byref(counters),counters.cb):
        return {"working_set_bytes":counters.WorkingSetSize,"private_bytes":counters.PrivateUsage}
    return {}


class Metrics:
    def __init__(self):
        self.lock = Lock()
        self.events = defaultdict(lambda: deque(maxlen=240))
        self.samples = defaultdict(lambda: deque(maxlen=600))
        self.counts = defaultdict(int)

    def event(self, name):
        with self.lock:
            self.events[name].append(time.monotonic())
            self.counts[name] += 1

    def sample(self, name, value):
        with self.lock:
            self.samples[name].append(float(value))

    def snapshot(self):
        now = time.monotonic()
        with self.lock:
            result = {f"{k}_count": v for k, v in self.counts.items()}
            for name, events in self.events.items():
                recent = [t for t in events if now - t < 2]
                result[name + "_fps"] = (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) > 1 else 0
            for name, values in self.samples.items():
                result[name + "_mean"] = float(np.mean(values))
                result[name + "_p95"] = float(np.percentile(values, 95))
            return result
