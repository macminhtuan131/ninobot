"""Sampling sensitivity is diagnostic; outliers remain in native measurements."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_governor_tuning_readiness import phase_sensitivity


def test_decimation_does_not_replace_or_trim_native_peak():
    samples=[(i*.02,100. if i==20 else 1.) for i in range(51)]
    result=phase_sensitivity(samples,0.,1.)
    assert result["native_50hz"]["peak"]==100.
    assert result["diagnostic_even_25hz"]["peak"]==100.
    assert result["diagnostic_odd_25hz"]["peak"]==1.


def test_missing_sampling_window_is_unavailable_not_zero_impact():
    result=phase_sensitivity([],0.,1.)
    assert result["native_50hz"]["available"] is False
    assert result["native_50hz"]["peak"] is None
