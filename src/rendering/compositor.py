import json
import cv2
import numpy as np
from ..core.settings import ROOT
from .anatomy_mapper import map_anatomy
from .anatomy_mapper import valid
from .variants import FlexBlend,joint_angle
from .arm_continuity import ArmContinuity
from ..core.packets import now_ms


class AssetLibrary:
    def __init__(self, root=None):
        self.root = root or ROOT / "assets"
        metadata = json.loads((self.root / "anchors/atlas.json").read_text(encoding="utf-8"))
        if metadata.get("schema_version") != 1 or metadata.get("alpha") != "straight":
            raise ValueError("자산 메타데이터/알파 규약 오류")
        self.images, self.entries = {}, {}
        for entry in metadata["assets"]:
            path = (self.root / entry["path"]).resolve()
            if not path.is_relative_to(self.root.resolve()):
                raise ValueError("자산 경로 범위 오류")
            img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if img is None or img.ndim != 3 or img.shape[2] != 4 or img.shape[0] > 4096 or img.shape[1] > 4096:
                raise ValueError(f"투명 PNG 자산 오류: {entry['id']}")
            rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
            rgba[:,:,:3] *= rgba[:,:,3:4]  # Premultiply before interpolation to avoid dark fringes.
            self.images[entry["id"]] = rgba
            self.entries[entry["id"]] = entry
        expected = {f"{mode}/{p}" for mode in ("bones","muscles") for p in ("head","torso","upper_arm","forearm","thigh","shin")}
        expected |= {f"{mode}/{p}_left" for mode in ("bones","muscles") for p in ("upper_arm","forearm","thigh","shin")}
        expected |= {f"muscles/{p}{side}_flex" for p in ("upper_arm","thigh") for side in ("","_left")}
        if set(self.images) != expected:
            raise ValueError("해부학 자산 부위 누락")
        for key in expected:
            if key.endswith("_flex"):
                h,w=self.images[key.removesuffix("_flex")].shape[:2]
                self.images[key]=cv2.resize(self.images[key],(w,h),interpolation=cv2.INTER_AREA)


