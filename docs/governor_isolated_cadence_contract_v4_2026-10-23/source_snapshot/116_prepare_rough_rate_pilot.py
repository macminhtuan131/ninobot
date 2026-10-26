#!/usr/bin/env python3
"""Freeze a fresh categorical rate-action pilot without altering saved experiments."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).parent))
from prepare_rough_foundations import digest,immutable
SOURCE=ROOT/'rl_runs/rough_holding_reference_candidate_v1'
OUTPUT=ROOT/'rl_runs/rough_rate_action_pilot_v1'

def patch(path,old,new):
    code=path.read_text()
    if code.count(old)!=1:raise ValueError('Unexpected patch anchor '+str(path)+': '+old)
    path.write_text(code.replace(old,new))

def verify(plan):
    for path,expected in plan['assets'].items():
        if digest(path)!=expected:raise ValueError('Frozen rate-pilot input changed: '+path)

def prepare():
    if (OUTPUT/'pilot_contract.json').exists():
        plan=json.loads((OUTPUT/'pilot_contract.json').read_text());verify(plan)
        return yaml.safe_load((OUTPUT/'config.yaml').read_text()),plan
    source=json.loads((SOURCE/'pilot_contract.json').read_text())
    for path,expected in source['assets'].items():
        if digest(path)!=expected:raise ValueError('Source snapshot changed: '+path)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    package=OUTPUT/'python/nino_rl'
    shutil.copytree(SOURCE/'python/nino_rl',package,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(Path(__file__).with_name('rough_rate_actions.py'),package/'rate_actions.py')
    config=yaml.safe_load((SOURCE/'config.yaml').read_text())
    original=deepcopy(config)
    config['reactive_probe']['hold_seconds']=.8
    config['rate_actions']=dict(labels=['BRAKE','HOLD','RECOVER'],rates_per_s=[-.4,0.,.4],
        semantics='Increment from last executed scale; unchanged .55–1 bounds and .4/s ramp')
    config['ppo']['use_sde']=False;config['ppo']['sde_sample_freq']=-1
    config['exploration_contract']=dict(action_probability='Categorical softmax, three logits',
        initialization='Fresh generic actor, critic and optimizer; no Gaussian checkpoint transfer',
        qualification='Measured live action execution and fresh stochastic exposure; no teacher override')
    restored=deepcopy(config)
    for key in ('rate_actions','exploration_contract'):restored.pop(key)
    restored['exploration_contract']=original['exploration_contract']
    restored['reactive_probe']['hold_seconds']=.6
    restored['ppo']=original['ppo']
    assert restored==original
    patch(package/'train.py','from nino_rl.policies import policy_spec','from nino_rl.rate_actions import policy_spec')
    patch(package/'train.py','    env = NinoGazeboEnv(config, total_training_steps=args.timesteps)',
        '    from nino_rl.rate_actions import RateEnv\n    env = RateEnv(NinoGazeboEnv(config, total_training_steps=args.timesteps))')
    patch(package/'train.py','use_sde=True, sde_sample_freq=int(ppo["sde_sample_freq"]),','use_sde=False, sde_sample_freq=-1,')
    start='            labels = ("speed",)\n'
    code=(package/'train.py').read_text();a=code.index(start);b=code.index('            # Do not leave',a)
    code=code[:a]+'''            from nino_rl.rate_actions import LABELS
            from torch import as_tensor
            buffer = self.model.rollout_buffer
            distribution = self.model.policy.get_distribution(as_tensor(
                buffer.observations.reshape(-1, env.history.size), device=self.model.device))
            probabilities = distribution.distribution.probs.detach().cpu().numpy()
            for index, name in enumerate(LABELS):
                self.logger.record(f"policy/probability_{name.lower()}", float(probabilities[:,index].mean()))
                self.logger.record(f"policy/frequency_{name.lower()}", float((buffer.actions==index).mean()))
'''+code[b:];(package/'train.py').write_text(code)
    patch(package/'evaluation.py','    env = NinoGazeboEnv(config, total_training_steps=1)',
        '    env = NinoGazeboEnv(config, total_training_steps=1)\n    if not baseline:\n        from nino_rl.rate_actions import RateEnv\n        env = RateEnv(env)')
    patch(package/'evaluation.py','            if args.reactive:\n                raise ValueError("Observable pilot compares free PPO with fixed PI, not a teacher override")',
        '            if args.reactive and not baseline:\n                raise ValueError("Reactive reference is a PI baseline only")')
    patch(package/'control_v2.py','or tuple(model.action_space.shape) != (actions,)):',
        'or not (tuple(model.action_space.shape) == (actions,) or getattr(model.action_space, "n", None) == 3)):')
    patch(package/'control_v2.py','    expected = config.get("action_mode", "wheel_torque")',
        '''    categorical = bool(config.get('rate_actions'))
    if categorical != (getattr(model.action_space, 'n', None) == 3) or saved.get('rate_actions') != config.get('rate_actions'):
        raise ValueError('Checkpoint categorical rate-action contract differs from config')
    expected = config.get("action_mode", "wheel_torque")''')
    patch(package/'training_contract.py','    contract["revision"] = 49','    contract["revision"] = 51')
    patch(package/'training_contract.py','    contract["exploration_interface"] = "SB3 gSDE; matrix refresh every 6 control steps"',
        '''    contract['rate_actions'] = deepcopy(config['rate_actions'])
    contract['action_interface']['outputs'] = ['BRAKE','HOLD','RECOVER']
    contract['action_interface']['rate_per_s'] = [-.4,0.,.4]
    contract["exploration_interface"] = "Categorical softmax; PPO uses exact discrete log probabilities"''')
    path=package/'ros_env.py';code=path.read_text()
    anchor='action=float(raw_action[0]),'
    if code.count(anchor)!=1:raise ValueError('Actor capture anchor changed')
    path.write_text(code.replace(anchor,anchor+' rate_action=int(getattr(self,"selected_rate_action",-1)),'))
    changed={'train.py','evaluation.py','control_v2.py','training_contract.py','ros_env.py','rate_actions.py'}
    for p in package.glob('*.py'):
        compile(p.read_text(),str(p),'exec')
        if p.name not in changed:assert p.read_bytes()==(SOURCE/'python/nino_rl'/p.name).read_bytes()
    immutable(OUTPUT/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    assets=dict(source['assets'])
    assets.update({str(p):digest(p) for p in package.glob('*.py')})
    for p in [Path(__file__),Path(__file__).with_name('rough_rate_actions.py'),OUTPUT/'config.yaml']:
        assets[str(p)]=digest(p)
    plan=dict(revision='rough_rate_action_pilot_v1',training_contract_revision=51,assets=assets,
        steps=20480,training_seed=17000,evaluation_seeds=list(range(17100,17105)),
        initialization='Fresh categorical actor, critic, optimizer; no actor or optimizer transfer',
        changes=['Discrete BRAKE/HOLD/RECOVER speed increments','Holding .6s to .8s; .75s required at existing ramp'],
        unchanged=['Terrain','speed bounds and ramp','360 causal observations','all reward weights and terms','physical scoring'],
        quality_gate=source['quality_gate'],scoring=source['scoring'],optuna_held=True)
    immutable(OUTPUT/'pilot_contract.json',json.dumps(plan,indent=2)+'\n')
    return config,plan

if __name__=='__main__':
    config,plan=prepare();print(OUTPUT)
