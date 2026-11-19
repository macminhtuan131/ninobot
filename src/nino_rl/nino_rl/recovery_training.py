"""Explicit bounded live recovery smoke. No hardware or long training mode."""
from copy import deepcopy
from dataclasses import asdict
import argparse
import fcntl
import json
from pathlib import Path
import pickle
import random
import shutil
import signal
import time
import uuid

import gymnasium as gym
import numpy as np

from .recovery_curriculum import FamilyCurriculum
from .recovery_training_contract import (CHECKPOINT_KIND, EpisodeAssignment,
    REQUIRED_FILES, RecoverySmokeRequest, inspect_recovery_checkpoint,
    require_live_qualification, sha, training_identity)
from .residual_workflow import save


class _LaunchBudgetSpent(Exception):
    pass


class RecoveryBankEnv(gym.Env):
    observation_space = gym.spaces.Box(-5., 5., shape=(100,), dtype=np.float32)
    action_space = gym.spaces.Box(-1., 1., shape=(1,), dtype=np.float32)

    def __init__(self, out, request, qualified, *, lifecycle=None,
                 environment_factory=None, qc=None):
        from . import recovery_runner as runner
        from .recovery_startup import RecoveryBackend
        from .reliable_episode import EpisodeLifecycle
        self.out, self.request, self.qualified = Path(out), request, qualified
        self.config = qualified.bank['config']
        self.environment_factory = environment_factory or runner.environment
        self.qc = qc or runner.raw_qc
        self.started = time.monotonic()
        self.cursor, self.count, self.launch_attempts = 0, 0, 0
        self.assignments, self.completed, self.censored = [], [], []
        self.curricula = {f: FamilyCurriculum(f, request.seed, self.config['curriculum'])
                          for f in request.families}
        self.phase, self.inner, self.last, self.current = 'ready', None, None, None
        self.episode_steps = 0
        if lifecycle is None:
            layout = qualified.layout(request.families[0], 0)
            c, g, task, condition = runner.runtime_configuration(self.config, layout)
            lp = dict(training_episodes_per_seed_maximum=request.maximum_launches,
                observer_start_deadline_s=15., feedback_deadline_s=5., observer_ipc_grace_s=1.,
                maximum_support_age_ns=40_000_000)
            lifecycle = EpisodeLifecycle(c, self.out/'episodes', layout['world'], g, task,
                condition, lp, backend_factory=lambda *args: RecoveryBackend(
                    *args, expected_envelope=qualified.bank['envelope']))
        self.backend = lifecycle

    def require_resources(self):
        if time.monotonic()-self.started >= self.request.wall_seconds:
            raise TimeoutError('Recovery smoke wall budget exhausted')
        if shutil.disk_usage(self.out).free < self.request.minimum_free_bytes:
            raise ValueError('Recovery smoke disk reserve reached')

    def reset(self, *, seed=None, options=None):
        from . import recovery_runner as runner
        super().reset(seed=seed)
        if self.phase != 'ready':
            raise RuntimeError('Finish stored episode QC before recovery reset')
        self.require_resources()
        if self.count >= self.request.transitions or self.launch_attempts >= self.request.maximum_launches:
            raise ValueError('Recovery smoke budget exhausted')
        family = self.request.families[self.cursor % len(self.request.families)]
        stage = self.curricula[family].sample_stage()
        layout = self.qualified.layout(family, stage)
        if family == 'mixed':
            runner.require_components(self.qualified.root, family)
        c, g, task, condition = runner.runtime_configuration(self.config, layout)
        self.backend._close_current()
        self.backend.world = layout['world']
        self.backend.config, self.backend.gconf = deepcopy(c), deepcopy(g)
        self.backend.protocol, self.backend.condition = deepcopy(task), deepcopy(condition)
        assignment = EpisodeAssignment(f'episode_{self.launch_attempts}', family, stage,
                                       layout['id'], layout['world_sha256'])
        self.current = asdict(assignment)
        self.assignments.append(self.current)
        self.cursor += 1
        self.launch_attempts += 1
        save(self.out/'assignments.json', self.assignments)
        self.phase = 'failed'
        self.inner = self.environment_factory(self.config, layout, self.qualified.bank['envelope'],
                                              self.backend, c)
        observation, info = self.inner.reset(seed=layout['seed'])
        self.episode_steps, self.last = 0, None
        save(self.out/(assignment.episode_id+'_reset.json'), dict(reset=info,
            assignment=self.current, private_layout=layout, environment_identity=self.inner.identity))
        self.phase = 'active'
        return observation, dict(info, recovery_assignment=self.current)

    def step(self, action):
        from .unknown_step_runner import append
        if self.phase != 'active':
            raise RuntimeError('Recovery episode is not active')
        self.require_resources()
        if self.count >= self.request.transitions:
            raise ValueError('Recovery transition budget exhausted')
        try:
            observation, reward, term, trunc, info = self.inner.step(action)
            info = deepcopy(info)
            self.episode_steps += 1
            administrative = (not term and not trunc
                              and self.episode_steps >= self.request.episode_transition_limit)
            if administrative:
                trunc = True
                info['task'].update(terminated=False, truncated=True, right_censored=True,
                    task_success=False, termination_reason='smoke_episode_limit')
                info.update(right_censored=True, termination_reason='smoke_episode_limit')
            info['TimeLimit.truncated'] = bool(trunc and not term)
            row = dict(info, episode=self.launch_attempts-1, step=self.episode_steps,
                global_step=self.count+1, assignment=self.current, reward=float(reward),
                terminated=bool(term), truncated=bool(trunc), done=bool(term or trunc),
                administrative_censor=administrative)
            append(self.out/'environment_trace.jsonl', row)
            self.last = row
            self.count += 1
            if term or trunc:
                self.phase = 'pending'
            return observation, reward, term, trunc, info
        except BaseException:
            self.phase = 'failed'
            raise

    def finish_stored_episode(self):
        if self.phase != 'pending':
            raise RuntimeError('No stored terminal recovery episode to finish')
        self.phase = 'failed'
        self.backend._close_current()
        qc = self.audit_sources()
        episode = self.current['episode_id']
        if qc.get('valid') is not True or qc.get('episodes', {}).get(episode, {}).get('valid') is not True:
            raise ValueError('Retained recovery episode source QC failed')
        outcome = dict(self.last['task'], terminated=self.last['terminated'],
                       truncated=self.last['truncated'])
        if self.last['administrative_censor'] or (outcome['truncated'] and not outcome['terminated']):
            self.censored.append(dict(assignment=self.current, outcome=outcome))
        else:
            if outcome.get('measurement_valid') is not True:
                raise ValueError('Invalid physical outcome cannot update recovery curriculum')
            self.curricula[self.current['family']].record(episode,
                self.current['sampled_stage'], outcome)
            self.completed.append(dict(assignment=self.current, outcome=outcome))
        self.phase = 'ready'
        save(self.out/'scheduler_state.json', self.state())
        return qc

    def audit_sources(self):
        qc = self.qc(self.out)
        expected = {row['episode_id'] for row in self.assignments}
        missing = expected-set(qc.get('episodes', {}))
        for episode in missing:
            qc.setdefault('episodes', {})[episode] = dict(valid=False,
                reasons=[dict(reason='missing_attempted_epoch_artifacts')])
        if missing:
            qc['valid'] = False
        save(self.out/'source_qc.json', qc)
        return qc

    def state(self):
        return dict(cursor=self.cursor, transitions=self.count, launch_attempts=self.launch_attempts,
            assignments=deepcopy(self.assignments), completed=deepcopy(self.completed),
            censored=deepcopy(self.censored),
            curricula={f: c.state() for f, c in self.curricula.items()})

    def restore(self, state):
        if self.phase != 'ready' or self.launch_attempts:
            raise ValueError('Recovery state restores only before the first launch')
        if (set(state['curricula']) != set(self.curricula)
                or state['cursor'] != state['launch_attempts']
                or len(state['assignments']) != state['launch_attempts']
                or len({a['episode_id'] for a in state['assignments']}) != state['launch_attempts']
                or len(state['completed'])+len(state['censored']) != state['launch_attempts']):
            raise ValueError('Invalid fresh-episode recovery scheduler state')
        for f, c in self.curricula.items():
            c.restore(state['curricula'][f])
        self.cursor, self.count, self.launch_attempts = (state[k] for k in
            ('cursor', 'transitions', 'launch_attempts'))
        self.assignments, self.completed, self.censored = (deepcopy(state[k]) for k in
            ('assignments', 'completed', 'censored'))
        self.backend.index = self.launch_attempts-1

    def close(self):
        if self.phase != 'closed':
            self.phase = 'closed'
            self.backend.close()


