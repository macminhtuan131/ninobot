"""Finite V2 tracking/stop task, independent of V1's progress reward and ledger.

Actual Nino + passive casters + Gazebo wheel PI, no hardware. Body truth and
caster positions are reward/evaluation labels only. Fixed observation/action
ABI is retained; a new task ID/fingerprint prevents mixing checkpoints.
"""
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
from nino_control.residual_velocity import ReferenceLimits, ResidualReference
from nino_control.residual_actor import PortableActor, export_actor
from .core import load_config
from .factory_velocity_backend import FactoryVelocityBackend, stamp
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds, scenario_config, describe, fingerprint as v1_fingerprint
from .residual_experiment import experiment_contract, build_model, source_fingerprint
from .residual_workflow import save, emit, json_value, runtime_versions, latest
from .td3_config import apply_profile

ACTIONS = ('sim-v2-baselines', 'sim-v2-train', 'sim-v2-evaluate')


def fingerprint():
    paths = [Path(__file__), repo()/'src/nino_rl/config/residual_sim_task_v2.yaml',
             repo()/'src/nino_rl/scripts/residual_sim_task.sh']
    hashes = {str(p.relative_to(repo())): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(dict(files=hashes, parent=v1_fingerprint()), sort_keys=True).encode()).hexdigest()


def config():
    c = apply_profile(load_config(repo()/'src/nino_rl/config/residual_sim_task_v2.yaml'), 'nino_td3_smoke_h5_v1')
    t = c['task']
    if (t['training_transitions'], t['steps_per_rollout'], t['baseline_repeats'], t['evaluation_repeats'], c['hardware_authority']) != (512, 140, 2, 2, 0):
        raise ValueError('Changed finite budget requires a new task protocol')
    if c['backend']['horizon_s'] != 14 or c['backend']['command_until_s'] != 8:
        raise ValueError('Fixed V2 source/deadline mismatch')
    stop_budget = t['horizon_s']-t['command_until_s']
    decel = (c['backend']['cruise_m_s']+c['reference_limits']['residual_wheel_m_s'])/c['reference_limits']['wheel_acceleration_m_s2']
    if stop_budget < decel+t['stop_continuous_s']+1:
        raise ValueError('Insufficient reference deceleration + quiet + 1 s lag allowance')
    return c


class TaskBackend(FactoryVelocityBackend):
    """Additional read-only labels. Never put caster/truth in ObservationAssembler."""
    def _receive(self, key, msg):
        super()._receive(key, msg)
        if key == 'wheel':
            try:
                values = {name: dict(position_rad=msg.position[i] if i < len(msg.position) else None,
                                     velocity_rad_s=msg.velocity[i] if i < len(msg.velocity) else None)
                          for i, name in enumerate(msg.name) if 'caster' in name}
                self._store('caster_audit', stamp(msg), values)
            except Exception as exc:
                with self.lock: self.error = repr(exc)

    def advance_reference(self, v, w, dt):
        view, labels, terminal, truncated, info = super().advance_reference(v, w, dt)
        with self.lock:
            truth = deepcopy(self.messages['truth']['values'])
            caster = deepcopy(self.messages.get('caster_audit', {}).get('values'))
        info.update(body_speed_norm_m_s=truth['speed_norm'], body_roll_rad=truth['roll'],
                    body_pitch_rad=truth['pitch'], caster_audit=caster)
        return view, labels, terminal, truncated, info


