"""Ambiguous raw stamps remain unknown; V1 failure is never overwritten."""
from copy import deepcopy
import json,subprocess
from pathlib import Path
import pytest
from nino_rl import sim_chain_dynamics_audit as v1
from nino_rl import sim_chain_dynamics_audit_v2 as m
from test_sim_chain_dynamics_audit import raw,fixture_cell,inputs


def conflict(t):
    row=deepcopy(next(r for r in raw(t) if r['channel']=='wheel'))
    row['values'][0]+=.001
    return row


def test_unambiguous_query_matches_frozen_v1_alignment():
    records=[r for i in range(10) for r in raw(3.+i*.02)]
    a,duplicates=v1.align_raw(records,1.,3.,3.2)
    b=m.align_raw(records,1.,3.,3.2)
    assert b['query_complete'] and b['conflicts']==[]
    assert len(a)==len(b['rows']) and duplicates==b['duplicate_counts']
    for x,y in zip(a,b['rows']):
        for key in ('task_s','truth','wheel','drive','gain','source_ages_s'):assert x[key]==y[key]


def test_outside_query_conflict_is_retained_without_changing_query_values():
    records=raw(1.)+[conflict(1.)]+raw(3.)
    report=m.align_raw(records,1.,3.,3.1)
    assert report['query_complete'] and len(report['conflicts'])==1
    assert not report['conflicts'][0]['within_query_support']
    assert len(report['conflicts'][0]['payload_variants'])==2
    assert report['rows'][0]['wheel']==raw(3.)[2]['values']


def test_ambiguous_nearest_joint_source_is_not_replaced_by_older_good_sample():
    records=raw(3.)+raw(3.02)+[conflict(3.02)]
    report=m.align_raw(records,1.,3.,3.1)
    assert not report['query_complete'] and report['eligible_samples']==2
    assert len(report['rows'])==1 and report['unsupported'][0]['reasons']==['ambiguous_wheel']
    assert report['no_payload_selected_from_ambiguous_stamps']


def test_older_unused_ambiguity_does_not_invalidate_newer_unique_support():
    records=[r for r in raw(3.) if r['channel']!='truth']+[conflict(3.)]+raw(3.02)
    report=m.align_raw(records,1.,3.,3.1)
    assert report['query_complete'] and len(report['conflicts'])==1
    assert len(report['rows'])==1


@pytest.mark.parametrize('name',['truth','drive','gain_map'])
def test_any_selected_ambiguous_channel_makes_query_unknown(name):
    records=raw(3.);r=deepcopy(next(r for r in records if r['channel']==name))
    if name=='truth':r['values']['speed']+=.001
    if name=='drive':r['values']['left_actual_rad_s']+=.001
    if name=='gain_map':r['values']['common_gain']=.98
    report=m.align_raw(records+[r],1.,3.,3.1)
    assert not report['query_complete'] and report['unsupported']


def test_one_ambiguous_sample_marks_entire_cell_raw_metrics_unknown(tmp_path):
    cell=fixture_cell(tmp_path/'cell');p=cell/'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
    with p.open('a') as f:f.write(json.dumps(conflict(4.))+'\n')
    report,points=m.audit_cell(cell,v1.specification())
    assert report['native_rows']==140 and report['primary_rmse_reproduced_m_s']>0
    assert not report['raw_query_complete'] and report['raw_query_eligible_samples']==221
    assert report['raw_query_supported_samples']==220
    assert report['raw_target_encoder_rmse_m_s'] is None and report['raw_encoder_body_rmse_m_s'] is None
    assert report['pi_algorithm_state_proxy'] is None and not report['relaxation_models']['eligible']
    assert points==[]


def test_valid_v2_cell_numerics_equal_frozen_v1(tmp_path):
    cell=fixture_cell(tmp_path/'cell');p=v1.specification()
    a,ap=v1.audit_cell(cell,p);b,bp=m.audit_cell(cell,p)
    assert ap==bp and a['native_open_component_statistics']==b['native_open_component_statistics']
    for name in ('raw_target_encoder_rmse_m_s','raw_encoder_body_rmse_m_s','relaxation_models','pi_algorithm_state_proxy'):
        assert a[name]==b[name]


def fixture_sources(tmp_path,monkeypatch):
    upstream,held=inputs(tmp_path,monkeypatch);failed=tmp_path/'v1_failed';failed.mkdir()
    v1.save(failed/'failure.json',dict(error='fixture failure retained'))
    monkeypatch.setattr(m,'source',lambda:(upstream,held,failed))
    return upstream,held,failed


def test_coordinator_seals_unknown_without_lowering_support_or_mutating_inputs(tmp_path,monkeypatch):
    upstream,held,failed=fixture_sources(tmp_path,monkeypatch)
    rawfile=upstream/'eval_05/episodes/episode_0/backend/episode_0/raw_samples.jsonl'
    with rawfile.open('a') as f:f.write(json.dumps(conflict(4.))+'\n')
    original={str(p):m.sha(p) for root in (upstream,held,failed) for p in root.rglob('*') if p.is_file()}
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:pytest.fail('No subprocess from offline audit'))
    output=tmp_path/'v2';r=m.run(output)
    assert (r['complete_raw_query_cells'],r['unknown_raw_query_cells'],r['raw_conflicting_stamps'])==(8,1,1)
    assert r['native_rows_checked']==1260 and not any(r['release'].values())
    assert m.verified_report(output)==r
    assert original=={str(p):m.sha(p) for root in (upstream,held,failed) for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='exists'):m.run(output)


@pytest.mark.parametrize('target',['raw','report','failure'])
def test_source_or_v1_failure_or_v2_report_tampering_invalidates_result(tmp_path,monkeypatch,target):
    upstream,_,failed=fixture_sources(tmp_path,monkeypatch);output=tmp_path/'v2';m.run(output)
    path=(upstream/'eval_00/trace.jsonl' if target=='raw' else
          failed/'failure.json' if target=='failure' else output/'diagnostic.json')
    path.write_text('{}')
    with pytest.raises(ValueError):m.verified_report(output)
