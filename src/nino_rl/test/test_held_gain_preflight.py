"""Actual offline pipeline with synthetic sealed inputs; never physical outcomes."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import numpy as np
import pytest
from nino_rl import held_gain_preflight as m


def rows():
    result=[]
    for i in range(140):
        obs=m.packet([.2]*5,[.196]*5);obs[101]=float(25<=i<75)
        t=i*.1
        samples={n:dict(source_s=None if n=='baseline' else t,receipt_s=t,values=[])
            for n in ('imu','wheel','baseline','final','status')}
        samples['status']['values']=dict(permission=True,fault=False,emergency_stop=False)
        result.append(dict(step=i,equal_observation=obs.tolist(),requested_scalar_action=[0.],
            qualification_condition=dict(arm='source_fixture',gain=.98),
            reference_trace=dict(input_stamp_s=t,source_samples=samples,history_ready=i>=4),
            sensor_clock_s=t+.1,truth_pose_m_rad=[0.,0.,0.]))
    return result


def input_artifact(tmp_path,monkeypatch):
    source=tmp_path/'sealed_source';source.mkdir()
    for i in range(9):
        cell=source/f'eval_{i:02d}';cell.mkdir()
        (cell/'trace.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows()))
        m.write(cell/'config.json',dict(config=dict(nominal_geometry=dict(radius_l=.0625,radius_r=.0625))))
    (source/'manifest.json').write_text('{}')
    monkeypatch.setattr(m,'SOURCE_MANIFEST',m.sha(source/'manifest.json'))
    monkeypatch.setattr(m,'source',lambda:source)
    return source


def test_synthetic_feedback_and_lag_fixtures_do_not_claim_identification():
    cases,traces=m.fixtures()
    assert len(cases)==5 and sum(c['decisions'] for c in cases)==143
    for c,t in zip(cases[:3],traces[:3]):
        assert c['bounded'] and c['window_close_zero'] and len(t)==31
        assert not c['physical_outcome_evaluated']
    assert cases[0]['held_ticks']>0 and cases[2]['held_ticks']>0
    assert cases[3]['first_update_s']>=1.
    assert cases[4]['identification'].startswith('unknown')


def test_shadow_uses_decision_support_and_keeps_outcome_unknown():
    summary,trace=m.shadow(rows(),dict(radius_l=.0625,radius_r=.0625))
    assert summary['source_rows']==summary['shadow_ticks']==len(trace)==140
    assert summary['open_ticks']==50 and summary['not_a_counterfactual_outcome']
    assert summary['states']==dict(updated=50)
    assert all(r['shadow_request_scalar']==0 for r in trace if not r['shared_window'])
    assert not any(r['new_outcome'] for r in trace)


def test_hidden_gain_gt_and_post_decision_clock_cannot_change_shadow_action():
    a=rows();b=deepcopy(a)
    for row in b:
        row.update(qualification_condition=dict(arm='different_hidden_label',gain=100.),
            sensor_clock_s=-999.,truth_pose_m_rad=[99.,99.,99.],body_speed_m_s=-100.)
    _,x=m.shadow(a,dict(radius_l=.0625,radius_r=.0625))
    _,y=m.shadow(b,dict(radius_l=.0625,radius_r=.0625))
    assert x==y


@pytest.mark.parametrize('fault',['missing','sequence'])
def test_partial_or_out_of_order_source_rows_never_qualify(fault):
    r=rows()
    if fault=='missing':r.pop()
    else:r[1]['step']=3
    with pytest.raises(ValueError,match='ordered'):m.shadow(r,dict(radius_l=.0625,radius_r=.0625))


def test_stale_packet_in_shadow_immediately_zeroes_and_requires_refill():
    r=rows();r[35]['reference_trace']['source_samples']['wheel']['source_s']=3.
    _,trace=m.shadow(r,dict(radius_l=.0625,radius_r=.0625))
    assert trace[34]['shadow_request_scalar']!=0
    assert trace[35]['shadow_request_scalar']==0 and trace[35]['reason']=='stale_future_or_missing_source'
    assert all(trace[i]['shadow_request_scalar']==0 for i in range(36,40))
    assert trace[40]['state']=='updated'


def test_actual_run_seals_1260_shadow_rows_no_processes_and_preserves_inputs(tmp_path,monkeypatch):
    source=input_artifact(tmp_path,monkeypatch)
    before={str(p):m.sha(p) for p in source.rglob('*') if p.is_file()}
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:pytest.fail('Offline must not spawn a process'))
    output=tmp_path/'derived';r=m.run(output)
    assert r['source_rows']==r['shadow_decisions']==1260 and r['synthetic_decisions']==143
    assert not any(r[k] for k in ('new_gazebo_launches','new_physics_steps','actor_loads','new_training_transitions','new_optimizer_updates','hardware_actions','physics_released','training_released'))
    assert r['correction_count']==1 and r['correction_budget_closed'] and not r['physical_benefit_verified']
    assert r['gain_identification'].startswith('unknown')
    assert m.verified_report(output)==r
    assert before=={str(p):m.sha(p) for p in source.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='already exists'):m.run(output)


@pytest.mark.parametrize('target',['report','source','traversal'])
def test_artifact_or_input_tampering_fails_closed(tmp_path,monkeypatch,target):
    source=input_artifact(tmp_path,monkeypatch);output=tmp_path/'derived';m.run(output)
    if target=='report':(output/'qualification.json').write_text('{}')
    elif target=='source':(source/'eval_00/trace.jsonl').write_text('{}')
    else:
        manifest=m.read(output/'manifest.json');manifest['files']['../outside']='ignored'
        m.write(output/'manifest.json',manifest)
    with pytest.raises(ValueError):m.verified_report(output)


def test_failure_preserves_diagnostic_without_sealing_success_or_overwrite(tmp_path,monkeypatch):
    input_artifact(tmp_path,monkeypatch)
    def failure():raise RuntimeError('synthetic fixture fault')
    monkeypatch.setattr(m,'fixtures',failure)
    output=tmp_path/'derived'
    with pytest.raises(RuntimeError):m.run(output)
    assert m.read(output/'failure.json')['retain_do_not_retry']
    assert not (output/'manifest.json').exists()
    with pytest.raises(ValueError,match='already exists'):m.run(output)


def test_no_derived_writes_inside_sealed_source(tmp_path,monkeypatch):
    source=input_artifact(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='outside'):m.run(source/'child')
    assert not (source/'child').exists()
