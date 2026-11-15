"""Bounded opt-in recovery preparation, software TD3 smoke and Gazebo baseline.

No hardware control or long training entry point. All attempts get fresh output.
"""
import argparse
from dataclasses import asdict
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import signal
import time

import numpy as np

from nino_control.residual_velocity import FEATURES
from . import recovery_bank as bank_module
from .common_training_studio_v2 import build_model, actor_steps
from .recovery_contract import CONTRACT_ID, StartBudget, implementation_sources
from .recovery_environment import RecoveryEnv
from .recovery_task import RecoveryBands
from .reliable_episode import EpisodeLifecycle
from .residual_factory_workflow import repo
from .residual_workflow import save
from .studio_deferred_reset import DeferredResetVecEnv
from .recovery_startup import RecoveryBackend, INITIALIZATION_ID
from .recovery_sim_runtime import dependency_identity
from .unknown_step_runtime import PhysicalSample, RewardSettings
from . import unknown_step_plan
from .unknown_step_runner import append, raw_qc, sources as inherited_sources


def sources():
    return dict(inherited=inherited_sources(), files=implementation_sources(),
                simulation_runtime=dependency_identity())


def runtime_configuration(config, layout):
    from .residual_guided_td3 import configuration as guided_configuration
    c, g, task, condition = guided_configuration()
    c['purpose'] = CONTRACT_ID
    c['backend'].update(scenario_id=CONTRACT_ID, horizon_s=config['horizon_s'],
                        command_until_s=config['horizon_s'], max_episodes=1,
                        cruise_m_s=config['cruise_m_s'],
                        startup_initialization=INITIALIZATION_ID,
                        simulation_runtime=dependency_identity(),
                        initial_pose_xy_yaw=layout['initial_pose_xy_yaw'])
    c['task'].update(command_until_s=config['horizon_s'], horizon_s=config['horizon_s'])
    g.update(baseline_id=CONTRACT_ID+'_follower', path_points_m=config['route_m'],
             goal_tolerance_m=config['start_budget']['estimated_stop_m'],
             maximum_corridor_error_m=config['maximum_cross_track_m'])
    g['navigation']['straight_speed_m_s'] = config['cruise_m_s']
    task.update(protocol_id=CONTRACT_ID, command_until_s=config['horizon_s'],
                horizon_s=config['horizon_s'], warmup_s=.5,
                initial_pose_m_rad=list(layout['initial_pose_xy_yaw']))
    condition['scenario'] = CONTRACT_ID
    return c, g, task, condition


def environment(config, layout, envelope, backend, controller=None):
    from .unknown_step_runtime import TaskSettings
    c, g, protocol, condition = runtime_configuration(config, layout)
    c = controller or c
    return RecoveryEnv(c, backend, TaskSettings(**layout['task_settings']),
                       RewardSettings(**config['task_reward']), layout['obstacles'],
                       RecoveryBands(**config['recovery_bands']), StartBudget(**config['start_budget']),
                       config['recovery_reward'], dict(guidance=g, protocol=protocol, condition=condition),
                       macro_ramp=layout.get('macro_ramp'), motion_quality=config['motion_quality'])


class SoftwareFixtureBackend:
    """Ideal wheel integrator fixture, without simulated contact or real sensors."""
    def __init__(self, controller):
        self.config = controller

    def reset(self, seed=None):
        self.t, self.x, self.v, self.w = 0., 0., 0., 0.
        return self.result()

    def result(self):
        features = dict.fromkeys(FEATURES[:18], 0.)
        radius = self.config['nominal_geometry']['radius_l']
        features.update(wheel_l_rad_s=self.v/radius, wheel_r_rad_s=self.v/radius,
                        gyro_z_rad_s=self.w, accel_z_m_s2=9.80665,
                        last_final_v_m_s=self.v)
        baseline = (.2, 0.) if self.x < 3.98 else (0., 0.)
        features['baseline_v_m_s'], features['baseline_yaw_rad_s'] = baseline
        view = dict(features=features, baseline=baseline, stamp_s=self.t, command_age_s=0.,
                    sensors_fresh=True, permission=True, fault=False, emergency_stop=False)
        physical = PhysicalSample(self.t, self.t, (self.x, 0., .1, 0., 0., 0.),
                                  abs(self.v), self.w, (self.v/radius, self.v/radius),
                                  (self.v, self.v), baseline != (0.,0.), False, False)
        return view, dict(physical_sample=physical, truth_used_for_guidance=False,
                          synthetic_fixture=True, physics_qualified=False)

    def advance_reference(self, v, w, dt):
        self.t += dt
        self.x += v*dt
        self.v, self.w = v, w
        view, info = self.result()
        return view, {}, False, False, info

    def close(self):
        pass


