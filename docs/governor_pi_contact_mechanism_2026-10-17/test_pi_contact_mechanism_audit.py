from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_pi_contact_mechanism import asof, force_summary, phase_sensitivity


def test_causal_lookup_rejects_future_and_stale_feedback():
    series=[(1., "past"), (1.02, "future")]
    assert asof(series,1.01,.02)["value"]=="past"
    assert asof(series,.99,.02) is None
    assert asof(series,1.1,.02) is None


def test_manifold_and_zero_depth_force_do_not_prove_load():
    def contact(depth, force):
        return dict(depths=[depth],wrenches=[dict(body_1_wrench=dict(force=dict(x=force,y=0.,z=0.)))])
    assert not force_summary(contact(0.,10.))["loaded"]
    assert not force_summary(contact(.001,0.))["loaded"]
    assert force_summary(contact(.001,10.))["loaded_force_norm_sum_N"]==10.


def test_phase_sweep_keeps_spike_and_all_residues_without_claiming_acquisition():
    times=np.arange(-.04,3.061,.02)
    values=np.zeros(len(times));values[np.argmin(abs(times-.5))]=80.
    result=phase_sensitivity([(float(t),dict(vertical_m_s2=float(v))) for t,v in zip(times,values)],0.,3.)
    assert result["original_50Hz_samples"]["peak_abs"]==80.
    assert len(result["linear_50Hz_grid_offsets"])==10
    peaks=[s["peak_abs"] for s in result["decimated_10Hz_residues"]]
    assert max(peaks)==80. and min(peaks)==0.
    assert not result["acquisition_phase_identifiable"]


def test_missing_imu_support_is_not_silently_interpolated():
    series=[(float(t),dict(vertical_m_s2=1.)) for t in np.arange(-.04,3.061,.02) if not .5<t<.7]
    with pytest.raises(ValueError,match="Missing IMU support"):
        phase_sensitivity(series,0.,3.)