class TaskScore:
    """Independent B0-shaped target and fixed-horizon success, not progress reward."""
    def __init__(self, c):
        self.c = c
        self.reference = ResidualReference(ReferenceLimits(**c['reference_limits']))
        self.previous = np.zeros(2)
        self.quiet_s = 0.
        self.marker = False

    def update(self, info, action, elapsed, physical_failure=False):
        c, t, dt = self.c, self.c['task'], self.c['control_interval_s']
        # A completely separate zero-residual composer, not the policy's previous
        # accepted reference, defines the same target for every arm.
        nominal = self.reference.compose(info['reference_trace']['original_baseline_body'], (0., 0.), dt,
            permission=True, sensors_fresh=True, history_ready=True, command_age_s=0.)['body_reference']
        action = np.asarray(action, dtype=float)
        pose = info['truth_pose_m_rad']
        scales, weights = t['reward_scales'], t['reward_weights']
        errors = dict(tracking=(info['body_speed_m_s']-nominal[0])/scales['speed_m_s'],
                      yaw=(info['body_yaw_rad_s']-nominal[1])/scales['yaw_rad_s'],
                      lateral=pose[1]/scales['lateral_m'])
        terms = {k: -weights[k]*v*v*dt for k, v in errors.items()}
        terms.update(action=-weights['action']*float(action@action)*dt,
                     action_change=-weights['action_change']*float(np.sum((action-self.previous)**2))/dt,
                     time=-weights['time']*dt)
        self.previous = action
        self.marker |= pose[0] >= t['local_marker_x_m']
        reference = info['reference_trace']['accepted_reference_wheel_m_s']
        quiet = (elapsed >= t['command_until_s'] and max(map(abs, reference)) <= t['stop_reference_wheel_m_s']
                 and info['body_speed_norm_m_s'] < t['stop_speed_norm_m_s']
                 and abs(info['body_yaw_rad_s']) < t['stop_yaw_rad_s']
                 and max(map(abs, info['feedback_wheel_rad_s'])) < t['stop_wheel_rad_s'])
        self.quiet_s = self.quiet_s+dt if quiet else 0.
        stopped = self.quiet_s >= t['stop_continuous_s']-1e-8
        deadline = elapsed >= t['horizon_s']-1e-8
        if physical_failure:
            terms['physical_failure'] = -t['terminal_penalties']['physical_failure']
        elif deadline:
            if not self.marker: terms['missing_marker'] = -t['terminal_penalties']['missing_marker']
            if not stopped: terms['not_stopped'] = -t['terminal_penalties']['not_stopped']
        return sum(terms.values()), dict(task_id=t['id'], elapsed_s=elapsed,
            nominal_shaped_body=nominal, normalized_errors=errors, reward_terms=terms,
            marker_reached=self.marker, quiet_now=quiet, continuous_quiet_s=self.quiet_s,
            stop_completed=stopped, task_deadline=deadline,
            task_success=bool(deadline and self.marker and stopped and not physical_failure))


def environment(c, directory, world):
    import gymnasium as gym
    from .residual_experiment import make_environment
    inner = make_environment(c, TaskBackend(c, directory, repo(), world))
    class TaskEnvironment(gym.Wrapper):
        def __init__(self):
            super().__init__(inner)
            self.backend = inner.backend
            self.score = None
            self.steps = 0
        def reset(self, **kwargs):
            self.score = TaskScore(c)
            self.steps = 0
            return self.env.reset(**kwargs)
        def step(self, action):
            obs, _, terminal, truncated, info = self.env.step(action)
            self.steps += 1
            reward, task = self.score.update(info, action, self.steps*c['control_interval_s'], terminal)
            deadline = task['task_deadline']
            # The 14 s deadline is part of this finite task, not an external
            # training cutoff. Success and missed deadline are true terminals.
            if deadline and not terminal:
                terminal, truncated = True, False
                info['termination_reason'] = 'task_success' if task['task_success'] else 'task_deadline_failure'
            return obs, reward, terminal, truncated, dict(info, task=task, reward_terms=task['reward_terms'])
    return TaskEnvironment()


