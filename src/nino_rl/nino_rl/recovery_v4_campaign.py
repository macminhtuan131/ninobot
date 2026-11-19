"""Qualified simulator campaigns for causal slowdown TD3. No hardware access."""
from copy import deepcopy
from dataclasses import asdict, replace
import argparse
import fcntl
import json
import math
from pathlib import Path
import shutil
import time

import numpy as np

from . import recovery_runner as runner
from .recovery_campaign import CampaignEnv, CampaignStop, CampaignOperations, train as learn, file_manifest
from .recovery_v4_campaign_contract import (CAMPAIGN_KIND, CHECKPOINT_KIND, PHYSICAL_TERMINALS,
    CampaignRequest, ReadyBank, algorithm, campaign_identity, inspect_checkpoint, require_ready)
from . import recovery_v4_runtime as runtime
from .recovery_v4_environment import V4Env, governor_action
from .recovery_v4_bank import prepare, require_bank, sample_layout
from .recovery_training_contract import EpisodeAssignment, read_json, sha
from .residual_workflow import save
from .unknown_step_runner import append


class FixtureLifecycle(runner.SoftwareFixtureBackend):
    index = -1

    def reset(self, seed=None):
        self.index += 1
        return super().reset(seed)

    def result(self):
        view, info = super().result()
        x0,y0,yaw = self.config['backend']['initial_pose_xy_yaw']
        info['physical_sample'] = replace(info['physical_sample'], pose_m_rad=(
            x0+self.x*math.cos(yaw),y0+self.x*math.sin(yaw),.1,0.,0.,yaw))
        return view,info

    def _close_current(self):
        pass