def software_smoke(out):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.monitor import Monitor
    config = bank_module.configuration()
    c, _, _, _ = runtime_configuration(config, dict(initial_pose_xy_yaw=[0.,0.,0.]))
    template = unknown_step_plan.task_settings(dict(corners_m=[(x,y,z) for x in (-.3,.3)
        for y in (-.25,.25) for z in (-.05,.2)], sha256='software_fixture'), dict(bump_x_m=None))
    task = asdict(template)
    task.update(route_m=config['route_m'], maximum_seconds=config['horizon_s'],
                maximum_cross_track_m=config['maximum_cross_track_m'])
    layout = dict(obstacles=[], task_settings=task, initial_pose_xy_yaw=[0.,0.,0.])
    env = environment(config, layout, {}, SoftwareFixtureBackend(c), c)
    rows = []

    class Trace(BaseCallback):
        def _on_step(self):
            info = self.locals['infos'][0]
            rows.append(dict(info, reward=float(self.locals['rewards'][0]),
                             done=bool(self.locals['dones'][0])))
            append(out/'training_trace.jsonl', rows[-1])
            return True

        def _on_rollout_end(self):
            if vec.pending_reset:
                raise RuntimeError('Unexpected fixture terminal; no implicit second episode')

    torch.set_num_threads(1)
    vec = DeferredResetVecEnv(Monitor(env))
    model = build_model(vec, dict(profile='nino_td3_smoke_h5_v1', seed=1511))
    before = [p.detach().clone() for p in model.actor.parameters()]
    try:
        model.learn(total_timesteps=config['budget']['software_smoke_transitions'], callback=Trace())
        for i, row in enumerate(rows):
            b = model.replay_buffer
            for actual, expected in ((b.actions[i,0], row['replay_action']),
                                     (b.observations[i,0], row['observation']),
                                     (b.next_observations[i,0], row['next_observation'])):
                np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0.)
            assert b.rewards[i,0] == np.float32(row['reward'])
            assert bool(b.dones[i,0]) == row['done']
        change = sum(float((p.detach()-old).abs().sum()) for p, old in zip(model.actor.parameters(), before))
        if not change > 0 or not all(torch.isfinite(p).all() for p in model.policy.parameters()):
            raise ValueError('Nonfinite or missing TD3 update')
        model.save(out/'fixture_model.zip')
        model.save_replay_buffer(out/'fixture_replay.pkl')
        save(out/'identity.json', env.identity)
        from .recovery_curriculum import FamilyCurriculum, FAMILIES
        save(out/'curriculum_state.json', {f: FamilyCurriculum(f, 1511, config['curriculum']).state()
                                           for f in FAMILIES})
        return dict(steps=int(model.num_timesteps), replay_size=int(model.replay_buffer.size()),
                    critic_updates=int(model._n_updates), actor_updates=actor_steps(model),
                    replay_rows_verified=len(rows), actor_parameter_l1_change=change,
                    software_fixture_only=True, contact_physics_tested=False,
                    checkpoint_qualified_for_gazebo=False, learned_benefit_verified=False)
    finally:
        vec.close()


def require_bank(root):
    manifest = json.loads((root/'inputs/manifest.json').read_text())
    for name, digest in manifest.items():
        path = (root/'inputs'/name).resolve()
        if not path.is_relative_to((root/'inputs').resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Prepared input manifest differs: '+name)
    if 'bank.json' not in manifest or 'source_pins.json' not in manifest:
        raise ValueError('Incomplete preparation manifest')
    bank = json.loads((root/'inputs/bank.json').read_text())
    if bank['config_sha256'] != hashlib.sha256(bank_module.CONFIG.read_bytes()).hexdigest():
        raise ValueError('Prepared recovery config changed')
    if bank['config'] != bank_module.configuration():
        raise ValueError('Prepared embedded config differs from pinned config')
    pins = json.loads((root/'inputs/source_pins.json').read_text())
    if pins != sources():
        raise ValueError('Prepared recovery sources changed; prepare a new immutable root')
    for row in bank['layouts']:
        paths = dict(row['meshes'], **{row['world']: row['world_sha256']})
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p,h in paths.items()):
            raise ValueError('Prepared world or mesh changed')
    return bank


