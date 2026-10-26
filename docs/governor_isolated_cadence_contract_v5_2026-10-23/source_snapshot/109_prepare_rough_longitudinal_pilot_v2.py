#!/usr/bin/env python3
"""Freeze a fresh one-action PPO contract; never mutate a saved experiment."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from prepare_rough_foundations import ROOT, SOURCE, digest, immutable
from run_hardware_sensor_preflight import OUTPUT as SENSOR, prepare as sensor_prepare, replace

OUTPUT=ROOT/'rl_runs/rough_longitudinal_pilot_v2'


def prepare(output):
    import yaml
    base,sensor=sensor_prepare(SENSOR)
    output.mkdir(parents=True,exist_ok=True)
    saved=output/'pilot_contract.json'
    if saved.exists():
        plan=json.loads(saved.read_text())
        for group in (plan['assets'],plan['implementation']):
            for path,expected in group.items():
                if digest(path)!=expected:raise ValueError('Pilot input changed: '+path)
        return yaml.safe_load((output/'config.yaml').read_text()),plan
    package=output/'python/nino_rl'
    if not package.exists():shutil.copytree(SENSOR/'python/nino_rl',package,ignore=shutil.ignore_patterns('__pycache__'))
    helper=Path(__file__).with_name('rough_longitudinal_control.py')
    (package/'longitudinal_control.py').write_text(helper.read_text())
    control=(SENSOR/'python/nino_rl/control_v2.py').read_text()
    control=replace(control,'    return 2 if config.get("action_mode") == "speed_yaw_reference" else ACTION_SIZE',
        '    return 1 if config.get("action_mode") == "speed_reference" else (2 if config.get("action_mode") == "speed_yaw_reference" else ACTION_SIZE)')
    control=replace(control,'    return np.array([1., 0.], dtype=np.float32) if action_size(config) == 2 else BASELINE_ACTION.copy()',
        '    if action_size(config) == 1: return np.array([1.], dtype=np.float32)\n'
        '    return np.array([1., 0.], dtype=np.float32) if action_size(config) == 2 else BASELINE_ACTION.copy()')
    control=replace(control,'    u = np.clip(u, -1., 1.)\n    return np.array([u[0], 0., u[1]], dtype=np.float32) if action_size(config) == 2 else u.copy()',
        '    u = np.clip(u, -1., 1.)\n'
        '    if action_size(config) == 1: return np.array([u[0], 0., 0.], dtype=np.float32)\n'
        '    return np.array([u[0], 0., u[1]], dtype=np.float32) if action_size(config) == 2 else u.copy()')
    control=replace(control,'    if config.get("action_mode") == "speed_yaw_reference":\n        u = history_action(action, config)',
        '    if config.get("action_mode") == "speed_reference":\n'
        '        from nino_rl.longitudinal_control import decode_speed\n'
        '        return decode_speed(action, config), np.zeros(2), 0.\n'
        '    if config.get("action_mode") == "speed_yaw_reference":\n        u = history_action(action, config)')
    control+='\n# Explicit new reward contract; legacy implementations remain archived.\nfrom nino_rl.longitudinal_control import compute_reward\n'
    env=(SENSOR/'python/nino_rl/ros_env.py').read_text()
    # Initialize/reset rate limiter alongside each existing action reset.
    if env.count('        self.previous_action = BASELINE_ACTION.copy()')!=2:raise ValueError('Unexpected action reset count')
    env=env.replace('        self.previous_action = BASELINE_ACTION.copy()',
        '        self.previous_action = BASELINE_ACTION.copy()\n        self.longitudinal_scale = 1.')
    env=replace(env,'        desired_linear, desired_angular = self.ros.desired_twist()',
        '        desired_linear, desired_angular = self.ros.desired_twist()\n'
        '        if self.route_set.enabled and self.config.get("action_mode") == "speed_reference":\n'
        '            desired_linear, desired_angular = route_command(self.ros.snapshot(), self.path, tracking,\n'
        '                route_controller_config(self.config, self.episode_route["id"]))')
    env=replace(env,'        if self.config.get("action_mode") == "speed_yaw_reference":\n            action = history_action(action, self.config)',
        '        if self.config.get("action_mode") in ("speed_yaw_reference", "speed_reference"):\n            action = history_action(action, self.config)')
    env=replace(env,'            else:\n                self.ros.publish_motion_command(linear, angular)',
        '            else:\n'
        '                from nino_rl.longitudinal_control import ramp_speed, velocity_reference\n'
        '                self.unscaled_motion_request = (linear, angular)\n'
        '                self.longitudinal_scale = ramp_speed(self.longitudinal_scale, scale, self.control_dt,\n'
        '                    self.config["longitudinal_control"]["scale_rate_per_s"])\n'
        '                scale = self.longitudinal_scale\n'
        '                linear, angular = velocity_reference(linear, angular, scale)\n'
        '                self.ros.publish_motion_command(linear, angular)')
    env=replace(env,'        reward_reference = self._reference(\n            self.previous_tracking, started_sim - self.episode_started_sim)',
        '        reward_reference = self._reference(\n            self.previous_tracking, started_sim - self.episode_started_sim)\n'
        '        from dataclasses import replace as replace_reference\n'
        '        if not (corner_override or recovery_override):\n'
        '            reward_reference = replace_reference(reward_reference,\n'
        '                desired_linear_velocity=self.unscaled_motion_request[0],\n'
        '                desired_angular_velocity=self.unscaled_motion_request[1])')
    env=replace(env,'        self.ros.publish_control(scale, float(torque[0]), float(torque[1]))',
        '        # Scaling already changes only linear /cmd_vel. Adapter remains at 1.\n'
        '        torque[:] = 0.\n'
        '        self.ros.publish_control(1., 0., 0.)')
    env=replace(env,'                "action_yaw": float(raw_action[-1]),',
        '                "action_yaw": 0.,  # One speed action has no yaw dimension.')
    anchor='            timeout=self.simulation_step_timeout\n        )\n        truth = self.ros.snapshot()'
    env=replace(env,anchor,'            timeout=self.simulation_step_timeout\n        )\n'
        '        self.ros.refresh_reset_sensors(["imu", "ground_truth", "scan"],\n'
        '            timeout=self.sensor_timeout, step_timeout=self.simulation_step_timeout)\n'
        '        self.lockstep_sim_time = self.ros.wait_for_clock_quiescence(timeout=self.simulation_step_timeout)\n'
        '        truth = self.ros.snapshot()')
    routes=(package/'routes.py').read_text()
    routes=replace(routes,'        if config.get("action_mode", "wheel_torque") != "wheel_torque":',
        '        if config.get("action_mode", "wheel_torque") not in ("wheel_torque", "speed_reference"):')
    policies=(package/'policies.py').read_text().replace('((2,), (3,))','((1,), (2,), (3,))')
    train=(SOURCE/'python/nino_rl/train.py').read_text()
    train=replace(train,'    config = load_config(args.config)',
        '    config = load_config(args.config)\n'
        '    if args.resume or args.init_model or args.init_speed_model:\n'
        '        raise SystemExit("This bounded pilot requires fresh actor, critic and optimizer")')
    train=replace(train,'        monitored = Monitor(env, filename=str(run_dir / "monitor.csv"))',
        '        monitored = Monitor(env, filename=str(run_dir / "monitor.csv"))\n'
        '        from nino_rl.alignment_helpers import scaled_environment\n'
        '        learning_env = scaled_environment(monitored, config["training_reward_scale"])')
    train=replace(train,'                monitored,\n                learning_rate=','                learning_env,\n                learning_rate=')
    train=replace(train,'            labels = (("speed", "yaw_reference") if action_size(config) == 2\n                      else ("speed", "common_torque", "steering"))',
        '            from nino_rl.alignment_helpers import record_value_diagnostics\n'
        '            record_value_diagnostics(self)\n'
        '            labels = ("speed",)')
    preflight=(package/'preflight.py').read_text()
    preflight=replace(preflight,'        preview = node.terrain_preview(timeout)',
        '        preview = [0., 0., 0., 0.]  # No unavailable sensor queried.')
    preflight=replace(preflight,'        passed.append("6 forward and downward terrain laser scans are valid")',
        '        passed.append("6 horizontal laser scan is valid; downward sensor excluded")')
    preflight=replace(preflight,'            ("base_link", "terrain_laser"),\n','')
    preflight=replace(preflight,'            node.publish_control(1.0, test_torque, -test_torque)',
        '            node.publish_control(1.0, 0., 0.)')
    preflight=replace(preflight,'        passed.append("2 both wheel joints rotate under bounded v2 residual torque")',
        '        passed.append("2 both wheel joints rotate under bounded PI velocity references")')
    evaluation=(package/'evaluation.py').read_text()
    evaluation=replace(evaluation,'        validate_model(model, 60 * config["policy_v2"]["history_frames"], action_size(config))',
        '        validate_model(model, 56 * config["policy_v2"]["history_frames"], action_size(config))')
    evaluation=replace(evaluation,'                    action[0] = 2.0 * args.baseline_speed_scale - 1.0',
        '                    from nino_rl.longitudinal_control import encode_speed\n'
        '                    action[0] = encode_speed(args.baseline_speed_scale, config)')
    contract=(package/'training_contract.py').read_text()
    contract=replace(contract,'    contract["revision"] = 42','    contract["revision"] = 44')
    for name,code in dict(control_v2=control,ros_env=env,routes=routes,policies=policies,train=train,
                          preflight=preflight,evaluation=evaluation,training_contract=contract).items():
        compile(code,name,'exec');(package/(name+'.py')).write_text(code)
    shutil.copyfile(Path(__file__).with_name('flat_reward_alignment.py'),package/'alignment_helpers.py')
    config=base
    config['action_mode']='speed_reference';config['seed']=14000
    config['rough_runtime']['stage_index']=0;config['routes']['fixed_route']='E1'
    config['policy_v2']['imu_strict_coverage']=True
    config['longitudinal_control']=dict(minimum_scale=.55,scale_rate_per_s=.4,
        yaw_authority='unscaled PI yaw; adapter scale 1; zero residual torque',route='E1')
    config['hardware_sensor_contract']['actor_initialization']='fresh near-PI actor; fresh critic/optimizer'
    config['reward_v2']['longitudinal_weights']=dict(progress_per_m=2.,time_per_s=.1,velocity=1.,
        velocity_sigma_m_s=.4,vibration=.5,acceleration_sigma_m_s2=2.,slip=.2,slip_sigma=.3,
        lateral=.2,lateral_sigma_m=.05,heading=.05,heading_sigma_rad=.2,action_rate=.01,
        arrival=10.,failure=50.)
    config['reward_v2']['implementation']='compact_longitudinal_v1; legacy weights unused'
    config['training_reward_scale']=.1
    config['ppo'].update(learning_rate=1e-4,n_steps=1024,batch_size=256,n_epochs=3,clip_range=.2,
        ent_coef=.001,initial_speed_scale=.90,initial_action_std=[.25],target_kl=.015)
    immutable(output/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    assets={str(p):digest(p) for p in package.glob('*.py')}
    assets.update(sensor['assets']);assets.update(sensor['implementation'])
    assets[str(output/'config.yaml')]=digest(output/'config.yaml')
    plan=dict(revision='rough_longitudinal_pilot_v2',assets=assets,
        implementation={str(Path(__file__)):digest(__file__),str(helper):digest(helper)},
        steps=20480,training_seed=14000,route='E1',train_physics='nominal',terrain='half_relief',
        actor_inputs='horizontal lidar, IMU, encoders, estimated path and command/action history; no virtual preview/cloud or truth velocity',
        initialization='fresh actor, critic, optimizer; normalized head mean .8 maps to .955 scale',
        actions='one target speed scale .55–1; fixed .4 scale/s ramp; unchanged PI yaw; no residual torque',
        reward='signed progress, unscaled external speed request, vertical squared energy, slip, path/heading, action rate; fixed .1 learner units',
        qualification='requires confirmation_result.passed, new-controller PI checks and actuator tests before training',
        evaluation_seeds=[14010,14011,14012,14013,14014],optuna_held=True)
    immutable(saved,json.dumps(plan,indent=2)+'\n')
    return config,plan


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUTPUT)
    output=parser.parse_args().output.resolve();os.chdir(ROOT)
    prepare(output);print('Prepared fresh longitudinal pilot',output)


if __name__=='__main__':main()
