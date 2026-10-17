"""Protect the two-parameter contract and physical failure handling."""
from dataclasses import replace
from pathlib import Path
import sys
import pytest

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/"scripts"),
               str(Path(__file__).resolve().parents[2]/"nino_control")]
from nino_control.governor_core import GovernorSettings,GovernorFrame,ReactiveGovernor
from tune_classical_governor import score


def test_reactive_point_85_matches_legacy_moderate_execution():
    legacy=ReactiveGovernor(GovernorSettings(profile="moderate",startup_seconds=0.))
    tunable=ReactiveGovernor(replace(legacy.settings,profile="reactive",target_scale=.85))
    for i in range(60):
        frame=GovernorFrame(4. if 2<=i<22 else 0.,.6 if 2<=i<22 else 0.,6.,6.,6.,6.,.4)
        assert legacy.update(frame,.1,.4)==tunable.update(frame,.1,.4)
    assert legacy.events>0


def report(**changes):
    common=dict(seed=1,complete=True,available=True,physical_success=True,stop_settled=True,
        time_s=10.,postcontact_slip_energy_per_m=.1,truth_rmse_m=.01)
    return dict(episodes=[dict(common,profile="full"),dict(common,profile="reactive",**changes)])


def test_identical_metrics_have_fixed_reference_cost_one():
    assert score(report())["value"]==pytest.approx(1.)


def test_physical_failure_kept_even_when_contact_analysis_missing():
    result=score(report(physical_success=False,available=False))
    assert not result["feasible"] and result["value"]==110.


def test_missing_measurement_not_fake_zero_or_physical_failure():
    with pytest.raises(ValueError):score(report(available=False))
