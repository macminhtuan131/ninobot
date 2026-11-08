"""Physical claims are not made by these static algebra/software checks."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
from nino_control.residual_velocity import FEATURES,SCALES
from nino_rl import sim_benchmark_decision as m


GEOMETRY=dict(radius_l=.0625,radius_r=.0625)


def packet(gain,reference=.2):
    frames=np.zeros((5,20))
    for name,value in [('baseline_v_m_s',.2),('last_final_v_m_s',reference),
                       ('wheel_l_rad_s',gain*reference/GEOMETRY['radius_l']),
                       ('wheel_r_rad_s',gain*reference/GEOMETRY['radius_r'])]:
        frames[:,FEATURES.index(name)]=value/SCALES[FEATURES.index(name)]
    return np.r_[frames.ravel(),.5,1.,0.]


@pytest.mark.parametrize('gain',[.98,1.,1.02])
def test_unknown_static_gain_is_compensated_without_privileged_input(gain):
    p=m.specification();observation=packet(gain)
    before=observation.copy()
    request,audit=m.causal_gain_request(observation,GEOMETRY,p['candidate'])
    assert abs(request)<=1. and audit['valid']
    # Outcome of the ideal algebraic model only, not a Gazebo/body response.
    assert gain*(.2+request*.005)==pytest.approx(.2,abs=1e-14)
    np.testing.assert_array_equal(observation,before)
    assert not audit['body_reference_verified']


def test_closed_window_and_small_or_varying_reference_fall_back_to_zero():
    p=m.specification();obs=packet(.98);obs[101]=0
    assert m.causal_gain_request(obs,GEOMETRY,p['candidate'])[0]==0
    for obs in (packet(.98,reference=.01),packet(.98)):
        if obs[90]>.1:obs[10]=.16/SCALES[10]
        request,audit=m.causal_gain_request(obs,GEOMETRY,p['candidate'])
        assert request==0 and not audit['valid']


@pytest.mark.parametrize('bad',[np.zeros(100),np.full(103,np.nan),np.full(103,np.inf)])
def test_invalid_sensor_packet_is_not_silently_compensated(bad):
    with pytest.raises(ValueError,match='causal observation'):
        m.causal_gain_request(bad,GEOMETRY,m.specification()['candidate'])


def test_unknown_geometry_and_nonbinary_mask_are_rejected():
    obs=packet(1.);obs[101]=.5
    with pytest.raises(ValueError,match='binary'):
        m.causal_gain_request(obs,GEOMETRY,m.specification()['candidate'])
    with pytest.raises(ValueError,match='radii'):
        m.causal_gain_request(packet(1.),dict(radius_l=0.,radius_r=.0625),m.specification()['candidate'])


def test_unreachable_ideal_gain_is_reported_as_saturation_not_a_guarantee():
    p=m.specification();obs=packet(.9)
    request,audit=m.causal_gain_request(obs,GEOMETRY,p['candidate'])
    assert request==1. and .9*(.2+.005)<.2
    assert not m.ideal_authority(p)['physical_feasibility_verified']
    assert all(row['within_ideal_bound'] for row in m.ideal_authority(p)['rows'])


def trace():
    return [dict(step=i,equal_observation=packet(1.).tolist(),
        qualification_condition=dict(arm='fixture',source_stop_s=8.),
        plan_projection=dict(window_open=True,decision_task_s=i*.1),
        task=dict(velocity_error_m_s=.01 if i<70 else .02)) for i in range(140)]


def test_cost_partition_and_shadow_are_descriptive_not_counterfactual():
    rows=trace()
    for row in rows[70:]:
        row['equal_observation'][101]=0.;row['plan_projection']['window_open']=False
    summary,shadow=m.summarize_trace(rows,GEOMETRY,m.specification())
    assert summary['open_ticks']==summary['closed_ticks']==70
    assert summary['observed_open_cost_fraction']==pytest.approx(.2)
    assert summary['observed_closed_cost_fraction']==pytest.approx(.8)
    assert summary['partition_is_not_counterfactual_or_benefit_bound']
    assert summary['shadow_is_not_new_controller_outcome']
    assert len(shadow)==140 and all(r['request_scalar']==0. for r in shadow)


@pytest.mark.parametrize('fault',['missing','window_mismatch','nonfinite','sequence'])
def test_partial_or_inconsistent_trace_cannot_become_a_decision(fault):
    rows=trace()
    if fault=='missing':rows.pop()
    if fault=='window_mismatch':rows[1]['equal_observation'][101]=0.
    if fault=='nonfinite':rows[1]['task']['velocity_error_m_s']=float('nan')
    if fault=='sequence':rows[1]['step']=9
    with pytest.raises(ValueError):m.summarize_trace(rows,GEOMETRY,m.specification())


def test_specification_does_not_authorize_any_proposed_physics_budget():
    p=m.specification()
    assert p['proposed_qualification']['maximum_launches']==9
    assert p['proposed_qualification']['maximum_eval_ticks']==9*140
    assert not any(p['release'].values())
    assert p['holdout']['training_steps'] is None
    assert p['application_effect_accepted'] is None


def test_release_edit_is_rejected_even_when_valid_json(monkeypatch):
    altered=deepcopy(m.specification());altered['release']['physics_authorized']=True
    monkeypatch.setattr(m,'read',lambda p:altered)
    with pytest.raises(ValueError,match='cannot release'):m.specification()


def test_gui_verification_rejects_derived_tampering_and_failed_source(tmp_path,monkeypatch):
    source=tmp_path/'source'/'eval';source.mkdir(parents=True)
    files=['evaluation_result.json']+[f'eval_{i:02d}/{name}' for i in range(6)
        for name in ('config.json','summary.json','trace.jsonl')]
    for name in files:
        path=source/name;path.parent.mkdir(exist_ok=True);path.write_text('{}')
    (source/'manifest.json').write_text(json.dumps(dict(files={name:m.sha(source/name) for name in files})))
    pin=m.sha(source/'manifest.json');monkeypatch.setattr(m,'SOURCE_MANIFEST',pin)
    state=source.parent/'state.json'
    state.write_text(json.dumps(dict(latest={'sim-ready-eval-only':source.name},runs=[dict(status='completed')])))
    out=tmp_path/'report';out.mkdir()
    r=dict(source_artifact=str(source),source_manifest_sha256=pin,trace_sha256={})
    (out/'decision.json').write_text(json.dumps(r))
    (out/'manifest.json').write_text(json.dumps(dict(fingerprint=m.fingerprint(),files={'decision.json':m.sha(out/'decision.json')})))
    assert m.verified_report(out)==r
    target=source/'eval_00/config.json';target.write_text('changed')
    with pytest.raises(ValueError,match='input changed'):m.verified_report(out)
    target.write_text('{}');state.write_text(json.dumps(dict(latest={'sim-ready-eval-only':source.name},runs=[])))
    with pytest.raises(ValueError,match='superseded or failed'):m.verified_report(out)
    (out/'decision.json').write_text('{}')
    with pytest.raises(ValueError,match='artifact changed'):m.verified_report(out)
