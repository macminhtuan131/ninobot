#!/usr/bin/env python3
"""Prepare the isolated bounded-cue, hardware-summary, gSDE rough pilot."""
import json
from pathlib import Path
import shutil
import yaml
from prepare_rough_foundations import ROOT, digest, immutable
from prepare_rough_reactive_pilot import OUTPUT as PREVIOUS, prepare as verify_previous
from run_hardware_sensor_preflight import replace

OUTPUT = ROOT/'rl_runs/rough_observable_pilot_v2'


def prepare(output=OUTPUT):
    base, previous = verify_previous(PREVIOUS)
    output.mkdir(parents=True, exist_ok=True)
    saved = output/'pilot_contract.json'
    if saved.exists():
        plan = json.loads(saved.read_text())
        for group in ('assets', 'implementation'):
            for path, expected in plan[group].items():
                if digest(path) != expected:
                    raise ValueError('Frozen observable pilot changed: '+path)
        return yaml.safe_load((output/'config.yaml').read_text()), plan
    package = output/'python/nino_rl'
    shutil.copytree(PREVIOUS/'python/nino_rl', package,
                    ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
    helper = Path(__file__).with_name('rough_reactive_observable.py')
    shutil.copyfile(helper, package/'reactive_observable.py')
    control = (package/'control_v2.py').read_text()
    control = replace(control, 'FRAME_SIZE = 56', 'FRAME_SIZE = 72\nBASE_FRAME_SIZE = 56')
    control = replace(control, '    if observation.shape != (FRAME_SIZE,) or not np.all(np.isfinite(observation)):',
                      '    if observation.shape != (BASE_FRAME_SIZE,) or not np.all(np.isfinite(observation)):')
    env = (package/'ros_env.py').read_text()
    env = env.replace('from nino_rl.reactive_speed import ReactiveSpeed',
                      'from nino_rl.reactive_observable import BoundedCue as ReactiveSpeed')
    anchor = '        self.reward_cue = ReactiveSpeed(self.config["reactive_probe"], self.ros.imu_includes_gravity)'
    if env.count(anchor) != 2:
        raise ValueError('Expected constructor/reset cue initialization')
    env = env.replace(anchor, anchor+'\n        self.reward_cue.elapsed = -self.control_dt\n'
        '        self.last_imu_summary = {}\n        self.last_executed_motion = (0., 0.)')
    env = replace(env, '        self.previous_tracking = None',
        '        from nino_rl.reactive_observable import Capture\n        self.actor_capture = Capture()\n'
        '        self.previous_tracking = None')
    env = replace(env, '        return frame\n\n    def reset(',
        '        from nino_rl.reactive_observable import extra_observation\n'
        '        published = self.ros.desired_twist()\n'
        '        _, self.reward_cue_trace = self.reward_cue.update(state, published,\n'
        '            self.longitudinal_scale, self.control_dt)\n'
        '        return np.concatenate((frame, extra_observation(self.last_imu_summary,\n'
        '            self.reward_cue_trace, self.longitudinal_scale, published,\n'
        '            self.last_executed_motion, self.control_dt)))\n\n    def reset(')
    env = replace(env, '        return observation, {',
        '        self.last_actor_observation = observation.copy()\n        return observation, {')
    env = replace(env, '        _, self.reward_cue_trace = self.reward_cue.update(self.previous_robot_state,\n'
        '            self.ros.desired_twist(), self.longitudinal_scale, self.control_dt)',
        '        action_cue_trace = self.reward_cue_trace.copy()\n'
        '        input_observation = self.last_actor_observation.copy()')
    env = replace(env, '        observation = self.history.append(self._actor_observation(',
        '        self.last_imu_summary = dict(imu)\n'
        '        drive_samples = self.ros.drive_diagnostics(started_sim, ended_sim)\n'
        '        if not drive_samples:\n'
        '            raise RuntimeError("No stamped executed-command diagnostics for actor")\n'
        '        self.last_executed_motion = (float(drive_samples[-1]["executed_linear_m_s"]),\n'
        '            float(drive_samples[-1]["executed_yaw_rad_s"]))\n'
        '        observation = self.history.append(self._actor_observation(')
    env = replace(env, 'reactive_holding=self.reward_cue_trace["cue_phase"] == "holding",',
                      'reactive_holding=action_cue_trace["cue_phase"] == "holding",')
    env = replace(env, '        return observation, reward, terminated, truncated, info',
        '        if self.config.get("evaluation_control_trace", False):\n'
        '            info["control_trace"].update(action_cue_trace)\n'
        '        self.actor_capture.add(input_observation, dict(attempt=self.attempt_number,\n'
        '            elapsed_s=elapsed, dt_s=step_dt, action=float(raw_action[0]),\n'
        '            scale=scale, cue=action_cue_trace, reward_terms=reward_terms,\n'
        '            succeeded=succeeded, terminal=bool(terminated or truncated)))\n'
        '        self.last_actor_observation = observation.copy()\n'
        '        return observation, reward, terminated, truncated, info')
    env = replace(env, '    def close(self) -> None:\n        try:',
                      '    def close(self) -> None:\n        self.actor_capture.flush()\n        try:')
    policies = (package/'policies.py').read_text()
    policies = replace(policies, 'or self.use_sde:', ':')
    policies = replace(policies, 'Keep SB3\'s rollout log-probabilities and action clipping intact.',
                       'Use SB3 standard Gaussian/gSDE log-probabilities and action clipping intact.')
    # Matrix log_std is per latent feature for gSDE, not total action std.
    train = (package/'train.py').read_text()
    train = replace(train, '                policy_kwargs=policy_kwargs,',
        '                use_sde=True, sde_sample_freq=int(ppo["sde_sample_freq"]),\n'
        '                policy_kwargs=policy_kwargs,')
    evaluation = (package/'evaluation.py').read_text()
    evaluation = replace(evaluation, 'validate_model(model, 56 * config["policy_v2"]["history_frames"],',
                         'validate_model(model, 72 * config["policy_v2"]["history_frames"],')
    evaluation = replace(evaluation,
        '                target, cue_trace = cue_monitor.update(env.previous_robot_state,\n'
        '                    env.ros.desired_twist(), env.longitudinal_scale, env.control_dt)',
        '                cue_trace = env.reward_cue_trace.copy()\n'
        '                target = cue_trace["cue_target_scale"]')
    evaluation = replace(evaluation, '            from nino_rl.reactive_speed import ReactiveSpeed\n'
        '            cue_monitor = ReactiveSpeed(config["reactive_probe"], env.ros.imu_includes_gravity)',
        '            if args.reactive:\n'
        '                raise ValueError("Observable pilot compares free PPO with fixed PI, not a teacher override")')
    contract = replace((package/'training_contract.py').read_text(),
                       '    contract["revision"] = 45', '    contract["revision"] = 47')
    contract = replace(contract,
        '    contract["observation_interface"] = "56/frame; no downward preview; 280 history"',
        '    contract["observation_interface"] = "72/frame; causal hardware summaries and bounded cue; no preview; 360 history"\n'
        '    contract["action_interface"] = {"outputs": ["speed_target"], "range": [.55, 1.],\n'
        '        "slew_per_s": .4, "yaw": "unscaled PI", "residual_torque": False}\n'
        '    contract["exploration_interface"] = "SB3 gSDE; matrix refresh every 6 control steps"')
    for name, code in dict(control_v2=control, ros_env=env, policies=policies,
                           train=train, evaluation=evaluation, training_contract=contract).items():
        compile(code, name, 'exec')
        (package/(name+'.py')).write_text(code)
    config = base
    config['seed'] = 17000
    config['reactive_probe']['maximum_recovery_seconds'] = .8
    config['hardware_sensor_contract'].update(frame_size=72, history_size=360,
        revision='causal_interval_command_bounded_cue_v1')
    config['ppo'].update(initial_speed_scale=(.85-.55)/.45,
        initial_action_std=[.065], use_sde=True, sde_sample_freq=6)
    config['exploration_contract'] = dict(actual_initial_bias_scale=.85,
        sde_matrix_std=.065, noise_refresh_control_steps=6, action_probability='SB3 gSDE',
        qualification='Empirical hardware rollout gate required; latent-dependent action std is not matrix std')
    # Weights and all independent physical success settings must remain identical.
    old = yaml.safe_load((PREVIOUS/'config.yaml').read_text())
    if config['reward_v2'] != old['reward_v2']:
        raise ValueError('Reward weights changed')
    immutable(output/'config.yaml', yaml.safe_dump(config, sort_keys=False))
    assets = dict(previous['assets'])
    assets.update({str(p): digest(p) for p in package.glob('*.py')})
    assets[str(output/'config.yaml')] = digest(output/'config.yaml')
    # v1 was stopped during simulator startup, before any PPO training. Its
    # nine physical screen episodes are reusable only after checking that all
    # executable controller/actor/sensor modules and config bytes match.
    screen_source = ROOT/'rl_runs/rough_observable_pilot_v1'
    source_plan = json.loads((screen_source/'pilot_contract.json').read_text())
    for group in ('assets', 'implementation'):
        for path, expected in source_plan[group].items():
            if digest(path) != expected:
                raise ValueError('Source screen input changed: '+path)
    if list((screen_source/'train').glob('*/nino_ppo*.zip')):
        raise ValueError('Unexpected training under the prototype contract')
    if digest(output/'config.yaml') != digest(screen_source/'config.yaml'):
        raise ValueError('Cannot reuse screen with different configuration')
    for source in (screen_source/'python/nino_rl').glob('*.py'):
        if source.name != 'training_contract.py' and digest(source) != digest(package/source.name):
            raise ValueError('Screen executable code differs: '+source.name)
    screen_assets = {str(p): digest(p) for label in ('controller_pi', 'exploration')
                     for p in (screen_source/label).rglob('*') if p.is_file()}
    assets.update(screen_assets)
    plan = dict(revision='rough_observable_pilot_v2', assets=assets,
        implementation={str(Path(__file__)): digest(__file__), str(helper): digest(helper)},
        steps=20480, training_seed=17000, evaluation_seeds=list(range(17100,17105)),
        exploration_seeds=[17010,17011,17012], route='E1', initialization='fresh actor, critic, optimizer',
        previous_contract_sha256=digest(PREVIOUS/'pilot_contract.json'),
        controls='same speed target .55–1, .4/s ramp, PI yaw and zero torque residual',
        observations='72 causal hardware/command/cue features x5; no truth velocity or preview',
        scoring='strict physical arrival and unchanged route/path/localization/timing gates',
        quality_gate=dict(min_gain=.05, max_other_quality_ratio=1.10, max_time_ratio=1.15,
            max_duration_match_error=.03),
        validated_screen_source=str(screen_source),
        screen_reuse_qualification='Config and all actor/controller/sensor code identical; only training-contract metadata corrected before any PPO transitions',
        optuna_held=True)
    immutable(saved, json.dumps(plan, indent=2)+'\n')
    return config, plan


if __name__ == '__main__':
    prepare()
    print('Prepared', OUTPUT)
