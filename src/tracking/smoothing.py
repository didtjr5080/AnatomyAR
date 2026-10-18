import math
import numpy as np


class PoseFilter:
    def __init__(self):
        self.reset()

    def reset(self):
        self.previous = None
        self.timestamp = None
        self.center = None
        self.candidate = None
        self.candidate_frames = 0

    def update(self, points, timestamp, width, height, confidence, tau_ms):
        if points.shape != (33, 5):
            self.reset()
            return np.empty((0, 5), np.float32), "표시된 영역에 서 주세요"
        out = points.copy()
        valid = np.isfinite(out).all(axis=1) & (out[:, 3] >= confidence) & (out[:, 4] >= confidence)
        # Keep nearby offscreen joints for clipping a visible limb/torso, never distant guesses.
        valid &= (out[:, 0] >= -.35*width) & (out[:, 0] < 1.35*width) & (out[:, 1] >= -.35*height) & (out[:, 1] < 1.35*height)
        out[~valid, 3:5] = 0
        if self.timestamp is not None and timestamp - self.timestamp > 250:
            self.reset()
        anchors = [i for i in (11, 12) if valid[i] and 0<=out[i,0]<width and 0<=out[i,1]<height]
        if len(anchors) < 2:
            self.reset()
            return out, "조명과 위치를 확인해 주세요"
        center = out[anchors, :2].mean(axis=0)
        if not .15 * width <= center[0] <= .85 * width:
            self.reset()
            out[:, 3:5] = 0
            return out, "표시된 영역에 서 주세요"
        if self.center is not None and np.linalg.norm(center - self.center) > .20 * width:
            self.previous = None
            if self.candidate is None or np.linalg.norm(center - self.candidate) > .08 * width:
                self.candidate, self.candidate_frames = center, 0
            self.candidate_frames += 1
            if self.candidate_frames < 3:
                out[:, 3:5] = 0
                return out, "한 분씩 체험해 주세요"
        self.candidate = None
        self.candidate_frames = 0
        if self.previous is not None and self.timestamp is not None:
            usable = valid & (self.previous[:, 3] >= confidence) & (self.previous[:, 4] >= confidence)
            alpha = 1.0 if tau_ms <= 0 else 1 - math.exp(-max(1, timestamp - self.timestamp) / tau_ms)
            out[usable, :3] = self.previous[usable, :3] + alpha * (out[usable, :3] - self.previous[usable, :3])
        self.previous, self.timestamp, self.center = out.copy(), timestamp, center
        return out, ""
