#!/usr/bin/env python3
"""Freeze the reactive authority test; old learning contracts remain unchanged."""
import json
import shutil
from pathlib import Path
from prepare_rough_foundations import ROOT,digest,immutable
from prepare_rough_longitudinal_pilot_v2 import OUTPUT as BASE,prepare as verify_base
from run_hardware_sensor_preflight import replace

OUTPUT=ROOT/'rl_runs/rough_reactive_confirmation_v1'
SEEDS=list(range(15200,15205))


def prepare(output=OUTPUT):
    import yaml
    _,base=verify_base(BASE);output.mkdir(parents=True,exist_ok=True)
    manifest=output/'authority_contract.json'
    if manifest.exists():
        plan=json.loads(manifest.read_text());verify(plan)
        return yaml.safe_load((output/'config.yaml').read_text()),plan
    package=output/'python/nino_rl'
    shutil.copytree(BASE/'python/nino_rl',package,ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    helper=Path(__file__).with_name('rough_reactive_speed.py')
    shutil.copyfile(helper,package/'reactive_speed.py')
    env=(package/'ros_env.py').read_text()
    env=replace(env,'                "action_speed": float(raw_action[0]),',
        '                "step_dt_s": step_dt, "step_imu_energy": imu["square_integral"],\n'
        '                "step_imu_coverage_s": imu["duration"], "step_imu_peak_m_s2": imu["peak"],\n'
        '                "step_slip_square": (slip_left**2+slip_right**2)/2,\n'
        '                "action_speed": float(raw_action[0]),')
    (package/'ros_env.py').write_text(env)
    code=(package/'evaluation.py').read_text()
    code=replace(code,'    args = parser.parse_args()\n    if args.episodes < 1:',
        '    parser.add_argument("--reactive", action="store_true", help="Sensor-triggered baseline speed probe")\n'
        '    args = parser.parse_args()\n'
        '    if args.reactive and not baseline: parser.error("--reactive is a PI probe, not PPO")\n'
        '    if args.episodes < 1:')
    code=replace(code,'        "action_ablation": "speed_only" if speed_only else "none",',
        '        "reactive_probe": args.reactive,\n'
        '        "action_ablation": "speed_only" if speed_only else "none",')
    code=replace(code,'            observation, reset_info = env.reset(seed=scenario_seed)',
        '            observation, reset_info = env.reset(seed=scenario_seed)\n'
        '            from nino_rl.reactive_speed import ReactiveSpeed\n'
        '            cue_monitor = ReactiveSpeed(config["reactive_probe"], env.ros.imu_includes_gravity)')
    code=replace(code,'                start_sim = env.lockstep_sim_time',
        '                target, cue_trace = cue_monitor.update(env.previous_robot_state,\n'
        '                    env.ros.desired_twist(), env.longitudinal_scale, env.control_dt)\n'
        '                if args.reactive: action[0] = encode_speed(target, config)\n'
        '                start_sim = env.lockstep_sim_time')
    code=replace(code,'                    if args.control_trace:\n                        samples =',
        '                    if args.control_trace:\n'
        '                        info["control_trace"].update(cue_trace)\n'
        '                        samples =')
    (package/'evaluation.py').write_text(code)
    (package/'train.py').write_text('def main():\n    raise SystemExit("Authority test only; new reward pilot is gated separately")\n')
    for path in package.glob('*.py'):compile(path.read_text(),str(path),'exec')
    config=yaml.safe_load((BASE/'config.yaml').read_text())
    from rough_reactive_speed import DEFAULTS
    config['reactive_probe']=DEFAULTS.copy()
    immutable(output/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    assets={str(p):digest(p) for p in package.glob('*.py')}
    assets.update(base['assets']);assets.update(base['implementation'])
    assets[str(output/'config.yaml')]=digest(output/'config.yaml')
    plan=dict(revision='rough_reactive_confirmation_v1',assets=assets,
        implementation={str(Path(__file__)):digest(__file__),str(helper):digest(helper)},seeds=SEEDS,
        window=dict(before_m=.10,after_m=.80,selection='PI-only trigger positions; union; physical X only for offline E1 scoring'),
        gate=dict(max_time_ratio=1.15,min_quality_gain=.05,max_other_quality_ratio=1.10,
            max_global_slip_ratio=1.10,require_median_paired_gain=True),
        scoring='Unchanged physical arrival/route/localization/timing; additional quality screen',
        qualification='Five paired fixed-map reset seeds, nominal physics; authority screen only',optuna_held=True)
    immutable(manifest,json.dumps(plan,indent=2)+'\n');return config,plan


def verify(plan):
    for group in (plan['assets'],plan['implementation']):
        for path,expected in group.items():
            if digest(path)!=expected:raise ValueError('Frozen reactive authority input changed: '+path)


if __name__=='__main__':
    prepare();print('Prepared',OUTPUT)
