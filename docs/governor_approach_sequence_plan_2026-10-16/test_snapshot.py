from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from prepare_governor_contact_sequence import (angle_delta,closed_contact_end,
    sequence_windows,sustained,post_reset_readiness)


def event(t,kind):
    return dict(time_s=t,event=kind,component="right_wheel",collisions=["cable","wheel"],named_positive_obstacle=True)


def test_unclosed_and_recontact_sequence_cannot_finish_at_first_end():
    assert not closed_contact_end([event(1.,"begin")],1.,4.)["available"]
    last=closed_contact_end([event(1.,"begin"),event(1.2,"end"),event(1.3,"begin"),event(1.8,"end")],1.,4.)
    assert last["available"] and last["last_end_upper_bound_s"]==1.8
    window=sequence_windows(1.,1.5,last,4.,dict(confirmed_s=2.4))
    assert window["contact_end_s"]==pytest.approx(2.)
    assert window["recovery_end_s"]==2.4
    assert not sequence_windows(1.,None,last,4.,None)["available"]


def test_sustained_recovery_cannot_bridge_gap_or_bad_state():
    samples=[(0.,True),(.02,True),(.4,True),(.42,True)]
    assert sustained(samples,0.,1.,bool,duration=.3) is None
    samples=[(i*.02,i!=4) for i in range(22)]
    answer=sustained(samples,0.,1.,bool)
    assert answer["begin_s"]==pytest.approx(.1)
    assert answer["confirmed_s"]==pytest.approx(.4)


def test_post_reset_gate_rejects_pre_epoch_stale_and_moving_windows():
    samples=[dict(time_s=i*.02,v_m_s=0.,yaw_rate_rad_s=0.,left_wheel_m_s=0.,right_wheel_m_s=0.,
                  command_v=0.,command_w=0.,feedback_age_s=.02) for i in range(26)]
    assert post_reset_readiness(samples,0.,.5)["ready"]
    assert not post_reset_readiness(samples,.1,.5)["ready"]
    samples[10]["v_m_s"]=.02
    assert not post_reset_readiness(samples,0.,.5)["ready"]
    samples[10]["v_m_s"]=0.
    samples[10]["feedback_age_s"]=-.001
    assert not post_reset_readiness(samples,0.,.5)["ready"]


def test_circular_angles_do_not_create_fake_full_rotation_difference():
    assert abs(angle_delta(3.13,-3.13))<.03
