#!/usr/bin/env python3
"""Freeze a revision-57 actor-anchor candidate; preserve revision-56 artifacts."""
import inspect
import json
import shutil
from pathlib import Path
from copy import deepcopy
import yaml
from stable_baselines3 import PPO
from prepare_rough_foundations import ROOT, digest, immutable
from run_disturbance_reference_comparisons import replace, verify

SOURCE = ROOT / 'rl_runs/rough_rate_bc_pilot_v2'
OUTPUT = ROOT / 'rl_runs/rough_phase_anchor_pilot_v2'
AUDIT = ROOT / 'docs/rough_phase_anchor_gradient_2026-10-12/analysis.json'


def prepare():
    if (OUTPUT / 'pilot_contract.json').exists():
        plan = json.loads((OUTPUT / 'pilot_contract.json').read_text())
        verify(plan)
        return yaml.safe_load((OUTPUT / 'config.yaml').read_text()), plan
    old_plan = json.loads((SOURCE / 'pilot_contract.json').read_text())
    verify(old_plan)
    audit = json.loads(AUDIT.read_text())
    bc = json.loads((SOURCE / 'bc_verification.json').read_text())
    probe = json.loads((SOURCE / 'probe.json').read_text())
    if not audit['passed'] or not bc['passed'] or not probe['physical_passed'] or not probe['deterministic_response_passed']:
        raise ValueError('Original BC or gradient prerequisites failed')
    if digest(SOURCE / 'bc_actor.zip') != bc['actor_sha256'] or bc['actor_sha256'] != audit['actor_sha256']:
        raise ValueError('Original BC actor changed')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    package = OUTPUT / 'python/nino_rl'
    shutil.copytree(SOURCE / 'python/nino_rl', package, ignore=shutil.ignore_patterns('__pycache__'))
    config = yaml.safe_load((SOURCE / 'config.yaml').read_text())
    original = deepcopy(config)
    config['bc_anchor'] = dict(revision='holding_recovery_actor_anchor_v1',
        coefficient=audit['coefficient'], maximum_actor_gradient_ratio=.5,
        intended_initial_median_gradient_ratio=.25, samples_per_class=64, sampling_seed=17000,
        phase_filter='pre-action holding or recovering only', demonstrations=audit['demonstrations'],
        gradient_audit=str(AUDIT), original_actor=str(SOURCE / 'bc_actor.zip'),
        actor_sha256=bc['actor_sha256'], source_contract_config=str(SOURCE / 'config.yaml'))
    restored = deepcopy(config)
    restored.pop('bc_anchor')
    assert restored == original
    # Reuse the installed PPO update verbatim, with one additional actor loss
    # before backward and the existing global gradient clip/optimizer step.
    train = inspect.getsource(PPO.train)
    installed_train_sha = __import__('hashlib').sha256(train.encode()).hexdigest()
    train = replace(train, '        entropy_losses = []', '        entropy_losses = []\n        anchor_stats = []')
    train = replace(train,
        '                loss = policy_loss + self.ent_coef * entropy_loss + self.vf_coef * value_loss',
        '''                anchor_loss, anchor_stat = anchor_terms(self, policy_loss + self.ent_coef * entropy_loss)
                anchor_stats.append(anchor_stat)
                loss = policy_loss + self.ent_coef * entropy_loss + self.vf_coef * value_loss + anchor_loss''')
    train = replace(train, '        # Logs', '''        for name in anchor_stats[0]:
            self.logger.record('anchor/' + name, float(np.mean([r[name] for r in anchor_stats])))
        self.logger.record('anchor/maximum_weighted_gradient_ratio', max(r['weighted_gradient_ratio'] for r in anchor_stats))
        # Logs''')
    module = '''import numpy as np
import torch as th
import torch.nn.functional as F
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.utils import explained_variance
from nino_rl.phase_anchor import anchor_terms

class AnchoredPPO(PPO):
    def _excluded_save_params(self):
        return super()._excluded_save_params() + ['_bc_anchor_data', '_anchor_generator']

''' + train
    immutable(package / 'anchored_ppo.py', module)
    immutable(package / 'phase_anchor.py', Path(__file__).with_name('rough_phase_anchor.py').read_bytes())
    path = package / 'train.py'
    code = replace(path.read_text(), '        from stable_baselines3 import PPO', '        from nino_rl.anchored_ppo import AnchoredPPO as PPO')
    code = replace(code, '                source = PPO.load(args.init_model, device=device)',
        '                from stable_baselines3 import PPO as SourcePPO\n                source = SourcePPO.load(args.init_model, device=device)')
    code = replace(code, '                validate_resume(source, config)',
        '''                import importlib.util
                source_config_path = Path(config['bc_anchor']['source_contract_config'])
                source_contract_path = source_config_path.parent / 'python/nino_rl/training_contract.py'
                source_spec = importlib.util.spec_from_file_location('original_bc_contract', source_contract_path)
                source_module = importlib.util.module_from_spec(source_spec)
                source_spec.loader.exec_module(source_module)
                source_module.validate_resume(source, load_config(source_config_path))''')
    code = replace(code, '            model.nino_training_contract = training_contract(config)',
        '            model.nino_bc_anchor = deepcopy(config["bc_anchor"])\n            model.nino_training_contract = training_contract(config)')
    code = replace(code, '    import json\n    import platform', '    import json\n    from copy import deepcopy\n    import platform')
    path.write_text(code)
    path = package / 'training_contract.py'
    path.write_text(replace(path.read_text(), '    contract["revision"] = 56',
        '    contract["revision"] = 57\n    contract["bc_anchor"] = deepcopy(config["bc_anchor"])'))
    for path in package.glob('*.py'):
        compile(path.read_text(), str(path), 'exec')
        if path.name not in ('train.py', 'training_contract.py', 'phase_anchor.py', 'anchored_ppo.py'):
            assert path.read_bytes() == (SOURCE / 'python/nino_rl' / path.name).read_bytes()
    immutable(OUTPUT / 'config.yaml', yaml.safe_dump(config, sort_keys=False))
    assets = dict(old_plan['assets'])
    assets.update({str(p): digest(p) for p in package.glob('*.py')})
    for p in [Path(__file__), Path(__file__).with_name('rough_phase_anchor.py'), Path(__file__).with_name('run_rough_phase_anchor_pilot_v2.py'),
              AUDIT, SOURCE / 'bc_actor.zip', SOURCE / 'bc_verification.json', SOURCE / 'probe.json', SOURCE / 'config.yaml', OUTPUT / 'config.yaml']:
        assets[str(p)] = digest(p)
    assets.update(audit['demonstrations'])
    final = next((SOURCE / 'train').glob('*/nino_ppo_final.zip'))
    assets[str(final)] = digest(final)
    plan = dict(revision='rough_phase_anchor_pilot_v2', training_contract_revision=57, assets=assets,
        steps=20480, training_seed=17000, evaluation_seeds=list(range(17400,17405)),
        source_actor=str(SOURCE / 'bc_actor.zip'), source_actor_sha256=bc['actor_sha256'],
        preserved_checkpoint=str(final), preserved_checkpoint_sha256=digest(final),
        selected_change='Actor-only phase-selective BC auxiliary loss; bounded relative to actor PPO gradients',
        installed_ppo_train_sha256=installed_train_sha,
        unchanged=['reward weights and terms', 'training reward scale', 'terrain', 'controller', 'observations',
            'categorical action meanings', 'speed bounds/ramp', 'training seed/budget', 'physical scoring'],
        initialization='Original BC actor, fresh critic/optimizer and zero PPO counter',
        quality_gate=old_plan['quality_gate'], scoring=old_plan['scoring'], optuna_held=True)
    immutable(OUTPUT / 'pilot_contract.json', json.dumps(plan, indent=2) + '\n')
    return config, plan


if __name__ == '__main__':
    config, plan = prepare()
    print(json.dumps(plan, indent=2))
