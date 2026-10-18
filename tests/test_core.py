from dataclasses import asdict,replace
from types import SimpleNamespace
import json
import numpy as np
import pytest
from src.core.settings import Settings,validate,save,load
from src.core.packets import TimestampClock,FramePacket,FrameMatcher,Latest
from src.rendering.coordinates import display_transform,mirror_x,inference_geometry,restore_landmarks
from src.tracking.smoothing import PoseFilter
from src.rendering.anatomy_mapper import map_anatomy
from src.tracking.mediapipe_tracker import verify_model


def frame(fid=0,ts=100,generation=1):
    size,transform = inference_geometry(1280,720,640)
    return FramePacket(fid,ts,generation,np.zeros((720,1280,3),np.uint8),size,transform)


def person():
    points = np.zeros((33,5),np.float32)
    points[:,3:] = 1
    for i,x,y in ((0,640,150),(2,660,140),(5,620,140),(7,682,150),(8,598,150),
                  (11,740,240),(12,540,240),(13,790,350),(14,490,350),(15,805,450),(16,475,450),
                  (23,705,430),(24,575,430),(25,710,550),(26,570,550),(27,720,680),(28,560,680)):
        points[i,:2] = x,y
    return points


@pytest.mark.parametrize("view,expected",[((800,600),(.625,0,75)),((600,1000),(.46875,0,331.25))])
def test_fit(view,expected):
    assert display_transform(1280,720,*view)==pytest.approx(expected)


def test_letterbox_inverse_and_mirror():
    f = frame()
    p = SimpleNamespace(x=.5,y=.5,z=0,visibility=1,presence=1)
    out = restore_landmarks([p],f)
    assert out[0,:2]==pytest.approx((640,360))
    assert mirror_x(0,1280)==1279
    assert mirror_x(mirror_x(312.2,1280),1280)==pytest.approx(312.2)


def test_timestamp_strict_even_clock_repeat_or_regress():
    clock = TimestampClock()
    assert [clock.next(t) for t in (100,100,99,110)]==[100,101,102,110]


def test_bounded_buffer_reorder_stale_and_old_generation():
    matcher = FrameMatcher(1,capacity=3)
    for i in range(10): matcher.add(frame(i,100+i))
    assert len(matcher.frames)==3
    assert matcher.match(108,2,110,200) is None
    assert matcher.match(108,1,110,200).frame_id==8
    assert matcher.match(107,1,111,200) is None
    assert matcher.match(109,1,310,200) is None
    matcher.close()
    assert not matcher.add(frame(20,320))
    assert matcher.match(320,1,321,200) is None


def test_latest_overwrites_instead_of_accumulating():
    queue = Latest()
    for i in range(1000): queue.put(i)
    assert queue.take()==999 and queue.take() is None
    assert queue.dropped==999


@pytest.mark.parametrize("corrupt",[{"opacity":float("nan")},{"mirror":"yes"},{"capture_width":1280.5},{"schema_version":2},{"widths":{}},{"background":"bad"},{"screen":{"name":[]}}])
def test_invalid_settings_rejected(corrupt):
    with pytest.raises(ValueError): validate(corrupt)


def test_settings_atomic_roundtrip_and_corruption(tmp_path):
    path = tmp_path/"settings.json"
    settings = replace(Settings(),mode="bones",guidance="안내")
    save(settings,path)
    assert load(path)==settings
    assert not list(tmp_path.glob("*.tmp"))
    path.write_text("broken",encoding="utf-8")
    with pytest.raises(ValueError): load(path)


def test_filter_loss_resets_and_bad_joint_does_not_poison():
    smoother = PoseFilter()
    p = person()
    smoother.update(p,100,1280,720,.6,100)
    p[15,0] = float("nan")
    output,_ = smoother.update(p,130,1280,720,.6,100)
    assert output[15,3]==0
    smoother.update(np.empty((0,5)),160,1280,720,.6,100)
    p = person(); p[:,0]+=90
    output,_ = smoother.update(p,190,1280,720,.6,100)
    assert output[11,0]==p[11,0]


def test_target_jump_requires_reacquisition():
    smoother = PoseFilter(); p = person()
    smoother.update(p,100,1280,720,.6,0)
    p[:,0]+=300
    for t in (130,160):
        output,message=smoother.update(p,t,1280,720,.6,0)
        assert np.all(output[:,3:]==0)
    output,_=smoother.update(p,190,1280,720,.6,0)
    assert output[11,3]==1


@pytest.mark.parametrize("kind",["zero_length","nan","confidence","offscreen"])
def test_bad_limb_hidden_without_hiding_other_side(kind):
    p=person()
    if kind=="zero_length": p[15,:2]=p[13,:2]
    if kind=="nan": p[15,0]=np.nan
    if kind=="confidence": p[15,3]=.1
    if kind=="offscreen": p[15,0]=2000
    placements,_=map_anatomy(p,1280,720,Settings())
    assert not any(x.part=="forearm" and x.side=="left" for x in placements)
    assert any(x.part=="forearm" and x.side=="right" for x in placements)


def test_back_is_hidden_but_crossed_arms_remain_visible():
    p=person(); p[11,0],p[12,0]=p[12,0],p[11,0]
    assert map_anatomy(p,1280,720,Settings())[0]==[]
    p=person(); p[15,:2]=(450,420); p[16,:2]=(830,420)
    placements,_=map_anatomy(p,1280,720,Settings())
    forearms=[x for x in placements if x.part=="forearm"]
    assert len(forearms)==2
    assert all(0<x.opacity<1 for x in forearms)


def test_partial_upper_body():
    p=person(); p[23:,3:]=0
    placements,_=map_anatomy(p,1280,720,Settings())
    assert any(x.part=="upper_arm" for x in placements)
    assert any(x.part=="torso" and x.upper_crop for x in placements)
    assert not any(x.part in ("head","thigh","shin") for x in placements)


def test_missing_corrupt_and_real_model(tmp_path):
    with pytest.raises(FileNotFoundError): verify_model(tmp_path/"missing.task")
    path=tmp_path/"corrupt.task"; path.write_bytes(b"broken")
    with pytest.raises(ValueError): verify_model(path)
    assert verify_model().is_file()