def summarize(rows, raw_paths):
    result = describe(rows, raw_paths)
    task = rows[-1]['task']
    nominal = np.asarray([r['task']['nominal_shaped_body'] for r in rows])
    speed = np.asarray([r['body_speed_m_s'] for r in rows])
    times = [r['task']['elapsed_s'] for r in rows]
    first = lambda predicate: next((tm for r, tm in zip(rows, times) if predicate(r)), None)
    result.update(physical_failure=any(r.get('termination_reason') == 'physical_envelope_failure' or r.get('intervention') for r in rows),
        nominal_shaped_tracking_rmse_m_s=float(np.sqrt(np.mean((speed-nominal[:, 0])**2))),
        task_success=task['task_success'], marker_reached=task['marker_reached'],
        stop_completed=task['stop_completed'], continuous_quiet_s=task['continuous_quiet_s'],
        deadline_reached=task['task_deadline'], termination_reason=rows[-1]['termination_reason'],
        first_source_zero_after_motion_s=first(lambda r: r['task']['elapsed_s'] > 8 and tuple(r['reference_trace']['original_baseline_body'])==(0., 0.)),
        first_shaped_zero_after_motion_s=first(lambda r: r['task']['elapsed_s'] > 8 and max(map(abs, r['reference_trace']['accepted_reference_wheel_m_s'])) < 1e-6),
        first_continuous_stop_completed_s=first(lambda r: r['task']['stop_completed']),
        caster_labels_available=any(bool(r.get('caster_audit')) for r in rows),
        final_caster_audit=rows[-1].get('caster_audit'),
        minimum_effect_accepted=None, benefit_verified=False, hardware_authorized=False)
    return result


def rollout(out, c, world, arm, actor=None):
    out.mkdir()
    env = environment(c, out/'backend', world)
    rows = []
    try:
        obs, _ = env.reset(seed=701)
        for step in range(c['task']['steps_per_rollout']):
            action = actor(obs) if actor is not None else np.array([
                c['task']['speed_control_delta_m_s']/c['reference_limits']['residual_wheel_m_s'] if arm == 'B_speed_control' else 0., 0.], dtype=np.float32)
            obs, reward, terminal, truncated, info = env.step(action)
            row = dict(step=step, reward=reward, terminated=terminal, truncated=truncated, **info)
            rows.append(row)
            with (out/'trace.jsonl').open('a') as stream: stream.write(json.dumps(row, default=json_value, allow_nan=False)+'\n')
            if (step+1) % 35 == 0: emit('sim-v2-evaluate', out.name+' '+str(step+1)+'/140')
            if terminal or truncated: break
    finally:
        env.close()
    result = summarize(rows, sorted((out/'backend').glob('episode_*/raw_samples.jsonl')))
    save(out/'summary.json', dict(arm=arm, **result))
    return result


def baselines(out, c, worlds):
    results = {}
    for scenario in c['task']['baseline_scenarios']:
        results[scenario] = []
        for repeat in range(c['task']['baseline_repeats']):
            result = rollout(out/(scenario+'_'+str(repeat)), scenario_config(c, scenario), worlds[scenario], 'B0')
            results[scenario].append(result)
            save(out/'baseline_progress.json', results)
            if result['physical_failure']: raise RuntimeError('Physical envelope failure; no automatic retry')
    if not all(r['task_success'] for r in results['clear_box']):
        raise RuntimeError('Clear B0 did not complete fixed motion/stop task in both runs; no learning release')
    selected = 'box_c1_6mm' if all(r['task_success'] for r in results['box_c1_6mm']) else 'clear_box'
    sc = scenario_config(c, selected)
    abi = experiment_contract(sc)
    save(out/'validation.json', dict(contract_id=abi['id'], features=abi['features'], history_frames=abi['history_frames'],
        abi_sha256=abi['abi_sha256'], source_fingerprint=source_fingerprint(), backend_kind=TaskBackend.kind,
        backend_configuration=sc['backend'], backend_validated=True, integration_pass=True,
        task_fingerprint=fingerprint(), scope='finite task functional release only; not calibrated or learned benefit'))
    result = dict(selected_scenario=selected, results=results, benefit_verified=False, hardware_authorized=False,
                  selection_rule='6 mm only if both B0 runs reach marker and stop; otherwise clear floor')
    save(out/'baseline_result.json', result)
    return result


