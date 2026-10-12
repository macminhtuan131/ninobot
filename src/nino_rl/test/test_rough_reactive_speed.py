"""Causal trigger, bounded recovery and unbiased spatial-window checks."""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rough_reactive_speed import ReactiveSpeed,hardware_cue
from analyze_rough_reactive_authority import windows,window_metrics


def sensor(**extra):
    return SimpleNamespace(roll=0.,pitch=0.,accel_x=0.,accel_y=0.,accel_z=9.80665,
        gyro_x=0.,gyro_y=0.,left_wheel_velocity=6.4,right_wheel_velocity=6.4,**extra)


def test_no_truth_or_position_and_bounded_hold_recovery():
    s=sensor(ground_linear_velocity=float('nan'),ground_x=999.,x=-999.)
    assert hardware_cue(s,(.4,0.))==pytest.approx((0.,0.,0.,.4))
    probe=ReactiveSpeed()
    for _ in range(10):assert probe.update(s,(.4,0.),1.,.1)[0]==1.
    s.gyro_x=.8
    target,trace=probe.update(s,(.4,0.),1.,.1)
    assert target==.7 and trace['cue_triggered']==1
    for _ in range(6):target,trace=probe.update(s,(.4,0.),.76,.1)
    assert target==1. and trace['cue_phase']=='recovering'
    target,trace=probe.update(s,(.4,0.),1.,.1)
    assert trace['cue_phase']=='cooldown' and trace['cue_events']==1


def test_spatial_energy_overlap_and_pi_only_window_union():
    assert windows([dict(physical_x_m=1.,cue_triggered=1),dict(physical_x_m=1.3,cue_triggered=1)],
        dict(before_m=.1,after_m=.8))==[[.9,2.1]]
    rows=[dict(physical_x_m=1.,step_dt_s=1.,step_imu_energy=4.,step_imu_coverage_s=1.,
        step_slip_square=.01,step_imu_peak_m_s2=3.)]
    result=window_metrics(rows,[[.25,.75]])
    assert result['imu_energy']==2.
    assert result['duration_s']==.5
    assert result['vibration_rms']==2.
    assert result['slip_rms']==.1
