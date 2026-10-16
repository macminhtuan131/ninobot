"""Diagnostics must expose duplicate/stale cycles without hiding or altering them."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nino_control.control_timing import ControlTimingWindow


def test_duplicate_and_gap_are_measured_before_pi_fallback():
    window=ControlTimingWindow()
    for dt,age in ((.002,.001),(0.,.006),(.3,.012)):
        window.observe(dt,age)
    report=window.take()
    assert report["control_updates"]==3
    assert report["control_dt_fallbacks"]==2
    assert report["control_raw_dt_sum_s"]==pytest.approx(.302)
    assert report["control_raw_dt_min_s"]==0.
    assert report["control_raw_dt_max_s"]==.3
    assert report["control_joint_age_max_s"]==.012
    assert window.take()["control_updates"]==0


def test_missing_feedback_is_unavailable_and_nonfinite_does_not_break_control():
    window=ControlTimingWindow()
    window.observe(float("nan"))
    report=window.take()
    assert report["control_dt_invalid"]==1
    assert report["control_joint_age_max_s"]==-1.
