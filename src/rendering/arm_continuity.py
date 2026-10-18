import numpy as np
from .anatomy_mapper import valid


class ArmContinuity:
    """Bridge brief joint loss for drawing only, never for gesture selection."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.joints={}
        self.timestamp=None
        self.confidence=None

    def update(self,points,timestamp,width,height,confidence):
        weights=np.ones(33,np.float32)
        if (self.timestamp is not None and not 0<=timestamp-self.timestamp<=250
                or self.confidence!=confidence):
            self.reset()
        if not valid(points,(11,12),width,height,confidence):
            self.reset()
            return points,weights
        span=float(np.linalg.norm(points[11,:2]-points[12,:2]))
        if points[11,0]<=points[12,0] or span<25 or abs(points[11,2]-points[12,2])>span*.65:
            self.reset()
            return points,weights
        self.timestamp,self.confidence=timestamp,confidence
        result=points.copy()
        for joint,shoulder in ((13,11),(15,11),(14,12),(16,12)):
            if valid(points,(joint,),width,height,confidence,margin=.35):
                self.joints[joint]=(points[joint].copy(),points[shoulder,:3].copy(),span,timestamp)
                continue
            saved=self.joints.get(joint)
            if saved is None:
                continue
            position,anchor,old_span,seen=saved
            age=timestamp-seen
            xy=points[joint,:2]
            outside=np.isfinite(xy).all() and not (-.35*width<=xy[0]<1.35*width and -.35*height<=xy[1]<1.35*height)
            if outside or age>=300 or not .75<=span/old_span<=1.25 or np.linalg.norm(points[shoulder,:2]-anchor[:2])>width*.15:
                del self.joints[joint]
                continue
            result[joint]=position
            result[joint,:3]=points[shoulder,:3]+(position[:3]-anchor)*(span/old_span)
            progress=float(np.clip((age-100)/200,0,1))
            weights[joint]=1-progress*progress*(3-2*progress)
        return result,weights