def require_components(root, family):
    if family != 'mixed':
        return
    for component in ('short_obstacle', 'pothole'):
        prior = root/f'baseline_{component}_s0'
        if not (prior/'result.json').is_file():
            raise ValueError('Mixed geometry needs qualified component baseline: '+component)
        manifest = json.loads((prior/'manifest.json').read_text())
        result = json.loads((prior/'result.json').read_text())
        job = json.loads((prior/'job.json').read_text())
        if (hashlib.sha256((prior/'result.json').read_bytes()).hexdigest() != manifest.get('result.json')
                or result.get('physical_gate_pass') is not True
                or job.get('source_pins') != sources() or job.get('status') != 'completed'):
            raise ValueError('Mixed component baseline is unqualified or historical: '+component)


def baseline(out, root, family, stage):
    require_components(root, family)
    bank = require_bank(root)
    config = bank['config']
    layout = next(r for r in bank['layouts'] if (r['family'],r['stage'],r['split']) == (family,stage,'development'))
    c, g, task, condition = runtime_configuration(config, layout)
    lp = dict(training_episodes_per_seed_maximum=1, observer_start_deadline_s=15.,
              feedback_deadline_s=5., observer_ipc_grace_s=1., maximum_support_age_ns=40_000_000)
    backend = EpisodeLifecycle(c, out/'episodes', layout['world'], g, task, condition, lp,
        backend_factory=lambda *args: RecoveryBackend(*args, expected_envelope=bank['envelope']))
    env = environment(config, layout, bank['envelope'], backend)
    last = None
    try:
        _, info = env.reset(seed=layout['seed'])
        save(out/'episode_0_reset.json', dict(reset=info, private_layout=layout, environment_identity=env.identity))
        for i in range(config['budget']['gazebo_transitions']):
            if shutil.disk_usage(out).free < config['budget']['minimum_free_bytes']//2:
                raise ValueError('Disk reserve reached')
            _, reward, term, trunc, info = env.step([0.])
            last = dict(info, reward=reward, terminated=term, truncated=trunc, episode=0, step=i+1)
            append(out/'environment_trace.jsonl', last)
            if term or trunc:
                break
    finally:
        env.close()
    qc = raw_qc(out)
    return dict(family=family, stage=stage, layout_id=layout['id'], outcome=None if last is None else last['task'],
                bank_sha256=hashlib.sha256((root/'inputs/bank.json').read_bytes()).hexdigest(),
                world_sha256=layout['world_sha256'],
                source_qc=qc, classical_baseline_only=True, optimizer_updates=0,
                physical_gate_pass=bool(last and last['task']['task_success'] and qc['valid']),
                held_out=False, learned_benefit_verified=False)


def run(root, action, family='clean', stage=0):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < bank_module.configuration()['budget']['minimum_free_bytes']:
        raise ValueError('Recovery disk budget unavailable')
    lock_path = Path.home()/'nino_research/.factory_sim.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        target = root/('inputs' if action == 'prepare' else f'{action}_{family}_s{stage}')
        if target.exists():
            raise ValueError('Attempt already consumed; keep evidence and prepare a reviewed new attempt')
        if action != 'prepare':
            target.mkdir()
        frozen = sources()
        error, result = None, None
        started = time.monotonic()
        previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('Recovery wall budget')))
        signal.alarm(bank_module.configuration()['budget']['wall_deadline_s'])
        try:
            if action == 'prepare':
                result = bank_module.prepare(target)
                save(target/'source_pins.json', frozen)
            elif action == 'software-smoke':
                result = software_smoke(target)
            else:
                result = baseline(target, root, family, stage)
            if sources() != frozen:
                raise ValueError('Source changed during attempt')
            save(target/'result.json', result)
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            if target.exists():
                save(target/'job.json', dict(action=action, family=family, stage=stage,
                    status='failed' if error else 'completed', error=error,
                    wall_s=time.monotonic()-started, source_pins=frozen, hardware_actions=0))
                save(target/'manifest.json', {str(p.relative_to(target)):
                    hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*')
                    if p.is_file() and p != target/'manifest.json'})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'software-smoke', 'baseline'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--family', choices=bank_module.FAMILIES, default='clean')
    parser.add_argument('--stage', choices=(0,1,2), type=int, default=0)
    args = parser.parse_args()
    result = run(args.output, args.action, args.family, args.stage)
    print(json.dumps(dict(action=args.action, complete=True,
                          result=None if args.action == 'prepare' else result)), flush=True)


if __name__ == '__main__':
    main()
