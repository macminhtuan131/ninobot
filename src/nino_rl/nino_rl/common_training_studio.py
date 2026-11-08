"""Bounded common103D/1D TD3 Studio jobs, fresh drive-ready epochs, Sim only."""
from collections import deque
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import signal
import time
import traceback
import uuid
import numpy as np
from . import common_studio_contract as spec
from . import residual_common_td3 as frozen
from . import residual_drive_readiness as ready
from .coverage_reset_readiness import require_uninhibited_transition
from .drive_readiness_candidate import DriveReadinessBackend
from .reliable_episode import EpisodeLifecycle
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import save, emit, runtime_versions
from .td3_studio_contract import digest
from .td3_training_studio import append, audit_tail, Cancelled

ACTION = 'td3-common-studio'


def sources():
    paths = [Path(__file__), Path(spec.__file__), Path(__file__).with_name('training_studio_api.py'),
             Path(__file__).with_name('td3_training_studio.py'),
             frozen.repo()/'src/nino_rl/scripts/common_training_studio.sh']
    return dict(controller=spec.controller.fingerprint(), drive_ready=ready.fingerprint(),
                files={str(p.relative_to(frozen.repo())): digest(p) for p in paths})


def make_backend(out, world, launches):
    c, g, task, condition = spec.controller.configuration(6.)
    lp = ready.parent.lifecycle_protocol()
    lp.update(protocol_id=spec.ENGINE, training_episodes_per_seed_maximum=launches)
    return EpisodeLifecycle(c, out/'episodes', world, g, task, condition, lp,
                            backend_factory=DriveReadinessBackend)


