from dataclasses import dataclass
import cv2
import numpy as np

LIMBS = {"upper_arm": (11, 13, 12, 14, .30), "forearm": (13, 15, 14, 16, .23),
         "thigh": (23, 25, 24, 26, .45), "shin": (25, 27, 26, 28, .28)}
NAMES = {"torso": ("흉곽·척추·골반", "대흉근·복부"),
         "upper_arm": ("상완골", "상완 근육"), "forearm": ("요골·척골", "전완 근육"),
         "thigh": ("대퇴골", "대퇴사두근"), "shin": ("경골·비골", "전경골근·신근군")}


@dataclass
class Placement:
    part: str
    side: str
    points: np.ndarray
    depth: float
    label: str
    opacity: float = 1.0
    upper_crop: bool = False


def valid(points, ids, width, height, threshold, margin=0):
    if points.shape != (33, 5):
        return False
    p = points[list(ids)]
    return bool(np.isfinite(p).all() and np.all(p[:, 3:] >= threshold)
                and np.all((p[:, 0] >= -margin*width) & (p[:, 0] < (1+margin)*width))
                and np.all((p[:, 1] >= -margin*height) & (p[:, 1] < (1+margin)*height)))


def segment_quad(a, b, width):
    v = b - a
    length = float(np.linalg.norm(v))
    if not np.isfinite(length) or length < 4 or width <= 0:
        return None
    n = np.array([v[1], -v[0]], np.float32) / length * width / 2
    # The PNG's joint anchors sit inside the artwork to overlap connections.
    start, end = a - .068 * v, b + .068 * v
    return np.array([start - n, start + n, end + n, end - n], np.float32)


def segments_cross(a, b, c, d):
    def cross(u, v):
        return u[0] * v[1] - u[1] * v[0]
    return cross(b-a, c-a) * cross(b-a, d-a) < 0 and cross(d-c, a-c) * cross(d-c, b-c) < 0


def map_anatomy(points, width, height, settings):
    conf = settings.confidence
    if not valid(points, (11, 12), width, height, conf):
        return [], "카메라를 바라봐 주세요"
    p = points.copy()
    shoulder = np.linalg.norm(p[11, :2] - p[12, :2])
    # The unmirrored camera sees the subject's right on image left.
    if p[11, 0] <= p[12, 0] or shoulder < 25 or abs(p[11, 2] - p[12, 2]) > shoulder * .65:
        return [], "카메라를 바라봐 주세요"
    origin = p[[11, 12], :2].mean(axis=0)
    p[:, :2] = origin + (p[:, :2] - origin) * settings.scale
    p[:, :2] += (settings.offset_x * width, settings.offset_y * height)
    shoulder *= settings.scale
    placements, limited = [], False
    name_index = 0 if settings.mode == "bones" else 1
    torso_ids = (11, 12, 23, 24)
    if valid(points, torso_ids, width, height, conf, margin=.35):
        quad = p[[12, 11, 23, 24], :2].copy()
        torso_length = np.linalg.norm(quad[:2].mean(axis=0) - quad[2:].mean(axis=0))
        if cv2.isContourConvex(quad) and cv2.contourArea(quad) > 300 and .6 < torso_length / shoulder < 2.8:
            for pair in ((0, 1), (3, 2)):
                mid = quad[list(pair)].mean(axis=0)
                quad[list(pair)] = mid + (quad[list(pair)] - mid) * settings.widths["torso"]
            placements.append(Placement("torso", "center", quad, float(p[[11,12,23,24],2].mean()), NAMES["torso"][name_index]))
        else:
            limited = True
    else:
        # Only the chest is shown when hips cannot anchor the torso; fade its lower end.
        across = p[11,:2]-p[12,:2]
        down = np.array([-across[1],across[0]],np.float32)
        mid = p[[11,12],:2].mean(axis=0)
        bottom = mid + down*1.15
        quad = np.array([mid-across*.5,mid+across*.5,bottom+across*.35,bottom-across*.35],np.float32)
        for pair in ((0,1),(3,2)):
            center = quad[list(pair)].mean(axis=0)
            quad[list(pair)] = center+(quad[list(pair)]-center)*settings.widths["torso"]
        placements.append(Placement("torso","center",quad,float(p[[11,12],2].mean()),
                                    "흉곽" if name_index==0 else "대흉근",upper_crop=True))
        torso_ids = (11,12)
    crossed = set()
    for part in ("upper_arm", "forearm"):
        a,b,c,d,_ = LIMBS[part]
        if valid(points, (a,b,c,d), width, height, conf, margin=.35) and segments_cross(p[a,:2],p[b,:2],p[c,:2],p[d,:2]):
            crossed.add(part)
    for part, (a,b,c,d,ratio) in LIMBS.items():
        if settings.upper_only and part in ("thigh", "shin"):
            continue
        for side, start, end in (("left",a,b),("right",c,d)):
            if not valid(points, (start,end), width, height, conf, margin=.35):
                limited = True
                continue
            length = np.linalg.norm(p[end,:2] - p[start,:2])
            arm = part in ("upper_arm", "forearm")
            depth_ratio = abs(p[end,2]-p[start,2])/max(length,1)
            if length < shoulder * (.15 if arm else .24) or depth_ratio > (1.8 if arm else .85):
                limited = True
                continue
            part_width = shoulder * ratio * settings.widths[part] * settings.side_widths[side]
            if settings.mode == "bones":
                part_width *= .65
            quad = segment_quad(p[start,:2], p[end,:2], part_width)
            if quad is not None:
                opacity=float(np.clip((1.8-depth_ratio)/.95,0,1)) if arm else 1.0
                if part in crossed: opacity*=.75
                placements.append(Placement(part, side, quad, float(p[[start,end],2].mean()), ("왼 " if side=="left" else "오른 ") + NAMES[part][name_index],opacity=opacity))
    for item in placements:
        if item.part=="torso":
            ids=torso_ids
        else:
            a,b,c,d,_=LIMBS[item.part]
            ids=(a,b) if item.side=="left" else (c,d)
        strength=float(np.clip((points[list(ids),3:].min()-conf)/min(.2,1-conf),0,1))
        item.opacity*=strength*strength*(3-2*strength)
    placements.sort(key=lambda item: (-item.depth, item.part != "torso"))
    return placements, "상체만 보여도 괜찮아요 · 보이는 부위만 표시합니다" if limited or any(x.upper_crop for x in placements) else ""
