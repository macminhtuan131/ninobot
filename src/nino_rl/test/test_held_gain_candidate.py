"""Synthetic causal packets only. No ROS, Gazebo or calibrated body model."""
from dataclasses import replace
import numpy as np
import pytest
from nino_control.residual_velocity import FEATURES, SCALES
from nino_rl.held_gain_candidate import HeldGainCandidate, DecisionSupport, support_from_trace

GEOMETRY = dict(radius_l=.0625, radius_r=.0625)


def packet(gain=.98, references=None, wheels=None, window=1.):
    refs=np.full(5,.2) if references is None else np.asarray(references)
    measured=np.tile(gain*refs,(2,1)) if wheels is None else np.asarray(wheels)
    f=np.zeros((5,20))
    for name, values in [('baseline_v_m_s',np.full(5,.2)),('last_final_v_m_s',refs),
            ('wheel_l_rad_s',measured[0]/.0625),('wheel_r_rad_s',measured[1]/.0625)]:
        f[:,FEATURES.index(name)]=values/SCALES[FEATURES.index(name)]
    return np.r_[f.ravel(),.5,window,0.]


def support(t, **changes):
    return replace(DecisionSupport(t,'epoch1',(t,)*5,True,True,True,False,False),**changes)


def primed(gain=.98):
    c=HeldGainCandidate(GEOMETRY)
    for i in range(5):result=c.step(packet(gain),support(i*.1))
    assert result[1]['state']=='updated'
    return c,result


@pytest.mark.parametrize('gain',[.98,1.,1.02])
def test_ideal_static_algebra_after_trusted_refill(gain):
    c,(a,meta)=primed(gain)
    assert gain*(.2+a*.005)==pytest.approx(.2)
    assert meta['update_accepted'] and abs(a)<=1
    assert not meta['physical_gain_identified'] and not meta['execution_verified']


def test_own_reference_change_holds_estimate_not_a_zero_command():
    c,(first,_)=primed()
    changing=packet(references=[.2,.2,.2,.2,.2+first*.005])
    action,meta=c.step(changing,support(.5))
    assert action==pytest.approx(first)
    assert meta['state']=='held' and meta['reason']=='reference_changing'
    assert not meta['update_accepted'] and meta['estimate_age_s']==pytest.approx(.1)


def test_constant_reference_during_wheel_transient_cannot_update_estimate():
    c=HeldGainCandidate(GEOMETRY)
    wheels=np.tile([.10,.13,.16,.18,.19],(2,1))
    for i in range(7):action,meta=c.step(packet(wheels=wheels),support(i*.1))
    assert action==0 and meta['reason']=='no_estimate:encoder_changing'
    assert c.gain is None


def test_single_changing_wheel_cannot_be_hidden_by_steady_average():
    c=HeldGainCandidate(GEOMETRY)
    wheels=np.array([[.18,.19,.20,.21,.22],[.22,.21,.20,.19,.18]])
    for i in range(5):action,meta=c.step(packet(wheels=wheels),support(i*.1))
    assert action==0 and meta['reason']=='no_estimate:encoder_changing'


def test_hold_expires_at_finite_lease_without_refresh_from_invalid_updates():
    c,(first,_)=primed()
    changing=packet(references=[.20,.20,.20,.20,.205])
    for i in range(5,11):
        action,meta=c.step(changing,support(i*.1))
        assert action==pytest.approx(first) and meta['state']=='held'
    action,meta=c.step(changing,support(1.1))
    assert action==0 and meta['reason'].startswith('estimate_lease_expired')
    assert c.gain is None


@pytest.mark.parametrize('change,reason',[
    ({'permission':False},'owner_freshness_fault_or_stop'),
    ({'permission':None},'owner_freshness_fault_or_stop'),
    ({'sensors_fresh':False},'owner_freshness_fault_or_stop'),
    ({'fault':True},'owner_freshness_fault_or_stop'),
    ({'emergency_stop':True},'owner_freshness_fault_or_stop'),
    ({'source_stamps_s':(.4,)*5},'stale_future_or_missing_source'),
    ({'source_stamps_s':(.51,)*5},'stale_future_or_missing_source'),
    ({'source_stamps_s':(.5,.5,None,.5,.5)},'unknown_clock_or_source'),
])
def test_authority_and_source_faults_immediately_clear_held_state(change,reason):
    c,_=primed()
    action,meta=c.step(packet(),support(.5,**change))
    assert action==0 and meta['reason']==reason and c.gain is None
    assert c.healthy_ticks==0
    for i in range(6,10):assert c.step(packet(),support(i*.1))[0]==0
    result=c.step(packet(),support(1.))
    if reason=='unknown_clock_or_source':
        # Unknown support did not advance the clock high-water mark; the next
        # valid decision also detects a gap, then refills five trusted packets.
        assert result[0]==0
        result=c.step(packet(),support(1.1))
    assert result[1]['state']=='updated'


