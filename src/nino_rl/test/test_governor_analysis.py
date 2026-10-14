"""Missing time series must not turn into a successful quality measurement."""
import importlib.util
from pathlib import Path

import pytest

path=Path(__file__).resolve().parents[1]/"scripts/analyze_governor_experiment.py"
spec=importlib.util.spec_from_file_location("governor_analysis",path)
analysis=importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def test_missing_impact_is_unavailable_not_zero():
    result=analysis.energy([],0.,2.)
    assert not result["available"]
    assert result["rms"] is None and result["peak"] is None


def test_long_sensor_gap_does_not_count_as_coverage():
    result=analysis.energy([(0.,1.),(.02,1.),(1.98,1.),(2.,1.)],0.,2.)
    assert not result["available"]
    assert result["coverage_s"]==pytest.approx(.04)


def test_constant_signal_with_coverage_has_correct_energy():
    result=analysis.energy([(i*.02,3.) for i in range(101)],0.,2.)
    assert result["available"]
    assert result["rms"]==pytest.approx(3.)


def test_independent_runs_do_not_share_episode_identity():
    first=analysis.identity({"episode":{"run_id":"first","attempt":1}})
    second=analysis.identity({"episode":{"run_id":"second","attempt":1}})
    assert first!=second
    assert analysis.identity({"episode":first})==first
