import numpy as np


def victory_hands(result,frame):
    """Use actual hand detections, including close-ups where body pose is unavailable."""
    h,w=frame.bgr.shape[:2]
    sx,sy,px,py=frame.transform
    iw,ih=frame.inference_size
    hands=set()
    for categories,landmarks,sides in zip(result.gestures,result.hand_landmarks,result.handedness):
        if not categories or len(landmarks)!=21 or not sides: continue
        gesture=max(categories,key=lambda item:item.score)
        if gesture.category_name!="Victory" or not np.isfinite(gesture.score) or gesture.score<.7: continue
        wrist=np.array([(landmarks[0].x*iw-px)/sx,(landmarks[0].y*ih-py)/sy])
        if not np.isfinite(wrist).all() or not (0<=wrist[0]<w and 0<=wrist[1]<h): continue
        side=max(sides,key=lambda item:item.score)
        if side.category_name in ("Left","Right") and np.isfinite(side.score) and side.score>=.6:
            hands.add(side.category_name.lower())
    return tuple(sorted(hands))