@pytest.mark.parametrize('time,reason',[(.4,'duplicate_or_reversed_clock'),(.3,'duplicate_or_reversed_clock'),(.6,'history_clock_gap')])
def test_invalid_clock_never_retains_old_estimate(time,reason):
    c,_=primed()
    action,meta=c.step(packet(),support(time))
    assert action==0 and meta['reason']==reason and c.gain is None


def test_reordered_source_with_fresh_age_is_rejected():
    c,_=primed()
    # 20ms decision advance: old source .4 is fresh but duplicated.
    action,meta=c.step(packet(),support(.42,source_stamps_s=(.4,)*5))
    assert action==0 and meta['reason']=='duplicate_or_reordered_source'


@pytest.mark.parametrize('kind',['window','stop_baseline','reverse','nominal_change','stale_history'])
def test_window_or_plan_or_history_invalidates_hold(kind):
    c,_=primed();obs=packet()
    if kind=='window':obs[101]=0
    if kind in ('stop_baseline','reverse','nominal_change'):
        obs[80+FEATURES.index('baseline_v_m_s')]=(0 if kind=='stop_baseline' else -.1 if kind=='reverse' else .1)/SCALES[0]
    if kind=='stale_history':obs[FEATURES.index('wheel_age_s')]=.05/SCALES[17]
    action,meta=c.step(obs,support(.5))
    assert action==0 and c.gain is None


def test_epoch_and_explicit_reset_clear_cache_and_trusted_history():
    c,_=primed()
    assert c.step(packet(),support(0.,epoch='epoch2'))[0]==0
    assert c.gain is None and c.healthy_ticks==1
    for i in range(1,5):action,meta=c.step(packet(),support(i*.1,epoch='epoch2'))
    assert meta['state']=='updated'
    c.reset('epoch3')
    assert c.gain is c.last_clock is c.last_stamps is None


@pytest.mark.parametrize('obs',[np.zeros(100),np.full(103,np.nan),['bad'],np.r_[np.zeros(101),.5,0.]])
def test_malformed_packet_raises_and_discards_old_state(obs):
    c,_=primed()
    with pytest.raises(ValueError):c.step(obs,support(.5))
    assert c.gain is None and c.healthy_ticks==0


def test_missing_typed_support_cannot_reuse_last_estimate():
    c,_=primed()
    with pytest.raises(ValueError,match='Typed'):c.step(packet(),{})
    assert c.gain is None


def test_support_adapter_has_only_declared_causal_sources():
    trace=dict(input_stamp_s=1.,history_ready=True,source_samples={n:dict(
        source_s=None if n=='baseline' else .99,receipt_s=1.,values={})
        for n in ('imu','wheel','baseline','final','status')})
    trace['source_samples']['status']['values']=dict(permission=True,fault=False,emergency_stop=False)
    s=support_from_trace(trace,epoch='fixture')
    assert s.source_stamps_s==(.99,.99,1.,.99,.99) and s.permission
    trace['source_samples']['privileged_gain']=dict(source_s=1.)
    with pytest.raises(ValueError,match='five'):support_from_trace(trace,epoch='fixture')


def test_finite_history_cannot_identify_static_gain_against_hidden_lag():
    # The same five sensor frames can be a true .98 steady gain or a gain-one
    # actuator temporarily flat at .196m/s. Hidden condition labels never enter.
    a,b=HeldGainCandidate(GEOMETRY),HeldGainCandidate(GEOMETRY)
    for i in range(5):
        x=a.step(packet(.98),support(i*.1));y=b.step(packet(.98),support(i*.1))
        assert x==y
    assert x[1]['update_accepted'] and not x[1]['physical_gain_identified']
