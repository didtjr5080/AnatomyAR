import math
import numpy as np


def joint_angle(points,ids):
    a,b,c=points[list(ids),:2]
    u,v=a-b,c-b
    denominator=np.linalg.norm(u)*np.linalg.norm(v)
    if not np.isfinite(denominator) or denominator<1:
        return None
    return math.degrees(math.acos(float(np.clip(np.dot(u,v)/denominator,-1,1))))


class FlexBlend:
    """Screen-space joint angle is an illustration cue, never muscle activation."""
    def __init__(self):
        self.states={}

    def reset(self):
        self.states.clear()

    def update(self,key,angle,timestamp):
        active,weight,previous=self.states.get(key,(False,0.0,timestamp))
        if timestamp-previous>250 or timestamp<previous:
            active,weight=False,0.0
        if angle is None:
            active=False
        elif angle<125:
            active=True
        elif angle>140:
            active=False
        dt=max(0,min(100,timestamp-previous))
        weight+=(float(active)-weight)*(1-math.exp(-dt/100))
        self.states[key]=(active,weight,timestamp)
        return weight