def verify_replay_row(model, row, index):
    replay = model.replay_buffer
    for actual, expected in ((replay.observations[index, 0], row['observation']),
            (replay.next_observations[index, 0], row['next_observation']),
            (replay.actions[index, 0], row['replay_action'])):
        np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0.)
    np.testing.assert_allclose(replay.actions[index, 0], row['requested_scalar_action'],
                               atol=2e-6, rtol=0.)
    if (replay.rewards[index, 0] != np.float32(row['reward'])
            or bool(replay.dones[index, 0]) != row['done']
            or bool(replay.timeouts[index, 0]) != row['TimeLimit.truncated']):
        raise ValueError('Recovery replay reward/terminal/timeout differs')


def capture_rng(model):
    import torch
    return dict(python=random.getstate(), numpy=np.random.get_state(), torch=torch.get_rng_state(),
        action_space=deepcopy(model.action_space.np_random.bit_generator.state),
        exploration=deepcopy(model.action_noise.__dict__))


def restore_rng(model, state):
    import torch
    random.setstate(state['python'])
    np.random.set_state(state['numpy'])
    torch.set_rng_state(state['torch'])
    model.action_space.np_random.bit_generator.state = deepcopy(state['action_space'])
    model.action_noise.__dict__.update(deepcopy(state['exploration']))


