"""New job gates and fault handling; no physics or new learner transitions."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from nino_rl import residual_reliable_eval_only as job


def training_fixture(tmp_path):
    out = tmp_path / 'training';out.mkdir()
    p = deepcopy(job.protocol())
    job.save(out / 'job.json', dict(status='failed', error=p['expected_parent_error']))
    for seed in (11,22,33):
        d=out/f'seed_{seed}';d.mkdir()
        (d/'model.zip').write_bytes(f'model{seed}'.encode())
        (d/'replay_buffer.pkl').write_bytes(f'replay{seed}'.encode())
        job.save(d/'learner_identity.json',job.learner.identity())
        job.save(d/'training_result.json',dict(seed=seed,training_transitions=1024,optimizer_updates=960,
            episodes_launched=8,full_task_terminals=7,final_segment_steps=44,final_segment_right_censored=True,
            model_optimizer_target_replay_parity=True,replay=dict(rows_checked=1024)))
        p['checkpoint_sha256'][seed]=job.sha(d/'model.zip');p['replay_sha256'][seed]=job.sha(d/'replay_buffer.pkl')
    seal(out,p)
    return out,p


def seal(out,p):
    job.save(out/'manifest.json',dict(status='failed',reliable_td3_fingerprint=p['parent_fingerprint'],runtime={},
        files={str(f.relative_to(out)):job.sha(f) for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
    p['parent_manifest_sha256']=job.sha(out/'manifest.json')


def test_fixed_budget_order_and_no_training_release():
    p=job.protocol()
    assert p['evaluation_order']==job.learner.protocol()['evaluation_order']
    assert p['maximum_gazebo_launches']==10 and p['maximum_evaluation_transitions']==1400
    assert p['optimizer_updates']==p['training_transitions']==p['hardware_actions']==0
    assert p['training_episodes_per_seed_maximum']==1 and p['minimum_effect_accepted'] is None


def test_actor_snapshot_detects_parameter_or_counter_change_and_nonfinite():
    import torch
    from types import SimpleNamespace
    actor=SimpleNamespace(policy=torch.nn.Linear(103,1),num_timesteps=1024,_n_updates=960)
    before=job.correction.actor_snapshot(actor)
    assert before==job.correction.actor_snapshot(actor)
    actor._n_updates+=1
    assert before!=job.correction.actor_snapshot(actor)
    actor._n_updates-=1
    with torch.no_grad():actor.policy.weight[0,0]+=1
    assert before!=job.correction.actor_snapshot(actor)
    with torch.no_grad():actor.policy.weight[0,0]=float('nan')
    with pytest.raises(ValueError,match='Nonfinite'):job.correction.actor_snapshot(actor)


@pytest.mark.parametrize('field,value',[('maximum_evaluation_transitions',1401),('training_transitions',1),('native_boundary_support_s',.05),('training_episodes_per_seed_maximum',2)])
def test_changed_budget_or_gate_rejected_before_launch(monkeypatch,field,value):
    p=deepcopy(job.protocol());p[field]=value
    monkeypatch.setattr(job,'load_config',lambda path:p)
    with pytest.raises(ValueError,match='budget/gates'):job.protocol()


def test_dependency_record_json_roundtrip_and_all_final_checkpoints(tmp_path):
    out,p=training_fixture(tmp_path)
    assert job.validate_training_artifact(out,p,check_runtime=False)==out
    d=job.dependency_record(out,p)
    assert json.loads(json.dumps(d))==d and set(d['checkpoint_sha256'])=={'11','22','33'}


@pytest.mark.parametrize('fault',['manifest','raw_file','model_pin','failure_reason','incomplete','identity','runtime'])
def test_parent_tamper_wrong_failure_or_incomplete_seed_fails_closed(tmp_path,monkeypatch,fault):
    out,p=training_fixture(tmp_path)
    if fault=='manifest':(out/'manifest.json').write_text('{}')
    elif fault=='raw_file':(out/'seed_22/model.zip').write_bytes(b'changed')
    elif fault=='model_pin':p['checkpoint_sha256'][22]='wrong pinned digest'
    elif fault=='failure_reason':
        job.save(out/'job.json',dict(status='failed',error='sensor timeout'));seal(out,p)
    elif fault=='incomplete':
        path=out/'seed_22/training_result.json';r=job.read(path);r['training_transitions']=1023;job.save(path,r);seal(out,p)
    elif fault=='identity':
        job.save(out/'seed_22/learner_identity.json',{});seal(out,p)
    elif fault=='runtime':monkeypatch.setattr(job,'runtime_versions',lambda:dict(changed=True))
    with pytest.raises(ValueError):job.validate_training_artifact(out,p,check_runtime=fault=='runtime')


@pytest.mark.parametrize('cancel',[False,True])
def test_slot_failure_or_cancel_closes_rest_and_keeps_consumed_ledger(tmp_path,monkeypatch,cancel):
    source,p=training_fixture(tmp_path)
    monkeypatch.setattr(job,'parent',lambda *a,**kw:source)
    monkeypatch.setattr(job,'protocol',lambda:p)
    monkeypatch.setattr(job,'runtime_versions',lambda:{})
    monkeypatch.setattr(job,'prepare_worlds',lambda out:dict(clear_box='world'))
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    called=[]
    def fail(out,condition,*args,**kwargs):
        called.append(condition)
        assert kwargs['evaluation_protocol']['training_episodes_per_seed_maximum']==1
        assert kwargs['verify_actor_unchanged']
        raise KeyboardInterrupt() if cancel else RuntimeError('retained acquisition failure')
    monkeypatch.setattr(job.correction,'evaluate_rollout',fail)
    root=tmp_path/'new_eval'
    with pytest.raises(KeyboardInterrupt if cancel else RuntimeError):job.run(root)
    assert called==[p['evaluation_order'][0]]
    state=job.read(root/'state.json');assert not state['latest'] and len(state['runs'])==1
    assert state['runs'][0]['status']==('cancelled' if cancel else 'failed')
    artifact=root/state['runs'][0]['path'];progress=job.read(artifact/'evaluation_progress.json')
    assert progress['failed_slot']==0 and progress['remaining_slots_closed'] and progress['runs']==[]
    with pytest.raises(ValueError,match='already consumed'):job.run(root)


def test_corrupt_ledger_never_reopens_job(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    (tmp_path/'state.json').write_text('corrupt')
    with pytest.raises(ValueError,match='already consumed'):job.run(tmp_path)


def test_ten_slots_keep_order_context_and_no_optimizer(tmp_path,monkeypatch):
    source,p=training_fixture(tmp_path)
    monkeypatch.setattr(job,'protocol',lambda:p)
    monkeypatch.setattr(job,'prepare_worlds',lambda out:dict(clear_box='world'))
    called=[]
    def rollout(out,condition,*args,**kwargs):
        called.append(condition)
        c,g,task,bc=kwargs['evaluation_config']
        assert c['purpose']==task['protocol_id']==p['protocol_id']
        assert c['backend']['max_episodes']==1 and task['command_until_s']==condition['source_stop_s']
        return dict(steps=140,actor_inference_calls=140 if condition['arm']=='TD3' else 0)
    monkeypatch.setattr(job.correction,'evaluate_rollout',rollout)
    result=job.execute(tmp_path,source)
    assert called==p['evaluation_order'] and result['evaluation_transitions']==1400
    assert result['optimizer_updates']==result['training_transitions']==0 and result['actor_inference_calls']==840
