import numpy as np
import pytest
from src.rendering.variants import FlexBlend,joint_angle


def test_joint_angle_and_degenerate_geometry():
    points=np.array([[0,0],[1,0],[1,1]],np.float32)
    assert joint_angle(points,(0,1,2))==pytest.approx(90)
    points[2]=points[1]
    assert joint_angle(points,(0,1,2)) is None


def test_flex_hysteresis_and_continuous_transition():
    blend=FlexBlend()
    blend.update("arm",120,0)
    weights=[blend.update("arm",angle,t) for angle,t in ((120,33),(126,66),(124,99),(130,132),(139,165))]
    assert all(0<a<b<1 for a,b in zip(weights,weights[1:]))
    lower=blend.update("arm",145,198)
    assert 0<lower<weights[-1]
    assert blend.update("arm",170,500)==0
    blend.reset()
    assert not blend.states