def write_checkpoint(model, out, identity, state, qc, replay_audit, *, boundary, qualified):
    from .common_training_studio_v2 import actor_steps
    directory = Path(out)/'checkpoints'
    directory.mkdir(exist_ok=True)
    target = directory/f'step_{state["transitions"]:06d}_{uuid.uuid4().hex[:8]}'
    pending = directory/('.pending_'+uuid.uuid4().hex)
    pending.mkdir()
    resumable = bool(boundary and qualified and qc.get('valid') is True
                     and replay_audit.get('valid') is True)
    model.save(pending/'model.zip')
    model.save_replay_buffer(pending/'replay_buffer.pkl')
    save(pending/'identity.json', identity)
    save(pending/'job_state.json', state)
    save(pending/'source_qc.json', qc)
    save(pending/'replay_audit.json', replay_audit)
    with (pending/'rng.pkl').open('wb') as stream:
        pickle.dump(capture_rng(model), stream, protocol=pickle.HIGHEST_PROTOCOL)
    metadata = dict(kind=CHECKPOINT_KIND,
        global_steps=state['transitions'], replay_size=int(model.replay_buffer.size()),
        critic_updates=int(model._n_updates), actor_updates=actor_steps(model),
        stored_episode_boundary=bool(boundary), episode_qc_pass=qc.get('valid') is True,
        qualified=bool(qualified), resumable=resumable,
        continuation='next_fresh_episode_only', physical_continuation_reproduced=False)
    if 'smoke_protocol' in identity:
        metadata['smoke_protocol'] = deepcopy(identity['smoke_protocol'])
    save(pending/'checkpoint.json', metadata)
    save(pending/'manifest.json', {name: sha(pending/name) for name in sorted(REQUIRED_FILES)})
    inspect_recovery_checkpoint(pending, expected_identity=identity)
    pending.rename(target)
    return target


def restore_checkpoint(model, environment, inspected):
    path = Path(inspected['path'])
    model.load_replay_buffer(path/'replay_buffer.pkl')
    environment.restore(inspected['state'])
    with (path/'rng.pkl').open('rb') as stream:
        restore_rng(model, pickle.load(stream))
    if (int(model.num_timesteps) != inspected['state']['transitions']
            or int(model.replay_buffer.size()) != inspected['state']['transitions']):
        raise ValueError('Loaded recovery model/replay counters differ')


