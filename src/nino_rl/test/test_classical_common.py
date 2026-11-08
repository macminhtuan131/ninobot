"""Classical schedule/projection semantics and one-shot experiment budget."""
from pathlib import Path
import numpy as np
import pytest
from nino_control.residual_velocity import ResidualReference,ReferenceLimits
from nino_rl import residual_classical_common as common

def setup():
    c,_,_,_=common.learner.configuration('clear_box')
    return c,common.ClassicalCommonProfile(c,common.protocol())

def view(**kwargs):return dict(dict(baseline=(.2,0.),permission=True,sensors_fresh=True,fault=False,emergency_stop=False,command_age_s=0.),**kwargs)

def steady(profile):
    for i in range(20):profile.proposal(i*.1,view(),True)

def test_schedule_has_fixed_amplitude_and_withdraws_at_boundary():
    c,p=setup();steady(p)
    a,trace=p.proposal(7.4,view(),True)
    np.testing.assert_array_equal(a,[.125,0.]);assert trace['requested_common_m_s']==.005 and not trace['truth_input']
    for t in (7.5,7.6,8.,14.):
        a,trace=p.proposal(t,view(),True);assert not any(a) and trace['reason']=='planned_withdrawal'

@pytest.mark.parametrize('changes,ready,extra',[
    ({'permission':False},True,{}),({'sensors_fresh':False},True,{}),({'fault':True},True,{}),
    ({'emergency_stop':True},True,{}),({'command_age_s':-.01},True,{}),({'command_age_s':.3},True,{}),
    ({},False,{}),({},True,{'done':True}),({},True,{'latched':True}),({'baseline':(0.,0.)},True,{})])
def test_invalid_inputs_and_zero_source_cannot_enable_compensation(changes,ready,extra):
    _,p=setup();steady(p);a,_=p.proposal(3.,view(**changes),ready,**extra);assert not any(a)

def test_ramp_and_withdrawal_pass_through_unchanged_projection():
    c,p=setup();actual=ResidualReference(ReferenceLimits(**c['reference_limits']));previous=np.zeros(2);active=[]
    for i in range(140):
        t=i*.1;v=view(baseline=(.2 if .5<=t<8 else 0.,0.))
        a,audit=p.proposal(t,v,i>=4)
        if any(a):
            assert abs(audit['nominal_shaped_body'][0]-.2)<1e-8 and t<7.5
            active.append(t)
        trace=actual.compose(v['baseline'],a,.1,1.,permission=True,sensors_fresh=True,history_ready=i>=4,command_age_s=0.)
        wheels=np.asarray(trace['accepted_reference_wheel_m_s'])
        assert max(abs(wheels-previous))<=.01+1e-9;previous=wheels
        if 7.5<=t<=8:np.testing.assert_allclose(trace['accepted_policy_delta_wheel_m_s'],[0,0],atol=1e-9)
    assert active and max(active)<7.5 and not any(previous)

def test_budget_and_closed_ledger_are_not_reopened(tmp_path,monkeypatch):
    p=common.protocol();assert len(p['order'])==6 and p['maximum_transitions']==840
    assert p['training_transitions']==p['optimizer_updates']==p['hardware_actions']==0
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    (tmp_path/'state.json').write_text('{}')
    with pytest.raises(ValueError,match='already consumed'):common.run(tmp_path)

def test_physical_failure_retains_one_attempt_and_closes_remaining_slots(tmp_path,monkeypatch):
    monkeypatch.setattr(common,'parents',lambda:(tmp_path,tmp_path))
    monkeypatch.setattr(common.learner,'dependency_record',lambda p:{})
    monkeypatch.setattr(common,'PortableActor',lambda *args:None)
    monkeypatch.setattr(common,'prepare_worlds',lambda p:{'clear_box':'world'})
    calls=[]
    def fail(*args):calls.append(1);return dict(physical_failure=True,guidance_faults=0,steps=20)
    monkeypatch.setattr(common,'rollout',fail)
    with pytest.raises(RuntimeError,match='no retry'):common.evaluate(tmp_path)
    assert len(calls)==1 and (tmp_path/'evaluation_progress.json').is_file()
    assert not (tmp_path/'evaluation_result.json').exists()
