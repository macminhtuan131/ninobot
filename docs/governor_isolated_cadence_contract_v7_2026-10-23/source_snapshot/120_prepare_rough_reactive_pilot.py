#!/usr/bin/env python3
"""Prepare fresh PPO only after the frozen reactive authority gate passes."""
import json
from pathlib import Path
import shutil
from prepare_rough_foundations import ROOT,digest,immutable
from prepare_rough_reactive_authority import OUTPUT as AUTHORITY,prepare as verify_authority
from prepare_rough_longitudinal_pilot_v2 import OUTPUT as ORIGINAL
from run_hardware_sensor_preflight import replace

OUTPUT=ROOT/'rl_runs/rough_reactive_reward_pilot_v1'


def prepare(output=OUTPUT):
    import yaml
    base,authority=verify_authority(AUTHORITY)
    result=json.loads((AUTHORITY/'authority_result.json').read_text())
    result_path=AUTHORITY/'authority_result.json';confirmation_assets={}
    from prepare_rough_reactive_confirmation import OUTPUT as confirmation_output,prepare as verify_confirmation
    combined=confirmation_output/'combined_result.json'
    if combined.exists():
        _,second=verify_confirmation(confirmation_output)
        protocol=json.loads((confirmation_output/'confirmation_protocol.json').read_text())
        if (protocol['script_sha256']!=digest(Path(__file__).with_name('run_rough_reactive_confirmation.py'))
                or protocol['first_contract_sha256']!=digest(AUTHORITY/'authority_contract.json')
                or protocol['second_contract_sha256']!=digest(confirmation_output/'authority_contract.json')):
            raise ValueError('Confirmation protocol changed')
        result=json.loads(combined.read_text());result_path=combined
        if (result['first_result_sha256']!=digest(AUTHORITY/'authority_result.json')
                or result['second_result_sha256']!=digest(confirmation_output/'authority_result.json')):
            raise ValueError('Combined authority evidence changed')
        confirmation_assets.update(second['assets']);confirmation_assets.update(second['implementation'])
        for name in ('confirmation_protocol.json','authority_contract.json','authority_result.json'):
            confirmation_assets[str(confirmation_output/name)]=digest(confirmation_output/name)
    runner=json.loads((AUTHORITY/'runner_contract.json').read_text())
    if (runner['authority_contract_sha256']!=digest(AUTHORITY/'authority_contract.json')
            or runner['analysis_sha256']!=digest(Path(__file__).with_name('analyze_rough_reactive_authority.py'))
            or runner['script_sha256']!=digest(Path(__file__).with_name('run_rough_reactive_authority.py'))):
        raise ValueError('Authority result provenance changed; preserve and review before a new pilot')
    if not result['passed']:raise ValueError('Reactive authority failed; new reward/PPO and Optuna remain held')
    output.mkdir(parents=True,exist_ok=True);saved=output/'pilot_contract.json'
    if saved.exists():
        plan=json.loads(saved.read_text())
        for group in (plan['assets'],plan['implementation']):
            for path,expected in group.items():
                if digest(path)!=expected:raise ValueError('Frozen reactive pilot input changed: '+path)
        return yaml.safe_load((output/'config.yaml').read_text()),plan
    package=output/'python/nino_rl'
    shutil.copytree(AUTHORITY/'python/nino_rl',package,ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    helper=Path(__file__).with_name('rough_reactive_reward.py')
    shutil.copyfile(helper,package/'reactive_reward.py')
    (package/'train.py').write_text((ORIGINAL/'python/nino_rl/train.py').read_text())
    control=replace((package/'control_v2.py').read_text(),
        'from nino_rl.longitudinal_control import compute_reward',
        'from nino_rl.reactive_reward import compute_reward')
    (package/'control_v2.py').write_text(control)
    env=(package/'ros_env.py').read_text()
    anchor='        self.longitudinal_scale = 1.'
    if env.count(anchor)!=2:raise ValueError('Unexpected reset anchors')
    env=env.replace(anchor,anchor+'\n        from nino_rl.reactive_speed import ReactiveSpeed\n'
        '        self.reward_cue = ReactiveSpeed(self.config["reactive_probe"], self.ros.imu_includes_gravity)')
    env=replace(env,'        scale, torque, yaw_reference = decode_control(',
        '        previous_executed_scale = self.longitudinal_scale\n'
        '        _, self.reward_cue_trace = self.reward_cue.update(self.previous_robot_state,\n'
        '            self.ros.desired_twist(), self.longitudinal_scale, self.control_dt)\n'
        '        scale, torque, yaw_reference = decode_control(')
    env=replace(env,'            timed_out=timed_out,',
        '            reactive_holding=self.reward_cue_trace["cue_phase"] == "holding",\n'
        '            executed_scale=scale, previous_executed_scale=previous_executed_scale,\n'
        '            timed_out=timed_out,')
    (package/'ros_env.py').write_text(env)
    contract=replace((package/'training_contract.py').read_text(),
        '    contract["revision"] = 44','    contract["revision"] = 45')
    (package/'training_contract.py').write_text(contract)
    for p in package.glob('*.py'):compile(p.read_text(),str(p),'exec')
    config=base;config['seed']=16000
    w=config['reward_v2']['longitudinal_weights']
    w.update(time_per_s=.05,velocity=.25,vibration=.8,slip=.10,slip_sigma=.05,
        action_rate=.003,late_after_s=31.,late_time_per_s=.30)
    config['reward_v2']['implementation']='bounded_reactive_comfort_v1; holding suppresses cruise tracking only; no teacher actuation'
    config['ppo']['initial_speed_scale']=.78
    config['ppo']['initial_action_std']=[.20]
    immutable(output/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    assets={str(p):digest(p) for p in package.glob('*.py')};assets.update(authority['assets']);assets.update(authority['implementation'])
    assets.update(confirmation_assets)
    assets[str(output/'config.yaml')]=digest(output/'config.yaml')
    assets[str(result_path)]=digest(result_path)
    plan=dict(revision='rough_reactive_reward_pilot_v1',assets=assets,
        implementation={str(Path(__file__)):digest(__file__),str(helper):digest(helper)},
        steps=20480,training_seed=16000,evaluation_seeds=list(range(16100,16105)),route='E1',
        initialization='Fresh actor/critic/optimizer; initial target scale .901, standard Gaussian PPO, no model transfer',
        reward='Bounded hardware-cue holding excludes cruise tracking cost; recovery restores it; comfort, time, lateness and executed-reference slew',
        authority_contract_sha256=digest(AUTHORITY/'authority_contract.json'),
        authority_result_sha256=digest(result_path),authority_result_path=str(result_path),
        actor_inputs='Unchanged 280 hardware history features; no preview, truth velocity or cue-controller action override',
        qualification='Fixed nominal E1, one training seed; evaluate actual slowdown and recovery as well as physical outcomes',optuna_held=True)
    immutable(saved,json.dumps(plan,indent=2)+'\n');return config,plan


if __name__=='__main__':
    prepare();print('Prepared conditional fresh pilot',OUTPUT)