def validated_latest(root, action, check_runtime=True):
    path = latest(root, action, check_runtime=check_runtime)
    if json.loads((path/'manifest.json').read_text()).get('task_fingerprint') != fingerprint():
        raise ValueError('V2 task source changed; retained artifact is historical')
    if action != ACTIONS[0]:
        previous = validated_latest(root, ACTIONS[ACTIONS.index(action)-1], check_runtime)
        dependency = json.loads((path/'dependencies.json').read_text())
        if dependency != dependency_record(previous): raise ValueError('Upstream V2 artifact changed; downstream is historical')
    return path


def dependency_record(path):
    return dict(path=str(path), manifest_sha256=hashlib.sha256((path/'manifest.json').read_bytes()).hexdigest())


def train(out, c, worlds, root):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    torch.set_num_threads(1)
    baseline = validated_latest(root, ACTIONS[0])
    selected = json.loads((baseline/'baseline_result.json').read_text())['selected_scenario']
    c = scenario_config(c, selected)
    c['training'] = dict(allowed=True, backend_validation_artifact=str(baseline/'validation.json'), budget_transitions=512)
    save(out/'training_config.json', c)
    save(out/'dependencies.json', dependency_record(baseline))
    env = environment(c, out/'backend', worlds[selected])
    model = build_model(c, env, c['task']['learner_seed'])
    before = [p.detach().clone() for p in model.actor.parameters()]
    class Trace(BaseCallback):
        def _on_step(self):
            for i, info in enumerate(self.locals['infos']):
                row = dict(timestep=self.num_timesteps, done=bool(self.locals['dones'][i]),
                    next_observation=info.get('terminal_observation', self.locals['new_obs'][i]),
                    reward=float(self.locals['rewards'][i]), **info)
                with (out/'training_trace.jsonl').open('a') as stream: stream.write(json.dumps(row, default=json_value, allow_nan=False)+'\n')
            if self.num_timesteps % 64 == 0: emit(ACTIONS[1], 'TD3 V2 '+str(self.num_timesteps)+'/512', self.num_timesteps/512)
            return True
    try:
        model.learn(total_timesteps=512, callback=Trace())
        model.save(out/'model.zip')
        model.save_replay_buffer(out/'replay_buffer.pkl')
        change = float(sum((p.detach()-q).abs().sum().item() for p, q in zip(model.actor.parameters(), before)))
        if not math.isfinite(change) or change <= 0: raise ValueError('No finite actor update')
        parity = export_actor(model, 'TD3', out, experiment_contract(c), purpose=c['task']['id'])
        save(out/'task_checkpoint.json', dict(task_id=c['task']['id'], task_fingerprint=fingerprint(),
             abi_sha256=experiment_contract(c)['abi_sha256'], hardware_authorized=False))
        rows = [json.loads(line) for line in (out/'training_trace.jsonl').read_text().splitlines()]
        b = model.replay_buffer
        if len(rows) != 512 or b.size() != 512: raise ValueError('Finite replay budget mismatch')
        for i, row in enumerate(rows):
            for actual, expected in [(b.actions[i, 0], row['policy_proposal']), (b.observations[i, 0], row['reference_trace']['observation']),
                    (b.next_observations[i, 0], row['next_observation']), ([b.rewards[i, 0]], [row['reward']])]:
                np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0)
            if bool(b.dones[i, 0]) != row['done'] or bool(b.timeouts[i, 0]) != row['TimeLimit.truncated']:
                raise ValueError('V2 replay terminal/timeout mismatch')
        result = dict(scenario=selected, transitions=512, optimizer_updates=int(model._n_updates),
            actor_parameter_l1_change=change, replay_rows_checked=512, portable_actor=parity,
            task_terminals=sum(r['done'] for r in rows), timeouts=sum(r['TimeLimit.truncated'] for r in rows),
            learner_seed=7, benefit_verified=False, hardware_authorized=False)
        save(out/'training_result.json', result)
        return result
    except BaseException:
        model.save(out/'partial_model_failed.zip')
        model.save_replay_buffer(out/'partial_replay_failed.pkl')
        raise
    finally:
        env.close()


