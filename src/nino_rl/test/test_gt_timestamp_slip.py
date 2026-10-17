"""Preserve original GT observations and reject fabricated alignment/coverage."""
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_gt_timestamp_slip import gt_timestamp_series, common_bounds
from nino_rl.slip_reporting import integrate, synchronized_series


def test_gt_impulse_and_original_stamps_are_not_smoothed_onto_a_grid():
    times=np.array([.015,.035,.055])
    ground=np.column_stack([times,[.4,0.,.4],times*0,times*.4,times*0])
    joints=np.column_stack([np.arange(0.,.071,.001),np.full(71,6.4),np.full(71,6.4)])
    data=dict(ground=ground,joints=joints,start=.015,end=.055)
    saved_ground=ground.copy()
    signal=gt_timestamp_series(data)
    assert np.array_equal(signal["time"],times)
    assert np.array_equal(signal["ground_values"],ground[:,1:])
    assert np.array_equal(ground,saved_ground)
    assert signal["q"][1] == 1.
    assert np.allclose(signal["q"][[0,2]],0.)
    assert np.allclose(signal["wheel_rad_s"],6.4)


def test_joint_long_gap_and_extrapolation_are_not_filled_with_zero_slip():
    ground=np.array([[-.01,.4,0.,0.,0.],[.015,.4,0.,0.,0.],[.04,.4,0.,0.,0.]])
    data=dict(ground=ground,joints=np.array([[0.,6.4,6.4],[.03,6.4,6.4]]),start=0.,end=.03)
    signal=gt_timestamp_series(data)
    assert np.isnan(signal["q"]).all()
    metric=integrate(signal,0.,.03)
    assert not metric["available"] and metric["rms"] is None


def test_boundary_support_clips_quadrature_without_creating_gt_samples():
    times=np.array([-.01,.01,.03,.05])
    data=dict(ground=np.column_stack([times,times*0+.2,times*0,times*.2,times*0]),
              joints=np.column_stack([np.arange(-.02,.061,.001),np.full(81,6.4),np.full(81,6.4)]),start=0.,end=.04)
    signal=gt_timestamp_series(data)
    metric=integrate(signal,0.,.04)
    assert np.array_equal(signal["time"],times)
    assert 0. not in signal["time"] and .04 not in signal["time"]
    assert metric["available"]
    assert np.isclose(metric["coverage_s"],.04)
    assert np.isclose(metric["rms"],.5)
    assert np.isclose(metric["slip_square_integral_s"],.01)


def test_common_edge_support_is_same_for_all_methods():
    times=np.arange(-.02,.141,.02)
    data=dict(ground=np.column_stack([times,times*0+.2,times*0,times*.2,times*0]),
              joints=np.column_stack([np.arange(-.03,.151,.001),np.full(181,6.4),np.full(181,6.4)]),start=0.,end=.1)
    signals=[gt_timestamp_series(data),synchronized_series(data),synchronized_series(data,offset=.01)]
    bounds=common_bounds(signals,0.,.1)
    assert np.allclose(bounds,[.01,.09])
    metrics=[integrate(signal,*bounds) for signal in signals]
    assert all(m["available"] for m in metrics)
    assert np.allclose([m["rms"] for m in metrics],.5)
    assert common_bounds([dict(time=np.array([0.]),q=np.array([np.nan]),xy=np.zeros((1,2)))],0.,.1) is None