def _learn(out, request, qualified, identity, inspected=None):
    import torch
    from stable_baselines3 import TD3
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.monitor import Monitor
    from .common_training_studio_v2 import actor_steps, build_model
    from .studio_deferred_reset import DeferredResetVecEnv
    env = RecoveryBankEnv(out, request, qualified)
    vec = DeferredResetVecEnv(Monitor(env))
    model = None
    rows, verified = [], 0 if inspected is None else inspected['state']['transitions']
    initial_steps, initial_launches = verified, 0 if inspected is None else inspected['state']['launch_attempts']
    stop_reason = 'transition_budget'
    last_checkpoint = None
    error = None
    torch.set_num_threads(1)

    class Trace(BaseCallback):
        def _on_step(self):
            row = deepcopy(env.last)
            row['reward'] = float(self.locals['rewards'][0])
            np.testing.assert_allclose(self.locals['buffer_actions'][0], row['replay_action'],
                                       atol=2e-6, rtol=0.)
            rows.append(row)
            return True

        def _on_rollout_end(self):
            nonlocal verified, stop_reason, last_checkpoint
            verify_replay_row(model, rows[-1], int(model.replay_buffer.pos)-1)
            verified += 1
            if vec.pending_reset:
                qc = env.finish_stored_episode()
                last_checkpoint = write_checkpoint(model, out, identity, env.state(), qc,
                    dict(valid=True, rows_verified=verified), boundary=True, qualified=True)
            if env.count >= request.transitions or (vec.pending_reset
                    and env.launch_attempts >= request.maximum_launches):
                stop_reason = ('transition_budget' if env.count >= request.transitions
                               else 'launch_budget_exhausted')
                if stop_reason == 'launch_budget_exhausted':
                    raise _LaunchBudgetSpent()
                return
            if vec.pending_reset:
                vec.reset_after_store(model)

    try:
        if inspected is None:
            model = build_model(vec, dict(profile=request.profile, seed=request.seed))
        else:
            model = TD3.load(Path(inspected['path'])/'model.zip', env=vec, device='cpu')
            restore_checkpoint(model, env, inspected)
        if model.train_freq.frequency != 1 or model.gradient_steps != 1:
            raise ValueError('Recovery requires one-step TD3 collect/store/verify')
        before = [p.detach().clone() for p in model.actor.parameters()]
        try:
            model.learn(total_timesteps=request.transitions-initial_steps, callback=Trace(),
                        reset_num_timesteps=inspected is None)
        except _LaunchBudgetSpent:
            pass
        for index, row in enumerate(rows, initial_steps):
            verify_replay_row(model, row, index)
        if not all(torch.isfinite(p).all() for p in model.policy.parameters()):
            raise ValueError('Nonfinite recovery model parameters')
        change = sum(float((p.detach()-old).abs().sum())
                     for p, old in zip(model.actor.parameters(), before))
        if verified-initial_steps > 32 and (model._n_updates <= 0 or actor_steps(model) <= 0 or change <= 0):
            raise ValueError('Recovery smoke did not update actor and critic')
    except BaseException as exc:
        error = repr(exc)
        raise
    finally:
        closure_error = None
        try:
            vec.close()
        except BaseException as exc:
            closure_error = repr(exc)
        qc = env.audit_sources()
        state = env.state()
        replay_size = 0 if model is None else int(model.replay_buffer.size())
        state['returned_transitions'] = state['transitions']
        state['transitions'] = replay_size
        replay_audit = dict(valid=verified == replay_size, rows_verified=verified)
        from . import recovery_runner as runner
        current_sources = runner.sources()
        source_identity_pass = current_sources == identity.get('source_pins', current_sources)
        family_transitions = {family: sum(row['assignment']['family'] == family
            for row in rows) for family in request.families}
        family_coverage_pass = (not request.protocol.all_families
                                or all(family_transitions.values()))
        valid = bool(error is None and closure_error is None and qc.get('valid') is True
                     and replay_audit['valid'] and source_identity_pass and family_coverage_pass)
        for passed, reason in ((error is None, 'exception'),
                (closure_error is None, 'closure_failure'),
                (qc.get('valid') is True, 'source_qc_failure'),
                (replay_audit['valid'], 'replay_audit_failure'),
                (source_identity_pass, 'source_identity_changed'),
                (family_coverage_pass, 'family_coverage_failure')):
            if not passed:
                stop_reason = reason
                break
        boundary = bool(env.last and env.last['done'] and env.phase == 'closed'
                        and len(env.completed)+len(env.censored) == env.launch_attempts)
        if model is not None:
            last_checkpoint = write_checkpoint(model, out, identity, state, qc, replay_audit,
                                               boundary=boundary, qualified=valid)
        result = dict(status='completed' if valid and replay_size == request.transitions else
                      'budget_exhausted' if valid else 'failed', stop_reason=stop_reason,
            global_transitions=replay_size, invocation_transitions=replay_size-initial_steps,
            launch_attempts=env.launch_attempts, invocation_launch_attempts=env.launch_attempts-initial_launches,
            returned_transitions=env.count, replay_rows_verified=verified,
            critic_updates=0 if model is None else int(model._n_updates),
            actor_updates=0 if model is None else actor_steps(model),
            actor_parameter_l1_change=locals().get('change'), source_qc=qc,
            source_identity_pass=source_identity_pass,
            clean_closure=closure_error is None, error=error or closure_error,
            checkpoint=None if last_checkpoint is None else str(last_checkpoint),
            checkpoint_qualified=valid, censored_episodes=len(env.censored),
            administrative_censors=sum(row['outcome'].get('termination_reason') ==
                'smoke_episode_limit' for row in env.censored),
            physical_completed_episodes=len(env.completed),
            learned_benefit_verified=False, generalization_verified=False,
            loaded_contact_verified=False, hardware_actions=0)
        if request.protocol.all_families:
            result.update(smoke_protocol=request.protocol.identity(),
                family_transitions=family_transitions, family_coverage_pass=family_coverage_pass)
        save(out/'result.json', result)
        if closure_error and error is None:
            raise RuntimeError(closure_error)
        if not valid and error is None:
            raise ValueError('Final retained recovery audit failed')
    return result


