from dataclasses import replace
import cv2
import numpy as np
from src.core.settings import Settings
from src.rendering.compositor import AssetLibrary,Compositor,blend_warp
from test_core import person


def test_real_alpha_assets_and_each_mode_changes_pixels():
    assets = AssetLibrary()
    compositor = Compositor(assets)
    bg = np.full((720,1280,3),80,np.uint8)
    for mode in ("bones","muscles"):
        image,labels,message,count = compositor.render(bg,person(),replace(Settings(),mode=mode))
        assert count==9
        assert len(labels)==count
        assert np.count_nonzero(image!=80)>10000
    for image in assets.images.values():
        assert image[:,:,3].min()==0
        assert image[:,:,3].max()>.9
        assert np.all(image[:,:,:3]<=image[:,:,3:4]+1e-5)


def test_premultiplied_transparent_edges_do_not_dark_fringe():
    bg=np.full((20,20,3),255,np.uint8)
    sprite=np.zeros((2,2,4),np.float32)
    sprite[0,0]=[1,0,0,1]
    src=np.array([[0,0],[1,0],[1,1],[0,1]],np.float32)
    dst=np.array([[1,1],[18,1],[18,18],[1,18]],np.float32)
    blend_warp(bg,sprite,src,dst,1)
    assert np.all(bg[:,:,0]==255)
    assert bg[0,0].tolist()==[255,255,255]


def test_original_preserves_bgr_to_rgb_and_no_pose():
    bg=np.zeros((20,20,3),np.uint8); bg[:,:,2]=200
    image,labels,_,_=Compositor().render(bg,np.empty((0,5)),replace(Settings(),mode="original"))
    assert np.all(image[:,:,0]==200) and not labels
