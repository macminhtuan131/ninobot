"""Fresh bounded RELIABLE-joint TD3; new observer/backend per episode."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import signal
import time

import numpy as np
from . import residual_joint_reliability as candidate
from .reliable_episode import EpisodeLifecycle
from . import equal_information_contract as contract
from . import residual_equal_information as offline
from . import residual_equal_gazebo as qualified
from . import residual_guided_baseline as baseline
from . import residual_stop_transfer as timing
from .core import load_config
from .residual_experiment import source_fingerprint
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import emit, json_value, latest, runtime_versions, save

ACTION = 'sim-reliable-td3'
PARENT_ROOT = Path.home() / 'nino_research/sim_joint_reliability_v1'


def protocol():
    p = load_config(repo() / 'src/nino_rl/config/residual_reliable_td3_v1.yaml')
    expected = {(a, s, t) for a, seeds in [('B0', [None]), ('Classical_scheduled', [None]), ('TD3', [11, 22, 33])]
                for s in seeds for t in (6., 8.)}
    actual = [(r['arm'], r.get('seed'), r['source_stop_s']) for r in p['evaluation_order']]
    if len(actual) != 10 or set(actual) != expected:
        raise ValueError('Fixed ten evaluation conditions required')
    if (p['learner_seeds'], p['training_transitions_per_seed'], p['training_transitions_maximum'],
            p['training_episodes_per_seed_maximum'], p['steps_per_episode'], p['training_stop_schedule_s'],
            p['evaluation_transitions_maximum'], p['maximum_control_transitions'], p['maximum_gazebo_launches']) != (
                [11, 22, 33], 1024, 3072, 8, 140, [6., 8.], 1400, 4472, 34):
        raise ValueError('Bounded pilot budget changed; new protocol required')
    if (not p['training_released_for_this_pilot_only'] or p['resume_allowed'] or p['hardware_actions']
            or p['scenario'] != 'clear_box' or p['minimum_effect_accepted'] is not None):
        raise ValueError('Fresh Sim-only development pilot required')
    if qualified.fingerprint() != p['qualification_fingerprint'] or contract.identity()['abi_sha256'] != p['abi_sha256']:
        raise ValueError('Frozen qualification/controller ABI changed')
    return p


def fingerprint():
    paths = [Path(__file__), Path(__file__).with_name("reliable_episode.py"), repo() / 'src/nino_rl/config/residual_reliable_td3_v1.yaml',
             repo() / 'src/nino_rl/scripts/residual_reliable_td3.sh']
    return hashlib.sha256(json.dumps(dict(parent=candidate.fingerprint(), files={
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}), sort_keys=True).encode()).hexdigest()


def parent(check_runtime=True):
    out = candidate.validated_latest(PARENT_ROOT, candidate.ACTIONS[1], check_runtime=check_runtime)
    if candidate.fingerprint() != protocol()['candidate_fingerprint'] or hashlib.sha256((out / 'manifest.json').read_bytes()).hexdigest() != protocol()['candidate_manifest_sha256']:
        raise ValueError('Pinned reliable candidate changed')
    if not json.loads((out / 'qualification_result.json').read_text())['qualification_pass']:
        raise ValueError('Gazebo103D/1D prerequisite failed')
    return out


def identity():
    p = protocol()
    return dict(id=p['protocol_id'], fingerprint=fingerprint(), controller=contract.identity(),
                algorithm=p['algorithm'], observation_size=103, action_size=1,
                training_release=dict(this_pilot_only=True, seeds=p['learner_seeds'], transitions_per_seed=1024),
                reliable_candidate=p['candidate_fingerprint'], qualification_manifest=p['candidate_manifest_sha256'],
                lifecycle='fresh backend/context/observer/partition per episode; no cache reuse',
                normalization='frozen parent feature scaling; no learned VecNormalize statistics',
                resume_allowed=False, hardware_authorized=False)


def require_identity(actual):
    if actual != identity():
        raise ValueError('Common103D/1D learner identity mismatch; V3/Studio/inspection resume rejected')


def configuration(stop, training=False):
    c, g, task, condition = contract.configuration(stop)
    c['purpose'] = protocol()['protocol_id']
    c['backend'].update(scenario_id='clear_box_reliable_td3_v1', max_episodes=1)
    task['protocol_id'] = protocol()['protocol_id']
    return c, g, task, condition


def configure_episode(backend, episode):
    if not 0 <= episode < protocol()['training_episodes_per_seed_maximum']:
        raise ValueError('Episode budget exhausted')
    stop = protocol()['training_stop_schedule_s'][episode % 2]
    c, _, task, condition = configuration(stop, training=True)
    # Reset launches a fresh owned Gazebo instance; no snapshot or RNG claim.
    # These copies must change together BEFORE reset, including source/scorer.
    backend.config = deepcopy(c)
    backend.protocol = deepcopy(task)
    backend.condition = deepcopy(condition)
    return c, task, condition, stop


def feasibility(row, support_s=.04):
    task = row['task']
    values = [row['reward'], *row['equal_observation'], *row['equal_next_observation'],
              task['cross_track_m'], task['estimator_position_error_m'], task['estimator_yaw_error_rad']]
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError('Nonfinite transition')
    if (row.get('intervention') or row['guidance_audit']['fault'] or row['truth_used_for_guidance']
            or abs(task['cross_track_m']) > .04 or task['estimator_position_error_m'] > .05
            or abs(task['estimator_yaw_error_rad']) > .05):
        raise ValueError('Physical/guidance/engineering feasibility failure; remaining slots closed')
    if max(row['source_lags_s'].values()) > support_s + 1e-9:
        raise ValueError('Native boundary support failed; remaining slots closed')
    if row['truncated'] or (row['terminated'] and not task['task_success']):
        raise ValueError('Early/task/stop failure; remaining slots closed')


def append(path, row):
    with path.open('a') as stream:
        stream.write(json.dumps(row, default=json_value, allow_nan=False) + '\n')


def alternating_environment(backend, out, seed):
    import gymnasium as gym
    class AlternatingEnvironment(gym.Env):
        """One learner; eight fresh-launch episodes, alternating source stop6/8."""
        observation_space = gym.spaces.Box(-5., 5., shape=(103,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., shape=(1,), dtype=np.float32)

        def __init__(self, backend, out, seed):
            self.backend, self.out, self.seed = backend, out, seed
            self.inner = None
            self.episode = -1
            self.rows = []
            self.episode_rows = []
            self.resets = []
            self.epoch = None
            self.p = protocol()

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            self.episode += 1
            c, task, condition, self.stop = configure_episode(self.backend, self.episode)
            save(self.out / f'episode_{self.episode}_config.json', dict(config=c, task=task, condition=condition))
            self.inner = contract.environment(c, self.backend, task, condition)
            obs, info = self.inner.reset(seed=seed)
            self.episode_rows = []
            self.epoch = None
            self.resets.append(dict(episode=self.episode, source_stop_s=self.stop, reset=info))
            save(self.out / 'resets.json', self.resets)
            return obs, info

        def step(self, action):
            if len(self.rows) >= self.p['training_transitions_per_seed']:
                raise ValueError('No transitions beyond allocated seed budget')
            obs, reward, term, trunc, info = self.inner.step(action)
            row = dict(step=len(self.episode_rows), episode=self.episode, timestep=len(self.rows) + 1,
                       learner_seed=self.seed, reward=reward, terminated=term, truncated=trunc,
                       done=bool(term or trunc), **info,
                       qualification_condition=dict(arm='TD3_train', source_stop_s=self.stop), episode_namespace=self.backend.namespace)
            row['TimeLimit.truncated'] = bool(trunc and not term)
            append(self.out / 'training_trace.jsonl', row)
            previous = self.episode_rows[-1] if self.episode_rows else None
            self.epoch = self.epoch if self.epoch is not None else row['sensor_clock_s'] - row['task']['elapsed_s']
            # Validate before returning terminal to SB3: prevents auto-reset after a failure.
            qualified.verify_transition(row, previous, self.epoch, self.p['abi_sha256'])
            feasibility(row, self.p['native_boundary_support_s'])
            self.rows.append(row)
            self.episode_rows.append(row)
            if term:
                self.backend.current.flush_raw()
                target = self.backend.directory / self.backend.namespace
                summary = baseline.summarize(self.episode_rows, target)
                diagnostic = timing.timestamp_diagnostic(target, self.episode_rows)
                save(target / 'completed_episode_metrics.json', dict(summary, timestamp_diagnostic=diagnostic))
                if len(self.episode_rows) != 140 or not summary['functional_proposal_pass'] or not diagnostic['valid']:
                    raise ValueError('Full training episode task/header diagnostic failure')
                save(self.out / f'episode_{self.episode}_completion.json', dict(steps=len(self.episode_rows),
                    source_stop_s=self.stop, task_success=row['task']['task_success'], stop_completed=row['task']['stop_completed']))
            return obs, reward, term, trunc, info

        def close(self):
            self.backend.close()
    return AlternatingEnvironment(backend, out, seed)


def build_model(env, seed):
    from stable_baselines3 import TD3
    from stable_baselines3.common.noise import NormalActionNoise
    a = deepcopy(protocol()['algorithm'])
    sigma, net = a.pop('exploration_sigma'), a.pop('network_arch')
    return TD3('MlpPolicy', env, seed=seed, device='cpu', **a,
               action_noise=NormalActionNoise(np.zeros(1), sigma * np.ones(1)),
               policy_kwargs=dict(net_arch=net))


def checkpoint_check(model, out, rows):
    import torch
    from stable_baselines3 import TD3
    model.save(out / 'model.zip')
    model.save_replay_buffer(out / 'replay_buffer.pkl')
    save(out / 'learner_identity.json', identity())
    loaded = TD3.load(out / 'model.zip', device='cpu')
    require_identity(loaded.nino_reliable_identity)
    loaded.load_replay_buffer(out / 'replay_buffer.pkl')
    check = contract.audit_replay(loaded.replay_buffer, rows)
    check['scope'] = 'Fresh Gazebo training requests/103D transitions; no teleop or probe replay'
    for network in ('actor', 'actor_target', 'critic', 'critic_target'):
        for a, b in zip(getattr(model, network).parameters(), getattr(loaded, network).parameters()):
            if (not torch.equal(a, b) or not torch.isfinite(a).all()
                    or (a.grad is not None and not torch.isfinite(a.grad).all())):
                raise ValueError('Network/target save-load parity or finiteness failed')
    for name in ('actor', 'critic'):
        expected, actual = getattr(model, name).optimizer.state_dict(), getattr(loaded, name).optimizer.state_dict()
        if expected['param_groups'] != actual['param_groups']:
            raise ValueError('Optimizer group mismatch')
        for key, values in expected['state'].items():
            for field, value in values.items():
                other = actual['state'][key][field]
                if isinstance(value, torch.Tensor):
                    if not torch.equal(value, other) or not torch.isfinite(value).all():
                        raise ValueError('Optimizer state mismatch/nonfinite')
                elif value != other:
                    raise ValueError('Optimizer scalar mismatch')
    for row in rows[::43]:
        obs = np.asarray(row['equal_observation'], np.float32)
        np.testing.assert_array_equal(model.predict(obs, deterministic=True)[0], loaded.predict(obs, deterministic=True)[0])
    return dict(replay=check, model_optimizer_target_replay_parity=True,
                physics_restore=False, rng_restore=False, future_resume_requires_new_protocol=True)


def train_seed(out, seed, world):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    out.mkdir()
    c, g, task, condition = configuration(6., training=True)
    backend = EpisodeLifecycle(c, out / 'episodes', world, g, task, condition, protocol())
    env = alternating_environment(backend, out, seed)
    save(out / 'initial_config.json', dict(config=c, guidance=g, task=task, condition=condition))
    model = None
    try:
        model = build_model(env, seed)
        save(out / 'zero_initialization.json', offline.zero_initialize_scalar(model))
        model.nino_reliable_identity = identity()
        before = [v.detach().clone() for v in model.actor.parameters()]
        class Trace(BaseCallback):
            def _on_step(self):
                row = env.rows[-1]
                np.testing.assert_allclose(self.locals['actions'][0], row['requested_scalar_action'], atol=2e-6, rtol=0)
                for name in ('actor', 'critic'):
                    for value in getattr(self.model, name).parameters():
                        if not torch.isfinite(value).all():
                            raise ValueError('Nonfinite learner parameter')
                loss = {k: float(v) for k, v in self.model.logger.name_to_value.items()
                        if k in ('train/actor_loss', 'train/critic_loss')}
                if not all(math.isfinite(v) for v in loss.values()):
                    raise ValueError('Nonfinite learner loss')
                if self.num_timesteps % 64 == 0:
                    progress = dict(seed=seed, transitions=self.num_timesteps, optimizer_updates=self.model._n_updates,
                                    episode=env.episode, losses=loss)
                    append(out / 'learning_progress.jsonl', progress)
                    emit(ACTION, f'TD3 seed{seed}: {self.num_timesteps}/1024 · updates {self.model._n_updates}',
                         (env.p['learner_seeds'].index(seed) * 1024 + self.num_timesteps) / 4472)
                return True
        model.learn(total_timesteps=1024, callback=Trace())
        if len(env.rows) != 1024 or model.num_timesteps != 1024 or model._n_updates != 960:
            raise ValueError('Exact transition/update budget mismatch')
        change = float(sum((v.detach() - q).abs().sum().item() for v, q in zip(model.actor.parameters(), before)))
        if not math.isfinite(change) or change <= 0:
            raise ValueError('Actor did not change finitely')
        check = checkpoint_check(model, out, env.rows)
        result = dict(seed=seed, training_transitions=1024, optimizer_updates=int(model._n_updates),
            actor_parameter_l1_change=change, episodes_launched=len(env.resets), full_task_terminals=sum(r['done'] for r in env.rows),
            source_stop_schedule_s=[r['source_stop_s'] for r in env.resets], final_segment_steps=len(env.episode_rows),
            final_segment_right_censored=not env.rows[-1]['done'], **check,
            checkpoint_selection='last fixed-budget checkpoint, no evaluation selection', benefit_verified=False)
        save(out / 'training_result.json', result)
        return result
    except BaseException:
        if model is not None:
            model.save(out / 'partial_model_failed.zip')
            model.save_replay_buffer(out / 'partial_replay_failed.pkl')
        raise
    finally:
        env.close()


def evaluate_rollout(out, condition, world, checkpoints):
    out.mkdir()
    c, g, task, backend_condition = configuration(condition['source_stop_s'])
    for name, value in [('config', c), ('guidance', g), ('task', task)]:
        save(out / (name + '.json'), value)
    actor = None
    if condition['arm'] == 'TD3':
        from stable_baselines3 import TD3
        actor = TD3.load(checkpoints[condition['seed']] / 'model.zip', device='cpu')
        require_identity(actor.nino_reliable_identity)
    backend = baseline.GuidedBackend(c, out / 'backend', world, g, task, backend_condition)
    env = contract.environment(c, backend, task, backend_condition)
    rows, epoch = [], None
    p = protocol()
    try:
        obs, info = env.reset(seed=701)
        save(out / 'reset.json', info)
        for step in range(140):
            action = actor.predict(obs, deterministic=True)[0] if actor is not None else (
                contract.classical_request(obs) if condition['arm'] == 'Classical_scheduled' else np.zeros(1, np.float32))
            obs, reward, term, trunc, info = env.step(action)
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc, done=bool(term or trunc), **info,
                       qualification_condition=condition, episode_namespace=backend.namespace)
            row['TimeLimit.truncated'] = bool(trunc and not term)
            append(out / 'trace.jsonl', row)
            epoch = epoch if epoch is not None else row['sensor_clock_s'] - row['task']['elapsed_s']
            qualified.verify_transition(row, rows[-1] if rows else None, epoch, p['abi_sha256'])
            feasibility(row, p['native_boundary_support_s'])
            rows.append(row)
            if (step + 1) % 35 == 0:
                emit(ACTION, out.name + f' {step + 1}/140')
            if term or trunc:
                break
    finally:
        env.close()
    target = backend.directory / backend.namespace
    result = baseline.summarize(rows, target)
    diagnostic = timing.timestamp_diagnostic(target, rows)
    result.update(evaluation_condition=condition, timestamp_diagnostic=diagnostic,
                  maximum_native_boundary_support_age_s=max(max(r['source_lags_s'].values()) for r in rows))
    save(out / 'summary.json', result)
    if len(rows) != 140 or not result['functional_proposal_pass'] or not diagnostic['valid']:
        raise ValueError('Evaluation task/measurement failure; remaining slots closed')
    return result


def execute(out):
    import torch
    torch.set_num_threads(1)
    p = protocol()
    save(out / 'dependencies.json', contract.guided.dependency_record(parent()))
    save(out / 'learner_identity.json', identity())
    worlds = prepare_worlds(out)
    trained, runs, checkpoints = [], [], {}
    progress = dict(training=trained, runs=runs, benefit_verified=False, minimum_effect_accepted=None, hardware_actions=0)
    for seed in p['learner_seeds']:
        emit(ACTION, f'Fresh learner seed{seed}; no V3/Studio resume')
        target = out / f'seed_{seed}'
        try:
            result = train_seed(target, seed, worlds['clear_box'])
        except BaseException as exc:
            save(out / 'pilot_progress.json', dict(progress, failed_seed=seed, error=repr(exc), remaining_slots_closed=True))
            raise
        trained.append(result)
        checkpoints[seed] = target
        save(out / 'pilot_progress.json', progress)
    for index, condition in enumerate(p['evaluation_order']):
        emit(ACTION, f'Evaluation {index + 1}/10: {condition}', (3072 + index * 140) / 4472)
        try:
            result = evaluate_rollout(out / f'eval_{index:02d}', condition, worlds['clear_box'], checkpoints)
        except BaseException as exc:
            save(out / 'pilot_progress.json', dict(progress, failed_evaluation=index, error=repr(exc), remaining_slots_closed=True))
            raise
        runs.append(result)
        save(out / 'pilot_progress.json', progress)
    result = dict(progress, pilot_completed=True, training_transitions=sum(r['training_transitions'] for r in trained),
        optimizer_updates=sum(r['optimizer_updates'] for r in trained), evaluation_transitions=sum(r['steps'] for r in runs),
        gazebo_launches=sum(r['episodes_launched'] for r in trained) + len(runs), observation_size=103, action_size=1,
        all_task_stop_bounds_pass=True, evaluation_conditions_seen_before=True, independent_physics_rng_verified=False,
        conclusion='Finite development pilot only; no convergence/generalization/learned-benefit promotion')
    save(out / 'pilot_result.json', result)
    return result


def validated_latest(root, check_runtime=True):
    out = latest(root, ACTION, check_runtime=check_runtime)
    if json.loads((out / 'manifest.json').read_text()).get('reliable_td3_fingerprint') != fingerprint():
        raise ValueError('Reliable TD3 sources/protocol changed')
    require_identity(json.loads((out / 'learner_identity.json').read_text()))
    if json.loads((out / 'dependencies.json').read_text()) != contract.guided.dependency_record(parent(check_runtime)):
        raise ValueError('Qualification prerequisite changed')
    return out


def run(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    shared = Path.home() / 'nino_research/.factory_sim.lock'
    shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root / '.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / 'state.json').exists():
            raise ValueError('Reliable TD3 pilot already consumed; no retry or reopening')
        p = protocol()
        parent()
        out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + ACTION)
        out.mkdir()
        ledger = dict(schema_version=1, latest={}, runs=[dict(action=ACTION, path=out.name, status='running', error=None)])
        save(root / 'state.json', ledger)
        save(out / 'protocol.json', p)
        current, started, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame):
            raise TimeoutError('Finite reliable TD3 pilot wall deadline')
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(p['wall_deadline_s'])
        try:
            result = execute(out)
            if fingerprint() != current:
                raise ValueError('Scientific source changed during pilot')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            save(out / 'job.json', dict(action=ACTION, status=status, error=error, wall_s=time.monotonic() - started, hardware_actions=0))
            save(out / 'manifest.json', dict(action=ACTION, status=status, reliable_td3_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)): hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*')
                       if f.is_file() and f.name != 'manifest.json'}))
            ledger['runs'][0].update(status=status, error=error)
            if status == 'completed':
                ledger['latest'][ACTION] = out.name
            save(root / 'state.json', ledger)
            emit(ACTION, status, 1. if status == 'completed' else None, directory=str(out), result=result, error=error)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.output)
    except (Exception, KeyboardInterrupt) as exc:
        print('Reliable TD3 pilot failed/retained:', exc, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