def run_live_smoke(root, request):
    from . import recovery_runner as runner
    if not isinstance(request, RecoverySmokeRequest):
        request = RecoverySmokeRequest.parse(request)
    qualified = require_live_qualification(request)
    identity = training_identity(request, qualified)
    inspected = None
    if request.resume is not None:
        inspected = inspect_recovery_checkpoint(request.resume, expected_identity=identity,
                                                 require_resumable=True)
        if (inspected['state']['transitions'] >= request.transitions
                or inspected['state']['launch_attempts'] >= request.maximum_launches):
            raise ValueError('Recovery smoke campaign budget is spent; no resume launch permitted')
        raise ValueError('Partial live-smoke resume is not released; bundle restore is fixture-tested only')
    out = Path(root).expanduser().resolve()
    if out.exists():
        raise ValueError('Recovery output already exists; retain the immutable attempt')
    out.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(out.parent).free < request.minimum_free_bytes:
        raise ValueError('Recovery smoke disk reserve unavailable')
    lock_path = Path.home()/'nino_research/.factory_sim.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out.mkdir()
        save(out/'request.json', request.state())
        save(out/'identity.json', identity)
        save(out/'disk_budget.json', dict(minimum_free_bytes=request.minimum_free_bytes,
            estimated_raw_replay_checkpoint_bytes=536870912, estimate_not_measurement=True))
        started, error = time.monotonic(), None
        previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(
            TimeoutError('Recovery smoke wall budget exhausted')))
        signal.alarm(request.wall_seconds)
        try:
            result = _learn(out, request, qualified, identity, inspected)
            if runner.sources() != identity['source_pins']:
                raise ValueError('Recovery sources changed during live smoke')
            return result
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            save(out/'job.json', dict(action='live-smoke', status='failed' if error else 'completed',
                error=error, wall_s=time.monotonic()-started, source_pins=identity['source_pins'],
                hardware_actions=0))
            save(out/'manifest.json', {str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                                      if p.is_file() and p != out/'manifest.json'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('live-smoke', 'inspect-checkpoint'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--checkpoint', type=Path)
    args = parser.parse_args()
    if args.action == 'inspect-checkpoint':
        if args.checkpoint is None:
            parser.error('--checkpoint is required')
        result = inspect_recovery_checkpoint(args.checkpoint)
    else:
        if args.request is None or args.output is None:
            parser.error('--request and --output are required')
        result = run_live_smoke(args.output,
            RecoverySmokeRequest.parse(json.loads(args.request.read_text())))
    print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
