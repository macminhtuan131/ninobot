import hashlib
import json
import pytest
from nino_pi.studio_training_evidence import completed_training,continuation_summary,scientific_assessment


def fixture(tmp_path):
    def write(name,value):
        p=tmp_path/name;p.write_text(json.dumps(value));return hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(engine='common103_v1',transitions=20000,optimizer_updates_total=10000,actor_updates_total=5000)
    sha=write('training_result.json',result)
    job=write('job.json',dict(status='completed',request=dict(seed=11)))
    manifest=write('manifest.json',dict(status='completed',files={'training_result.json':sha,'job.json':job}))
    record=dict(artifact=str(tmp_path),manifest_sha256=manifest,training_result_sha256=sha,
        seed=11,training_transitions=20000,critic_updates=10000,actor_updates=5000)
    return dict(studio_training_completed=record)


def test_new_completed_counters_are_read_only_and_verified(tmp_path):
    plan=fixture(tmp_path)
    assert completed_training(plan)==dict(seed=11,studio_completed=True,training_transitions=20000,critic_updates=10000,actor_updates=5000)
    assert completed_training({}) is None


@pytest.mark.parametrize('kind',['counter','manifest','result','seed'])
def test_changed_or_inconsistent_evidence_is_rejected(tmp_path,kind):
    plan=fixture(tmp_path);r=plan['studio_training_completed']
    if kind=='counter':r['critic_updates']=9999
    elif kind=='seed':r['seed']=22
    else:(tmp_path/('manifest.json' if kind=='manifest' else 'training_result.json')).write_text('{}')
    with pytest.raises(ValueError):completed_training(plan)


def test_live_continuation_never_claims_verified_replay_or_releases_job(tmp_path):
    path=tmp_path/'status.json'
    record=dict(artifact='/owned/job',status_file=str(path),starting_global_steps=20000,target_global_steps=30000)
    plan=dict(training_studio=dict(active_continuation=record))
    assert continuation_summary({}) is None
    assert 'chưa đọc' in continuation_summary(plan)
    path.write_text(json.dumps(dict(artifact='/owned/job',status='running',global_steps_from_trace=20500)))
    assert '20,500/30,000' in continuation_summary(plan) and 'chưa là QC' in continuation_summary(plan)
    for state in ('completed','failed','cancelled'):
        path.write_text(json.dumps(dict(artifact='/owned/job',status=state)))
        text=continuation_summary(plan)
        assert 'ĐANG CHẠY' not in text and ('không tự' in text or 'không suy' in text)
    path.write_text(json.dumps(dict(artifact='/foreign',status='completed')))
    with pytest.raises(ValueError):continuation_summary(plan)
    path.write_text(json.dumps(dict(artifact='/owned/job',status='running',global_steps_from_trace=30001)))
    with pytest.raises(ValueError):continuation_summary(plan)


def assessed_fixture(tmp_path):
    plan=fixture(tmp_path);record=plan['studio_training_completed']
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    result=json.loads((tmp_path/'training_result.json').read_text())
    result.update(transitions=10000,starting_global_steps=20000,global_steps=30000,
        optimizer_updates_total=20000,actor_updates_total=10000)
    (tmp_path/'training_result.json').write_text(json.dumps(result))
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    manifest['files']['training_result.json']=sha(tmp_path/'training_result.json')
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    record.update(counter_scope='cumulative_single_learner',job_transitions=10000,starting_global_steps=20000,
        training_transitions=30000,critic_updates=20000,actor_updates=10000,
        manifest_sha256=sha(tmp_path/'manifest.json'),training_result_sha256=sha(tmp_path/'training_result.json'))
    root=tmp_path/'review';root.mkdir()
    values={
        'decision.json':dict(decision='KEEP_CLASSICAL_FOR_CURRENT_CLEAR_FLOOR_PLANNED_STOP_ENVELOPE',
            new_ablation_or_training_released=False,all_immutable_inputs_match=True,
            new_physics_steps=0,optimizer_updates=0,hardware_actions=0),
        'analysis.json':dict(models={'30000':dict(global_steps=30000,critic_updates=20000,actor_updates=10000)},
            training_counts={'20000':20000,'30000':10000},corpus_rows=1680),
        'protocol.json':dict(checkpoints={'30000':str(tmp_path/'checkpoints'/'step30000')})}
    for name,value in values.items():(root/name).write_text(json.dumps(value))
    (root/'manifest.json').write_text(json.dumps(dict(status='completed',files={name:sha(root/name) for name in values})))
    plan['latest_sim_assessment']=dict(artifact=str(root),manifest_sha256=sha(root/'manifest.json'),report='report.md')
    return plan


def test_continuation_counters_and_scientific_decision_are_separate_from_new_authority(tmp_path):
    plan=assessed_fixture(tmp_path);before=json.dumps(plan,sort_keys=True)
    completed=completed_training(plan)
    assert completed['training_transitions']==30000 and completed['job_transitions']==10000
    assert completed['starting_global_steps']==20000
    assert scientific_assessment(plan)['decision']['new_ablation_or_training_released'] is False
    assert 'ĐÃ REVIEW' in continuation_summary(plan)
    assert json.dumps(plan,sort_keys=True)==before
    plan['studio_training_completed']['starting_global_steps']=0
    with pytest.raises(ValueError,match='local counter'):completed_training(plan)


@pytest.mark.parametrize('kind',['tamper','release','learner','count','foreign'])
def test_scientific_assessment_rejects_changed_or_unlinked_evidence(tmp_path,kind):
    plan=assessed_fixture(tmp_path);record=plan['latest_sim_assessment'];root=tmp_path/'review'
    name={'tamper':'analysis.json','release':'decision.json','learner':'analysis.json',
        'count':'analysis.json','foreign':'protocol.json'}[kind]
    path=root/name;value=json.loads(path.read_text())
    if kind=='release':value['new_ablation_or_training_released']=True
    elif kind=='learner':value['models']['30000']['critic_updates']=19999
    elif kind=='count':value['corpus_rows']=1679
    elif kind=='foreign':value['checkpoints']['30000']='/foreign/checkpoints/step30000'
    else:value['corpus_rows']=0
    path.write_text(json.dumps(value))
    if kind!='tamper':
        manifest=json.loads((root/'manifest.json').read_text())
        manifest['files'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
        (root/'manifest.json').write_text(json.dumps(manifest))
        record['manifest_sha256']=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()
    with pytest.raises(ValueError):scientific_assessment(plan)
