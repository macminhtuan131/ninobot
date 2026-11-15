import math
import pytest
from nino_rl.motion_quality_metrics import vertical_rms


def measure(f,a,lo=0.,hi=.04,**kw):
    return vertical_rms(f,a,lo,hi,gravity_m_s2=9.8,convention_verified=True,mount_body_aligned=True,**kw)


def test_static_tilt_gravity_projection_is_not_vibration():
    roll,pitch=.2,-.3
    fz=9.8*math.cos(roll)*math.cos(pitch)
    r=measure([(0.,fz)],[(0.,[roll,pitch])])
    assert r['rms_m_s2']==pytest.approx(0,abs=1e-12) and r['coverage_pass']


def test_source_integral_clips_endpoints_and_retains_spike():
    r=measure([(0.,9.8),(.02,19.8),(.04,9.8)],[(0.,[0,0]),(.04,[0,0])],.01,.05)
    assert r['integral_m2_s3']==pytest.approx(2.)
    assert r['rms_m_s2']==pytest.approx(math.sqrt(50.))
    assert sum(s['end_s']-s['start_s'] for s in r['segments'])==pytest.approx(.04)


def test_expired_and_ambiguous_samples_are_not_silently_zero_or_fallback():
    r=measure([(0.,9.8),(.02,10.8),(.02,11.8),(.06,9.8)],[(0.,[0,0]),(.04,[0,0])],0.,.08)
    assert r['force_conflict_groups']==1
    assert r['supported_duration_s']==pytest.approx(.04)
    assert not r['coverage_pass']
    missing=[s for s in r['segments'] if not s['supported']]
    assert all(s['vertical_acceleration_m_s2'] is None for s in missing)
    stale=measure([(0.,9.8)],[(0.,[0,0])],0.,.1)
    assert stale['supported_duration_s']==pytest.approx(.04)


def test_no_future_sample_can_fill_initial_interval():
    r=measure([(.02,9.8)],[(0.,[0,0])])
    assert r['coverage_fraction']==pytest.approx(.5)
    assert r['segments'][0]['force_reason']=='before_first_source'


def test_unknown_mount_or_convention_and_reversed_source_are_rejected():
    for flag in ('convention_verified','mount_body_aligned'):
        kw=dict(gravity_m_s2=9.8,convention_verified=True,mount_body_aligned=True);kw[flag]=False
        with pytest.raises(ValueError):vertical_rms([(0.,9.8)],[(0.,[0,0])],0.,.04,**kw)
    with pytest.raises(ValueError):measure([(.02,9.8),(0.,9.8)],[(0.,[0,0])])