def blend_warp(canvas, sprite, src, dst, opacity, mask=None):
    h,w = canvas.shape[:2]
    if not np.isfinite(dst).all() or not cv2.isContourConvex(dst.astype(np.float32)):
        return
    # Affine patches, with a shared diagonal. Work only inside the destination ROI.
    low = np.maximum(np.floor(dst.min(axis=0)).astype(int), (0,0))
    high = np.minimum(np.ceil(dst.max(axis=0)).astype(int)+1, (w,h))
    rw,rh = high-low
    if rw <= 0 or rh <= 0:
        return
    target = dst - low
    if np.allclose(target[0]+target[2],target[1]+target[3],atol=.1):
        matrix=cv2.getAffineTransform(src[:3].astype(np.float32),target[:3].astype(np.float32))
        patch=cv2.warpAffine(sprite,matrix,(int(rw),int(rh)),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    else:
        patch = np.zeros((rh,rw,4), np.float32)
        for indices in ((0,1,2),(0,2,3)):
            ids = list(indices)
            matrix = cv2.getAffineTransform(src[ids].astype(np.float32), target[ids].astype(np.float32))
            warped = cv2.warpAffine(sprite, matrix, (int(rw),int(rh)), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            triangle = np.zeros((rh,rw), np.uint8)
            cv2.fillConvexPoly(triangle, np.rint(target[ids]).astype(np.int32), 1)
            patch[triangle>0] = warped[triangle>0]
    if mask is not None:
        opacity = opacity * mask[low[1]:high[1],low[0]:high[0],None]
    alpha = patch[:,:,3:4] * opacity
    roi = canvas[low[1]:high[1],low[0]:high[0]]
    roi[:] = np.clip(np.rint(patch[:,:,:3] * (255 * opacity) + roi * (1-alpha)),0,255).astype(np.uint8)


def overlay_mask(points,width,height,confidence):
    """Feather screen edges and protect the camera face, including from raised arms."""
    x=np.arange(width,dtype=np.float32)
    y=np.arange(height,dtype=np.float32)
    edge=np.minimum(np.minimum(x,width-1-x)[None,:],np.minimum(y,height-1-y)[:,None])
    mask=np.clip(edge/max(1,min(width,height)*.08),0,1)
    if not valid(points,(11,12),width,height,confidence):
        return mask
    shoulders=points[[11,12],:2]
    span=float(np.linalg.norm(shoulders[0]-shoulders[1]))
    center=shoulders.mean(axis=0)-np.array([0,span*.5])
    if valid(points,(0,),width,height,confidence):
        center=points[0,:2]-np.array([0,span*.08])
    rx,ry=max(1,span*.34),max(1,span*.48)
    low=np.maximum(np.floor(center-[rx*1.15,ry*1.15]).astype(int),0)
    high=np.minimum(np.ceil(center+[rx*1.15,ry*1.15]).astype(int)+1,(width,height))
    if np.all(high>low):
        distance=np.sqrt(((x[low[0]:high[0]]-center[0])/rx)[None,:]**2+
                         ((y[low[1]:high[1]]-center[1])/ry)[:,None]**2)
        mask[low[1]:high[1],low[0]:high[0]]*=np.clip((distance-1)/.15,0,1)
    return mask


class Compositor:
    def __init__(self, library=None):
        self.library = library or AssetLibrary()
        self.flex=FlexBlend()
        self.arms=ArmContinuity()

    def render(self, bgr, landmarks, settings, timestamp_ms=None):
        timestamp_ms=now_ms() if timestamp_ms is None else timestamp_ms
        canvas = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        if settings.mode == "original":
            self.flex.reset()
            self.arms.reset()
            return canvas, (), "", 0
        render_points,weights=self.arms.update(landmarks,timestamp_ms,canvas.shape[1],canvas.shape[0],settings.confidence)
        placements, message = map_anatomy(render_points, canvas.shape[1], canvas.shape[0], settings)
        if not placements or settings.mode!="muscles": self.flex.reset()
        mask=overlay_mask(landmarks,canvas.shape[1],canvas.shape[0],settings.confidence) if placements else None
        labels = []
        for item in placements:
            if item.part in ("upper_arm","forearm"):
                ids=(11,13) if item.part=="upper_arm" else (13,15)
                if item.side=="right": ids=tuple(i+1 for i in ids)
                item.opacity*=float(weights[list(ids)].min())
            key = f"{settings.mode}/{item.part}" + ("_left" if item.side=="left" else "")
            sprite = self.library.images[key]
            if item.upper_crop:
                # Fade the estimated lower torso instead of displaying a complete abdomen/pelvis.
                fade=np.clip((.68-np.linspace(0,1,sprite.shape[0],dtype=np.float32))/.20,0,1)
                sprite=sprite*fade[:,None,None]
            if settings.mode=="muscles" and item.part in ("upper_arm","thigh"):
                ids=(11,13,15) if item.part=="upper_arm" else (23,25,27)
                if item.side=="right": ids=tuple(i+1 for i in ids)
                angle=joint_angle(render_points,ids) if valid(render_points,ids,canvas.shape[1],canvas.shape[0],settings.confidence) else None
                weight=self.flex.update(key,angle,timestamp_ms)
                if weight>.001:
                    sprite=sprite*(1-weight)+self.library.images[key+"_flex"]*weight
            h,w = sprite.shape[:2]
            src = np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1]], np.float32)
            if item.part == "torso":
                src = np.array(self.library.entries[key]["torso_anchors"],np.float32) * (w-1,h-1)
                # Extend the anchor quadrilateral to artwork bounds using two affine patches.
                # The rendered torso remains conservative; sharp bends are rejected by mapper.
                dst = item.points.copy()
                top = cv2.getAffineTransform(src[:3].astype(np.float32),dst[:3].astype(np.float32))
                bottom = cv2.getAffineTransform(src[[0,2,3]].astype(np.float32),dst[[0,2,3]].astype(np.float32))
                top_corners=cv2.transform(np.array([[[0,0],[w-1,0]]],np.float32),top)[0]
                bottom_corners=cv2.transform(np.array([[[w-1,h-1],[0,h-1]]],np.float32),bottom)[0]
                dst=np.concatenate([top_corners,bottom_corners])
                src = np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1]],np.float32)
            else:
                dst = item.points
            blend_warp(canvas,sprite,src,dst,settings.opacity*item.opacity,mask)
            center = item.points.mean(axis=0)
            labels.append((float(center[0]),float(center[1]),item.label))
        return canvas, tuple(labels), message, len(placements)
