import cv2
import numpy as np
from src.capture import devices
from src.core.settings import Settings,validate


def test_auto_skips_bad_zero_and_only_reports_readable_camera(monkeypatch):
    cameras=[]
    class Camera:
        def __init__(self): self.released=False; cameras.append(self)
        def open(self,index,backend): self.index=index; return True
        def set(self,*args): return True
        def get(self,*args): return 30
        def read(self): return (False,None) if self.index==0 else (True,np.zeros((480,640,3),np.uint8))
        def release(self): self.released=True
    monkeypatch.setattr(devices.cv2,"VideoCapture",Camera)
    camera,frame,info=devices.select_camera(-1,Settings())
    assert info["index"]==1 and frame.shape==(480,640,3)
    assert all(c.released for c in cameras[:-1])
    assert not camera.released
    camera.release()


def test_backend_exception_falls_back_and_cancel_releases(monkeypatch):
    cameras=[]
    class Camera:
        def __init__(self): self.released=False; cameras.append(self)
        def open(self,index,backend):
            if backend==cv2.CAP_DSHOW: raise cv2.error("unsupported")
            return True
        def get(self,*args): return 30
        def read(self): return True,np.ones((10,20,3),np.uint8)
        def release(self): self.released=True
    monkeypatch.setattr(devices.cv2,"VideoCapture",Camera)
    camera,_,info=devices.open_camera(2)
    assert info["backend"]=="Media Foundation"
    assert cameras[0].released
    camera.release()
    count=[0]
    def cancelled():
        count[0]+=1
        return count[0]>=3
    assert devices.open_camera(2,cancelled=cancelled) is None
    assert all(c.released for c in cameras)


def test_explicit_camera_is_not_replaced_by_another(monkeypatch):
    indices=[]
    monkeypatch.setattr(devices,"open_camera",lambda index,*args:indices.append(index))
    assert devices.select_camera(4,Settings()) is None
    assert indices==[4]
    assert validate({"camera_index":-1}).camera_index==-1
