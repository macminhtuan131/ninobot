"""Isolated common103_v2 Studio trainer and multi-seed [11, 22, 33] orchestrator.

Preserves frozen common_training_studio.py (v1) untouched. Adds:
1. 100,000-transition replay buffer & up to 100,000 steps per job.
2. Zero request cost when window_open == False (no claim of improved Critic calibration).
3. Obstacle ('box_c1_6mm') and bounded Domain Randomization ('box_c1_6mm_dr') worlds.
4. Multi-seed [11, 22, 33] independent campaign execution with physical checkpoint
   development nomination and descriptive comparison, not independent confirmation.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import fcntl
import json
import math
from pathlib import Path
import shutil
import signal
import time
import traceback
import uuid

import numpy as np

from . import common_studio_v2_contract as spec
from . import residual_common_td3 as frozen
from . import residual_drive_readiness as ready
from .studio_startup_repair import StudioStartupBackend
from .reliable_episode import EpisodeLifecycle
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import emit, runtime_versions, save
from .td3_experiment_matrix import compare_experiment_arms, select_best_checkpoint
from .td3_studio_contract import digest
from .td3_training_studio import Cancelled, append, audit_tail

ACTION = 'td3-common-studio-v2'


def sources() -> dict:
    paths = [
        Path(__file__),
        Path(spec.__file__),
        Path(spec.controller.__file__),
        Path(__file__).with_name('studio_v2_metrics.py'),
        Path(__file__).with_name('td3_experiment_matrix.py'),
        Path(__file__).with_name('training_studio_api_v2.py'),
        Path(__file__).with_name('td3_training_studio.py'),
        Path(__file__).with_name('studio_startup_repair.py'),
        Path(__file__).with_name('studio_deferred_reset.py'),
        Path(__file__).with_name('studio_resume_migration.py'),
        frozen.repo() / 'src/nino_rl/scripts/common_training_studio_v2.sh',
    ]
    return dict(
        controller=spec.controller.fingerprint(),
        drive_ready=ready.fingerprint(),
        files={str(p.relative_to(frozen.repo())): digest(p) for p in paths},
    )


def make_backend(out: Path, world: Path, launches: int, scenario: str):
    c, g, task, condition = spec.controller.configuration(6.0, scenario=scenario)
    lp = ready.parent.lifecycle_protocol()
    lp.update(protocol_id=spec.ENGINE, training_episodes_per_seed_maximum=launches)
    return EpisodeLifecycle(
        c,
        out / 'episodes',
        world,
        g,
        task,
        condition,
        lp,
        backend_factory=StudioStartupBackend,
    )


def extract_physical_metrics(rows: list[dict], stop_s: float, config: dict) -> dict:
    from .studio_v2_metrics import physical_metrics
    return physical_metrics(rows, stop_s, config)


def aggregate_physical_metrics(episode_metrics: list[dict]) -> dict:
    if not episode_metrics:
        raise ValueError('At least one episode metric dict is required')
    result = {
        'rms_v_m_s': float(np.mean([m['rms_v_m_s'] for m in episode_metrics])),
        'rms_omega_rad_s': float(np.mean([m['rms_omega_rad_s'] for m in episode_metrics])),
        'max_overshoot_m_s': float(np.max([m['max_overshoot_m_s'] for m in episode_metrics])),
        'settling_time_s': float(np.mean([m['settling_time_s'] for m in episode_metrics])),
        'action_jerk_rms': float(np.mean([m['action_jerk_rms'] for m in episode_metrics])),
        'saturation_fraction': float(np.mean([m['saturation_fraction'] for m in episode_metrics])),
        'safety_intervention_rate': float(np.max([m['safety_intervention_rate'] for m in episode_metrics])),
    }
    for key in ('cross_track_rmse_m', 'reference_acceleration_rms_m_s2'):
        if all(key in m for m in episode_metrics):
            result[key] = float(np.mean([m[key] for m in episode_metrics]))
    return result


def environment(
    backend,
    out: Path,
    budget: int,
    scenario: str,
    *,
    worlds: dict | None = None,
    learner_seed: int = 11,
    evaluation_stop: float | None = None,
):
    import gymnasium as gym

    strict_eval = evaluation_stop is not None
    spec_info = spec.controller.scenario_spec(scenario)

    class EnvV2(gym.Env):
        observation_space = gym.spaces.Box(-5.0, 5.0, shape=(103,), dtype=np.float32)
        action_space = gym.spaces.Box(-1.0, 1.0, shape=(1,), dtype=np.float32)

        def __init__(self):
            self.backend = backend
            self.episode = -1
            self.count = 0
            self.episode_rows = []
            self.last = None
            self.inner = None
            self.abi = spec.controller.identity(scenario=scenario)['abi_sha256']

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            self.episode += 1
            self.stop = evaluation_stop if evaluation_stop is not None else (6.0, 8.0)[self.episode % 2]
            c, g, task, condition = spec.controller.configuration(self.stop, scenario=scenario)
            dr_meta = dict(randomized=False)
            if not strict_eval and spec_info['domain_randomization'] is not None and worlds is not None:
                rng = np.random.default_rng(int(learner_seed) * 100_003 + self.episode)
                dr_meta = spec.controller.sample_dr_params(rng, scenario=scenario)
                dr_sdf = out / 'dr_worlds' / f'episode_{self.episode:04d}.sdf'
                spec.controller.build_dr_world_sdf(worlds['mixed_original_22mm'], dr_sdf, dr_meta)
                backend.world = dr_sdf
            world_path = Path(backend.world).resolve()
            self.world_identity = dict(path=str(world_path), sha256=digest(world_path),
                                       scenario=scenario, episode=self.episode, parameters=dr_meta)
            backend.config, backend.gconf, backend.protocol, backend.condition = c, g, task, condition
            self.inner = spec.controller.environment(c, backend, task, condition, scenario=scenario)
            obs, info = self.inner.reset(seed=seed)
            self.episode_rows = []
            self.epoch = None
            ready.require_ready(backend.view())
            save(
                out / f'episode_{self.episode}_reset.json',
                dict(reset=info, stop_s=self.stop, scenario=scenario, domain_randomization=dr_meta,
                     world=self.world_identity, config=c),
            )
            save(out / 'current_world.json', self.world_identity)
            return obs, info

        def step(self, action):
            if self.count >= budget:
                raise ValueError('Transition budget exhausted; no automatic extension')
            if shutil.disk_usage(out).free < 1024 ** 3:
                raise RuntimeError('Free disk below 1 GiB reserve; closing job and retaining artifacts')
            ready.require_ready(backend.view())
            obs, reward, term, trunc, info = self.inner.step(action)
            row = dict(
                step=len(self.episode_rows),
                episode=self.episode,
                reward=reward,
                terminated=term,
                truncated=trunc,
                done=bool(term or trunc),
                **info,
                qualification_condition=dict(arm='StudioV2', source_stop_s=self.stop, scenario=scenario),
                episode_namespace=backend.namespace,
                episode_world=self.world_identity,
            )
            row['TimeLimit.truncated'] = bool(trunc and not term)
            append(out / 'environment_trace.jsonl', row)
            self.epoch = self.epoch if self.epoch is not None else row['sensor_clock_s'] - row['task']['elapsed_s']
            spec.controller.verify_transition_v2(
                row,
                self.episode_rows[-1] if self.episode_rows else None,
                self.epoch,
                self.abi,
                scenario,
                strict_task=strict_eval,
            )
            self.episode_rows.append(row)
            self.count += 1
            self.last = row
            return obs, reward, term, trunc, info

        def close(self):
            backend.close()

    return EnvV2()


def build_model(env, request: dict):
    from stable_baselines3 import TD3
    from stable_baselines3.common.noise import NormalActionNoise

    a = spec.profiles()[request['profile']]['algorithm']
    kwargs = {
        k: a[k]
        for k in (
            'gamma',
            'tau',
            'batch_size',
            'buffer_size',
            'learning_starts',
            'policy_delay',
            'target_policy_noise',
            'target_noise_clip',
            'train_freq',
            'gradient_steps',
        )
    }
    return TD3(
        'MlpPolicy',
        env,
        seed=request['seed'],
        device='cpu',
        **kwargs,
        learning_rate=a['actor_lr'],
        policy_kwargs=dict(net_arch=a['network_arch']),
        action_noise=NormalActionNoise(np.zeros(1), np.ones(1) * a['exploration_noise']),
    )


def checkpoint(model, out: Path, identity: dict, reason: str) -> Path:
    directory = out / 'checkpoints'
    directory.mkdir(exist_ok=True)
    target = directory / f'step_{model.num_timesteps:012d}_{reason}'
    pending = directory / ('.pending_' + uuid.uuid4().hex)
    pending.mkdir()
    model.save(pending / 'model.zip')
    model.save_replay_buffer(pending / 'replay_buffer.pkl')
    save(pending / 'resume_identity.json', identity)
    save(
        pending / 'checkpoint.json',
        dict(
            identity=identity,
            global_steps=int(model.num_timesteps),
            optimizer_updates=int(model._n_updates),
            replay_size=int(model.replay_buffer.size()),
            episode_state_restored=False,
            rng_state_restored=False,
            reason=reason,
            engine_sources=sources(),
        ),
    )
    save(
        pending / 'manifest.json',
        dict(
            kind=spec.CHECKPOINT_KIND,
            status='resumable',
            runtime=runtime_versions(),
            hardware_actions=0,
            files={p.name: digest(p) for p in pending.iterdir() if p.is_file()},
        ),
    )
    pending.rename(target)
    return target


def evaluate(out: Path, request: dict, worlds: dict, model, stopped) -> list[dict]:
    results = []
    scenario = request['scenario']
    eval_world_key = spec.controller.scenario_spec(scenario)['base_world']
    eval_world = worlds[eval_world_key]
    before = ready.parent.full_snapshot(model)
    for stop in (6.0, 8.0):
        for arm in ('B0', 'Classical_scheduled', 'TD3'):
            if stopped():
                raise Cancelled('Cancelled before evaluation')
            emit(ACTION, f'Eval {arm} ({eval_world_key}), source stop {stop}s', phase='evaluate')
            target = out / 'evaluation' / f'{int(stop)}_{arm}'
            target.mkdir(parents=True)
            backend = make_backend(target, eval_world, 1, scenario=scenario)
            env = environment(backend, target, 140, scenario=scenario, evaluation_stop=stop)
            rows = []
            try:
                obs, _ = env.reset(seed=701)
                for _ in range(140):
                    if stopped():
                        raise Cancelled('Cancelled during evaluation')
                    action = (
                        model.predict(obs, deterministic=True)[0]
                        if arm == 'TD3'
                        else spec.controller.classical_request(obs, scenario=scenario)
                        if arm == 'Classical_scheduled'
                        else np.zeros(1, np.float32)
                    )
                    obs, _, term, trunc, _ = env.step(action)
                    rows.append(env.last)
                    if term or trunc:
                        break
            finally:
                env.close()
            native = backend.directory / backend.namespace
            result = frozen.baseline.summarize(rows, native)
            timing = frozen.timing.timestamp_diagnostic(native, rows)
            config, _, _, _ = spec.controller.configuration(stop, scenario=scenario)
            phys = extract_physical_metrics(rows, stop, config)
            result.update(
                arm=arm,
                eval_world=eval_world_key,
                source_stop_s=stop,
                timestamp_diagnostic=timing,
                physical_metrics=phys,
                physical_metric_contract='common103_v2_native_metrics_v2',
                evaluation_split='development_nominal',
                heldout=False,
                domain_randomization_evaluated=False,
                baseline_scope='Ki0.10 + fixed common compensation; not tuned obstacle baseline',
            )
            save(target / 'summary.json', result)
            results.append(result)
            save(out / 'evaluation_progress.json', results)
            if len(rows) != 140 or not result['functional_proposal_pass'] or not timing['valid']:
                raise ValueError('Development evaluation task/measurement failed; no retries')
    if ready.parent.full_snapshot(model) != before:
        raise ValueError('Evaluation mutated model/targets/optimizers/counters')
    return results


def actor_steps(model) -> int:
    return max((int(v['step']) for v in model.actor.optimizer.state.values() if 'step' in v), default=0)


def train(out: Path, request: dict, stopped) -> dict:
    import torch
    from stable_baselines3 import TD3
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.logger import configure

    torch.set_num_threads(1)
    identity = spec.identity(request)
    resume = spec.require_resume(request)
    scenario = request['scenario']
    worlds = prepare_worlds(out)
    base_world = worlds[spec.controller.scenario_spec(scenario)['base_world']]
    backend = make_backend(out, base_world, spec.budget(request)['training_launches_max'], scenario=scenario)
    env = environment(
        backend,
        out,
        request['timesteps'],
        scenario=scenario,
        worlds=worlds,
        learner_seed=request['seed'],
    )
    from stable_baselines3.common.monitor import Monitor
    from .studio_deferred_reset import DeferredResetVecEnv
    if spec.profiles()[request['profile']]['algorithm']['train_freq'] != 1:
        raise ValueError('Deferred Gazebo reset requires train_freq=1 step')
    env = DeferredResetVecEnv(Monitor(env))
    save(out / 'resume_identity.json', identity)
    save(out / 'effective_profile.json', identity['effective_profile'])
    rows = deque(maxlen=256)
    model = None
    safe = False
    start_steps = start_updates = start_pos = terminals = start_actor = 0
    task_success_episodes = 0
    count = 0
    last_log = time.monotonic()
    coverage = dict(
        total=0,
        window_open=0,
        positive_open=0,
        negative_open=0,
        gated=0,
        closed_gate_penalty_charged=0,
    )

    class TraceV2(BaseCallback):
        def _on_rollout_start(self):
            nonlocal safe
            safe = False

        def _on_step(self):
            nonlocal count, terminals, task_success_episodes
            info = self.locals['infos'][0]
            row = dict(
                info,
                timestep=self.num_timesteps,
                done=bool(self.locals['dones'][0]),
                reward=float(self.locals['rewards'][0]),
                next_observation=info.get('terminal_observation', self.locals['new_obs'][0]),
                reference_trace=dict(info['reference_trace'], observation=info['equal_observation']),
            )
            np.testing.assert_allclose(self.locals['actions'][0], row['requested_scalar_action'], atol=2e-6, rtol=0)
            append(out / 'training_trace.jsonl', row)
            rows.append(row)
            count += 1
            if row['done']:
                terminals += 1
                if row['task']['task_success']:
                    task_success_episodes += 1
            opened = row['plan_projection']['window_open']
            action = row['requested_scalar_action'][0]
            coverage['total'] += 1
            coverage['window_open'] += bool(opened)
            coverage['positive_open'] += bool(opened and action > 0)
            coverage['negative_open'] += bool(opened and action < 0)
            coverage['gated'] += bool(not opened)
            if not opened and (
                row['reward_terms']['action_size'] != 0.0 or row['reward_terms']['action_change'] != 0.0
            ):
                coverage['closed_gate_penalty_charged'] += 1
                raise ValueError('Closed-gate penalty leak detected in common103_v2')
            for name, value in [
                ('reward', row['reward']),
                ('velocity_error_m_s', row['task']['velocity_error_m_s']),
                ('requested_action', action),
                ('effective_action', row['plan_projection']['effective_scalar']),
                ('window_open', float(opened)),
            ]:
                self.logger.record_mean('nino_v2/' + name, value)
            for net in ('actor', 'actor_target', 'critic', 'critic_target'):
                if any(not torch.isfinite(v).all() for v in getattr(self.model, net).parameters()):
                    raise ValueError('Nonfinite model parameter')
            return True

        def _on_rollout_end(self):
            nonlocal safe, last_log
            safe = True
            completed = self.num_timesteps - start_steps
            if request['checkpoint_every'] and completed % request['checkpoint_every'] == 0 and completed < request['timesteps']:
                cp_path = checkpoint(self.model, out, identity, 'periodic')
                emit(ACTION, 'Checkpoint v2 đã lưu', checkpoint=str(cp_path))
            now = time.monotonic()
            if now - last_log > 5 or completed == request['timesteps']:
                self.logger.dump(self.num_timesteps)
                emit(
                    ACTION,
                    f"Common103_v2 [{scenario} · seed {request['seed']}] {completed}/{request['timesteps']} · critic {self.model._n_updates}",
                    phase='train',
                    progress=completed / request['timesteps'],
                    global_steps=self.num_timesteps,
                )
                save(out / 'coverage.json', coverage)
                last_log = now
            if stopped():
                raise Cancelled('Stopped at stored-transition boundary')
            # SB3 has now stored the terminal transition. Keep safe=True so a
            # failed next-world startup retains the exact model/replay boundary.
            # Do not start an unused world after the requested final transition.
            if completed < request['timesteps']:
                env.reset_after_store(self.model)
            safe = False

    try:
        if resume:
            path = Path(resume['path'])
            model = TD3.load(path / 'model.zip', env=env, device='cpu', force_reset=True)
            if getattr(model, 'nino_common_studio_v2_identity', None) != identity:
                raise ValueError('Saved model v2 identity mismatch')
            model.load_replay_buffer(path / 'replay_buffer.pkl')
            if (model.num_timesteps, model._n_updates, model.replay_buffer.size()) != (
                resume['global_steps'],
                resume['optimizer_updates'],
                resume['replay_size'],
            ):
                raise ValueError('Loaded counters/replay mismatch')
        else:
            model = build_model(env, request)
            save(out / 'zero_initialization.json', frozen.offline.zero_initialize_scalar(model))
        model.nino_common_studio_v2_identity = identity
        start_steps, start_updates, start_pos = (
            int(model.num_timesteps),
            int(model._n_updates),
            int(model.replay_buffer.pos),
        )
        start_actor = actor_steps(model)
        model.set_logger(configure(str(out / 'tensorboard'), ['csv', 'tensorboard']))
        if stopped():
            raise Cancelled('Cancelled before learning')
        model.learn(total_timesteps=request['timesteps'], reset_num_timesteps=False, callback=TraceV2(), log_interval=1)
        safe = True
        if count != request['timesteps'] or model.num_timesteps - start_steps != count:
            raise ValueError('Actual transition budget mismatch')
        audit = audit_tail(model.replay_buffer, rows, start_pos, start_steps)
        for name, value in model.logger.name_to_value.items():
            if name in ('train/actor_loss', 'train/critic_loss') and not math.isfinite(value):
                raise ValueError('Nonfinite final loss')
        model.logger.record('nino_v2/final_critic_updates', model._n_updates)
        model.logger.record('nino_v2/final_actor_updates', actor_steps(model))
        model.logger.dump(model.num_timesteps)
        final_cp = checkpoint(model, out, identity, 'final')
        result = dict(
            engine=spec.ENGINE,
            mode=request['mode'],
            scenario=scenario,
            seed=request['seed'],
            profile=request['profile'],
            buffer_capacity=int(model.replay_buffer.buffer_size),
            transitions=count,
            requested_additional_steps=request['timesteps'],
            starting_global_steps=start_steps,
            global_steps=int(model.num_timesteps),
            optimizer_updates_this_job=int(model._n_updates) - start_updates,
            optimizer_updates_total=int(model._n_updates),
            replay_size=int(model.replay_buffer.size()),
            replay_audit=audit,
            actor_updates_this_job=actor_steps(model) - start_actor,
            actor_updates_total=actor_steps(model),
            terminal_episodes=terminals,
            task_success_episodes=task_success_episodes,
            final_segment_right_censored=bool(rows and not rows[-1]['done']),
            checkpoint=str(final_cp),
            tensorboard=str(out / 'tensorboard'),
            action_coverage=coverage,
            resumed_from=resume,
            continuation_is_bit_exact=False,
            benefit_verified=False,
            hardware_authorized=False,
            training_launches=backend.index + 1,
        )
        save(out / 'training_result.json', result)
        env.close()
        if request['evaluate']:
            eval_rows = evaluate(out, request, worlds, model, stopped)
            result['evaluation'] = eval_rows
            by_arm = {}
            for arm_name in ('B0', 'Classical_scheduled', 'TD3'):
                arm_eps = [r['physical_metrics'] for r in eval_rows if r['arm'] == arm_name]
                if arm_eps:
                    by_arm[arm_name] = aggregate_physical_metrics(arm_eps)
            result['development_physical_by_arm'] = by_arm
            result['evaluation_scope'] = 'development_nominal_only_not_heldout_or_DR_robustness'
            if 'TD3' in by_arm:
                result['checkpoint_candidate'] = dict(
                    checkpoint_id=f"seed_{request['seed']}_step_{int(model.num_timesteps)}",
                    checkpoint_path=str(final_cp),
                    seed=request['seed'],
                    episodes=sum(1 for r in eval_rows if r['arm'] == 'TD3'),
                    development_metrics=by_arm['TD3'],
                )
        save(out / 'result.json', result)
        emit(ACTION, 'Checkpoint cuối common103_v2 đã lưu', checkpoint=str(final_cp))
        return result
    except BaseException:
        if model is not None and safe:
            try:
                cp_path = checkpoint(model, out, identity, 'interrupted')
                emit(ACTION, 'Đã giữ checkpoint ranh giới transition', checkpoint=str(cp_path))
            except BaseException:
                (out / 'checkpoint_error.txt').write_text(traceback.format_exc())
        raise
    finally:
        try:
            if model is not None and getattr(model, '_logger', None):
                model.logger.close()
        finally:
            env.close()


def _run_unlocked(root: Path, request: dict) -> tuple[Path, str]:
    request = spec.validate_request(request)
    root = Path(root).expanduser().resolve()
    plan = spec.require_disk(root, request)
    spec.require_resume(request)
    current = sources()
    root.mkdir(parents=True, exist_ok=True)
    out = root / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        + f"_common_v2_seed{request['seed']}_{request['mode']}"
    )
    out.mkdir()
    save(out / 'request.json', dict(request, schema_version=2, engine=spec.ENGINE))
    save(out / 'budget.json', plan)
    save(out / 'engine_sources.json', current)
    save(out / 'job.json', dict(status='running', request=request, hardware_actions=0))
    emit(
        ACTION,
        f"Chuẩn bị common103_v2 · scenario={request['scenario']} · seed={request['seed']} · replay={spec.profiles()[request['profile']]['algorithm']['buffer_size']:,}",
        directory=str(out),
        phase='prepare',
        progress=0.0,
    )
    stop = [False]
    started = time.monotonic()

    def cancel(*_args):
        stop[0] = True

    def timeout(*_args):
        raise TimeoutError('Wall-time budget exhausted; no retry')

    handlers = {s: signal.signal(s, cancel) for s in (signal.SIGINT, signal.SIGTERM)}
    handlers[signal.SIGALRM] = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(request['wall_minutes'] * 60)
    status, error, result = 'running', None, None
    try:
        result = train(out, request, lambda: stop[0])
        if sources() != current:
            raise ValueError('common103_v2 source changed during job')
        status = 'completed'
    except BaseException as exc:
        status = 'cancelled' if isinstance(exc, (Cancelled, KeyboardInterrupt)) else 'failed'
        error = str(exc)
        (out / 'error.txt').write_text(traceback.format_exc())
    finally:
        signal.alarm(0)
        for sig, old in handlers.items():
            signal.signal(sig, old)
        save(
            out / 'job.json',
            dict(status=status, error=error, wall_s=time.monotonic() - started, request=request, hardware_actions=0),
        )
        save(
            out / 'manifest.json',
            dict(
                kind=spec.JOB_KIND,
                status=status,
                engine_sources=current,
                runtime=runtime_versions(),
                hardware_actions=0,
                files={
                    str(p.relative_to(out)): digest(p)
                    for p in out.rglob('*')
                    if p.is_file() and p != out / 'manifest.json'
                },
            ),
        )
        emit(
            ACTION,
            status,
            directory=str(out),
            error=error,
            result=result,
            progress=1.0 if status == 'completed' else None,
        )
    return out, status


def run(root: Path, request: dict) -> tuple[Path, str]:
    lock_path = Path.home() / 'nino_research/.factory_sim.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run_unlocked(root, request)


def summarize_multi_seed_results(seed_results: list[dict], *, min_eval_episodes: int = 2) -> dict:
    """Nominate a checkpoint descriptively; never promote from the nominal development pair."""
    if len(seed_results) < 3:
        raise ValueError(f'Multi-seed selection requires >= 3 independent seeds; got {len(seed_results)}')
    candidates = []
    baseline_runs = []
    td3_runs = []
    seen = set()
    for res in seed_results:
        seed = res['seed']
        if type(seed) is not int or seed < 0 or seed in seen:
            raise ValueError('Independent distinct non-negative learner seeds required')
        seen.add(seed)
        eval_rows = res.get('evaluation') or []
        td3_eps = [r['physical_metrics'] for r in eval_rows if r['arm'] == 'TD3']
        cls_eps = [r['physical_metrics'] for r in eval_rows if r['arm'] == 'Classical_scheduled']
        if not td3_eps or not cls_eps:
            raise ValueError(f'Seed {seed} missing development TD3 or Classical_scheduled metrics')
        for arm in ('TD3', 'Classical_scheduled'):
            arm_rows = [r for r in eval_rows if r['arm'] == arm]
            if sorted(r['source_stop_s'] for r in arm_rows) != [6.0, 8.0]:
                raise ValueError('Development evaluation needs both stops exactly once per arm')
        td3_agg = aggregate_physical_metrics(td3_eps)
        cls_agg = aggregate_physical_metrics(cls_eps)
        cid = f"seed_{seed}_step_{int(res['global_steps'])}"
        candidates.append(
            dict(
                checkpoint_id=cid,
                checkpoint_path=res['checkpoint'],
                seed=seed,
                heldout_metrics=td3_agg,
            )
        )
        baseline_runs.append(dict(seed=seed, episodes=len(cls_eps), metrics=cls_agg))
        td3_runs.append(dict(seed=seed, episodes=len(td3_eps), metrics=td3_agg))

    selection = select_best_checkpoint(candidates)
    selection['status'] = 'DEVELOPMENT_NOMINATION_ONLY' if selection['selected'] else 'NO_SAFE_CHECKPOINT'
    comparison = compare_experiment_arms(
        baseline_runs,
        td3_runs,
        min_seeds=len(seed_results),
        min_episodes=min_eval_episodes,
    )
    comparison['descriptive_gate'] = comparison['verdict']
    comparison['verdict'] = 'EXPLORATORY_ONLY_INDEPENDENT_TEST_REQUIRED'
    selected_path = None
    if selection['selected'] is not None:
        win_id = selection['selected']['checkpoint_id']
        selected_path = next((c['checkpoint_path'] for c in candidates if c['checkpoint_id'] == win_id), None)
    return dict(
        seeds=[int(r['seed']) for r in seed_results],
        checkpoint_selection=dict(selection, selected_checkpoint_path=selected_path),
        arm_comparison=comparison,
        evaluation_scope='development_nominal_only',
        selection_bias_note='Best learner seed nominated on development data; no independent confirmation',
        benefit_verified=False,
        deployment_eligible=False,
        hardware_authorized=False,
    )


def run_multi_seed_campaign(
    root: Path,
    base_request: dict,
    seeds: tuple[int, ...] | list[int] = spec.DEFAULT_SEEDS,
    *,
    auto_prune_raw: bool = False,
) -> tuple[Path, str]:
    """Run independent learner jobs across seeds=[11, 22, 33] and rank by physical error."""
    seeds_list = list(seeds)
    template = dict(base_request)
    if template.get('resume') is not None or template.get('evaluate') is not True or template.get('mode') != 'train':
        raise ValueError('Campaign requires fresh training with evaluation, not resume or smoke')
    spec.campaign_budget(template, seeds_list, auto_prune_raw=auto_prune_raw)
    template['seed'] = seeds_list[0]
    validated_template = spec.validate_request(template)

    root = Path(root).expanduser().resolve()
    campaign_plan = spec.require_campaign_disk(root, validated_template, seeds_list, auto_prune_raw=auto_prune_raw)
    campaign_sources = sources()
    campaign_dir = root / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        + f"_common_v2_multiseed_{'_'.join(map(str, seeds_list))}_{validated_template['mode']}"
    )
    campaign_dir.mkdir(parents=True, exist_ok=False)
    lock_path = campaign_dir / '.campaign.lock'

    seed_records = []
    seed_results = []
    status = 'running'
    error = None
    summary = None
    started = time.monotonic()

    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save(campaign_dir / 'budget.json', campaign_plan)
        save(
            campaign_dir / 'campaign_request.json',
            dict(validated_template, seeds=seeds_list, auto_prune_raw=auto_prune_raw, engine=spec.ENGINE),
        )
        save(
            campaign_dir / 'job.json',
            dict(status='running', mode='multi_seed', seeds=seeds_list, request=validated_template, hardware_actions=0),
        )
        try:
            for idx, seed in enumerate(seeds_list):
                if sources() != campaign_sources:
                    raise ValueError('Campaign sources changed between seeds; remaining seeds closed')
                emit(
                    ACTION,
                    f"Multi-seed campaign {idx + 1}/{len(seeds_list)}: running independent seed {seed}",
                    directory=str(campaign_dir),
                    phase='train',
                    progress=idx / len(seeds_list),
                )
                seed_req = dict(validated_template, seed=seed)
                # Each job and retention operation acquire the shared simulator lock
                # via their public API. Never bypass retention's receipt/stat checks.
                job_dir, job_status = run(campaign_dir, seed_req)
                seed_records.append(dict(seed=seed, job_dir=str(job_dir), status=job_status))
                save(campaign_dir / 'seed_progress.json', seed_records)
                if job_status != 'completed':
                    status = job_status
                    error = f'Seed {seed} ended with status={job_status}; remaining seeds closed'
                    break
                res = json.loads((job_dir / 'result.json').read_text())
                seed_results.append(res)
                if auto_prune_raw:
                    from nino_pi.training_storage import prune_completed_job
                    receipt = prune_completed_job(job_dir, apply=True)
                    if receipt.get('status') != 'completed':
                        raise ValueError('Raw retention did not complete; remaining seeds closed')
                    seed_records[-1]['retention_status'] = receipt['status']
                    save(campaign_dir / 'seed_progress.json', seed_records)

            if len(seed_results) == len(seeds_list):
                summary = summarize_multi_seed_results(seed_results, min_eval_episodes=2)
                save(campaign_dir / 'campaign_summary.json', summary)
                save(campaign_dir / 'result.json', summary)
                status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, (Cancelled, KeyboardInterrupt)) else 'failed'
            error = str(exc)
            (campaign_dir / 'error.txt').write_text(traceback.format_exc())
        finally:
            save(
                campaign_dir / 'job.json',
                dict(
                    status=status,
                    mode='multi_seed',
                    seeds=seeds_list,
                    seed_records=seed_records,
                    error=error,
                    wall_s=time.monotonic() - started,
                    request=validated_template,
                    hardware_actions=0,
                ),
            )
            save(
                campaign_dir / 'campaign_manifest.json',
                dict(
                    kind='nino_common_studio_v2_multiseed_campaign',
                    status=status,
                    seeds=seeds_list,
                    runtime=runtime_versions(),
                    hardware_actions=0,
                    engine_sources=campaign_sources,
                    files={str(p.relative_to(campaign_dir)): digest(p)
                           for p in campaign_dir.iterdir() if p.is_file() and p.name != 'campaign_manifest.json'},
                ),
            )
            emit(
                ACTION,
                status,
                directory=str(campaign_dir),
                error=error,
                result=summary,
                progress=1.0 if status == 'completed' else None,
            )
    return campaign_dir, status