class V4CampaignEnv(CampaignEnv):
    observation_space = V4Env.observation_space
    action_space = V4Env.action_space

    def __init__(self, out, request, ready):
        layout = ready.layout(request.families[0])
        backend = (FixtureLifecycle(runtime.runtime_configuration(ready.bank['config'], layout)[0]) if request.software_fixture else runtime.make_backend(
            ready.bank['config'], layout, ready.bank['envelope'], Path(out),
            maximum_launches=request.maximum_launches))
        fixture_qc = (lambda episode: dict(valid=True, synthetic_fixture=True,
            episodes={episode: dict(valid=True, synthetic_fixture=True)})) if request.software_fixture else None
        super().__init__(out, request, ready, lifecycle=backend,
            environment_factory=runtime.make_environment, episode_qc=fixture_qc,
            physical_terminals=PHYSICAL_TERMINALS)

    def reset(self, *, seed=None, options=None):
        if self.phase != 'ready':
            raise RuntimeError('Finish stored v4 episode before reset')
        self.require_resources()
        if self.count >= self.request.transitions or self.launch_attempts >= self.request.maximum_launches:
            raise CampaignStop('campaign_budget')
        family = self.request.families[self.cursor % len(self.request.families)]
        layout = sample_layout(self.ready.bank, family, 'train', self.request.seed,
                               self.cursor//len(self.request.families))
        c, g, protocol, condition = runtime.runtime_configuration(self.config, layout)
        self.backend._close_current()
        self.backend.world = layout['world']
        self.backend.config, self.backend.gconf = deepcopy(c), deepcopy(g)
        self.backend.protocol, self.backend.condition = deepcopy(protocol), deepcopy(condition)
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
        self.inner = runtime.make_environment(self.config, layout, self.ready.bank['envelope'], self.backend, c)
        observation, info = self.inner.reset(seed=layout['seed'])
        save(self.out/(assignment.episode_id+'_reset.json'), dict(reset=info,
            assignment=self.current, private_layout=layout, environment_identity=self.inner.identity))
        save(self.out/'current_world.json', dict(world=layout['world'], world_sha256=layout['world_sha256'],
            family=family, episode=self.launch_attempts-1, trace=str(self.current_trace)))
        self.episode_steps, self.last, self.phase = 0, None, 'active'
        return observation, dict(info, recovery_assignment=self.current)


def operations():
    return CampaignOperations(CAMPAIGN_KIND, CHECKPOINT_KIND, algorithm, inspect_checkpoint,
                              runner.sources, True)


def run_train(request, out, *, stop_after=None):
    ready = require_ready(request)
    identity = campaign_identity(request, ready)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(out).free < request.minimum_free_bytes+2**28:
        raise OSError('V4 campaign disk reserve unavailable')
    save(out/'request.json', request.state())
    save(out/'identity.json', identity)
    env = V4CampaignEnv(out, request, ready)
    result = learn(out, request, ready, identity, env=env, stop_after=stop_after, operations=operations())
    save(out/'manifest.json', file_manifest(out))
    return result


def run_case(request, bank, layout, arm, out, *, checkpoint=None):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins = runner.sources()
    backend = runtime.make_backend(bank['config'], layout, bank['envelope'], out, maximum_launches=1)
    env = runtime.make_environment(bank['config'], layout, bank['envelope'], backend)
    model = None
    if arm == 'td3':
        from stable_baselines3 import TD3
        candidate = inspect_checkpoint(checkpoint)
        if candidate['identity']['controller_abi'] != env.adapter.identity:
            raise ValueError('Evaluation actor ABI mismatch')
        model = TD3.load(Path(checkpoint)/'model.zip', device='cpu')
    error, closed, last = None, False, None
    started = time.monotonic()
    save(out/'job.json', dict(kind=CAMPAIGN_KIND, status='running', source_pins=pins, arm=arm))
    try:
        observation, info = env.reset(seed=layout['seed'])
        save(out/'episode_0_reset.json', dict(reset=info, private_layout=layout,
            environment_identity=env.identity))
        for index in range(400):
            if time.monotonic()-started > request.wall_seconds:
                raise TimeoutError('V4 qualification wall budget exhausted')
            action = ([-1.] if arm == 'classical' else [0.] if arm == 'constant'
                else governor_action(observation) if arm == 'governor'
                else model.predict(observation, deterministic=True)[0])
            observation, reward, term, trunc, info = env.step(action)
            last = dict(info, episode=0, step=index+1, reward=reward, terminated=term, truncated=trunc)
            append(out/'environment_trace.jsonl', last)
            save(out/'progress.json', dict(kind=CAMPAIGN_KIND, status='running', phase='qualification',
                global_steps=index+1, target_steps=400, family=layout['family'], arm=arm))
            if term or trunc:
                break
        if not last or not last['terminated'] or last['truncated']:
            raise ValueError('No classified intrinsic/physical v4 terminal')
        if last['task']['termination_reason'] not in PHYSICAL_TERMINALS:
            raise ValueError('Unknown v4 physical terminal')
    except BaseException as exc:
        error = repr(exc)
        raise
    finally:
        try:
            env.close()
            closed = True
        finally:
            qc = runner.raw_qc(out)
            result = dict(family=layout['family'], arm=arm, layout_id=layout['id'], split=layout['split'],
                world_sha256=layout['world_sha256'], bank_sha256=sha(request.prepared_root/'inputs/bank.json'),
                source_qc=qc, outcome=None if last is None else last['task'], optimizer_updates=0,
                learned_benefit_verified=False, hardware_actions=0)
            save(out/'result.json', result)
            save(out/'source_qc.json', qc)
            save(out/'job.json', dict(kind=CAMPAIGN_KIND, status='failed' if error else 'completed',
                error=error, clean_closure=closed, source_pins=pins, arm=arm, hardware_actions=0))
            save(out/'manifest.json', file_manifest(out))
    if not qc['valid'] or pins != runner.sources():
        raise ValueError('V4 retained source QC or identity failed')
    return result


def qualify(request, out):
    bank = require_bank(request.prepared_root)
    results = {}
    for family in request.families:
        layout = sample_layout(bank, family, 'tune', 0, 0)
        for arm in ('classical', 'constant', 'governor'):
            results[family+'/'+arm] = run_case(request, bank, layout, arm, Path(out)/family/arm)
    require_ready(replace(request, qualification_root=Path(out).resolve()))
    return dict(status='completed', qualification_pass=True, cases=list(results), hardware_actions=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'software-smoke', 'qualify', 'train', 'evaluate', 'inspect-checkpoint'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--checkpoint', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'inspect-checkpoint':
        result = inspect_checkpoint(args.checkpoint)
    elif args.action == 'prepare':
        bank = prepare(args.output)
        result = dict(status='completed', layouts=len(bank['layouts']), prepared_root=str(args.output))
    else:
        if args.request is None or args.output is None:
            parser.error('--request and --output required')
        raw = read_json(args.request)
        if args.action == 'software-smoke':
            raw.update(software_fixture=True, learning_starts=32, transitions=64)
        request = CampaignRequest.parse(raw)
        lock_path = Path.home()/'nino_research/.factory_sim.lock'
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.action in ('software-smoke', 'train'):
                if args.action == 'train' and request.software_fixture:
                    raise ValueError('Fixture checkpoint cannot authorize simulator research training')
                result = run_train(request, args.output)
            elif args.action == 'qualify':
                result = qualify(request, args.output)
            else:
                bank = require_bank(request.prepared_root)
                results = {}
                for family in request.families:
                    rows = [r for r in bank['layouts'] if r['family'] == family and r['split'] == request.evaluation_split]
                    for layout in rows:
                        for arm in ('classical', 'constant', 'governor', 'td3'):
                            key = layout['id']+'/'+arm
                            results[key] = run_case(request, bank, layout, arm, args.output/key,
                                checkpoint=args.checkpoint)
                result = dict(status='completed', cases=list(results), learned_benefit_verified=False)
    print(json.dumps(result, allow_nan=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
