import cv2
import numpy as np


def display_transform(width, height, view_width, view_height, fill=False):
    if min(width, height, view_width, view_height) <= 0:
        raise ValueError("영상/화면 크기는 양수여야 합니다")
    scale = (max if fill else min)(view_width / width, view_height / height)
    return scale, (view_width - scale * width) / 2, (view_height - scale * height) / 2


def mirror_x(x, width):
    return width - 1 - x


def inference_geometry(width, height, size):
    scale = size / max(width, height)
    rw, rh = max(1, round(width * scale)), max(1, round(height * scale))
    px, py = (size - rw) // 2, (size - rh) // 2
    return (size, size), (rw / width, rh / height, float(px), float(py))


def letterbox(bgr, size, transform):
    sx, sy, px, py = transform
    h, w = bgr.shape[:2]
    rw, rh = round(w * sx), round(h * sy)
    out = np.zeros((size[1], size[0], 3), np.uint8)
    out[int(py):int(py) + rh, int(px):int(px) + rw] = cv2.resize(bgr, (rw, rh))
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def restore_landmarks(landmarks, frame):
    pts = np.array([[p.x, p.y, p.z, p.visibility, p.presence] for p in landmarks], dtype=np.float32)
    if not len(pts):
        return np.empty((0, 5), np.float32)
    sx, sy, px, py = frame.transform
    iw, ih = frame.inference_size
    pts[:, 0] = (pts[:, 0] * iw - px) / sx
    pts[:, 1] = (pts[:, 1] * ih - py) / sy
    pts[:, 2] *= iw / sx
    return pts
