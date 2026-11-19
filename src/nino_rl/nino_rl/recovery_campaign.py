"""Full-episode recovery100 research training. Simulation only."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import pickle
import shutil
import signal
import tarfile
from tempfile import TemporaryDirectory
import time
import uuid

import numpy as np

from .recovery_campaign_contract import (CAMPAIGN_KIND, CHECKPOINT_KIND, PHYSICAL_TERMINALS,
    CampaignRequest, algorithm, campaign_identity, inspect_checkpoint, require_ready)
from .recovery_curriculum import FamilyCurriculum
from .recovery_training import (RecoveryBankEnv, capture_rng, restore_rng, verify_replay_row)
from .recovery_training_contract import EpisodeAssignment, read_json, sha
from .residual_workflow import save
from .unknown_step_runner import append


class CampaignStop(Exception):
    pass


def file_manifest(root):
    root = Path(root)
    return {str(p.relative_to(root)): sha(p) for p in root.rglob('*')
            if p.is_file() and p != root/'manifest.json'}


class EpisodeRetention:
    def __init__(self, root, request):
        self.root, self.request = Path(root).resolve(), request
        self.records = []

    def finish(self, episode, assignment, outcome, qc):
        record = self.root/'episode_records'/episode
        record.mkdir(parents=True, exist_ok=True)
        raw = self.root/'episodes'/episode
        if raw.is_dir():
            archive = record/'raw.tar.gz'
            manifest = file_manifest(raw)
            with tarfile.open(archive, 'w:gz', compresslevel=1) as stream:
                stream.add(raw, arcname=episode)
            with tarfile.open(archive, 'r:gz') as stream:
                members = {m.name for m in stream.getmembers() if m.isfile()}
                if members != {episode+'/'+name for name in manifest}:
                    raise ValueError('Episode archive does not cover every raw file')
                for name, expected in manifest.items():
                    digest = hashlib.sha256()
                    with stream.extractfile(episode+'/'+name) as content:
                        for chunk in iter(lambda:content.read(1024*1024), b''):
                            digest.update(chunk)
                    if digest.hexdigest() != expected:
                        raise ValueError('Episode archive payload differs from retained source')
            receipt = dict(archive_sha256=sha(archive), raw_files=manifest,
                           compressed_bytes=archive.stat().st_size, raw_qc=qc)
            save(record/'archive.json', receipt)
            shutil.rmtree(raw)
        else:
            archive, receipt = None, dict(raw_files={}, raw_qc=qc)
        summary = dict(episode_id=episode, assignment=assignment, outcome=outcome,
            source_qc=qc, task_success=outcome.get('task_success') is True,
            archive=None if archive is None else str(archive),
            archive_sha256=receipt.get('archive_sha256'), retained_raw=archive is not None)
        save(record/'summary.json', summary)
        self.records.append(summary)
        self.prune_successes()
        save(self.root/'retention.json', self.records)

    def retained_bytes(self):
        return sum((self.root/r['archive']).stat().st_size for r in self.records
                   if r.get('retained_raw'))

    def prune_successes(self):
        successes = [r for r in self.records if r['task_success'] and r.get('retained_raw')
                     and Path(r['archive']).is_relative_to(self.root)]
        keep = {r['episode_id'] for r in successes[-self.request.successful_raw_keep:]}
        if self.request.successful_raw_keep == 0:
            keep.clear()
        first = {}
        for row in successes:
            first.setdefault(row['assignment']['family'], row['episode_id'])
        keep.update(first.values())
        for row in successes:
            if row['episode_id'] in keep:
                continue
            path = (self.root/row['archive']).resolve()
            if not path.is_relative_to(self.root/'episode_records') or sha(path) != row['archive_sha256']:
                raise ValueError('Refuse pruning an unowned or changed episode archive')
            save(path.with_name('pruned.json'),dict(kind='nino_campaign_success_raw_pruned_v1',
                archive=str(path),archive_sha256=row['archive_sha256'],task_success=True,
                source_qc_valid=True))
            path.unlink()
            row.update(retained_raw=False, prune_reason='successful_episode_retention_limit')
            save(self.root/'episode_records'/row['episode_id']/'summary.json', row)


class CampaignEnv(RecoveryBankEnv):
    def __init__(self, out, request, ready, *, lifecycle=None, environment_factory=None,
                 episode_qc=None, physical_terminals=None):
        super().__init__(out, request, ready, lifecycle=lifecycle,
                         environment_factory=environment_factory)
        self.ready, self.retention = ready, EpisodeRetention(out, request)
        self.physical_terminals = PHYSICAL_TERMINALS if physical_terminals is None else physical_terminals
        settings = dict(self.config['curriculum'], maximum_stage=0)
        self.curricula = {f: FamilyCurriculum(f, request.seed, settings) for f in request.families}
        self.episode_qc = episode_qc or self._retained_episode_qc
        self.qc_records = {}
        self.current_trace = None
        self.current_limit = 400
        self.artifact_roots = [str(self.out.resolve())]

    def reset(self, *, seed=None, options=None):
        from . import recovery_runner as runner
        if self.phase != 'ready':
            raise RuntimeError('Finish prior campaign episode before reset')
        self.require_resources()
        if self.count >= self.request.transitions or self.launch_attempts >= self.request.maximum_launches:
            raise CampaignStop('campaign_budget')
        family = self.request.families[self.cursor % len(self.request.families)]
        layout = self.ready.layout(family, 0)
        c, g, task, condition = runner.runtime_configuration(self.config, layout)
        self.backend._close_current()
        self.backend.world = layout['world']
        self.backend.config, self.backend.gconf = deepcopy(c), deepcopy(g)
        self.backend.protocol, self.backend.condition = deepcopy(task), deepcopy(condition)
        assignment = EpisodeAssignment(f'episode_{self.launch_attempts}', family, 0,
                                      layout['id'], layout['world_sha256'])
        self.current = asdict(assignment)
        self.assignments.append(self.current)
        self.cursor += 1
        self.launch_attempts += 1
        self.current_limit = min(400, self.request.transitions-self.count)
        record = self.out/'episode_records'/assignment.episode_id
        record.mkdir(parents=True)
        self.current_trace = record/'environment_trace.jsonl'
        self.phase = 'failed'
        self.inner = self.environment_factory(self.config, layout, self.ready.bank['envelope'],
                                              self.backend, c)
        observation, info = self.inner.reset(seed=layout['seed'])
        save(self.out/(assignment.episode_id+'_reset.json'), dict(reset=info,
            assignment=self.current, private_layout=layout, environment_identity=self.inner.identity))
        self.episode_steps, self.last, self.phase = 0, None, 'active'
        return observation, dict(info, recovery_assignment=self.current)

    def step(self, action):
        if self.phase != 'active':
            raise RuntimeError('No active campaign episode')
        self.require_resources()
        observation, reward, term, trunc, info = self.inner.step(action)
        info = deepcopy(info)
        if info['task'].get('measurement_valid') is not True or term and (
                trunc or info['task'].get('termination_reason') not in self.physical_terminals) or trunc and (
                info['task'].get('termination_reason') != 'external_cutoff'
                or info.get('termination_reason') != 'time_limit'):
            raise ValueError('Campaign transition is not an ordinary measurement-valid physical task result')
        self.episode_steps += 1
        administrative = not term and not trunc and self.episode_steps >= self.current_limit
        if administrative:
            trunc = True
            reason = 'campaign_transition_limit' if self.count+1 >= self.request.transitions else 'campaign_episode_limit'
            info['task'].update(terminated=False, truncated=True, right_censored=True,
                               task_success=False, termination_reason=reason)
            if 'end_reason' in info['task']:
                info['task'].update(end_reason='campaign_cutoff', bootstrap=True)
                info['reward_state']['closed_reason'] = 'campaign_cutoff'
                info['termination_reason'] = reason
        info['TimeLimit.truncated'] = bool(trunc and not term)
        self.last = dict(info, episode=self.launch_attempts-1, step=self.episode_steps,
            global_step=self.count+1, assignment=self.current, reward=float(reward),
            terminated=bool(term), truncated=bool(trunc), done=bool(term or trunc),
            administrative_censor=administrative)
        append(self.current_trace, self.last)
        self.count += 1
        if term or trunc:
            self.phase = 'pending'
        return observation, reward, term, trunc, info

    def _retained_episode_qc(self, episode):
        from . import recovery_runner as runner
        with TemporaryDirectory(prefix='nino_campaign_episode_qc_') as temporary:
            audit = Path(temporary)
            (audit/'episodes').mkdir()
            (audit/'episodes'/episode).symlink_to(self.out/'episodes'/episode, target_is_directory=True)
            (audit/(episode+'_reset.json')).symlink_to(self.out/(episode+'_reset.json'))
            (audit/'environment_trace.jsonl').symlink_to(self.current_trace)
            qc = runner.raw_qc(audit)
        save(self.out/'episode_records'/episode/'source_qc.json', qc)
        return qc

    def finish_stored_episode(self):
        if self.phase != 'pending':
            raise RuntimeError('No stored terminal campaign episode')
        self.phase = 'failed'
        self.backend._close_current()
        episode = self.current['episode_id']
        qc = self.episode_qc(episode)
        self.qc_records[episode] = qc
        outcome = dict(self.last['task'], terminated=self.last['terminated'], truncated=self.last['truncated'])
        if qc.get('valid') is not True or outcome.get('measurement_valid') is not True:
            raise ValueError('Campaign episode measurement/backend QC failed')
        if outcome['terminated'] and (outcome['truncated']
                or outcome.get('termination_reason') not in self.physical_terminals):
            raise ValueError('Campaign terminal outcome is not an ordinary physical task result')
        if self.last['administrative_censor'] or outcome['truncated'] and not outcome['terminated']:
            self.censored.append(dict(assignment=self.current, outcome=outcome))
        else:
            self.curricula[self.current['family']].record(episode, 0, outcome)
            self.completed.append(dict(assignment=self.current, outcome=outcome))
        self.phase = 'ready'
        self.retention.finish(episode, self.current, outcome, qc)
        return self.audit_sources()

    def audit_sources(self):
        expected = {row['episode_id'] for row in self.assignments}
        valid = bool(expected) and expected == set(self.qc_records) and all(
            row.get('valid') is True for row in self.qc_records.values())
        result = dict(valid=valid, episodes=deepcopy(self.qc_records),
                      summaries_preserved=True, raw_retention='successful bounded; all failures kept')
        save(self.out/'source_qc.json', result)
        return result

    def state(self):
        return dict(super().state(), episode_qc=deepcopy(self.qc_records),
                    retention=deepcopy(self.retention.records),artifact_roots=self.artifact_roots)

    def restore(self, state):
        super().restore(state)
        self.qc_records = deepcopy(state['episode_qc'])
        self.retention.records = deepcopy(state['retention'])
        parent_root = self.request.resume.parent.parent.resolve()
        roots = state.get('artifact_roots',[])
        if (not roots or Path(roots[0]).resolve() != parent_root
                or any(not Path(root).is_absolute() for root in roots)):
            raise ValueError('Resumed campaign artifact ownership differs')
        self.artifact_roots = [str(self.out.resolve()),*roots]
        for row in self.retention.records:
            if not row.get('retained_raw'):
                continue
            path = Path(row['archive']).resolve()
            if not any(path.is_relative_to(Path(root)/'episode_records') for root in roots):
                raise ValueError('Resumed episode archive is outside its campaign')
            if path.is_file():
                if sha(path) != row['archive_sha256']:
                    raise ValueError('Resumed retained episode archive changed')
                continue
            receipt = read_json(path.with_name('pruned.json')) if path.with_name('pruned.json').is_file() else None
            expected = dict(kind='nino_campaign_success_raw_pruned_v1',archive=str(path),
                archive_sha256=row['archive_sha256'],task_success=True,source_qc_valid=True)
            if row.get('task_success') is not True or receipt != expected:
                raise ValueError('Resumed retained episode archive is missing, changed, or outside its campaign')
            row.update(retained_raw=False,prune_reason='verified_success_prune_after_checkpoint')


def build_model(vec, request, settings=None):
    from stable_baselines3 import TD3
    from stable_baselines3.common.noise import NormalActionNoise
    settings = algorithm(request) if settings is None else settings
    keys = ('gamma', 'tau', 'batch_size', 'buffer_size', 'learning_starts', 'policy_delay',
            'target_policy_noise', 'target_noise_clip', 'train_freq', 'gradient_steps')
    return TD3('MlpPolicy', vec, seed=request.seed, device='cpu',
        **{k: settings[k] for k in keys}, learning_rate=settings['actor_lr'],
        policy_kwargs=dict(net_arch=settings['network_arch']),
        tensorboard_log=None, action_noise=NormalActionNoise(np.zeros(1),
        np.ones(1)*settings['exploration_noise']))


@dataclass(frozen=True)
class CampaignOperations:
    kind: str = CAMPAIGN_KIND
    checkpoint_kind: str = CHECKPOINT_KIND
    algorithm: object = algorithm
    inspect: object = inspect_checkpoint
    source_check: object = None
    sparse_checkpoints: bool = False


def write_checkpoint(model, out, request, identity, env, verified, *, qualified, reason,
                     milestone=False, operations=None):
    import torch
    operations = operations or CampaignOperations()
    from .common_training_studio_v2 import actor_steps
    directory = Path(out)/'checkpoints'
    directory.mkdir(exist_ok=True)
    pending = directory/('.pending_'+uuid.uuid4().hex)
    pending.mkdir()
    n = int(model.num_timesteps)
    boundary = env.phase == 'ready'
    qc = env.audit_sources()
    if not all(torch.isfinite(parameter).all() for parameter in model.policy.parameters()):
        raise ValueError('Nonfinite campaign policy cannot be checkpointed as resumable')
    eligible = bool(qualified and boundary and qc['valid'] and verified == n)
    model.save(pending/'model.zip')
    model.save_replay_buffer(pending/'replay_buffer.pkl')
    save(pending/'identity.json', identity)
    save(pending/'state.json', env.state())
    with (pending/'rng.pkl').open('wb') as stream:
        pickle.dump(capture_rng(model), stream)
    save(pending/'source_qc.json', qc)
    save(pending/'replay_audit.json', dict(valid=verified == n, rows_verified=verified))
    save(pending/'checkpoint.json', dict(kind=operations.checkpoint_kind, global_steps=n,
        replay_size=int(model.replay_buffer.size()), critic_updates=int(model._n_updates),
        actor_updates=actor_steps(model), episode_boundary=boundary, optimizer_boundary=True,
        qualified=eligible, resumable=eligible, reason=reason,milestone=bool(milestone),
        continuation='fresh_episode_only', physical_continuation_bit_exact=False))
    save(pending/'manifest.json', file_manifest(pending))
    operations.inspect(pending, expected_identity=identity, require_resumable=False)
    target = directory/f'step_{n:06d}_{uuid.uuid4().hex[:8]}'
    pending.rename(target)
    save(Path(out)/'latest.json', dict(path=str(target), steps=n, manifest_sha256=sha(target/'manifest.json')))
    checkpoints = sorted((p for p in directory.glob('step_*') if p.is_dir()), key=lambda p:p.name)
    protected = set(checkpoints[-2:])
    protected.update(p for p in checkpoints if read_json(p/'checkpoint.json').get('milestone') is True)
    if len(protected) > request.checkpoint_keep:
        raise ValueError('Campaign checkpoint retention exceeds its declared budget')
    for old in checkpoints:
        if old in protected:
            continue
        operations.inspect(old, expected_identity=identity, require_resumable=False)
        shutil.rmtree(old)
    return target


def train(out, request, ready, identity, *, env=None, stop_after=None, operations=None):
    import torch
    from stable_baselines3 import TD3
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.monitor import Monitor
    from .common_training_studio_v2 import actor_steps
    from .studio_deferred_reset import DeferredResetVecEnv
    from . import recovery_runner as runner
    out = Path(out)
    operations = operations or CampaignOperations()
    env = env or CampaignEnv(out, request, ready)
    vec = DeferredResetVecEnv(Monitor(env))
    model, verified, checkpoint, error, stop_reason = None, 0, None, None, 'transition_budget'
    last_checkpoint_step = 0
    pause = dict(requested=False)
    prior_signals = {}
    started = time.monotonic()
    torch.set_num_threads(1)

    class Trace(BaseCallback):
        def _on_step(self):
            np.testing.assert_allclose(self.locals['buffer_actions'][0], env.last['replay_action'],
                                       atol=2e-6, rtol=0.)
            env.last['reward'] = float(self.locals['rewards'][0])
            return True

        def _on_rollout_end(self):
            nonlocal verified
            verify_replay_row(model, env.last, (int(model.replay_buffer.pos)-1)%model.buffer_size)
            verified += 1
            if vec.pending_reset:
                env.finish_stored_episode()

        def _on_rollout_start(self):
            nonlocal checkpoint, last_checkpoint_step, stop_reason
            n = int(model.num_timesteps)
            save(out/'progress.json', dict(kind=operations.kind,status='running',global_steps=n,
                target_steps=request.transitions,replay_rows_verified=verified,
                actor_updates=actor_steps(model),critic_updates=int(model._n_updates),
                episode=env.launch_attempts-1,family=None if env.current is None else env.current['family'],
                phase='optimizer_complete',elapsed_wall_s=time.monotonic()-started))
            model.logger.record('campaign/replay_rows_verified',verified)
            model.logger.record('campaign/actor_updates',actor_steps(model))
            model.logger.record('campaign/critic_updates',int(model._n_updates))
            if n%100 == 0:
                model.logger.dump(n)
            if (out/'STOP').exists():
                pause['requested'] = True
            if not vec.pending_reset:
                return
            milestone = n//request.checkpoint_every > last_checkpoint_step//request.checkpoint_every
            warmup = operations.algorithm(request)['learning_starts']
            early = last_checkpoint_step == 0 or last_checkpoint_step <= warmup < n
            if not operations.sparse_checkpoints or milestone or early or pause['requested'] or stop_after is not None and n >= stop_after:
                checkpoint = write_checkpoint(model,out,request,identity,env,verified,
                    qualified=True,reason='episode_boundary',milestone=milestone,operations=operations)
                last_checkpoint_step = n
            if pause['requested'] or stop_after is not None and n >= stop_after:
                stop_reason = 'paused_at_episode_boundary'
                raise CampaignStop(stop_reason)
            if env.launch_attempts >= request.maximum_launches:
                stop_reason = 'launch_budget_exhausted'
                raise CampaignStop(stop_reason)
            if env.retention.retained_bytes() > request.raw_retention_bytes:
                stop_reason = 'raw_retention_budget'
                raise CampaignStop(stop_reason)
            vec.reset_after_store(model)

    try:
        if request.resume is None:
            model = build_model(vec, request, operations.algorithm(request))
        else:
            inspected = operations.inspect(request.resume, expected_identity=identity)
            if inspected['state']['transitions'] >= request.transitions:
                raise ValueError('Campaign transition budget already spent')
            model = TD3.load(Path(inspected['path'])/'model.zip', env=vec, device='cpu',force_reset=False)
            model.load_replay_buffer(Path(inspected['path'])/'replay_buffer.pkl')
            env.restore(inspected['state'])
            verified = inspected['replay_audit']['rows_verified']
            if int(model.num_timesteps) != verified or model.replay_buffer.size() != verified:
                raise ValueError('Resumed campaign model/replay counters differ')
            with (Path(inspected['path'])/'rng.pkl').open('rb') as stream:
                restore_rng(model,pickle.load(stream))
            vec.pending_reset = True
            last_checkpoint_step = verified
        model.tensorboard_log = str(out/'tensorboard')
        before = [p.detach().clone() for p in model.actor.parameters()]
        for signum in (signal.SIGINT,signal.SIGTERM):
            prior_signals[signum] = signal.signal(signum,lambda *_:pause.update(requested=True))
        try:
            model.learn(total_timesteps=request.transitions-int(model.num_timesteps), callback=Trace(),
                        reset_num_timesteps=request.resume is None,log_interval=1)
        except CampaignStop as exc:
            stop_reason = str(exc)
        source_pass = (operations.source_check or runner.sources)() == identity['source_pins']
        valid = bool(source_pass and env.audit_sources()['valid'] and verified == model.num_timesteps)
        if not valid:
            raise ValueError('Campaign final source/replay audit failed')
        if verified > operations.algorithm(request)['learning_starts'] and (
                model._n_updates <= 0 or actor_steps(model) <= 0):
            raise ValueError('Research campaign failed to update the TD3 actor and critic')
        checkpoint = write_checkpoint(model,out,request,identity,env,verified,
            qualified=True,reason=stop_reason,
            milestone=verified//request.checkpoint_every > last_checkpoint_step//request.checkpoint_every,operations=operations)
        result = dict(status='completed' if verified == request.transitions else 'paused',
            stop_reason=stop_reason, global_transitions=int(model.num_timesteps),
            replay_rows_verified=verified, launch_attempts=env.launch_attempts,
            critic_updates=int(model._n_updates), actor_updates=actor_steps(model),
            actor_parameter_l1_change=sum(float((p.detach()-old).abs().sum())
                for p,old in zip(model.actor.parameters(),before)),
            checkpoint=str(checkpoint), checkpoint_qualified=True, source_identity_pass=source_pass,
            source_qc=env.audit_sources(), hardware_actions=0, learned_benefit_verified=False)
        save(out/'result.json',result)
        save(out/'progress.json',dict(result,global_steps=int(model.num_timesteps),
            target_steps=request.transitions,phase='closed'))
        return result
    except BaseException as exc:
        error = repr(exc)
        failure = dict(status='failed',error=error,global_transitions=verified,
            latest_boundary_checkpoint=None if checkpoint is None else str(checkpoint),
            hardware_actions=0,learned_benefit_verified=False)
        save(out/'result.json',failure)
        save(out/'progress.json',dict(failure,global_steps=verified,
            target_steps=request.transitions,phase='failed'))
        raise
    finally:
        for signum,handler in prior_signals.items():
            signal.signal(signum,handler)
        closure_error = None
        try:
            vec.close()
        except BaseException as exc:
            closure_error = repr(exc)
        save(out/'job.json',dict(kind=operations.kind,status='failed' if error or closure_error else 'closed',
            error=error,closure_error=closure_error,wall_s=time.monotonic()-started,
            source_pins=identity['source_pins'],clean_closure=closure_error is None,hardware_actions=0))
        if closure_error:
            failure = dict(status='failed',error=error,closure_error=closure_error,
                global_transitions=verified,clean_closure=False,hardware_actions=0)
            save(out/'result.json',failure)
            save(out/'progress.json',dict(failure,global_steps=verified,
                target_steps=request.transitions,phase='failed'))
            if error is None:
                raise RuntimeError('Campaign lifecycle closure failed: '+closure_error)


def probe(request, root):
    from . import recovery_runner as runner
    from .recovery_startup import RecoveryBackend
    from .reliable_episode import EpisodeLifecycle
    root = Path(root).expanduser().resolve()
    bank = runner.require_bank(request.prepared_root)
    pins = runner.sources()
    results = {}
    started = time.monotonic()
    for family in request.families:
        if time.monotonic()-started > request.wall_seconds:
            raise TimeoutError('Readiness probe wall budget exhausted')
        out = root/'readiness'/f'{family}_s0'
        out.mkdir(parents=True)
        layout = next(r for r in bank['layouts'] if
                      (r['family'],r['stage'],r['split']) == (family,0,'development'))
        c,g,task,condition = runner.runtime_configuration(bank['config'],layout)
        lp = dict(training_episodes_per_seed_maximum=1,observer_start_deadline_s=15.,
            feedback_deadline_s=5.,observer_ipc_grace_s=1.,maximum_support_age_ns=40_000_000)
        backend = EpisodeLifecycle(c,out/'episodes',layout['world'],g,task,condition,lp,
            backend_factory=lambda *args:RecoveryBackend(*args,expected_envelope=bank['envelope']))
        env = runner.environment(bank['config'],layout,bank['envelope'],backend,c)
        error, closed, last = None, False, None
        try:
            _,info = env.reset(seed=layout['seed'])
            save(out/'episode_0_reset.json',dict(reset=info,private_layout=layout,
                                               environment_identity=env.identity))
            for n in range(400):
                if time.monotonic()-started > request.wall_seconds:
                    raise TimeoutError('Readiness probe wall budget exhausted')
                if shutil.disk_usage(out).free < request.minimum_free_bytes:
                    raise OSError('Probe disk reserve reached')
                _,reward,term,trunc,info = env.step([0.])
                last = dict(info,episode=0,step=n+1,reward=reward,terminated=term,truncated=trunc)
                append(out/'environment_trace.jsonl',last)
                if term or trunc:
                    break
            if not last or not(last['terminated'] or last['truncated']):
                raise ValueError('Readiness probe has no classified terminal outcome')
            if (last['terminated'] is not True or last['truncated'] is not False
                    or last['task'].get('termination_reason') not in PHYSICAL_TERMINALS):
                raise ValueError('Readiness probe encountered a backend fault or unknown terminal')
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            try:
                env.close()
                closed = True
            finally:
                qc = runner.raw_qc(out)
                result = dict(family=family,stage=0,layout_id=layout['id'],
                    world_sha256=layout['world_sha256'],
                    bank_sha256=sha(request.prepared_root/'inputs/bank.json'),
                    source_qc=qc,outcome=None if last is None else last['task'],
                    classical_success_required=False,optimizer_updates=0)
                save(out/'result.json',result)
                save(out/'job.json',dict(kind=CAMPAIGN_KIND,action='readiness-probe',
                    status='failed' if error else 'completed',error=error,
                    clean_closure=closed,source_pins=pins,hardware_actions=0))
                save(out/'manifest.json',file_manifest(out))
        if (not qc['valid'] or last['task'].get('measurement_valid') is not True
                or runner.sources() != pins):
            raise ValueError('Readiness probe measurement/source failure')
        results[family] = result
    require_ready(request,root)
    return dict(kind=CAMPAIGN_KIND,readiness_pass=True,families=list(results),hardware_actions=0)


def run(request,ready_root,out):
    from . import recovery_runner as runner
    ready = require_ready(request,ready_root)
    identity = campaign_identity(request,ready)
    out = Path(out).expanduser().resolve()
    out.mkdir(parents=True)
    if shutil.disk_usage(out).free < request.minimum_free_bytes+2**28:
        raise OSError('Campaign disk reserve unavailable')
    save(out/'request.json',request.state())
    save(out/'identity.json',identity)
    result = train(out,request,ready,identity)
    if runner.sources() != identity['source_pins']:
        raise ValueError('Campaign sources changed during training')
    save(out/'manifest.json',file_manifest(out))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('probe','check-ready','run','inspect-checkpoint'))
    parser.add_argument('--request',type=Path)
    parser.add_argument('--readiness',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--checkpoint',type=Path)
    args = parser.parse_args()
    if args.action == 'inspect-checkpoint':
        if args.checkpoint is None:
            parser.error('--checkpoint is required')
        result = inspect_checkpoint(args.checkpoint)
    else:
        if args.request is None:
            parser.error('--request is required')
        request = CampaignRequest.parse(read_json(args.request))
        if args.action == 'check-ready':
            if args.readiness is None:
                parser.error('--readiness is required')
            ready = require_ready(request,args.readiness)
            result = dict(readiness_pass=True,families=list(ready.receipts),hardware_actions=0)
        else:
            if args.output is None or args.action == 'run' and args.readiness is None:
                parser.error('--output and, for run, --readiness are required')
            lockpath = Path.home()/'nino_research/.factory_sim.lock'
            lockpath.parent.mkdir(parents=True,exist_ok=True)
            with lockpath.open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                result = probe(request,args.output) if args.action == 'probe' else run(
                    request,args.readiness,args.output)
    print(json.dumps(result,allow_nan=False),flush=True)


if __name__ == '__main__':
    main()
