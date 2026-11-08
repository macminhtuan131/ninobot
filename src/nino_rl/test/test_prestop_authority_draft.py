"""Unreleased reference-only fixture. No Gym/Gazebo/learner or physical claims."""
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pytest
from nino_rl import prestop_authority_draft as draft
from nino_rl import equal_information_contract as parent
from nino_control.residual_velocity import ReferenceLimits,ResidualReference

PATH=Path(__file__).resolve().parents[1]/'config/prestop_tail_authority_draft_v1.json'


def test_draft_has_complete_bounded_proposal_but_no_execution_authority(tmp_path):
    plan=draft.load(PATH)
    assert len(plan['proposed_attempts'])==12 and plan['release']['allocated_attempts']==0
    assert not plan['release']['runtime_implemented'] and not plan['compatibility']['actor_checkpoint_loading_allowed']
    for mutation in ('release','duplicate','input'):
        p=deepcopy(plan)
        if mutation=='release':p['release']['physics_allowed']=True
        elif mutation=='duplicate':p['proposed_attempts'][-1]=p['proposed_attempts'][0]
        else:p['frozen_inputs'][str(tmp_path/'absent')]='abc'
        path=tmp_path/(mutation+'.json');path.write_text(json.dumps(p))
        with pytest.raises(ValueError):draft.load(path)


@pytest.mark.parametrize('stop',[6.,8.])
def test_neutral_reference_exactly_matches_frozen_classical_and_only_tail_differs(stop):
    plan=draft.load(PATH);limits=plan['unchanged']['reference_limits']
    curves=[r for r in draft.reference_preview(plan,limits) if r['stop_s']==stop]
    neutral=next(r['rows'] for r in curves if r['tail_scalar']==0)
    adapter=parent.PlannedCommonAdapter(parent.configuration(stop)[0],stop)
    ref=ResidualReference(ReferenceLimits(**limits))
    for row in neutral:
        view=dict(baseline=(row['source'],0.),permission=True,sensors_fresh=True,
            fault=False,emergency_stop=False,command_age_s=0.)
        obs,_=adapter.prepare(np.zeros(100),view,True)
        mapped,audit=adapter.project(parent.classical_request(obs))
        trace=ref.compose(view['baseline'],mapped,.1,authority=1.,permission=True,
            sensors_fresh=True,history_ready=True,command_age_s=0.)
        assert trace['body_reference'][0]==row['accepted_reference']
    for curve in curves:
        for row,control in zip(curve['rows'],neutral):
            if row['t']<stop-.5-1e-8:assert row==control
            if row['t']>=stop-1e-8:
                assert row['requested_scalar']==0. and row['proposed_common']==0.
            assert abs(row['proposed_common'])<=.005+1e-12
            assert abs(row['accepted_reference']-control['accepted_reference'])<=.005+1e-12
        if curve['tail_scalar']:
            changed=[row for row,control in zip(curve['rows'],neutral) if row['accepted_reference']!=control['accepted_reference']]
            assert changed[0]['t']==pytest.approx(stop-.5)
            assert all(row['accepted_reference']==0. for row in curve['rows'] if row['t']>=stop+2.5)


@pytest.mark.parametrize('t,healthy,forward,nominal',[(5.5,False,True,.2),(5.5,True,False,.2),
    (5.5,True,True,.19),(0.,True,True,0.),(6.,True,True,.2)])
def test_no_tail_authority_when_ineligible(t,healthy,forward,nominal):
    plan=draft.load(PATH)
    for level in (-1,0,1):assert draft.request_at(plan,t,6.,level,
        healthy=healthy,source_forward=forward,nominal_v=nominal)==0.


def test_draft_rejects_invalid_clock_and_action_instead_of_clipping():
    plan=draft.load(PATH)
    for t,stop,level in [(float('nan'),6.,1),(-.1,6.,1),(14.,6.,1),(5.5,7.,1),(5.5,6.,2),(5.5,6.,True)]:
        with pytest.raises(ValueError):draft.request_at(plan,t,stop,level,healthy=True,source_forward=True,nominal_v=.2)
