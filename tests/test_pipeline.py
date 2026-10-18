import time
from src.core.packets import Latest,now_ms
from src.core.state import AppState,Status
from src.core.metrics import Metrics
from src.tracking.mediapipe_tracker import TrackerWorker
from test_core import frame


def test_actual_live_stream_worker_pairs_original_and_stops():
    state=AppState()
    output=Latest()
    tracker=TrackerWorker(state,7,output,Metrics())
    tracker.start()
    found=None
    deadline=time.monotonic()+10
    try:
        fid=0
        while time.monotonic()<deadline:
            original=frame(fid,now_ms(),7)
            tracker.submit(original)
            time.sleep(.04)
            found=output.take()
            if found is not None: break
            fid+=1
        assert found is not None,"Real LIVE_STREAM worker did not produce a matched packet"
        assert found.frame.generation_id==found.pose.generation_id==7
        assert found.frame.frame_id==found.pose.frame_id
        assert found.frame.timestamp_ms==found.pose.timestamp_ms
        assert found.status==Status.WAITING_PERSON
        assert found.labels==()
    finally:
        tracker.stop()
        assert tracker.wait(5000),"Model shutdown did not finish"
    tracker.submit(frame(999,now_ms(),7))
    assert tracker.matcher.closed
