"""Read frames in memory only; output device/backend diagnostics, never images."""
import argparse
import ctypes
import json
import os
import time
import cv2


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--count",type=int,default=4)
    args=parser.parse_args()
    com=None
    if os.name=="nt":
        com=ctypes.windll.ole32.CoInitializeEx(None,0)
    print(json.dumps({"opencv":cv2.__version__,"com_hresult":com}),flush=True)
    try:
        for api,name in ((cv2.CAP_DSHOW,"DirectShow"),(cv2.CAP_MSMF,"MediaFoundation")):
            for index in range(args.count):
                camera=cv2.VideoCapture()
                start=time.monotonic()
                try:
                    opened=camera.open(index,api)
                    ok,image=camera.read() if opened else (False,None)
                    print(json.dumps({"backend":name,"index":index,"opened":opened,
                        "read":ok,"shape":None if image is None else list(image.shape),
                        "elapsed_ms":round((time.monotonic()-start)*1000)}),flush=True)
                except Exception as exc:
                    print(json.dumps({"backend":name,"index":index,"error":str(exc)}),flush=True)
                finally: camera.release()
    finally:
        if com in (0,1): ctypes.windll.ole32.CoUninitialize()


if __name__=="__main__": main()
