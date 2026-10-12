"""Independent checks for the new speed authority and physical reward units."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

path=Path(__file__).resolve().parents[1]/'scripts/rough_longitudinal_control.py'
spec=importlib.util.spec_from_file_location('longitudinal_helpers',path)
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
CONFIG={'longitudinal_control':{'minimum_scale':.55}}


def test_target_bounds_steering_authority_and_stop():
    assert helpers.decode_speed([-1],CONFIG)==.55
    assert helpers.decode_speed([1],CONFIG)==1.
    for scale in (.55,.7,.955,1.):
        assert helpers.decode_speed([helpers.encode_speed(scale,CONFIG)],CONFIG)==pytest.approx(scale)
        assert helpers.velocity_reference(.4,.3,scale)==pytest.approx((.4*scale,.3))
        assert helpers.velocity_reference(0.,.3,scale)==(0.,.3)
        assert helpers.velocity_reference(0.,0.,scale)==(0.,0.)
    for action in ([],[0,0],[np.nan]):
        with pytest.raises(ValueError):helpers.decode_speed(action,CONFIG)


def test_reference_ramp_rate_and_small_intervals():
    assert helpers.ramp_speed(1.,.55,.1,.4)==pytest.approx(.96)
    assert helpers.ramp_speed(.55,1.,.02,.4)==pytest.approx(.558)
    assert helpers.ramp_speed(.96,.97,.1,.4)==pytest.approx(.97)


def test_squared_energy_and_external_tracking_reference():
    from nino_rl.core import RobotState
    w=dict(progress_per_m=2.,time_per_s=.1,velocity=1.,velocity_sigma_m_s=.4,
        vibration=.5,acceleration_sigma_m_s2=2.,slip=.2,slip_sigma=.3,
        lateral=.2,lateral_sigma_m=.05,heading=.05,heading_sigma_rad=.2,action_rate=.01,
        arrival=10.,failure=50.)
    previous=SimpleNamespace(distance_remaining=10.)
    current=SimpleNamespace(distance_remaining=9.96,lateral_error=0.,heading_error=0.)
    state=RobotState(ground_linear_velocity=.2)
    ref=SimpleNamespace(valid=True,desired_linear_velocity=.4)
    args=(previous,current,state,[.2,0,0],[.2,0,0],[0,0],.1,{'square_integral':.4},{'longitudinal_weights':w})
    value,terms=helpers.compute_reward(*args,reference=ref)
    assert terms['command_velocity']==pytest.approx(-.025)
    assert terms['vibration']==pytest.approx(-.05)
    halves=[]
    for distance in (9.98,9.96):
        end=SimpleNamespace(distance_remaining=distance,lateral_error=0.,heading_error=0.)
        start=SimpleNamespace(distance_remaining=distance+.02)
        halves.append(helpers.compute_reward(start,end,state,[.2,0,0],[.2,0,0],[0,0],.05,
            {'square_integral':.2},{'longitudinal_weights':w},reference=ref)[0])
    assert sum(halves)==pytest.approx(value)
    _,failure=helpers.compute_reward(*args,reference=ref,succeeded=True,failed='off_path')
    assert failure['terminal']==-50.


def test_actuator_gate_accepts_startup_but_rejects_weakened_yaw(tmp_path):
    import csv
    import sys
    sys.path.insert(0,str(path.parent))
    from run_rough_longitudinal_pilot_v2 import authority_gate
    row=dict(cmd_fresh=1,policy_fresh=1,requested_linear_m_s=.4,
        requested_yaw_rad_s=.3,executed_yaw_rad_s=.3,filtered_speed_scale=1,
        speed_scale=1,left_residual_nm=0,right_residual_nm=0)
    def write_traces(weakened=False):
        for episode in range(3):
            target=tmp_path/'run'/f'episode-{episode:03d}'/'drive_trace.csv'
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('w') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(row));writer.writeheader()
                writer.writerow(dict(row,filtered_speed_scale=.04,executed_yaw_rad_s=.012))
                writer.writerows([dict(row,executed_yaw_rad_s=.21 if weakened else .3)]*100)
    write_traces()
    assert authority_gate(tmp_path)['passed']
    write_traces(weakened=True)
    assert not authority_gate(tmp_path)['passed']
