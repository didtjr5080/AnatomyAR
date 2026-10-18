from dataclasses import replace
import numpy as np
import pytest
from src.core.settings import Settings
from src.rendering.arm_continuity import ArmContinuity
from src.rendering.anatomy_mapper import map_anatomy
from src.rendering.compositor import Compositor
from src.ui.hand_selector import palm_points
from test_core import person


def test_short_occlusion_fades_and_expires_without_refreshing_cache():
    continuity=ArmContinuity()
    p=person()
    continuity.update(p,100,1280,720,.6)
    hidden=p.copy(); hidden[15,3:]=0
    weights=[]
    for timestamp in (150,200,250,350):
        rendered,weight=continuity.update(hidden,timestamp,1280,720,.6)
        assert np.array_equal(rendered[15,:3],p[15,:3])
        assert rendered[15,3]==1 and weight[16]==1
        weights.append(weight[15])
    assert weights[0]==weights[1]==1
    assert 1>weights[2]>weights[3]>0
    rendered,_=continuity.update(hidden,400,1280,720,.6)
    assert rendered[15,3]==0
    assert hidden[15,3]==0


def test_occluded_arm_follows_small_body_translation_then_reacquires():
    continuity=ArmContinuity(); p=person()
    continuity.update(p,100,1280,720,.6)
    moved=p.copy(); moved[:,:2]+=[20,5]; moved[13,3:]=0
    rendered,_=continuity.update(moved,150,1280,720,.6)
    np.testing.assert_allclose(rendered[13,:2],p[13,:2]+[20,5])
    moved[13,3:]=1; moved[13,0]+=15
    rendered,weights=continuity.update(moved,200,1280,720,.6)
    assert np.array_equal(rendered[13],moved[13]) and weights[13]==1


@pytest.mark.parametrize("loss",["person","shoulder","gap","back","jump","outside"])
def test_loss_or_large_motion_does_not_leave_an_old_arm(loss):
    continuity=ArmContinuity(); p=person()
    continuity.update(p,100,1280,720,.6)
    p[15,3:]=0
    timestamp=150
    if loss=="person": p=np.empty((0,5),np.float32)
    if loss=="shoulder": p[11,3:]=0
    if loss=="gap": timestamp=400
    if loss=="back": p[[11,12]]=p[[12,11]]
    if loss=="jump": p[:,:2]+=[220,0]
    if loss=="outside": p[15,0]=2000
    rendered,_=continuity.update(p,timestamp,1280,720,.6)
    assert not len(rendered) or rendered[15,3]==0
    hidden=person(); hidden[15,3:]=0
    rendered,_=continuity.update(hidden,timestamp+30,1280,720,.6)
    assert rendered[15,3]==0


def test_centerline_and_moderate_depth_remain_visible_but_degenerate_arm_does_not():
    p=person(); p[15,:2]=(600,410)
    assert any(x.part=="forearm" and x.side=="left" for x in map_anatomy(p,1280,720,Settings())[0])
    p=person(); p[15,2]=120
    arm=next(x for x in map_anatomy(p,1280,720,Settings())[0] if x.part=="forearm" and x.side=="left")
    assert 0<arm.opacity<1
    p[15,:2]=p[13,:2]
    assert not any(x.part=="forearm" and x.side=="left" for x in map_anatomy(p,1280,720,Settings())[0])


@pytest.mark.parametrize("mode",["muscles","bones"])
def test_compositor_bridges_only_drawing_not_hand_selection(mode):
    compositor=Compositor(); settings=replace(Settings(),mode=mode)
    bg=np.full((720,1280,3),80,np.uint8)
    p=person()
    compositor.render(bg,p,settings,100)
    p[[15,16],3:]=0
    _,_,_,count=compositor.render(bg,p,settings,150)
    assert count==9
    assert not palm_points(p,1280,720,.6)
    assert np.all(p[[15,16],3:]==0)
    compositor.render(bg,p,settings,300)
    _,_,_,count=compositor.render(bg,p,settings,400)
    assert count==7
