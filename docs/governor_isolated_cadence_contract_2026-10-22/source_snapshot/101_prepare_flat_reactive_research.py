#!/usr/bin/env python3
"""Prepare isolated sensor-only flat PI experiments. Does not launch or train."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'src/nino_rl'), str(Path(__file__).parent)]
from nino_rl.flat_reactive_research import FIELDS, scenario_bank
from prepare_rough_foundations import digest, immutable
from run_disturbance_reference_comparisons import replace, verify

SPEC = ROOT/'src/nino_rl/config/flat_proprioceptive_research.yaml'
OUTPUT = ROOT/'rl_runs/flat_proprioceptive_v1'

RUNTIME = '''"""Fresh, measured command feedback for sensor-only flat screening."""
import os
import time
from nino_rl.flat_reactive_research import ReactiveReference

def feedback(env, start, end):
    deadline = time.monotonic() + env.config['policy_v2']['sensor_wait_timeout_seconds']
    while True:
        rows = env.ros.drive_diagnostics(start, end)
        if rows:
            latest = rows[-1]
            if end-latest['sim_time_s'] <= env.config['policy_v2']['motion_max_lag_seconds']+1e-8:
                if not all(latest[k] > .5 for k in ('cmd_fresh','policy_fresh','have_wheel_state')):
                    raise RuntimeError('Stale motor command/state in reactive research')
                return latest
        if time.monotonic() >= deadline:
            raise RuntimeError('No fresh in-interval executed command feedback')
        time.sleep(.005)

def scripted_scale(env, previous):
    profile = os.environ.get('NINO_FLAT_RESEARCH_PROFILE', 'full')
    if profile not in ('full','reactive','matched'):
        raise ValueError('Coordinate schedules are excluded from reactive research')
    if env.research_reference is None:
        env.research_reference = ReactiveReference(env.config['flat_research']['reactive_reference'],
                                                  env.ros.imu_includes_gravity)
    target, trace = env.research_reference.update(env.previous_robot_state,
                                                 env.research_feedback, env.control_dt)
    env.research_cue = trace
    if profile == 'full': target = 1.
    elif profile == 'matched': target = float(os.environ['NINO_MATCH_SCALE'])
    if not .55 <= target <= 1.: raise ValueError('Scale outside new research bounds')
    # Always apply the declared slew to a target, never switch motor torque.
    delta = env.config['flat_research']['control']['scale_rate_per_second'] * env.control_dt
    return min(previous+delta, max(previous-delta, target))
'''


def prepare(output, spec_path=SPEC):
    output = Path(output).resolve()
    saved = output/'contract.json'
    if saved.exists():
        plan = json.loads(saved.read_text())
        verify(plan)
        verify({'assets': plan['source_assets']})
        if plan['spec_sha256'] != digest(Path(spec_path)):
            raise ValueError('Research specification changed; choose a new output')
        return plan
    spec = yaml.safe_load(Path(spec_path).read_text())
    if spec['training']['allowed'] or spec['training']['optuna_allowed']:
        raise ValueError('This preparer only supports the foundation/authority stage')
    source = ROOT/spec['source_bundle']
    original = json.loads((source/'contract.json').read_text())
    verify(original)
    package = output/'python/nino_rl'
    package.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source/'python/nino_rl', package, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    module = ROOT/'src/nino_rl/nino_rl/flat_reactive_research.py'
    immutable(package/module.name, module.read_bytes())
    immutable(package/'research_runtime.py', RUNTIME)
    bank = scenario_bank(spec)
    immutable(output/'scenarios.json', json.dumps(bank, indent=2)+'\n')

    # Existing reset calls sample_cables every episode; this supplies physical
    # x/radius/angle to the spawn API, never to the supervisor observation.
    path = package/'flat_curriculum.py'
    code = path.read_text()
    start = code.index('    def sample_cables(')
    end = code.index('    def record(', start)
    code = code[:start] + '''    def sample_cables(self, rng, stage_index):
        import json, os
        from pathlib import Path
        from nino_rl.flat_reactive_research import scenario_cables
        bank = json.loads(Path(os.environ['NINO_FLAT_SCENARIO_BANK']).read_text())
        return scenario_cables(bank, os.environ['NINO_FLAT_SCENARIO_ID'])

''' + code[end:]
    path.write_text(code)

    path = package/'ros_env.py'
    code = replace(path.read_text(),
        '        self.history = ObservationHistory(config["policy_v2"]["history_frames"])',
        '        from nino_rl.flat_reactive_research import SensorHistory\n'
        '        self.history = SensorHistory(config["policy_v2"]["history_frames"])')
    start = code.index('    def _actor_observation(')
    end = code.index('    def reset(', start)
    code = code[:start] + '''    def _actor_observation(self, state, action, reference):
        from nino_rl.flat_reactive_research import sensor_frame
        return sensor_frame(state, self.ros.desired_twist(), self.research_feedback,
                            self.research_imu, self.control_dt)

''' + code[end:]
    code = replace(code, '        self.attempt_number += 1', '''        self.research_reference = None
        self.research_cue = {}
        self.research_imu = {}
        # Reset frame has no prior action interval. Coverage explicitly is zero.
        self.research_feedback = dict(executed_linear_m_s=0., executed_yaw_rad_s=0.,
                                      filtered_speed_scale=0.)
        self.attempt_number += 1''')
    code = replace(code, '        imu["previous_episode_peak"] = self.peak_vertical_acceleration',
        '        from nino_rl.research_runtime import feedback\n'
        '        self.research_feedback = feedback(self, started_sim, ended_sim)\n'
        '        self.research_imu = dict(imu)\n'
        '        imu["previous_episode_peak"] = self.peak_vertical_acceleration')
    code = replace(code, '                "action_speed": float(raw_action[0]),',
        '                **{"research_"+k: v for k,v in self.research_cue.items()},\n'
        '                "action_speed": float(raw_action[0]),')
    path.write_text(code)
    path = package/'evaluation.py'
    code = replace(path.read_text(), 'def run(baseline=False):',
        'def run(baseline=False):\n'
        '    if not baseline:\n'
        '        raise ValueError("Sensor-only contract is PI screening only; legacy PPO excluded")')
    code = replace(code, 'from nino_rl.crossing_authority import scripted_scale',
                   'from nino_rl.research_runtime import scripted_scale')
    code = replace(code, '    (output / "metadata.json").write_text',
                   '    metadata["research_scenario_id"] = __import__("os").environ["NINO_FLAT_SCENARIO_ID"]\n'
                   '    metadata["research_profile"] = __import__("os").environ["NINO_FLAT_RESEARCH_PROFILE"]\n'
                   '    (output / "metadata.json").write_text')
    # Remove coordinate controller implementation from this isolated runtime.
    (package/'crossing_authority.py').unlink()
    path.write_text(code)
    path = package/'train.py'
    path.write_text('def main():\n'
        '    raise SystemExit("Flat proprioceptive foundation screen first; PPO/Optuna not released")\n')
    for p in package.glob('*.py'):
        compile(p.read_text(), str(p), 'exec')

    config = yaml.safe_load((source/'config.yaml').read_text())
    config['policy_v2'].update(require_terrain_preview=False, history_frames=5,
                             imu_strict_coverage=True)
    config['adaptive_terrain'].update(enabled=False, initial_features=0, evaluation_features=0)
    config['course_cable_randomization']['enabled'] = False
    config['flat_curriculum'].update(fixed_stage=0, evaluation_stage=0, replay_probability=0.,
        stages=[dict(name='scenario_manifest', cable_indices=[], angle_range_deg=[-30,30], adaptive_features=0)])
    config['fixed_terrain_challenges'] = []
    config['domain_randomization']['enabled'] = False
    for key in ('challenge_entry_bonus', 'challenge_clear_bonus', 'challenge_goal_bonus'):
        config['reward_v2'][key] = 0.
    config['flat_research'] = spec
    config['research_runtime_contract'] = dict(revision=spec['revision'],
        frame_fields=FIELDS, history_size=90, PPO_allowed=False, Optuna_allowed=False,
        residual_torque=False, yaw_residual=False, actor_absolute_pose=False)
    immutable(output/'config.yaml', yaml.safe_dump(config, sort_keys=False))
    immutable(output/'world.sdf', Path(original['world']).read_bytes())

    # Remove unavailable virtual terrain sensor without changing its physical
    # link. Prepare BOTH physical profiles; candidate never replaces nominal.
    robot_source = ROOT/'src/nino_description/urdf/nino.urdf.xacro'
    xml = ET.fromstring(subprocess.check_output(['xacro', str(robot_source)]))
    removed = []
    for gazebo in xml.findall('gazebo'):
        for sensor in list(gazebo.findall('sensor')):
            if sensor.get('name') == 'terrain_preview_sensor':
                gazebo.remove(sensor)
                removed.append(sensor.get('name'))
    if removed != ['terrain_preview_sensor']:
        raise ValueError('Unexpected virtual terrain sensor inventory')
    profiles = {}
    original_robot = ET.tostring(xml)
    for name, damping in [('original', '.01'), ('caster_damping_candidate', '.001')]:
        robot = ET.fromstring(original_robot)
        for side in ('left', 'right'):
            node = robot.find(f"joint[@name='caster_{side}_wheel_joint']/dynamics")
            if node is None or float(node.get('damping')) != .01:
                raise ValueError('Audited caster wheel damping changed')
            node.set('damping', damping)
        robot_path = output/'physics'/name/'robot.urdf'
        immutable(robot_path, ET.tostring(robot, encoding='utf-8', xml_declaration=True))
        sim = (ROOT/'src/nino_description/launch/sim.launch.py').read_text()
        sim = replace(sim, '    xacro_file = PathJoinSubstitution([package_share, "urdf", "nino.urdf.xacro"])',
                      '    xacro_file = '+repr(str(robot_path)))
        sim_path = robot_path.parent/'sim.launch.py'
        immutable(sim_path, sim)
        launch = (ROOT/'src/nino_rl/launch/training_sim.launch.py').read_text()
        anchor = '            PathJoinSubstitution(\n                [FindPackageShare("nino_description"), "launch", "sim.launch.py"]\n            )'
        launch = replace(launch, anchor, '            '+repr(str(sim_path)))
        launch_path = robot_path.parent/'training_sim.launch.py'
        immutable(launch_path, launch)
        profiles[name] = dict(launch=str(launch_path), robot=str(robot_path),
                             caster_axle_damping=float(damping), physically_validated=False)

    inputs = [p for p in output.rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    inputs += [Path(spec_path), module, Path(__file__), robot_source, source/'contract.json',
               ROOT/'src/nino_description/launch/sim.launch.py',
               ROOT/'src/nino_rl/launch/training_sim.launch.py']
    plan = dict(revision=spec['revision'], spec_sha256=digest(Path(spec_path)),
        assets={str(p):digest(p) for p in inputs}, source_assets=original['assets'],
        config=str(output/'config.yaml'), world=str(output/'world.sdf'),
        python_overlay=str(output/'python'), bank=str(output/'scenarios.json'), profiles=profiles,
        active_actor_fields=FIELDS, primary='flat_only', rough='deferred_and_preserved',
        training_started=False, optuna_held=True, simulator_started=False,
        limitation='No new learned policy. Rigid circular obstacles; no soft-cable or caster-observability claim.')
    immutable(saved, json.dumps(plan, indent=2)+'\n')
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--spec', type=Path, default=SPEC)
    args = parser.parse_args()
    plan = prepare(args.output, args.spec)
    print(f"Prepared {plan['revision']}: {args.output.resolve()}")
    print('18 sensor/command values × 5 frames; rough deferred; no simulation/PPO/Optuna started.')


if __name__ == '__main__':
    main()
