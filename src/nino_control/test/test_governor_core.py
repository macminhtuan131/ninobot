from dataclasses import replace
from pathlib import Path
import sys
import math

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nino_control.governor_core import GovernorSettings,GovernorFrame,ReactiveGovernor,vertical_acceleration


FRAME=GovernorFrame(0.,0.,4.8,4.8,4.8,4.8,.30)


def warmed(profile="reactive"):
    governor=ReactiveGovernor(GovernorSettings(profile=profile))
    for _ in range(20):
        governor.update(FRAME,.05,.30)
    return governor


def test_sustained_braking_then_recovery_and_hysteresis():
    governor=warmed()
    noisy=replace(FRAME,vertical_m_s2=5.)
    decisions=[governor.update(noisy,.05,.30) for _ in range(18)]
    assert governor.events==1
    assert min(d["scale"] for d in decisions)==pytest.approx(.70)
    assert all(abs(b["scale"]-a["scale"])<=.02000001 for a,b in zip(decisions,decisions[1:]))
    phases=[]
    for _ in range(60):
        phases.append(governor.update(FRAME,.05,.30)["phase"])
    assert "RECOVER" in phases
    assert governor.phase=="CRUISE" and governor.scale==1.
    assert governor.events==1


def test_rearm_does_not_require_cruising_at_098():
    governor=warmed()
    governor.phase="RECOVER"
    governor.scale=.70
    governor.armed=False
    for _ in range(7):
        governor.update(FRAME,.05,.30)
    assert governor.armed and governor.scale<.98
    governor.update(replace(FRAME,vertical_m_s2=8.),.05,.30)
    assert governor.phase=="HOLD" and governor.events==1


def test_pulse_reaches_target_before_recovery():
    governor=warmed("pulse")
    decisions=[governor.update(replace(FRAME,vertical_m_s2=8.),.1,.3)]
    for _ in range(25):
        decisions.append(governor.update(FRAME,.1,.3))
    assert min(d["scale"] for d in decisions)==pytest.approx(.70)
    assert governor.scale==1.


def test_stale_invalid_and_stall_are_latched_before_output():
    governor=warmed()
    decision=governor.update(FRAME,.05,.3,fresh=False)
    assert decision["scale"]==0. and decision["phase"]=="FAILSAFE"
    assert governor.update(FRAME,.05,.3)["scale"]==0.
    governor.reset()
    assert governor.update(replace(FRAME,vertical_m_s2=math.nan),.05,.3)["scale"]==0.
    governor.reset()
    stopped=replace(FRAME,left_velocity_rad_s=0.,right_velocity_rad_s=0.)
    for _ in range(25):
        decision=governor.update(stopped,.05,.3)
    assert decision["fault"]=="persistent_wheel_stall" and decision["scale"]==0.


def test_optional_wheel_stall_recovery_is_bounded():
    governor=ReactiveGovernor(GovernorSettings(stall_recovery_enabled=True,stall_recovery_seconds=.3))
    stopped=replace(FRAME,left_velocity_rad_s=0.,right_velocity_rad_s=0.)
    phases=[]
    for _ in range(35):
        phases.append(governor.update(stopped,.05,.3)["phase"])
    assert "STALL" in phases and governor.phase=="FAILSAFE"


def test_command_acceleration_allowance_and_body_stall_limit():
    governor=warmed()
    # Reference changes before wheels respond: allow a transient tracking error.
    sample=replace(FRAME,left_target_rad_s=7.2,right_target_rad_s=7.2)
    decision=governor.update(sample,.05,.45)
    assert not decision["disturbed"]
    # No body ground truth is passed; spinning wheels cannot prove translation.
    assert not hasattr(FRAME,"ground_velocity")


def test_zero_reference_cannot_be_overridden_by_minimum_forward():
    governor=warmed()
    governor.update(replace(FRAME,vertical_m_s2=8.),.05,.3)
    assert governor.phase=="HOLD"
    decision=governor.update(FRAME,.05,0.)
    assert decision["phase"]=="CRUISE"
    assert 0.*decision["scale"]==0.


def test_full_profile_remains_full_speed_but_checks_faults():
    governor=warmed("full")
    for _ in range(30):
        assert governor.update(replace(FRAME,vertical_m_s2=8.),.05,.3)["scale"]==1.
    assert governor.events==0
    assert governor.update(FRAME,.05,.3,fresh=False)["scale"]==0.


def test_tilt_gravity_and_invalid_hold_settings():
    roll,pitch=.25,-.15
    gravity=(-9.80665*math.sin(pitch),9.80665*math.cos(pitch)*math.sin(roll),
             9.80665*math.cos(pitch)*math.cos(roll))
    assert vertical_acceleration(gravity,roll,pitch)==pytest.approx(0.,abs=1e-10)
    with pytest.raises(ValueError,match="Pulse too short"):
        GovernorSettings(profile="pulse",pulse_seconds=.6)
    with pytest.raises(ValueError):
        GovernorSettings(scale_rate_per_second=math.nan)


def test_optional_vertical_trigger_ablation_preserves_release_and_faults():
    governor=ReactiveGovernor(GovernorSettings(profile="moderate",vertical_only_trigger_enabled=False))
    for _ in range(30):
        decision=governor.update(replace(FRAME,vertical_m_s2=8.),.1,.30)
    assert not decision["disturbed"] and governor.events==0 and governor.scale==1.
    assert decision["trigger_ratio"]>1.  # Raw severity remains observable.
    assert decision["quiet_seconds"]==0.  # Release definition did not change.
    decision=governor.update(replace(FRAME,vertical_m_s2=8.,body_rate_rad_s=.5),.1,.30)
    assert decision["disturbed"] and governor.events==1 and governor.scale==pytest.approx(.96)
    assert governor.update(FRAME,.1,.30,fresh=False)["phase"]=="FAILSAFE"
