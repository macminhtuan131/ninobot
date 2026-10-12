"""Check bounded cruise-cost suppression and partial soft-deadline intervals."""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rough_reactive_reward import compute_reward
from nino_rl.core import RobotState


def test_holding_suppresses_only_cruise_cost_and_recovery_restores_it():
    weights=dict(progress_per_m=2.,time_per_s=.05,velocity=.25,velocity_sigma_m_s=.4,
        vibration=.8,acceleration_sigma_m_s2=2.,slip=.1,slip_sigma=.05,lateral=.2,
        lateral_sigma_m=.05,heading=.05,heading_sigma_rad=.2,action_rate=.003,
        arrival=10.,failure=50.,late_after_s=31.,late_time_per_s=.3)
    state=RobotState(ground_linear_velocity=.2)
    start=SimpleNamespace(distance_remaining=10.)
    end=SimpleNamespace(distance_remaining=9.98,lateral_error=0.,heading_error=0.)
    args=(start,end,state,[0],[0],[0,0],.1,dict(square_integral=.4),dict(longitudinal_weights=weights))
    ref=SimpleNamespace(valid=True,desired_linear_velocity=.4)
    _,quiet=compute_reward(*args,reference=ref,elapsed=30.)
    _,holding=compute_reward(*args,reference=ref,elapsed=30.,reactive_holding=True)
    assert quiet['command_velocity']==pytest.approx(-.00625)
    assert holding['command_velocity']==0.
    for name in ('progress','vibration','slip','lateral','heading','terminal','time'):
        assert quiet[name]==holding[name]
    _,boundary=compute_reward(*args,reference=ref,elapsed=31.05)
    assert boundary['late_time']==pytest.approx(-.015)
    _,ramped=compute_reward(*args,reference=ref,elapsed=30.,executed_scale=.96,previous_executed_scale=1.)
    assert ramped['action_rate']==pytest.approx(-.000048)
    assert weights['velocity']==.25
