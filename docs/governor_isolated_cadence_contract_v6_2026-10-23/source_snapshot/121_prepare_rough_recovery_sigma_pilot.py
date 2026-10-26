#!/usr/bin/env python3
"""Freeze one reward-only change against the completed observable v2 pilot."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import yaml

from prepare_rough_foundations import ROOT, digest, immutable
from prepare_rough_observable_pilot_v2 import OUTPUT as SOURCE, prepare as verify_source
from run_hardware_sensor_preflight import replace

OUTPUT = ROOT / 'rl_runs/rough_recovery_sigma_pilot_v1'
AUDIT = ROOT / 'docs/rough_observable_audit_2026-10-11/audit.json'


def verify(plan):
    for group in ('assets', 'implementation'):
        for path, expected in plan[group].items():
            if digest(path) != expected:
                raise ValueError('Frozen recovery pilot input changed: ' + path)


def prepare(output=OUTPUT):
    original, source_plan = verify_source(SOURCE)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / 'pilot_contract.json'
    if manifest.exists():
        plan = json.loads(manifest.read_text())
        verify(plan)
        return yaml.safe_load((output / 'config.yaml').read_text()), plan
    audit = json.loads(AUDIT.read_text())
    if audit['selected_correction']['before'] != .4 or audit['selected_correction']['after'] != .1:
        raise ValueError('Audit does not authorize this single correction')
    for path, expected in audit['sources_sha256'].items():
        if digest(path) != expected:
            raise ValueError('Audit evidence changed: ' + path)
    config = deepcopy(original)
    if config['reward_v2']['longitudinal_weights']['velocity_sigma_m_s'] != .4:
        raise ValueError('Unexpected source reward normalization')
    config['reward_v2']['longitudinal_weights']['velocity_sigma_m_s'] = .1
    restored = deepcopy(config)
    restored['reward_v2']['longitudinal_weights']['velocity_sigma_m_s'] = .4
    if restored != original or config['seed'] != 17000:
        raise ValueError('Changes beyond the selected reward parameter')
    package = output / 'python/nino_rl'
    shutil.copytree(SOURCE / 'python/nino_rl', package,
                    ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
    code = replace((package / 'training_contract.py').read_text(),
                   '    contract["revision"] = 47', '    contract["revision"] = 48')
    (package / 'training_contract.py').write_text(code)
    for path in package.glob('*.py'):
        compile(path.read_text(), str(path), 'exec')
        if path.name != 'training_contract.py' and digest(path) != digest(SOURCE / 'python/nino_rl' / path.name):
            raise ValueError('Executable control or learning implementation changed')
    immutable(output / 'config.yaml', yaml.safe_dump(config, sort_keys=False))
    assets = dict(source_plan['assets'])
    assets.update({str(p): digest(p) for p in package.glob('*.py')})
    assets[str(output / 'config.yaml')] = digest(output / 'config.yaml')
    for name in ('pilot_contract.json', 'runner_contract.json', 'comparison.json'):
        assets[str(SOURCE / name)] = digest(SOURCE / name)
    assets[str(AUDIT)] = digest(AUDIT)
    # Only hardware arrival/actuation and untrained exploration outcomes are reused.
    # Reward totals in those old screens are not new-contract learning/evaluation evidence.
    for label in ('controller_pi', 'exploration'):
        for path in (SOURCE / label).rglob('*'):
            if path.is_file():
                assets[str(path)] = digest(path)
    helpers = [Path(__file__).resolve()] + [Path(__file__).with_name(name) for name in (
        'run_rough_recovery_sigma_pilot.py', 'run_rough_observable_pilot_v2.py',
        'verify_rough_recovery_sigma_pilot.py', 'verify_rough_observable_pilot.py',
        'analyze_rough_reactive_authority.py', 'run_rough_trial8_validation.py')]
    plan = dict(revision='rough_recovery_sigma_pilot_v1', training_contract_revision=48,
        assets=assets, implementation={str(p): digest(p) for p in helpers},
        steps=20480, training_seed=17000, evaluation_seeds=list(range(17100, 17105)),
        route='E1', initialization='same original fresh actor initialization; fresh critic/optimizer; zero steps',
        selected_change=dict(parameter='reward_v2.longitudinal_weights.velocity_sigma_m_s', before=.4, after=.1),
        previous_contract_sha256=digest(SOURCE / 'pilot_contract.json'),
        audit_sha256=digest(AUDIT), validated_screen_source=str(SOURCE),
        screen_reuse_qualification='Identical executable code except contract metadata; identical actor/physics/controller/sensor configuration. Reward-only change does not affect untrained exposure or physical feasibility. Old reward totals are diagnostic only.',
        controls=source_plan['controls'], observations=source_plan['observations'],
        scoring=source_plan['scoring'], quality_gate=source_plan['quality_gate'],
        confirmation=dict(only_if_pilot_passed=True, seeds=list(range(18100, 18105)),
            profiles=['nominal', 'low_friction', 'heavy'], route='E1',
            controllers=['ppo', 'pi_full', 'pi_matched'], same_gates=True,
            qualification='New reset seeds and physics absent from PPO training; same fixed terrain. No independent training-seed or unseen-layout claim.'),
        optuna_held=True)
    immutable(manifest, json.dumps(plan, indent=2) + '\n')
    return config, plan


if __name__ == '__main__':
    prepare()
    print('Prepared:', OUTPUT)
