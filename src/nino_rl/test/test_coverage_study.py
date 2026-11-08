"""Software fixtures only; new collection→adapter→reward→replay and job gates."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from nino_rl import residual_coverage_study as job


@pytest.mark.parametrize('arm',['A_gaussian','C_stratified_probes'])
def test_actual_collection_request_reward_replay_updates_and_checkpoint(tmp_path,arm):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    from nino_rl.coverage_td3 import build,CoverageTD3
    torch.set_num_threads(1)
    c,g,task,condition=job.configuration(8.)
    env=job.frozen.contract.environment(c,job.frozen.offline.fixture_backend(c,8.),task,condition)
    model=build(env,11,arm,job.frozen.protocol()['algorithm'])
    job.frozen.offline.zero_initialize_scalar(model)
    model.nino_coverage_identity=job.identity(arm,11)
    rows=[]
    class Trace(BaseCallback):
        def _on_step(self):
            info=self.locals['infos'][0];audit=deepcopy(model.nino_collection_audit)
            np.testing.assert_array_equal(self.locals['actions'][0],audit['requested_scalar'])
            np.testing.assert_array_equal(info['requested_scalar_action'],audit['requested_scalar'])
            assert info['equal_observation'][101]==float(audit['window_open'])
            rows.append(dict(info,collection=audit,done=bool(self.locals['dones'][0]),reward=float(self.locals['rewards'][0])))
            return True
    try:
        model.learn(total_timesteps=200,callback=Trace())
        assert (model._n_updates,model.nino_critic_optimizer_steps,model.nino_actor_optimizer_steps)==(136,136,68)
        result=job.checkpoint_check(model,tmp_path,rows,arm,11)
        assert result['replay']['rows_checked']==200
        probes=[r for r in rows if r['collection']['probe']]
        assert bool(probes)==(arm=='C_stratified_probes')
        for r in probes:
            assert r['plan_projection']['window_open']
            assert r['plan_projection']['windowed_common_m_s']==pytest.approx(.005*r['requested_scalar_action'][0])
        loaded=CoverageTD3.load(tmp_path/'model.zip',device='cpu')
        before=deepcopy(loaded.nino_sampler.__dict__)
        import pickle
        digest=pickle.dumps(before)
        for _ in range(8):loaded.predict(np.zeros(103,np.float32),deterministic=True)
        assert pickle.dumps(loaded.nino_sampler.__dict__)==digest
        # Imported checkpoints require this study's complete identity.
        with pytest.raises(ValueError,match='identity mismatch'):
            job.require_identity(job.frozen.identity(),arm,11)
    finally:env.close()


def test_release_guard_prevents_physics_and_does_not_consume_slot(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    monkeypatch.setattr(job,'execute',lambda *a:pytest.fail('Physics cannot start before release'))
    with pytest.raises(ValueError,match='not released'):job.run(tmp_path/'root',job.ACTION)
    assert not (tmp_path/'root/state.json').exists()


@pytest.mark.parametrize('cancel',[False,True])
def test_failure_or_cancel_closes_all_later_slots_and_retains_ledger(tmp_path,monkeypatch,cancel):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    src=tmp_path/'source';src.mkdir();job.save(src/'manifest.json',{})
    pre=tmp_path/'preflight';pre.mkdir();job.save(pre/'critic_reference_packets.json',[])
    monkeypatch.setattr(job,'source',lambda *a:src)
    monkeypatch.setattr(job,'release_ready',lambda *a:pre)
    monkeypatch.setattr(job,'fingerprint',lambda:'offline-test')
    calls=[]
    def fail(out,packets):
        calls.append(out);raise KeyboardInterrupt() if cancel else RuntimeError('retained fault')
    monkeypatch.setattr(job,'execute',fail)
    root=tmp_path/'new_study'
    with pytest.raises(KeyboardInterrupt if cancel else RuntimeError):job.run(root,job.ACTION)
    d=job.read(root/'state.json');row=d['runs'][-1]
    assert len(calls)==1 and row['status']==('cancelled' if cancel else 'failed') and d['latest']=={}
    out=root/row['path'];assert job.read(out/'manifest.json')['status']==row['status']
    with pytest.raises(ValueError,match='already consumed'):job.run(root,job.ACTION)


def test_corrupt_ledger_fails_before_release_or_source(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    (tmp_path/'state.json').write_text('broken')
    monkeypatch.setattr(job,'source',lambda:pytest.fail('Invalid ledger must fail first'))
    with pytest.raises(ValueError):job.run(tmp_path,job.ACTION)


def test_fixed_packets_are_selected_before_new_training(tmp_path):
    for slot,stop in ((0,6.),(7,8.)):
        d=tmp_path/f'eval_{slot:02d}';d.mkdir()
        rows=[dict(qualification_condition=dict(arm='B0',source_stop_s=stop),
            equal_observation=[0.]*101+[1.,0.]) for _ in range(30)]
        (d/'trace.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    packets=job.reference_packets(tmp_path)
    assert len(packets)==20 and len({(p['slot'],p['decision_index']) for p in packets})==20
    assert packets[0]['decision_index']==0 and packets[9]['decision_index']==29


@pytest.mark.parametrize('fault_at',[0,3])
def test_training_failure_never_starts_eval(tmp_path,monkeypatch,fault_at):
    monkeypatch.setattr(job.frozen,'prepare_worlds',lambda out:dict(clear_box='unused'))
    calls=[]
    def train(*args,**kwargs):
        calls.append(args[1:3])
        if len(calls)==fault_at+1:raise RuntimeError('training stopped')
        return dict(seed=args[2],initial_policy={'hash':'same'})
    monkeypatch.setattr(job,'train_learner',train)
    monkeypatch.setattr(job,'evaluate',lambda *a:pytest.fail('Evaluation after incomplete learners'))
    with pytest.raises(RuntimeError):job.execute(tmp_path,[])
    assert len(calls)==fault_at+1 and job.read(tmp_path/'study_progress.json')['remaining_slots_closed']


def test_study_identity_differs_by_arm_and_seed():
    assert job.identity('A_gaussian',11)!=job.identity('C_stratified_probes',11)
    assert job.identity('A_gaussian',11)!=job.identity('A_gaussian',22)
    assert job.frozen.fingerprint()==job.protocol()['parent']['learner_fingerprint']


@pytest.mark.parametrize('arm',['B0','Classical_scheduled','A_gaussian','C_stratified_probes'])
def test_each_eval_arm_checks_namespace_then_140_steps_without_sampling(tmp_path,monkeypatch,arm):
    import torch
    from nino_rl.coverage_td3 import CoverageTD3
    instances=[];events=[]
    class Lifecycle:
        def __init__(self,c,directory,*args):
            self.directory=directory;directory.mkdir();self.namespace=None;self.current=None;instances.append(self)
        def close(self):events.append('close')
    class Env:
        def reset(self,**kwargs):
            instances[-1].namespace='episode_0';instances[-1].current=object()
            events.append('reset');return np.zeros(103,np.float32),{}
        def step(self,action):
            assert instances[-1].namespace=='episode_0'
            events.append('step');n=events.count('step')
            return np.zeros(103,np.float32),0.,n==140,False,dict(sensor_clock_s=n*.1,task=dict(elapsed_s=n*.1))
        def close(self):instances[-1].close()
    monkeypatch.setattr(job,'EpisodeLifecycle',Lifecycle)
    monkeypatch.setattr(job.frozen.contract,'environment',lambda *a:Env())
    monkeypatch.setattr(job.frozen.qualified,'verify_transition',lambda *a:None)
    monkeypatch.setattr(job.frozen,'feasibility',lambda *a:None)
    monkeypatch.setattr(job.frozen.baseline,'summarize',lambda rows,path:dict(steps=len(rows),functional_proposal_pass=True))
    monkeypatch.setattr(job.frozen.timing,'timestamp_diagnostic',lambda *a:dict(valid=True))
    condition=dict(arm=arm,source_stop_s=6.)
    checkpoints={}
    if arm in job.protocol()['arms']:
        condition['seed']=11;checkpoints[(arm,11)]=tmp_path
        actor=SimpleNamespace(policy=torch.nn.Linear(103,1),num_timesteps=1024,_n_updates=960,
            nino_sampler=SimpleNamespace(decisions=1024),nino_coverage_identity=job.identity(arm,11),
            predict=lambda obs,deterministic:(np.zeros(1,np.float32),None))
        monkeypatch.setattr(CoverageTD3,'load',lambda *a,**kw:actor)
    result=job.evaluate(tmp_path/'eval',condition,'unused',checkpoints)
    assert events==['reset']+['step']*140+['close']
    assert result['actor_unchanged'] and result['exploration_unchanged'] and result['probes_during_evaluation']==0
    assert len((tmp_path/'eval/trace.jsonl').read_text().splitlines())==140


def test_full_matrix_uses_measured_counts_and_initialization_pairing(tmp_path,monkeypatch):
    monkeypatch.setattr(job.frozen,'prepare_worlds',lambda out:dict(clear_box='unused'))
    calls=[]
    def train(out,arm,seed,world,slot,expected_initial=None):
        calls.append((arm,seed));out.mkdir();(out/'model.zip').write_bytes(b'fixture')
        same=[r for r in calls[:-1] if r[1]==seed]
        assert (expected_initial is not None)==bool(same)
        return dict(arm=arm,seed=seed,initial_policy={'same':seed},training_transitions=1024,
            critic_updates=960,actor_updates=480,episodes_launched=8)
    evaluations=[]
    def evaluate(out,condition,*args):
        evaluations.append(condition);return dict(steps=140)
    monkeypatch.setattr(job,'train_learner',train);monkeypatch.setattr(job,'evaluate',evaluate)
    monkeypatch.setattr(job,'critic_audit',lambda *a:[])
    monkeypatch.setattr(job,'compare',lambda *a:dict(decision='fixture_only'))
    result=job.execute(tmp_path,[])
    assert calls==[(r['arm'],r['seed']) for r in job.protocol()['training_order']]
    assert evaluations==job.protocol()['evaluation_order']
    assert (result['training_transitions'],result['evaluation_transitions'],result['critic_updates'],
        result['actor_updates'],result['gazebo_launches'])==(6144,2240,5760,2880,64)


def test_loss_budget_rule_cannot_be_silently_replaced():
    from nino_rl.coverage_study_plan import validate
    p=deepcopy(job.protocol());p['decision']['minimum_relative_benefit_proposed']=.01
    with pytest.raises(ValueError,match='Decision/gate'):validate(p)


def test_full_snapshot_detects_optimizer_change_without_policy_or_counter_change():
    import torch
    policy=torch.nn.Linear(103,1)
    optimizer=torch.optim.Adam(policy.parameters())
    actor=SimpleNamespace(policy=policy,num_timesteps=0,_n_updates=0,
        actor=SimpleNamespace(optimizer=optimizer),critic=SimpleNamespace(optimizer=optimizer))
    before=job.full_snapshot(actor)
    optimizer.param_groups[0]['lr']=.00123
    assert job.evaluator.actor_snapshot(actor)=={k:before[k] for k in ('policy_sha256','num_timesteps','critic_updates')}
    assert job.full_snapshot(actor)!=before


@pytest.mark.parametrize('quality,expected',[
    ('benefit','candidate_for_separate_holdout'),('small','unknown_small_effect'),
    ('worse','no_go_expand_td3_clear_known_stop'),('grid','unknown_coverage_or_grid'),
    ('coverage','unknown_coverage_or_grid'),('weak','unknown_weak_coverage_contrast')])
def test_decision_separates_candidate_unknown_and_no_go(quality,expected):
    runs=[]
    for condition in job.protocol()['evaluation_order']:
        arm=condition['arm']
        v=1.2 if arm=='B0' else 1.1 if arm=='A_gaussian' else 1. if arm=='Classical_scheduled' else .94
        if arm=='C_stratified_probes' and quality=='small':v=.98
        if arm=='C_stratified_probes' and quality=='worse':v=1.02
        gt=1.02 if arm=='C_stratified_probes' and quality=='grid' else v
        runs.append(dict(evaluation_condition=condition,nominal_velocity_rmse_m_s=v,
            timestamp_diagnostic=dict(header_grid={'0.0':dict(rmse_m_s=gt),'0.01':dict(rmse_m_s=gt)})))
    trained=[dict(arm=arm,seed=seed,coverage=dict(coverage_proposal_pass=(
        quality=='weak' if arm=='A_gaussian' else quality!='coverage'))) for arm in job.protocol()['arms'] for seed in (11,22,33)]
    result=job.compare(runs,trained)
    assert result['decision']==expected and not result['benefit_verified']
