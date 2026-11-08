"""Bounded coverage study and offline preflight; physics requires a pinned release."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time
import numpy as np
from . import coverage_study_plan_v2 as plan
from .coverage_qualification_adapter import QualifiedBackend
from . import residual_coverage_study as failed_v1
from . import residual_reliable_td3 as frozen
from . import residual_reliable_eval_only as prior_eval
from . import residual_reliable_evaluation as evaluator
from .reliable_episode import EpisodeLifecycle
from .residual_workflow import save, emit, latest, runtime_versions
from .residual_experiment import source_fingerprint

PREFLIGHT, ACTION = 'sim-coverage-v2-preflight', 'sim-coverage-v2-study'
PARENT_ROOT = Path.home() / 'nino_research/sim_reliable_eval_only_v1'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return prior_eval.sha(path)


def protocol():
    return plan.load()


def fingerprint():
    base = frozen.repo()
    files = ["nino_rl/coverage_study_plan_v2.py", "nino_rl/residual_coverage_study_v2.py",
             "nino_rl/coverage_qualification_adapter.py", "config/residual_coverage_study_v2.json",
             "scripts/residual_coverage_study_v2.sh", "test/test_coverage_study_v2.py",
             "test/test_coverage_qualification_adapter.py", "test/test_coverage_v2_integration.py",
             "test/fixtures/coverage_first_tick_failure_v1.json"]
    return hashlib.sha256(json.dumps(dict(previous=failed_v1.fingerprint(), learner=frozen.fingerprint(),
        evaluator=prior_eval.fingerprint(), files={f:sha(base/'src/nino_rl'/f) for f in files}),
        sort_keys=True).encode()).hexdigest()


def source(check_runtime=True):
    p = protocol()
    if failed_v1.fingerprint() != p["revision"]["previous_fingerprint"]:
        raise ValueError("Historical V1 sources changed")
    failed = Path.home()/'nino_research/sim_coverage_study_v1/20261106T103952320046Z_sim-coverage-study'
    if sha(failed/'manifest.json') != p['revision']['failed_manifest_sha256']:
        raise ValueError('Historical failure manifest changed')
    manifest=read(failed/'manifest.json')
    if manifest['status']!='failed' or manifest['coverage_fingerprint']!=failed_v1.fingerprint():
        raise ValueError('Historical failure identity changed')
    for name,expected in manifest['files'].items():
        path=(failed/name).resolve()
        if not path.is_relative_to(failed.resolve()) or sha(path)!=expected:
            raise ValueError('Historical failure artifact changed')
    if (frozen.fingerprint() != p['parent']['learner_fingerprint']
            or frozen.contract.identity()['abi_sha256'] != p['parent']['controller_abi_sha256']):
        raise ValueError('Frozen learner/controller changed')
    out = prior_eval.validated_latest(PARENT_ROOT, check_runtime=check_runtime)
    if sha(out/'manifest.json') != p['parent']['evaluation_manifest_sha256']:
        raise ValueError('Pinned evaluation manifest changed')
    return out


def identity(arm, seed):
    if arm not in protocol()['arms'] or seed not in protocol()['seeds']:
        raise ValueError('Undeclared learner')
    return dict(protocol_id=protocol()['protocol_id'], fingerprint=fingerprint(), arm=arm, seed=seed,
        controller_abi_sha256=frozen.contract.identity()['abi_sha256'], observation_size=103,
        action_size=1, history_frames=5, replay_action='actual_request_after_probe_before_projection',
        hardware_authorized=False, resume_allowed=False)


def require_identity(actual, arm, seed):
    if actual != identity(arm, seed):
        raise ValueError('Coverage learner identity mismatch; resume/foreign checkpoints rejected')


def lifecycle_protocol(evaluation=False):
    p = deepcopy(frozen.protocol())
    p['protocol_id'] = protocol()['protocol_id']
    p['training_episodes_per_seed_maximum'] = 1 if evaluation else 8
    return p


def configuration(stop):
    c, g, task, condition = frozen.configuration(stop)
    c['purpose'] = task['protocol_id'] = protocol()['protocol_id']
    c['backend'].update(scenario_id='clear_box_coverage_v2', max_episodes=1)
    return c, g, task, condition


def reference_packets(source_path):
    packets = []
    for slot, stop in ((0, 6.), (7, 8.)):
        trace = source_path/f'eval_{slot:02d}/trace.jsonl'
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        candidates = [i for i, row in enumerate(rows) if row['equal_observation'][101] == 1.]
        if len(candidates) < 10 or any(r['qualification_condition'] != dict(arm='B0', source_stop_s=stop) for r in rows):
            raise ValueError('Fixed B0 reference packets unavailable')
        for i in np.linspace(0, len(candidates)-1, 10, dtype=int):
            index = candidates[i]
            packets.append(dict(slot=slot, stop_s=stop, decision_index=index,
                trace_sha256=sha(trace), observation=rows[index]['equal_observation']))
    return packets


def training_environment(backend, out, arm, seed):
    import gymnasium as gym
    backend = QualifiedBackend(backend, arm, seed)
    abi_sha256=frozen.protocol()['abi_sha256']
    class Environment(gym.Env):
        observation_space = gym.spaces.Box(-5., 5., (103,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)
        def __init__(self):
            self.rows, self.resets, self.episode_rows = [], [], []
            self.episode, self.inner, self.epoch, self.model = -1, None, None, None
        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            self.episode += 1
            if self.episode >= 8:
                raise ValueError('Eight training launches exhausted')
            c, _, task, condition = configuration((6., 8.)[self.episode % 2])
            backend.config, backend.protocol, backend.condition = deepcopy(c), deepcopy(task), deepcopy(condition)
            self.inner = frozen.contract.environment(c, backend, task, condition)
            obs, info = self.inner.reset(seed=seed)
            if not backend.namespace or backend.current is None:
                raise ValueError('Fresh namespace required before first step')
            self.episode_rows, self.epoch = [], None
            self.resets.append(dict(episode=self.episode, stop_s=task['command_until_s'], reset=info))
            save(out/'resets.json', self.resets)
            save(out/f'episode_{self.episode}_config.json', dict(config=c, task=task, condition=condition))
            return obs, info
        def step(self, action):
            if len(self.rows) >= 1024 or self.model is None:
                raise ValueError('Missing collector or exhausted transition budget')
            audit = deepcopy(self.model.nino_collection_audit)
            if audit['timestep'] != len(self.rows)+1:
                raise ValueError('Collector/step audit not aligned')
            np.testing.assert_array_equal(action, np.asarray(audit['requested_scalar'], np.float32))
            frozen.append(out/'control_attempts.jsonl', dict(episode=self.episode, collection=audit,
                requested=np.asarray(action).tolist(), namespace=backend.namespace))
            obs, reward, term, trunc, info = self.inner.step(action)
            row = dict(step=len(self.episode_rows), episode=self.episode, timestep=len(self.rows)+1,
                learner_arm=arm, learner_seed=seed, collection=audit, reward=reward,
                terminated=term, truncated=trunc, done=bool(term or trunc), **info,
                episode_namespace=backend.namespace)
            row['TimeLimit.truncated'] = bool(trunc and not term)
            frozen.append(out/'training_trace.jsonl', row)
            np.testing.assert_array_equal(row['requested_scalar_action'], audit['requested_scalar'])
            if row['equal_observation'][101] != float(audit['window_open']):
                raise ValueError('Probe eligibility differs from causal decision observation')
            self.epoch = self.epoch if self.epoch is not None else row['sensor_clock_s']-row['task']['elapsed_s']
            frozen.qualified.verify_transition(row, self.episode_rows[-1] if self.episode_rows else None,
                self.epoch, abi_sha256)
            frozen.feasibility(row, .04)
            self.rows.append(row);self.episode_rows.append(row)
            if term:
                backend.current.flush_raw()
                target = backend.directory/backend.namespace
                summary = frozen.baseline.summarize(self.episode_rows, target)
                diagnostic = frozen.timing.timestamp_diagnostic(target, self.episode_rows)
                save(target/'completed_episode_metrics.json', dict(summary, timestamp_diagnostic=diagnostic))
                if len(self.episode_rows) != 140 or not summary['functional_proposal_pass'] or not diagnostic['valid']:
                    raise ValueError('Training task/measurement failure before auto reset')
            return obs, reward, term, trunc, info
        def close(self):
            backend.close()
    return Environment()


def tensor_tree_equal(a, b):
    import torch
    if isinstance(a, torch.Tensor):
        return isinstance(b, torch.Tensor) and torch.equal(a, b) and bool(torch.isfinite(a).all())
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(tensor_tree_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(tensor_tree_equal(x, y) for x, y in zip(a, b))
    return a == b


def full_snapshot(model):
    """Include optimizer internals as well as policy/targets and counters."""
    import torch
    digest=hashlib.sha256()
    def visit(value):
        if isinstance(value,torch.Tensor):
            if not torch.isfinite(value).all():raise ValueError('Nonfinite optimizer state')
            digest.update(str((str(value.dtype),tuple(value.shape))).encode())
            digest.update(value.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(value,dict):
            for key in sorted(value,key=str):digest.update(repr(key).encode());visit(value[key])
        elif isinstance(value,(list,tuple)):
            for item in value:visit(item)
        else:digest.update(repr(value).encode())
    for name in ('actor','critic'):
        network=getattr(model,name,None)
        visit(network.optimizer.state_dict() if network is not None else None)
    return dict(evaluator.actor_snapshot(model),optimizer_sha256=digest.hexdigest(),
        actor_optimizer_steps=getattr(model,'nino_actor_optimizer_steps',0),
        critic_optimizer_steps=getattr(model,'nino_critic_optimizer_steps',0))


def checkpoint_check(model, out, rows, arm, seed):
    from .coverage_td3 import CoverageTD3
    model.save(out/'model.zip');model.save_replay_buffer(out/'replay_buffer.pkl')
    loaded = CoverageTD3.load(out/'model.zip', device='cpu')
    loaded.load_replay_buffer(out/'replay_buffer.pkl')
    require_identity(loaded.nino_coverage_identity, arm, seed)
    if (full_snapshot(loaded) != full_snapshot(model)
            or loaded.nino_actor_optimizer_steps != model.nino_actor_optimizer_steps
            or loaded.nino_critic_optimizer_steps != model.nino_critic_optimizer_steps):
        raise ValueError('Checkpoint targets/counters changed')
    for name in ('actor', 'critic'):
        if not tensor_tree_equal(getattr(model, name).optimizer.state_dict(), getattr(loaded, name).optimizer.state_dict()):
            raise ValueError('Optimizer checkpoint mismatch/nonfinite')
    replay = frozen.contract.audit_replay(loaded.replay_buffer, rows)
    for row in rows[::43]:
        obs = np.asarray(row['equal_observation'], np.float32)
        np.testing.assert_array_equal(model.predict(obs, deterministic=True)[0], loaded.predict(obs, deterministic=True)[0])
    return dict(replay=replay, model_optimizer_target_replay_parity=True, resume_allowed=False)


def coverage_summary(rows):
    selected = [r for r in rows if r['equal_observation'][101] == 1.]
    values = [r['requested_scalar_action'][0] for r in selected]
    counts = np.histogram(values, [-1., -.5, 0., .5, 1.])[0].tolist()
    fractions = [n/len(selected) if selected else 0. for n in counts]
    return dict(open_samples=len(selected), bin_counts=counts, bin_fractions=fractions,
        probes=sum(r.get('collection', {}).get('probe', False) for r in selected),
        coverage_proposal_pass=all(n >= 10 and f >= .05 for n, f in zip(counts, fractions)),
        post_warmup_bin_counts=np.histogram([r['requested_scalar_action'][0] for r in selected
            if not r.get('collection', {}).get('warmup', True)], [-1., -.5, 0., .5, 1.])[0].tolist(),
        requested=[r['requested_scalar_action'][0] for r in selected],
        windowed_common_m_s=[r['plan_projection']['windowed_common_m_s'] for r in selected],
        accepted_reference=[r['final_ros_reference'] for r in selected])


def train_learner(out, arm, seed, world, slot, expected_initial=None):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    from .coverage_td3 import build
    out.mkdir()
    c, g, task, condition = configuration(6.)
    backend = EpisodeLifecycle(c, out/'episodes', world, g, task, condition, lifecycle_protocol())
    env = training_environment(backend, out, arm, seed)
    model,error = None,None
    try:
        model = build(env, seed, arm, frozen.protocol()['algorithm'])
        frozen.offline.zero_initialize_scalar(model)
        model.nino_coverage_identity = identity(arm, seed)
        env.model = model
        initial = evaluator.actor_snapshot(model)
        save(out/'initial_policy.json', initial);save(out/'learner_identity.json', model.nino_coverage_identity)
        if expected_initial is not None and initial != expected_initial:
            raise ValueError('Same-seed initial policies differ before learning')
        class Trace(BaseCallback):
            def _on_step(self):
                np.testing.assert_array_equal(self.locals['actions'][0], env.rows[-1]['requested_scalar_action'])
                for value in self.model.policy.state_dict().values():
                    if not torch.isfinite(value).all():
                        raise ValueError('Nonfinite policy/target')
                losses={k:float(v) for k,v in self.model.logger.name_to_value.items()
                        if k in ('train/actor_loss','train/critic_loss')}
                if not all(math.isfinite(v) for v in losses.values()):raise ValueError('Nonfinite learner loss')
                if self.num_timesteps % 64 == 0:
                    progress = dict(arm=arm, seed=seed, transitions=self.num_timesteps,
                        critic_updates=getattr(self.model, 'nino_critic_optimizer_steps', 0),
                        actor_updates=getattr(self.model, 'nino_actor_optimizer_steps', 0),losses=losses)
                    frozen.append(out/'learning_progress.jsonl', progress)
                    emit(ACTION, f'{arm} seed{seed}: {self.num_timesteps}/1024',
                        (slot*1024+self.num_timesteps)/8384, learner=progress)
                return True
        model.learn(total_timesteps=1024, callback=Trace())
        if (len(env.rows), model.num_timesteps, model._n_updates,
            model.nino_critic_optimizer_steps, model.nino_actor_optimizer_steps) != (1024, 1024, 960, 960, 480):
            raise ValueError('Exact transition/actual optimizer budget mismatch')
        result = dict(arm=arm, seed=seed, training_transitions=1024, critic_updates=960,
            actor_updates=480, episodes_launched=len(env.resets), initial_policy=initial,
            full_task_terminals=sum(r['done'] for r in env.rows), final_segment_steps=len(env.episode_rows),
            final_segment_right_censored=not env.rows[-1]['done'], coverage=coverage_summary(env.rows),
            **checkpoint_check(model, out, env.rows, arm, seed))
        save(out/'training_result.json', result)
        return result
    except BaseException as exc:
        error=exc
        if model is not None:
            try:
                model.save(out/'partial_model_failed.zip');model.save_replay_buffer(out/'partial_replay_failed.pkl')
            except BaseException as dump_error:
                save(out/'partial_save_failure.json',dict(original=repr(exc),error=repr(dump_error)))
        raise
    finally:
        try:env.close()
        except BaseException as cleanup:
            save(out/'cleanup_failure.json',dict(error=repr(cleanup),original=repr(error)))
            if error is None:raise


def evaluate(out, condition, world, checkpoints):
    out.mkdir()
    arm, seed = condition['arm'], condition.get('seed')
    c, g, task, bc = configuration(condition['source_stop_s'])
    actor = None
    if arm in protocol()['arms']:
        from .coverage_td3 import CoverageTD3
        actor = CoverageTD3.load(checkpoints[(arm, seed)]/'model.zip', device='cpu')
        require_identity(actor.nino_coverage_identity, arm, seed)
    before = full_snapshot(actor) if actor is not None else None
    sampler_before = deepcopy(actor.nino_sampler.__dict__) if actor is not None else None
    # Hash the sampler via pickle rather than comparing Generator objects.
    import pickle
    sampler_before = hashlib.sha256(pickle.dumps(sampler_before)).hexdigest()
    p=lifecycle_protocol(True)
    backend = EpisodeLifecycle(c, out/'episodes', world, g, task, bc, p)
    env = frozen.contract.environment(c, backend, task, bc)
    rows, epoch, error = [], None, None
    save(out/'config.json', dict(config=c, guidance=g, task=task, condition=condition))
    try:
        obs, info = env.reset(seed=701);save(out/'reset.json', info)
        if not backend.namespace or backend.current is None:
            raise ValueError('Fresh evaluation namespace required')
        for step in range(140):
            request = (actor.predict(obs, deterministic=True)[0] if actor is not None else
                frozen.contract.classical_request(obs) if arm == 'Classical_scheduled' else np.zeros(1, np.float32))
            frozen.append(out/'control_attempts.jsonl', dict(step=step, requested=np.asarray(request).tolist()))
            obs, reward, term, trunc, info = env.step(request)
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc, done=bool(term or trunc),
                **info, qualification_condition=condition, episode_namespace=backend.namespace)
            row['TimeLimit.truncated'] = bool(trunc and not term)
            frozen.append(out/'trace.jsonl', row)
            epoch = epoch if epoch is not None else row['sensor_clock_s']-row['task']['elapsed_s']
            frozen.qualified.verify_transition(row, rows[-1] if rows else None, epoch, p['abi_sha256'])
            frozen.feasibility(row, .04);rows.append(row)
            if term or trunc:
                break
    except BaseException as exc:
        error = exc;save(out/'failure.json', dict(error=repr(exc), valid_rows=len(rows)));raise
    finally:
        try:env.close()
        except BaseException as exc:
            save(out/'cleanup_failure.json', dict(error=repr(exc), original=repr(error)))
            if error is None:raise
    after = full_snapshot(actor) if actor is not None else None
    sampler_after = hashlib.sha256(pickle.dumps(actor.nino_sampler.__dict__ if actor is not None else None)).hexdigest()
    if before != after or sampler_before != sampler_after:
        raise ValueError('Evaluation changed policy/targets/counters or exploration state')
    target = backend.directory/backend.namespace
    result = frozen.baseline.summarize(rows, target)
    diagnostic = frozen.timing.timestamp_diagnostic(target, rows)
    result.update(evaluation_condition=condition, timestamp_diagnostic=diagnostic,
        actor_unchanged=before == after, exploration_unchanged=True, probes_during_evaluation=0,
        optimizer_updates_in_job=0)
    save(out/'summary.json', result)
    if len(rows) != 140 or not result['functional_proposal_pass'] or not diagnostic['valid']:
        raise ValueError('Evaluation task/measurement failure')
    return result


def critic_audit(checkpoints, packets):
    import torch
    from .coverage_td3 import CoverageTD3
    result = []
    for (arm, seed), path in checkpoints.items():
        model = CoverageTD3.load(path/'model.zip', device='cpu')
        require_identity(model.nino_coverage_identity, arm, seed)
        before = full_snapshot(model)
        groups = [('fixed_B0', packets)]
        own = []
        # Own-policy packets are pinned by the same deterministic selection rule.
        for trace in sorted(path.parent.glob('eval_*/trace.jsonl')):
            rr = [json.loads(line) for line in trace.read_text().splitlines()]
            if rr and rr[0]['qualification_condition'].get('arm') == arm and rr[0]['qualification_condition'].get('seed') == seed:
                eligible = [r for r in rr if r['equal_observation'][101] == 1.]
                if len(eligible) < 10:raise ValueError('Insufficient own-policy critic packets')
                own.extend(dict(observation=eligible[i]['equal_observation']) for i in np.linspace(0,len(eligible)-1,10,dtype=int))
        if len(own) != 20:raise ValueError('Twenty own-policy packets required')
        groups.append(('own_policy', own))
        audits = {}
        with torch.no_grad():
            for label, selected in groups:
                obs = np.asarray([p['observation'] for p in selected], np.float32)
                actions = np.tile(np.array([-1., -.5, 0., .5, 1.], np.float32), (len(obs),1))
                repeated = torch.as_tensor(np.repeat(obs,5,axis=0))
                q1,q2 = model.critic(repeated,torch.as_tensor(actions.reshape(-1,1)))
                q1,q2=q1.reshape(-1,5),q2.reshape(-1,5)
                actor_action=model.predict(obs,deterministic=True)[0]
                actor_q1,_=model.critic(torch.as_tensor(obs),torch.as_tensor(actor_action))
                audits[label] = dict(observations=obs.tolist(), grid=[-1.,-.5,0.,.5,1.],
                    q1=q1.tolist(),q2=q2.tolist(),minimum_q=torch.minimum(q1,q2).tolist(),
                    q1_argmax=q1.argmax(dim=1).tolist(),min_q_argmax=torch.minimum(q1,q2).argmax(dim=1).tolist(),
                    mean_abs_critic_disagreement=float((q1-q2).abs().mean()),
                    grid_max_q1_minus_actor_q1=(q1.max(dim=1).values-actor_q1.flatten()).tolist(),
                    actor=actor_action.reshape(-1).tolist())
        if full_snapshot(model) != before:raise ValueError('Critic audit modified model')
        result.append(dict(arm=arm,seed=seed,unchanged=True,groups=audits))
    return result


def compare(runs, trained):
    def metrics(r):
        grid=r['timestamp_diagnostic']['header_grid']
        return np.array([r['nominal_velocity_rmse_m_s'],grid['0.0']['rmse_m_s'],grid['0.01']['rmse_m_s']])
    indexed={(r['evaluation_condition']['arm'],r['evaluation_condition'].get('seed'),r['evaluation_condition']['source_stop_s']):r for r in runs}
    pairs=[]
    for seed in (11,22,33):
        for stop in (6.,8.):
            c=metrics(indexed[('C_stratified_probes',seed,stop)])
            a=metrics(indexed[('A_gaussian',seed,stop)])
            classical=metrics(indexed[('Classical_scheduled',None,stop)])
            b0=metrics(indexed[('B0',None,stop)])
            pairs.append(dict(seed=seed,stop_s=stop,C=c.tolist(),A=a.tolist(),classical=classical.tolist(),B0=b0.tolist(),
                relative_C_vs_A=((c-a)/a).tolist() if np.all(a>0) else None,
                relative_C_vs_classical=((c-classical)/classical).tolist() if np.all(classical>0) else None,
                relative_C_vs_B0=((c-b0)/b0).tolist() if np.all(b0>0) else None))
    if any(r['relative_C_vs_A'] is None or r['relative_C_vs_classical'] is None for r in pairs):
        return dict(decision='unknown_zero_denominator',pairs=pairs,benefit_verified=False)
    ca=np.array([r['relative_C_vs_A'] for r in pairs]).reshape(3,2,3).mean(axis=1)
    cc=np.array([r['relative_C_vs_classical'] for r in pairs]).reshape(3,2,3)
    coverage=all(r['coverage']['coverage_proposal_pass'] for r in trained if r['arm']=='C_stratified_probes')
    candidate=bool(coverage and np.all(ca.mean(axis=0)<0) and np.all(cc.mean(axis=(0,1))<=-.05)
        and sum(np.all(cc[i]<0) for i in range(3))>=2 and np.all(cc<=.05))
    grid_sensitive=any((np.any(np.array(r['relative_C_vs_classical'])<0) and
                        np.any(np.array(r['relative_C_vs_classical'])>0)) for r in pairs)
    control_already_covered=all(r['coverage']['coverage_proposal_pass'] for r in trained if r['arm']=='A_gaussian')
    decision=('unknown_weak_coverage_contrast' if control_already_covered else
              'candidate_for_separate_holdout' if candidate else
              'unknown_coverage_or_grid' if not coverage or grid_sensitive else
              'no_go_expand_td3_clear_known_stop' if np.all(cc.mean(axis=(0,1))>=0) else
              'unknown_small_effect')
    return dict(decision=decision,pairs=pairs,per_seed_C_vs_A=ca.tolist(),
        mean_C_vs_A=ca.mean(axis=0).tolist(),mean_C_vs_classical=cc.mean(axis=(0,1)).tolist(),
        coverage_proposal_pass=coverage,criterion_proposed_not_application_accepted=True,benefit_verified=False)


def execute(out, packets):
    import torch
    torch.set_num_threads(1)
    worlds = frozen.prepare_worlds(out)
    p=protocol();trained,runs,checkpoints=[],[],{}
    progress=dict(training=trained,runs=runs,remaining_slots_closed=False)
    try:
        for i, cell in enumerate(p['training_order']):
            target=out/f"{cell['arm']}_seed_{cell['seed']}"
            emit(ACTION,f'Train {i+1}/6: {cell}',i*1024/8384)
            same=[r for r in trained if r['seed']==cell['seed']]
            result=train_learner(target,cell['arm'],cell['seed'],worlds['clear_box'],i,
                expected_initial=same[0]['initial_policy'] if same else None)
            trained.append(result);checkpoints[(cell['arm'],cell['seed'])]=target
            same=[r for r in trained if r['seed']==cell['seed']]
            if len(same)==2 and same[0]['initial_policy']!=same[1]['initial_policy']:
                raise ValueError('Same-seed initial policies differ between arms')
            save(out/'study_progress.json',progress)
        checkpoint_hashes={str(path/'model.zip'):sha(path/'model.zip') for path in checkpoints.values()}
        for i,cell in enumerate(p['evaluation_order']):
            emit(ACTION,f'Eval {i+1}/16: {cell}',(6144+i*140)/8384)
            runs.append(evaluate(out/f'eval_{i:02d}',cell,worlds['clear_box'],checkpoints))
            save(out/'study_progress.json',progress)
        for path,expected in checkpoint_hashes.items():
            if sha(path)!=expected:raise ValueError('Checkpoint changed during evaluation')
        save(out/'critic_audit.json',critic_audit(checkpoints,packets))
        counts=dict(training_transitions=sum(r['training_transitions'] for r in trained),
            evaluation_transitions=sum(r['steps'] for r in runs),critic_updates=sum(r['critic_updates'] for r in trained),
            actor_updates=sum(r['actor_updates'] for r in trained),gazebo_launches=sum(r['episodes_launched'] for r in trained)+len(runs))
        if counts!=dict(training_transitions=6144,evaluation_transitions=2240,critic_updates=5760,actor_updates=2880,gazebo_launches=64):
            raise ValueError('Measured study budget does not match protocol')
        result=dict(progress,study_completed=True,comparison=compare(runs,trained),**counts,
            hardware_actions=0,benefit_verified=False,remaining_slots_closed=True)
        save(out/'study_result.json',result)
        return result
    except BaseException as exc:
        save(out/'study_progress.json',dict(progress,error=repr(exc),remaining_slots_closed=True))
        raise


def release_record():
    return read(frozen.repo()/'src/nino_rl/config/residual_coverage_release_v2.json')


def release_ready(root, check_runtime=False):
    r=release_record()
    if (r['released'] is not True or r['research_effect_rule_reviewed'] is not True
            or r['hardware_authorized'] is not False or r['protocol_id']!=protocol()['protocol_id']
            or r['scope']!='sim_only_one_attempt_6144_train_2240_eval'
            or r['implementation_fingerprint']!=fingerprint()):
        raise ValueError('Coverage study not released; offline preflight only')
    pre=validated_latest(root,PREFLIGHT,check_runtime=check_runtime)
    if sha(pre/'manifest.json')!=r['preflight_manifest_sha256']:
        raise ValueError('Release does not pin the current preflight')
    return pre


def validated_latest(root, action, check_runtime=True):
    out=latest(root,action,check_runtime=check_runtime)
    m=read(out/'manifest.json')
    if m.get('coverage_fingerprint')!=fingerprint():raise ValueError('Coverage sources changed')
    src=source(check_runtime)
    if read(out/'dependencies.json')!=dict(artifact=str(src),manifest_sha256=sha(src/'manifest.json')):
        raise ValueError('Coverage dependency changed')
    return out


def offline_preflight(out, src):
    tests=[frozen.repo()/'src/nino_rl/test'/f for f in ('test_coverage_study_plan.py','test_coverage_sampling.py','test_coverage_study.py',
        'test_coverage_qualification_adapter.py','test_coverage_study_v2.py','test_coverage_v2_integration.py')]
    with (out/'software_tests.log').open('w') as log:
        done=subprocess.run([sys.executable,'-m','pytest',*[str(t) for t in tests],'-q',f'--junitxml={out / "tests.xml"}'],
            stdout=log,stderr=subprocess.STDOUT,timeout=240,check=False)
    if done.returncode:raise ValueError('Offline preflight tests failed; see software_tests.log')
    import xml.etree.ElementTree as ET
    suites=list(ET.parse(out/'tests.xml').getroot().iter('testsuite'))
    if not suites or any(int(s.get(k,'0')) for s in suites for k in ('failures','errors','skipped')):
        raise ValueError('Preflight requires executed, passing tests without skips')
    tests_passed=sum(int(s.get('tests','0')) for s in suites)
    packets=reference_packets(src)
    save(out/'critic_reference_packets.json',packets)
    result=dict(passed=True,ready_for_physics=False,release_required=True,fingerprint=fingerprint(),
        critic_reference_packets=len(packets),new_scientific_training_transitions=0,
        new_physics_transitions=0,hardware_actions=0,
        software_tests_passed=tests_passed,
        integration_scope='actual_train_learner_1024_each_arm_real_validator_reset6_8_terminal_replay_checkpoint',
        integration_plant='balanced_synthetic_fixture_not_gazebo_or_sensor_validation',
        software_fixture_optimizer_updates_are_not_scientific_training=True)
    save(out/'preflight_result.json',result)
    return result


def run(root, action):
    if action not in (PREFLIGHT,ACTION):raise ValueError('Unknown action')
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    shared=Path.home()/'nino_research/.factory_sim.lock';shared.parent.mkdir(parents=True,exist_ok=True)
    with shared.open('a') as resource,(root/'.job.lock').open('a') as lock:
        fcntl.flock(resource,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ledger=read(root/'state.json') if (root/'state.json').exists() else dict(schema_version=1,latest={},runs=[])
        if any(r['action'] not in (PREFLIGHT,ACTION) for r in ledger['runs']):
            raise ValueError('V2 requires a separate root; historical slots cannot be reused')
        if any(r['action']==ACTION for r in ledger['runs']):raise ValueError('Study budget already consumed; no retry')
        pre=release_ready(root,True) if action==ACTION else None
        src=source();current=fingerprint()
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+action);out.mkdir()
        row=dict(action=action,path=out.name,status='running',error=None);ledger['runs'].append(row)
        save(root/'state.json',ledger);save(out/'protocol.json',protocol())
        save(out/'dependencies.json',dict(artifact=str(src),manifest_sha256=sha(src/'manifest.json')))
        status,error,result,started='running',None,None,time.monotonic()
        def timeout(*args):raise TimeoutError('Coverage job wall deadline')
        old=signal.signal(signal.SIGALRM,timeout);signal.alarm(300 if action==PREFLIGHT else 10800)
        try:
            emit(action,'Offline preflight; no Gazebo' if action==PREFLIGHT else 'One bounded coverage study')
            if action==PREFLIGHT:result=offline_preflight(out,src)
            else:
                save(out/'release.json',release_record())
                packets=read(pre/'critic_reference_packets.json');save(out/'critic_reference_packets.json',packets)
                result=execute(out,packets)
            if fingerprint()!=current:raise ValueError('Sources changed during coverage job')
            source();status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,old)
            save(out/'job.json',dict(action=action,status=status,error=error,wall_s=time.monotonic()-started,hardware_actions=0))
            save(out/'manifest.json',dict(action=action,status=status,coverage_fingerprint=current,
                source_fingerprint=source_fingerprint(),runtime=runtime_versions(),hardware_actions=0,
                files={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
            row.update(status=status,error=error)
            if status=='completed':ledger['latest'][action]=out.name
            save(root/'state.json',ledger)
            emit(action,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=(PREFLIGHT,ACTION));parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:run(args.output,args.action)
    except (Exception,KeyboardInterrupt) as exc:
        print('Coverage job failed/retained:',exc,flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
