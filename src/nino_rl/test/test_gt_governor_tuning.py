"""Bounded search execution authority and honest fixed-objective accounting."""
from copy import deepcopy
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from tune_gt_governor import CANDIDATES,execution_preflight,score,ROOT
from nino_rl.core import load_config


def rows():
    common=dict(seed=1,complete=True,physical_pass=True,physical_success=True,available=True,
        native_replay=dict(matches_native=True),timestamps=dict(passed=True),time_s=20.,physical_rmse_m=.01)
    ref={**deepcopy(common),"profile":"full","gt_native":dict(whole_route=dict(available=True,rms=.1),crossing=dict(available=True,slip_square_per_m=.1))}
    actor={**deepcopy(common),"profile":"reactive","time_s":20.2,
        "gt_native":dict(whole_route=dict(available=True,rms=.095),crossing=dict(available=True,slip_square_per_m=.09))}
    return [ref,actor]


def test_all_six_points_have_distinct_depth_or_executed_timeout():
    base=load_config(ROOT/"docs/classical_governor_crossing_tune_2026-10-16/selected_candidate.yaml")
    unchanged=deepcopy(base)
    result=execution_preflight(base)
    assert base==unchanged
    assert len(result)==len(CANDIDATES)==6
    assert len({(round(r["synthetic_hold"]["minimum_scale"],3),round(r["synthetic_hold"]["commanded_hold_seconds"],3)) for r in result})==6


def test_cost_uses_fixed_time_and_gt_slip_and_accepts_only_guarded_candidate():
    data=rows();s=score(data)
    assert np.isclose(s["value"],.955)
    assert s["eligible"] and s["feasible"]
    data[1]["physical_rmse_m"]*=1.06
    assert not score(data)["eligible"]
    data=rows();data[1]["gt_native"]["whole_route"]["rms"]*=1.2
    assert not score(data)["eligible"]


def test_physical_failure_counts_even_when_contact_measurement_is_missing():
    data=rows();data[1].update(physical_success=False,physical_pass=False,available=False)
    data[1].pop("gt_native")
    s=score(data)
    assert s["value"]==110 and s["physical_failures"]==[1]
    assert not s["eligible"]


def test_missing_or_failed_reference_and_corrupt_measurement_never_become_zero_cost():
    data=rows();data[0]["physical_pass"]=False
    with pytest.raises(ValueError,match="PI reference"):score(data)
    data=rows();data[1]["gt_native"]["crossing"]["available"]=False
    with pytest.raises(ValueError,match="coverage"):score(data)
    data=rows();data[1]["native_replay"]["matches_native"]=False
    with pytest.raises(ValueError,match="reporting"):score(data)
