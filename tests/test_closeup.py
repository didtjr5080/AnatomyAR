from dataclasses import replace
import numpy as np
import pytest
from src.core.settings import Settings
from src.rendering.anatomy_mapper import map_anatomy
from src.rendering.compositor import Compositor,blend_warp,overlay_mask
from src.tracking.smoothing import PoseFilter
from test_core import person


def closeup():
    p=person()
    p[:,:2]=(p[:,:2]-[640,150])*2.6+[640,180]
    p[23:,3:]=0
    return p


@pytest.mark.parametrize("mode",["muscles","bones"])
def test_closeup_without_hips_preserves_face_and_shows_chest(mode):
    points,_=PoseFilter().update(closeup(),100,1280,720,.6,65)
    settings=replace(Settings(),mode=mode)
    items,message=map_anatomy(points,1280,720,settings)
    assert any(item.part=="torso" and item.upper_crop for item in items)
    assert not any(item.part in ("head","thigh","shin") for item in items)
    bg=np.full((720,1280,3),(30,60,90),np.uint8)
    rgb,_,_,_=Compositor().render(bg,points,settings,100)
    original=bg[:,:,::-1]
    assert np.array_equal(rgb[90:260,550:730],original[90:260,550:730])
    assert np.count_nonzero(rgb[420:600,500:780]!=original[420:600,500:780])>10000
    assert np.array_equal(rgb[-1,550:730],original[-1,550:730])
    assert np.abs(rgb[715:,550:730].astype(int)-original[715:,550:730]).max()<16


def test_nearby_offscreen_elbow_is_clipped_but_distant_guess_is_hidden():
    p=closeup()
    p[13,:2]=(1050,750)
    p,_=PoseFilter().update(p,100,1280,720,.6,0)
    items,_=map_anatomy(p,1280,720,Settings())
    assert any(x.part=="upper_arm" and x.side=="left" for x in items)
    p[13,1]=2000
    items,_=map_anatomy(p,1280,720,Settings())
    assert not any(x.part=="upper_arm" and x.side=="left" for x in items)


def test_confidence_fades_before_hiding_without_affecting_other_arm():
    strengths=[]
    for score in (1,.7,.61):
        p=person()
        p[15,3:]=score
        items,_=map_anatomy(p,1280,720,Settings())
        strengths.append(next(x.opacity for x in items if x.part=="forearm" and x.side=="left"))
        assert next(x.opacity for x in items if x.part=="forearm" and x.side=="right")==1
    assert strengths[0]>strengths[1]>strengths[2]>0


def test_face_protection_and_screen_fade_apply_to_every_sprite():
    mask=overlay_mask(person(),1280,720,.6)
    assert mask[150,640]==0
    assert mask[400,640]==1
    assert mask[0,100]==0 and 0<mask[20,100]<mask[40,100]<mask[60,100]==1
    canvas=np.full((720,1280,3),80,np.uint8)
    sprite=np.ones((2,2,4),np.float32)
    src=np.array([[0,0],[1,0],[1,1],[0,1]],np.float32)
    dst=np.array([[0,0],[1279,0],[1279,719],[0,719]],np.float32)
    blend_warp(canvas,sprite,src,dst,1,mask)
    assert np.all(canvas[150,640]==80)
    assert np.all(canvas[400,640]==255)
    assert np.all(canvas[0,100]==80)


def test_closeup_still_rejects_missing_shoulders_and_reversed_pose():
    p=closeup(); p[11,3:]=0
    assert not map_anatomy(p,1280,720,Settings())[0]
    p=closeup(); p[[11,12]]=p[[12,11]]
    assert not map_anatomy(p,1280,720,Settings())[0]
