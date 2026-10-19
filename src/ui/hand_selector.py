"""Dwell selection from fresh pose packets; holding a stale image cannot click."""
import numpy as np


def palm_points(landmarks, width, height, confidence):
    if landmarks is None or landmarks.shape != (33, 5):
        return []
    hands = []
    for side, wrist, index, pinky in (("left",15,19,17),("right",16,20,18)):
        def usable(i):
            p=landmarks[i]
            return (np.isfinite(p).all() and min(p[3:])>=confidence
                    and 0<=p[0]<width and 0<=p[1]<height)
        if not usable(wrist): continue
        ids=[i for i in (wrist,index,pinky) if usable(i)]
        x,y=landmarks[ids,:2].mean(axis=0)
        hands.append((side,float(x),float(y)))
    return hands


class DwellSelector:
    def __init__(self, dwell_ms=800):
        self.dwell_ms=dwell_ms
        self.reset()

    def reset(self):
        self.target=None
        self.since=None
        self.last=None
        self.last_hit=None
        self.progress=0.0
        self.latched=False

    def update(self, hits, timestamp, now, max_age, selected, tracking_lost=False):
        if timestamp is None or not 0<=now-timestamp<=max_age:
            self.reset()
            return None
        if self.last is not None and timestamp<=self.last:
            return None
        if self.last is not None and timestamp-self.last>max_age:
            self.reset()
        self.last=timestamp
        if not hits:
            if tracking_lost and self.last_hit is not None and timestamp-self.last_hit<=150:
                return None
            self.target=self.since=None
            self.last_hit=None
            self.progress=0.0
            self.latched=False
            return None
        choices={mode for hand,mode in hits}
        if self.latched or len(choices)!=1 or next(iter(choices))==selected:
            self.target=self.since=None
            self.progress=0.0
            return None
        # Keep the same hand while counting; swapping hands must start a new dwell.
        target=self.target if self.target in hits else sorted(hits)[0]
        if target!=self.target:
            self.target,self.since=target,timestamp
        self.last_hit=timestamp
        self.progress=min(1.0,(timestamp-self.since)/self.dwell_ms)
        if self.progress>=1:
            self.latched=True
            return target[1]
        return None