def environment(backend, out, budget, *, evaluation_stop=None):
    import gymnasium as gym
    class Env(gym.Env):
        observation_space = gym.spaces.Box(-5., 5., shape=(103,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., shape=(1,), dtype=np.float32)

        def __init__(self):
            self.backend = backend
            self.episode = -1
            self.count = 0
            self.episode_rows = []
            self.last = None
            self.inner = None
            self.abi = spec.controller.identity()['abi_sha256']

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            self.episode += 1
            self.stop = evaluation_stop if evaluation_stop is not None else (6., 8.)[self.episode % 2]
            c, g, task, condition = spec.controller.configuration(self.stop)
            backend.config, backend.gconf, backend.protocol, backend.condition = c, g, task, condition
            self.inner = spec.controller.environment(c, backend, task, condition)
            obs, info = self.inner.reset(seed=seed)
            self.episode_rows = []
            self.epoch = None
            ready.require_ready(backend.view())
            save(out/f'episode_{self.episode}_reset.json', dict(reset=info, stop_s=self.stop, config=c))
            return obs, info

        def step(self, action):
            if self.count >= budget:
                raise ValueError('Transition budget exhausted; no automatic extension')
            if shutil.disk_usage(out).free < 512*1024**2:
                raise RuntimeError('Free disk below 512 MiB; close job and retain artifacts')
            ready.require_ready(backend.view())
            obs, reward, term, trunc, info = self.inner.step(action)
            row = dict(step=len(self.episode_rows), episode=self.episode, reward=reward,
                       terminated=term, truncated=trunc, done=bool(term or trunc), **info,
                       qualification_condition=dict(arm='Studio', source_stop_s=self.stop),
                       episode_namespace=backend.namespace)
            row['TimeLimit.truncated'] = bool(trunc and not term)
            append(out/'environment_trace.jsonl', row)
            # Fail before returning to SB3, so a failed terminal never auto-resets.
            require_uninhibited_transition(row)
            self.epoch = self.epoch if self.epoch is not None else row['sensor_clock_s']-row['task']['elapsed_s']
            frozen.qualified.verify_transition(row, self.episode_rows[-1] if self.episode_rows else None,
                                               self.epoch, self.abi)
            frozen.feasibility(row, .04)
            self.episode_rows.append(row)
            self.count += 1
            self.last = row
            return obs, reward, term, trunc, info

        def close(self):
            backend.close()
    return Env()


def build_model(env, request):
    from stable_baselines3 import TD3
    from stable_baselines3.common.noise import NormalActionNoise
    a = spec.profiles()[request['profile']]['algorithm']
    kwargs = {k: a[k] for k in ('gamma', 'tau', 'batch_size', 'buffer_size', 'learning_starts',
              'policy_delay', 'target_policy_noise', 'target_noise_clip', 'train_freq', 'gradient_steps')}
    return TD3('MlpPolicy', env, seed=request['seed'], device='cpu', **kwargs,
               learning_rate=a['actor_lr'], policy_kwargs=dict(net_arch=a['network_arch']),
               action_noise=NormalActionNoise(np.zeros(1), np.ones(1)*a['exploration_noise']))


def checkpoint(model, out, identity, reason):
    directory = out/'checkpoints'
    directory.mkdir(exist_ok=True)
    target = directory/f'step_{model.num_timesteps:012d}_{reason}'
    pending = directory/('.pending_'+uuid.uuid4().hex)
    pending.mkdir()
    model.save(pending/'model.zip')
    model.save_replay_buffer(pending/'replay_buffer.pkl')
    save(pending/'resume_identity.json', identity)
    save(pending/'checkpoint.json', dict(identity=identity, global_steps=int(model.num_timesteps),
        optimizer_updates=int(model._n_updates), replay_size=int(model.replay_buffer.size()),
        episode_state_restored=False, rng_state_restored=False, reason=reason, engine_sources=sources()))
    save(pending/'manifest.json', dict(kind=spec.CHECKPOINT_KIND, status='resumable',
        runtime=runtime_versions(), hardware_actions=0,
        files={p.name: digest(p) for p in pending.iterdir() if p.is_file()}))
    pending.rename(target)
    return target


def evaluate(out, request, world, model, stopped):
    results = []
    before = ready.parent.full_snapshot(model)
    for stop in (6., 8.):
        for arm in ('B0', 'Classical_scheduled', 'TD3'):
            if stopped():
                raise Cancelled('Cancelled before evaluation')
            emit(ACTION, f'Eval {arm}, source stop {stop}s', phase='evaluate')
            target = out/'evaluation'/f'{int(stop)}_{arm}'
            target.mkdir(parents=True)
            backend = make_backend(target, world, 1)
            env = environment(backend, target, 140, evaluation_stop=stop)
            rows = []
            try:
                obs, _ = env.reset(seed=701)
                for _ in range(140):
                    if stopped():
                        raise Cancelled('Cancelled during evaluation')
                    action = (model.predict(obs, deterministic=True)[0] if arm == 'TD3' else
                              spec.controller.classical_request(obs) if arm == 'Classical_scheduled' else np.zeros(1, np.float32))
                    obs, _, term, trunc, _ = env.step(action)
                    rows.append(env.last)
                    if term or trunc:
                        break
            finally:
                env.close()
            native = backend.directory/backend.namespace
            result = frozen.baseline.summarize(rows, native)
            timing = frozen.timing.timestamp_diagnostic(native, rows)
            result.update(arm=arm, source_stop_s=stop, timestamp_diagnostic=timing)
            save(target/'summary.json', result)
            results.append(result)
            save(out/'evaluation_progress.json', results)
            if len(rows) != 140 or not result['functional_proposal_pass'] or not timing['valid']:
                raise ValueError('Evaluation task/measurement failed; no retries')
    if ready.parent.full_snapshot(model) != before:
        raise ValueError('Evaluation changed model/targets/optimizers/counters')
    return results


def actor_steps(model):
    return max((int(v['step']) for v in model.actor.optimizer.state.values() if 'step' in v), default=0)


def train(out, request, stopped):
    import torch
    from stable_baselines3 import TD3
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.logger import configure
    torch.set_num_threads(1)
    identity = spec.identity(request)
    resume = spec.require_resume(request)
    world = prepare_worlds(out)['clear_box']
    backend = make_backend(out, world, spec.budget(request)['training_launches_max'])
    env = environment(backend, out, request['timesteps'])
    save(out/'resume_identity.json', identity)
    save(out/'effective_profile.json', identity['effective_profile'])
    rows = deque(maxlen=256)
    model = None
    safe = False
    start_steps = start_updates = start_pos = terminals = start_actor = 0
    count = 0
    last_log = time.monotonic()
    coverage = dict(total=0, window_open=0, positive_open=0, negative_open=0, gated=0)

    class Trace(BaseCallback):
        def _on_rollout_start(self):
            nonlocal safe
            safe = False

        def _on_step(self):
            nonlocal count, terminals
            info = self.locals['infos'][0]
            row = dict(info, timestep=self.num_timesteps, done=bool(self.locals['dones'][0]),
                reward=float(self.locals['rewards'][0]),
                next_observation=info.get('terminal_observation', self.locals['new_obs'][0]),
                reference_trace=dict(info['reference_trace'], observation=info['equal_observation']))
            np.testing.assert_allclose(self.locals['actions'][0], row['requested_scalar_action'], atol=2e-6, rtol=0)
            append(out/'training_trace.jsonl', row)
            rows.append(row)
            count += 1
            terminals += row['done']
            opened = row['plan_projection']['window_open']
            action = row['requested_scalar_action'][0]
            coverage['total'] += 1
            coverage['window_open'] += opened
            coverage['positive_open'] += bool(opened and action > 0)
            coverage['negative_open'] += bool(opened and action < 0)
            coverage['gated'] += not opened
            for name, value in [('reward', row['reward']), ('velocity_error_m_s', row['task']['velocity_error_m_s']),
                                ('requested_action', action), ('window_open', float(opened))]:
                self.logger.record_mean('nino/'+name, value)
            for net in ('actor', 'actor_target', 'critic', 'critic_target'):
                if any(not torch.isfinite(v).all() for v in getattr(self.model, net).parameters()):
                    raise ValueError('Nonfinite model parameter')
            return True

        def _on_rollout_end(self):
            nonlocal safe, last_log
            safe = True
            completed = self.num_timesteps-start_steps
            if request['checkpoint_every'] and completed % request['checkpoint_every'] == 0 and completed < request['timesteps']:
                path = checkpoint(self.model, out, identity, 'periodic')
                emit(ACTION, 'Checkpoint đã lưu', checkpoint=str(path))
            now = time.monotonic()
            if now-last_log > 5 or completed == request['timesteps']:
                self.logger.dump(self.num_timesteps)
                emit(ACTION, f'Common103 train {completed}/{request["timesteps"]} · critic {self.model._n_updates}',
                     phase='train', progress=completed/request['timesteps'], global_steps=self.num_timesteps)
                save(out/'coverage.json', coverage)
                last_log = now
            if stopped():
                raise Cancelled('Stopped at stored-transition boundary')
            safe = False  # optimizer may now be mid-update; never snapshot that state

    try:
        if resume:
            path = Path(resume['path'])
            model = TD3.load(path/'model.zip', env=env, device='cpu', force_reset=True)
            if model.nino_common_studio_identity != identity:
                raise ValueError('Saved model identity mismatch')
            model.load_replay_buffer(path/'replay_buffer.pkl')
            if (model.num_timesteps, model._n_updates, model.replay_buffer.size()) != (
                    resume['global_steps'], resume['optimizer_updates'], resume['replay_size']):
                raise ValueError('Loaded counters/replay mismatch')
        else:
            model = build_model(env, request)
            save(out/'zero_initialization.json', frozen.offline.zero_initialize_scalar(model))
        model.nino_common_studio_identity = identity
        start_steps, start_updates, start_pos = int(model.num_timesteps), int(model._n_updates), int(model.replay_buffer.pos)
        start_actor = actor_steps(model)
        model.set_logger(configure(str(out/'tensorboard'), ['csv', 'tensorboard']))
        if stopped():
            raise Cancelled('Cancelled before learning')
        model.learn(total_timesteps=request['timesteps'], reset_num_timesteps=False, callback=Trace(), log_interval=1)
        safe = True
        if count != request['timesteps'] or model.num_timesteps-start_steps != count:
            raise ValueError('Actual transition budget mismatch')
        audit = audit_tail(model.replay_buffer, rows, start_pos, start_steps)
        for name, value in model.logger.name_to_value.items():
            if name in ('train/actor_loss', 'train/critic_loss') and not np.isfinite(value):
                raise ValueError('Nonfinite final loss')
        model.logger.record('nino/final_critic_updates', model._n_updates)
        model.logger.record('nino/final_actor_updates', actor_steps(model))
        model.logger.dump(model.num_timesteps)
        path = checkpoint(model, out, identity, 'final')
        result = dict(engine=spec.ENGINE, mode=request['mode'], scenario=request['scenario'], profile=request['profile'],
            transitions=count, requested_additional_steps=request['timesteps'], starting_global_steps=start_steps,
            global_steps=int(model.num_timesteps), optimizer_updates_this_job=int(model._n_updates)-start_updates,
            optimizer_updates_total=int(model._n_updates), replay_size=int(model.replay_buffer.size()), replay_audit=audit,
            actor_updates_this_job=actor_steps(model)-start_actor, actor_updates_total=actor_steps(model),
            terminal_episodes=terminals, final_segment_right_censored=bool(rows and not rows[-1]['done']),
            checkpoint=str(path), tensorboard=str(out/'tensorboard'), action_coverage=coverage,
            resumed_from=resume, continuation_is_bit_exact=False, benefit_verified=False, hardware_authorized=False,
            training_launches=backend.index+1)
        save(out/'training_result.json', result)
        env.close()  # close-before-start evaluation ownership
        if request['evaluate']:
            result['evaluation'] = evaluate(out, request, world, model, stopped)
        save(out/'result.json', result)
        emit(ACTION, 'Checkpoint cuối đã lưu', checkpoint=str(path))
        return result
    except BaseException:
        if model is not None and safe:
            try:
                path = checkpoint(model, out, identity, 'interrupted')
                emit(ACTION, 'Đã giữ checkpoint ranh giới transition', checkpoint=str(path))
            except BaseException:
                (out/'checkpoint_error.txt').write_text(traceback.format_exc())
        raise
    finally:
        try:
            if model is not None and getattr(model, '_logger', None):
                model.logger.close()
        finally:
            env.close()


def run(root, request):
    request = spec.validate_request(request)
    root = Path(root).expanduser().resolve()
    plan = spec.require_disk(root, request)
    spec.require_resume(request)
    current = sources()
    lock_path = Path.home()/'nino_research/.factory_sim.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root.mkdir(parents=True, exist_ok=True)
        out = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_common_'+request['mode'])
        out.mkdir()
        save(out/'request.json', dict(request, schema_version=2, engine=spec.ENGINE))
        save(out/'budget.json', plan)
        save(out/'engine_sources.json', current)
        save(out/'job.json', dict(status='running', request=request, hardware_actions=0))
        emit(ACTION, 'Chuẩn bị common103D/1D · baseline Ki0.10 frozen', directory=str(out), phase='prepare', progress=0.)
        stop = [False]
        started = time.monotonic()
        def cancel(*args):
            stop[0] = True
        def timeout(*args):
            raise TimeoutError('Wall-time budget exhausted; no retry')
        handlers = {s: signal.signal(s, cancel) for s in (signal.SIGINT, signal.SIGTERM)}
        handlers[signal.SIGALRM] = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(request['wall_minutes']*60)
        status, error, result = 'running', None, None
        try:
            result = train(out, request, lambda: stop[0])
            if sources() != current:
                raise ValueError('Source changed during job')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, (Cancelled, KeyboardInterrupt)) else 'failed'
            error = str(exc)
            (out/'error.txt').write_text(traceback.format_exc())
        finally:
            signal.alarm(0)
            for sig, old in handlers.items():
                signal.signal(sig, old)
            save(out/'job.json', dict(status=status, error=error, wall_s=time.monotonic()-started, request=request, hardware_actions=0))
            save(out/'manifest.json', dict(kind='nino_common_studio_job_v1', status=status, engine_sources=current,
                runtime=runtime_versions(), hardware_actions=0,
                files={str(p.relative_to(out)): digest(p) for p in out.rglob('*') if p.is_file() and p != out/'manifest.json'}))
            emit(ACTION, status, directory=str(out), error=error, result=result, progress=1. if status == 'completed' else None)
        return out, status