def evaluate(out, c, worlds, root):
    trained = validated_latest(root, ACTIONS[1])
    save(out/'dependencies.json', dependency_record(trained))
    if json.loads((trained/'task_checkpoint.json').read_text())['task_fingerprint'] != fingerprint():
        raise ValueError('Checkpoint objective mismatch')
    selected = json.loads((trained/'training_result.json').read_text())['scenario']
    c = scenario_config(c, selected)
    actor = PortableActor(trained, experiment_contract(c)['abi_sha256'])
    results = {arm: [] for arm in c['task']['evaluation_arms']}
    for arm in c['task']['evaluation_order']:
        result = rollout(out/(arm+'_'+str(len(results[arm]))), c, worlds[selected], arm, actor if arm == 'TD3_h5' else None)
        results[arm].append(result)
        save(out/'evaluation_progress.json', results)
        if result['physical_failure']: raise RuntimeError('Evaluation physical envelope failure; stop finite screen')
    result = dict(scenario=selected, arms=results, checkpoint=str(trained), task_id=c['task']['id'],
        learner_seeds=1, evaluation_runs_per_arm=2, independent_gazebo_seeds_verified=False,
        baseline='B0 same nominal profile; B_speed_control predefined V1 mean boost, diagnostic not tuned/optimal',
        conclusion='Fixed-task descriptive pilot; no accepted minimum effect, no benefit promotion',
        benefit_verified=False, hardware_authorized=False)
    save(out/'evaluation_result.json', result)
    return result


def run(root, action):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Serialize V2 launches even when callers use different output roots.
    # Legacy V1 workers predate this lock; do not launch them concurrently.
    global_lock = Path.home()/'nino_research/.factory_sim.lock'
    global_lock.parent.mkdir(parents=True, exist_ok=True)
    with global_lock.open('a') as shared, (root/'.job.lock').open('a') as lock:
        fcntl.flock(shared, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+action)
        out.mkdir()
        c = config()
        current, started, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        save(out/'config.json', c)
        save(out/'protocol.json', c['task'])
        def timeout(signum, frame): raise TimeoutError('V2 finite wall deadline; retain partial data')
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(c['task']['wall_deadline_per_job_s'])
        emit(action, 'Start finite tracking/stop V2', 0., directory=str(out))
        try:
            worlds = prepare_worlds(out)
            result = baselines(out, c, worlds) if action == ACTIONS[0] else train(out, c, worlds, root) if action == ACTIONS[1] else evaluate(out, c, worlds, root)
            if fingerprint() != current: raise RuntimeError('Task sources changed during run')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            save(out/'job.json', dict(action=action, status=status, error=error, wall_s=time.monotonic()-started, hardware_actions=0))
            save(out/'manifest.json', dict(action=action, status=status, task_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in out.rglob('*') if p.is_file() and p.name != 'manifest.json'}))
            path = root/'state.json'
            state = json.loads(path.read_text()) if path.exists() else dict(schema_version=1, latest={}, runs=[])
            state['runs'].append(dict(action=action, path=out.name, status=status, error=error))
            if status == 'completed': state['latest'][action] = out.name
            save(path, state)
            emit(action, status, 1. if status == 'completed' else None, directory=str(out), result=result, error=error)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=ACTIONS)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try: run(args.output, args.action)
    except (Exception, KeyboardInterrupt) as exc:
        print('V2 sim task failed/retained:', exc, flush=True)
        return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
