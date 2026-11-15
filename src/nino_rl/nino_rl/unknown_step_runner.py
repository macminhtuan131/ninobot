"""Short Sim qualification only: prepare -> B0 -> 384-step TD3 -> development eval.

Never starts a long campaign or real hardware. Uses separate immutable stage
directories and fails on missing data; intended task failures remain outcomes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import signal
import time

import gymnasium as gym
import numpy as np

from . import unknown_step_plan as plan
from .common_training_studio_v2 import build_model, actor_steps
from .residual_factory_workflow import repo, factory_sources
from .residual_workflow import save, json_value
from .reliable_episode import EpisodeLifecycle
from .studio_deferred_reset import DeferredResetVecEnv
from .unknown_step_environment import UnknownStepEnv
from .unknown_step_gazebo import UnknownStepBackend
from .unknown_step_geometry import sha
from .unknown_step_runtime import RewardSettings, TaskSettings

STAGES = ('prepare', 'baseline', 'smoke', 'evaluate')


def append(path, row):
    with Path(path).open('a') as stream:
        stream.write(json.dumps(row, default=json_value, allow_nan=False)+'\n')


def sources():
    files = list(Path(__file__).parent.glob('unknown_step_*.py'))
    files += [plan.PROTOCOL, repo()/'src/nino_rl/scripts/unknown_step_runner.sh']
    files += [repo()/'src/nino_rl/config/unknown_step_short_gate_amendment_v1.json']
    # Include inherited observation/projection, estimator, lifecycle and backend.
    for name in ('residual_guidance.py', 'causal_planar_estimator.py', 'reliable_episode.py',
                 'studio_startup_repair.py', 'drive_readiness_candidate.py',
                 'joint_reliability_candidate.py', 'residual_joint_boundary.py',
                 'studio_deferred_reset.py', 'common_training_studio_v2.py'):
        files.append(Path(__file__).with_name(name))
    for name in ('residual_velocity.py', 'residual_pipeline.py'):
        files.append(repo()/'src/nino_control/nino_control'/name)
    return dict(files={str(p.relative_to(repo())):sha(p) for p in files}, factory=factory_sources())


def require_inputs(root):
    data = json.loads((root/'inputs/bank.json').read_text())
    if data['protocol_sha256'] != sha(plan.PROTOCOL):
        raise ValueError('Prepared protocol changed')
    for row in data['layouts']:
        if sha(row['world']) != row['world_sha256']:
            raise ValueError('Prepared world changed: '+row['id'])
    return data


def backend_for(out, bank, launches):
    c, g, task, condition = plan.configuration()
    lp = dict(training_episodes_per_seed_maximum=launches, observer_start_deadline_s=15.,
              feedback_deadline_s=5., observer_ipc_grace_s=1., maximum_support_age_ns=40_000_000)
    def factory(*args):
        return UnknownStepBackend(*args, expected_envelope=bank['envelope'])
    return EpisodeLifecycle(c, out/'episodes', bank['layouts'][0]['world'], g, task,
                            condition, lp, backend_factory=factory)


class BankEnvironment(gym.Env):
    observation_space = UnknownStepEnv.observation_space
    action_space = UnknownStepEnv.action_space

    def __init__(self, out, bank, order, *, launches, budget, global_launch_limit=8):
        super().__init__()
        self.out, self.bank, self.order = out, bank, order
        self.backend = backend_for(out, bank, launches)
        self.budget, self.steps, self.episode = budget, 0, -1
        if type(global_launch_limit) is not int or global_launch_limit < 1:
            raise ValueError('Explicit positive launch limit required')
        self.global_launch_limit = global_launch_limit
        self.inner, self.last = None, None
        self.completed = []

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        resource = next(p for p in [self.out, *self.out.parents] if (p/'ledger.json').exists())
        if len(list(resource.rglob('launch_argv.json'))) >= self.global_launch_limit:
            raise ValueError('Global short Gazebo launch budget exhausted')
        self.episode += 1
        name = self.order[self.episode % len(self.order)]
        layout = next(r for r in self.bank['layouts'] if r['id'] == name)
        if layout['split'] != 'development':
            raise ValueError('Short runner cannot consume reserved validation/test layouts')
        self.layout = layout
        self.backend.world = Path(layout['world'])
        c, g, task, condition = plan.configuration()
        self.backend.config, self.backend.gconf = c, g
        self.backend.protocol, self.backend.condition = task, condition
        settings = TaskSettings(**layout['task_settings'])
        self.inner = UnknownStepEnv(c, self.backend, settings, RewardSettings(**plan.protocol()['reward']))
        obs, info = self.inner.reset(seed=seed)
        save(self.out/f'episode_{self.episode}_reset.json', dict(
            reset=info, private_layout=layout, environment_identity=self.inner.identity))
        self.episode_start = self.steps
        return obs, info

    def step(self, action):
        if self.steps >= self.budget:
            raise ValueError('Short transition budget exhausted')
        if shutil.disk_usage(self.out).free < plan.protocol()['budget']['reserve_bytes']:
            raise ValueError('Disk reserve reached; preserve failure')
        append(self.out/'attempts.jsonl', dict(step=self.steps, episode=self.episode,
                                              action=np.asarray(action).tolist()))
        obs, reward, term, trunc, info = self.inner.step(action)
        self.steps += 1
        self.last = dict(info, reward=reward, terminated=term, truncated=trunc,
                         done=bool(term or trunc), step=self.steps, episode=self.episode,
                         layout_id=self.layout['id'], world_sha256=self.layout['world_sha256'])
        append(self.out/'environment_trace.jsonl', self.last)
        if term or trunc:
            self.completed.append(dict(episode=self.episode, layout_id=self.layout['id'],
                                       steps=self.steps-self.episode_start, **info['task']))
            save(self.out/'episode_outcomes.json', self.completed)
        return obs, reward, term, trunc, info

    def close(self):
        self.backend.close()


def raw_qc(out):
    out = Path(out)
    channels = ('imu', 'wheel', 'truth', 'drive')
    counts, maximum, last, episodes = {}, {}, {}, {}
    boundaries = {}
    trace = out/'environment_trace.jsonl'
    if trace.is_file():
        for line in trace.read_text().splitlines():
            row = json.loads(line)
            end = row.get('physical_sample', {}).get('stamp_s')
            if type(end) in (float, int) and np.isfinite(end):
                boundaries['episode_'+str(row['episode'])] = end
    expected = {p.name[:-len('_reset.json')] for p in out.glob('episode_*_reset.json')}
    expected.update(p.name for p in (out/'episodes').glob('episode_*') if p.is_dir())
    for episode in sorted(expected):
        path = out/'episodes'/episode/'backend/episode_0/raw_samples.jsonl'
        local_counts, local_maximum, local, reasons = {}, {}, {}, []
        first = {}
        first_stamp = None
        try:
            reset = json.loads((out/(episode+'_reset.json')).read_text())
            first_stamp = reset['reset']['physical_sample']['stamp_s']
            if type(first_stamp) not in (int, float) or not np.isfinite(first_stamp):
                raise ValueError('Physical sample stamp_s must be a finite number')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            first_stamp = None
            reasons.append(dict(reason='invalid_reset_metadata', detail=str(exc)))
        if not path.is_file():
            reasons.append(dict(reason='missing_raw_samples', path=str(path)))
        elif first_stamp is not None:
            try:
                with path.open() as stream:
                    for number, line in enumerate(stream, 1):
                        try:
                            row = json.loads(line)
                            key = row['channel']
                            if not isinstance(key, str):
                                raise ValueError('Raw channel must be a string')
                            if key not in channels:
                                continue
                            t = row['stamp_s']
                            if type(t) not in (int, float) or not np.isfinite(t):
                                raise ValueError('Raw stamp_s must be a finite number')
                        except (ValueError, TypeError, KeyError) as exc:
                            reasons.append(dict(reason='malformed_raw_record', line=number, detail=str(exc)))
                            continue
                        if t < first_stamp-1e-8:
                            continue
                        first.setdefault(key, t)
                        local_counts[key] = local_counts.get(key, 0)+1
                        if key in local:
                            gap = t-local[key]
                            if gap <= 0:
                                reasons.append(dict(reason='duplicate_source_timestamp' if gap == 0 else
                                    'source_timestamp_reversal', channel=key, line=number))
                            local_maximum[key] = max(local_maximum.get(key, gap), gap)
                        local[key] = t
            except OSError as exc:
                reasons.append(dict(reason='unreadable_raw_samples', detail=str(exc)))
            for key in channels:
                count = local_counts.get(key, 0)
                if count < 2:
                    reasons.append(dict(reason='missing_channel' if count == 0 else
                        'insufficient_source_samples', channel=key, count=count))
                if key in first and first[key]-first_stamp > .04000001:
                    reasons.append(dict(reason='missing_head_support', channel=key,
                                        gap_s=first[key]-first_stamp))
                if key in local and episode in boundaries and boundaries[episode]-local[key] > .04000001:
                    reasons.append(dict(reason='missing_tail_support', channel=key,
                                        gap_s=boundaries[episode]-local[key]))
                if key in local_maximum and local_maximum[key] > .04000001:
                    reasons.append(dict(reason='source_gap_exceeds_limit', channel=key,
                                        maximum_source_gap_s=local_maximum[key]))
            last[str(path)] = local
        for key, count in local_counts.items():
            counts[key] = counts.get(key, 0)+count
        for key, gap in local_maximum.items():
            maximum[key] = max(maximum.get(key, gap), gap)
        episodes[episode] = dict(valid=not reasons, reasons=reasons, counts=local_counts,
            maximum_source_gap_s=local_maximum, final_stamps=local, raw_path=str(path),
            end_boundary_s=boundaries.get(episode),
            boundary_coverage_checked=episode in boundaries)
    valid = bool(episodes) and all(episode['valid'] for episode in episodes.values())
    result = dict(valid=valid, counts=counts, maximum_source_gap_s=maximum,
                  scope='task_source_epoch_onward_retained_raw_no_interpolation', final_stamps=last,
                  episodes=episodes, reasons=[] if episodes else [dict(reason='no_expected_episodes')])
    save(out/'source_qc.json', result)
    return result


def rollout(out, bank, layout, *, model=None):
    out.mkdir()
    env = BankEnvironment(out, bank, [layout], launches=1, budget=250)
    rows = []
    try:
        obs, _ = env.reset(seed=701)
        for n in range(250):
            a = model.predict(obs, deterministic=True)[0] if model else np.zeros(1, np.float32)
            obs, reward, term, trunc, info = env.step(a)
            rows.append(env.last)
            if (n+1) % 50 == 0:
                print(json.dumps(dict(stage='evaluation' if model else 'baseline', layout=layout,
                                      step=n+1, progress=info['task']['progress_m'])), flush=True)
            if term or trunc:
                break
    finally:
        env.close()
    final = rows[-1]['task']
    qc = raw_qc(out)
    result = dict(layout_id=layout, steps=len(rows), outcome=final, source_qc=qc,
                  complete=rows[-1]['done'], benefit_verified=False,
                  split='development', held_out=False, hardware_actions=0)
    save(out/'summary.json', result)
    return result


def baseline(out, root):
    bank = require_inputs(root)
    results = []
    for row in plan.protocol()['bank']['development']:
        r = rollout(out/row['id'], bank, row['id'])
        results.append(r)
        save(out/'results.json', results)
        if not r['source_qc']['valid'] or not r['complete'] or not r['outcome']['task_success']:
            raise ValueError('B0 task/measurement failed; no TD3 smoke release')
    return dict(baseline_pass=True, results=results, learned_benefit=False)


def checkpoint(model, out, identity):
    out.mkdir(exist_ok=False)
    model.save(out/'model.zip')
    model.save_replay_buffer(out/'replay_buffer.pkl')
    save(out/'identity.json', identity)
    save(out/'checkpoint.json', dict(global_steps=int(model.num_timesteps),
        optimizer_updates=int(model._n_updates), actor_updates=actor_steps(model),
        replay_size=int(model.replay_buffer.size()), hardware_authorized=False,
        purpose='short_unknown_step_integration_not_promoted', rng_restored=False))
    save(out/'manifest.json', {p.name:sha(p) for p in out.iterdir() if p.is_file()})


def family_identity(root):
    p = plan.protocol()
    return dict(engine='unknown_step_goal100_v1', observation_size=100, action_size=1,
                bank_sha256=sha(root/'inputs/bank.json'), source_pins=sources(),
                profile=p['smoke_profile'], seed=p['seed'], purpose='short_integration',
                reward=p['reward'], hardware_authorized=False)


def smoke(out, root):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.logger import configure
    from stable_baselines3.common.monitor import Monitor
    p = plan.protocol()
    bank = require_inputs(root)
    torch.set_num_threads(1)
    env = BankEnvironment(out, bank, p['bank']['training_layout_order'], launches=3, budget=384)
    vec = DeferredResetVecEnv(Monitor(env))
    model = build_model(vec, dict(profile=p['smoke_profile'], seed=p['seed']))
    model.set_logger(configure(str(out/'tensorboard'), ['tensorboard']))
    initial = [v.detach().clone() for v in model.actor.parameters()]
    safe = False
    traces = []

    class Trace(BaseCallback):
        def _on_rollout_start(self):
            nonlocal safe
            safe = False

        def _on_step(self):
            row = dict(env.last, timestep=int(self.num_timesteps))
            np.testing.assert_allclose(self.locals['actions'][0], row['replay_action'], atol=2e-6, rtol=0)
            row['next_observation'] = self.locals['infos'][0].get('terminal_observation', self.locals['new_obs'][0])
            traces.append(row)
            append(out/'training_trace.jsonl', row)
            if self.num_timesteps % 32 == 0:
                print(json.dumps(dict(stage='smoke_train', steps=self.num_timesteps,
                                      critic_updates=model._n_updates, episodes=len(env.completed))), flush=True)
            return True

        def _on_rollout_end(self):
            nonlocal safe
            safe = True
            if self.num_timesteps < 384:
                vec.reset_after_store(model)

    try:
        model.learn(total_timesteps=384, callback=Trace())
        if model.num_timesteps != 384 or model.replay_buffer.size() != 384:
            raise ValueError('Smoke/replay counters differ')
        for i, row in enumerate(traces):
            b = model.replay_buffer
            for actual, expected in ((b.actions[i, 0], row['replay_action']),
                                     (b.observations[i, 0], row['observation']),
                                     (b.next_observations[i, 0], row['next_observation'])):
                np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0)
            if bool(b.dones[i, 0]) != row['done']:
                raise ValueError('Replay terminal flag differs')
        change = sum(float((v.detach()-old).abs().sum()) for v, old in zip(model.actor.parameters(), initial))
        if not change > 0 or not all(torch.isfinite(v).all() for v in model.policy.parameters()):
            raise ValueError('Missing/nonfinite optimizer update')
        checkpoint(model, out/'checkpoint_final', family_identity(root))
        result = dict(transitions=384, critic_updates=int(model._n_updates), actor_updates=actor_steps(model),
            replay_rows_checked=len(traces), actor_parameter_l1_change=change,
            complete_episodes=env.completed, final_segment_right_censored=not traces[-1]['done'],
            profile=p['smoke_profile'], seed=p['seed'], research_training=False, benefit_verified=False)
        save(out/'result.json', result)
    except BaseException:
        if safe:
            checkpoint(model, out/'checkpoint_interrupted', family_identity(root))
        raise
    finally:
        vec.close()
    qc = raw_qc(out)
    if not qc['valid']:
        raise ValueError('Smoke measurement QC failed; checkpoint retained but not qualified')
    return result


def evaluate(out, root):
    from stable_baselines3 import TD3
    record = json.loads((root/'ledger.json').read_text())
    trained = Path(record['stages']['smoke']['path'])/'checkpoint_final'
    saved = json.loads((trained/'manifest.json').read_text())
    if any(sha(trained/n) != h for n, h in saved.items()):
        raise ValueError('Smoke checkpoint changed')
    if json.loads((trained/'identity.json').read_text()) != family_identity(root):
        raise ValueError('Checkpoint family/reward/controller/bank identity changed')
    model = TD3.load(trained/'model.zip', device='cpu')
    snapshot = [p.detach().clone() for p in model.policy.parameters()]
    r = rollout(out/'dev_late_TD3', require_inputs(root), 'dev_late', model=model)
    if any(not np.array_equal(p.detach().numpy(), old.numpy()) for p, old in zip(model.policy.parameters(), snapshot)):
        raise ValueError('Evaluation mutated checkpoint')
    if not r['source_qc']['valid']:
        raise ValueError('Development evaluation measurement QC failed')
    return dict(result=r, deterministic=True, optimizer_updates=0, independent_test=False,
                benefit_verified=False, next='review_then_request_long_training_separately')


def run(root, stage):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < plan.protocol()['budget']['required_free_bytes']:
        raise ValueError('Short-run disk budget unavailable')
    shared = Path.home()/'nino_research/.factory_sim.lock'
    with shared.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger_path = root/'ledger.json'
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else dict(
            protocol_id=plan.protocol()['protocol_id'], stages={}, hardware_actions=0, long_training_allowed=False)
        if stage in ledger['stages']:
            raise ValueError('Stage already consumed; retain failed attempt, no implicit retry')
        index = STAGES.index(stage)
        prior = ledger['stages'].get(STAGES[index-1], {}) if index else {}
        reviewed_baseline = stage == 'smoke' and ledger.get('baseline_review', {}).get('status') == 'qualified_for_smoke_only'
        if reviewed_baseline:
            review = ledger['baseline_review']
            amendment = repo()/'src/nino_rl/config/unknown_step_short_gate_amendment_v1.json'
            if review['amendment_sha256'] != sha(amendment) or review['report_sha256'] != sha(review['report']):
                raise ValueError('Baseline gate amendment proof changed')
        if index and prior.get('status') != 'completed' and not reviewed_baseline:
            raise ValueError('Previous stage has not qualified')
        target = root/'inputs' if stage == 'prepare' else root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+stage)
        if stage != 'prepare':
            target.mkdir()
        frozen = sources()
        save(root/f'{stage}_source_pins.json', frozen)
        ledger['stages'][stage] = dict(path=str(target), status='running')
        save(ledger_path, ledger)
        start = time.monotonic()
        error, result = None, None
        previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('Short stage wall deadline')))
        signal.alarm(plan.protocol()['budget']['wall_deadline_s'])
        try:
            result = plan.prepare(target) if stage == 'prepare' else globals()[stage](target, root)
            if sources() != frozen:
                raise ValueError('Source changed during short stage')
            ledger['stages'][stage]['status'] = 'completed'
            save(target/'stage_result.json', result)
        except BaseException as exc:
            error = repr(exc)
            ledger['stages'][stage]['status'] = 'failed'
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            ledger['stages'][stage].update(error=error, wall_s=time.monotonic()-start)
            save(target/'job.json', dict(stage=stage, **ledger['stages'][stage], hardware_actions=0))
            save(target/'stage_manifest.json', dict(source_pins=frozen, files={
                str(f.relative_to(target)):sha(f) for f in target.rglob('*') if f.is_file() and f.name != 'stage_manifest.json'}))
            save(ledger_path, ledger)
            print(json.dumps(ledger['stages'][stage]), flush=True)
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=STAGES)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    run(args.output, args.stage)


if __name__ == '__main__':
    main()
