import importlib.util
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('envelope',Path(__file__).with_name('audit.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(step):
    t=np.arange(-.3,1.001,.02)
    reference=np.column_stack([t,np.ones(len(t))*.4])
    candidate=reference.copy()
    candidate[:,1]-=np.where(t>=step,.04,0.)
    return candidate,reference


def test_precommand_difference_is_not_attributed_to_command():
    c,r=fixture(0.)
    d=m.divergence(c,r,.08,.02,.040001)
    assert d['onset']['precedes_earliest_input']
    assert d['causal_response_onset'] is None


def test_postcommand_divergence_remains_descriptive_and_bracketed():
    c,r=fixture(.2)
    d=m.divergence(c,r,.08,.02,.040001)
    assert not d['onset']['precedes_earliest_input']
    lo,hi=d['onset']['bracket_s']
    assert lo<hi<=d['onset']['confirmed_s']-.06+1e-8
    assert d['causal_response_onset'] is None


def test_future_reference_cannot_support_candidate():
    c,r=fixture(.2)
    r[:,0]+=2.
    assert not m.divergence(c,r,.08,.02,.040001)['available']


def test_gap_does_not_confirm_short_transient():
    c,r=fixture(.2)
    c=c[(c[:,0]<.24)|(c[:,0]>.5)]
    c[c[:,0]>.5,1]=.4
    assert m.divergence(c,r,.08,.02,.040001)['onset'] is None


def test_nan_is_unavailable_not_a_difference():
    c,r=fixture(.2)
    r[:,1]=np.nan
    assert not m.divergence(c,r,.08,.02,.040001)['available']


def test_remaining_slip_conserves_and_keeps_spike():
    t=np.arange(0.,3.001,.02)
    q=np.zeros(len(t));q[5]=100.
    s=dict(time=t,q=q,xy=np.column_stack([t,np.zeros(len(t))]))
    imu=list(zip(t,np.sqrt(q)))
    total=m.residual(s,imu,0.,0.)
    tail=m.residual(s,imu,0.,.2)
    assert total['slip_fraction_remaining']==1.
    assert total['slip']['slip_square_integral_s']>0
    assert tail['slip_fraction_remaining']==0.
    assert total['imu_squared_sample_fraction_remaining']==1.


def test_missing_slip_coverage_never_returns_zero_cost():
    t=np.array([0.,.02,2.98,3.])
    s=dict(time=t,q=np.ones(4),xy=np.column_stack([t,np.zeros(4)]))
    d=m.residual(s,list(zip(t,np.ones(4))),0.,.1)
    assert d['slip_fraction_remaining'] is None
    assert not d['slip']['available']
