#!/usr/bin/env python3
"""Prepare one cue-conditional holding cost; do not train or change old snapshots."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
from prepare_rough_foundations import digest, immutable
from prepare_rough_recovery_sigma_pilot import OUTPUT as SOURCE, prepare as verify_source

OUTPUT = ROOT / 'rl_runs/rough_holding_reference_candidate_v1'
REFERENCE = ROOT / 'rl_runs/disturbance_reference_comparisons_v1/rough'


def prepare():
    original, source_plan = verify_source(SOURCE)
    reference = json.loads((REFERENCE / 'comparison.json').read_text())
    contract = json.loads((REFERENCE / 'contract.json').read_text())
    for path, expected in contract['assets'].items():
        if digest(path) != expected:
            raise ValueError('Reference input changed: '+path)
    if not reference['reference_passed']:
        raise ValueError('Time-matched reactive reference did not pass; correction held')
    if not all(r['profiles']['reactive']['response']['recovered'] and
               r['profiles']['reactive']['response']['minimum_scale'] < .9 and
               not r['profiles']['ppo']['response']['recovered'] for r in reference['paired']):
        raise ValueError('No consistent reference-versus-PPO holding-depth evidence')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = OUTPUT / 'pilot_contract.json'
    if manifest.exists():
        plan = json.loads(manifest.read_text())
        for path, expected in plan['assets'].items():
            if digest(path) != expected: raise ValueError('Prepared correction changed: '+path)
        return plan
    config = deepcopy(original)
    config['reward_v2']['holding_reference_target_scale'] = .70
    restored = deepcopy(config); restored['reward_v2'].pop('holding_reference_target_scale')
    assert restored == original
    package = OUTPUT / 'python/nino_rl'
    shutil.copytree(SOURCE / 'python/nino_rl', package, ignore=shutil.ignore_patterns('__pycache__'))
    code = (package / 'reactive_reward.py').read_text()
    anchor = "    terms['late_time']=-w['late_time_per_s']*late\n"
    assert code.count(anchor) == 1
    addition = '''    # Sensor-cue state is already actor-visible before this action.
    # Use the unmodified route PI request; no terrain X/teacher action is read.
    # This is a training cost, not an inference-time action override.
    ref = kwargs.get('reference')
    terms['holding_reference'] = 0.
    if reactive_holding and ref is not None and ref.valid:
        difference = (executed_scale-cfg['holding_reference_target_scale'])*ref.desired_linear_velocity
        terms['holding_reference'] = -dt*w['velocity']*(difference/w['velocity_sigma_m_s'])**2
'''
    (package / 'reactive_reward.py').write_text(code.replace(anchor, anchor+addition))
    path = package / 'training_contract.py'
    code = path.read_text(); assert code.count('    contract["revision"] = 48') == 1
    path.write_text(code.replace('    contract["revision"] = 48','    contract["revision"] = 49'))
    for p in package.glob('*.py'):
        compile(p.read_text(), str(p), 'exec')
        if p.name not in ('reactive_reward.py','training_contract.py'):
            assert p.read_bytes() == (SOURCE/'python/nino_rl'/p.name).read_bytes()
    immutable(OUTPUT / 'config.yaml', yaml.safe_dump(config, sort_keys=False))
    assets = dict(source_plan['assets']); assets.update(source_plan['implementation'])
    assets.update({str(p):digest(p) for p in package.glob('*.py')})
    for p in (Path(__file__), OUTPUT/'config.yaml', REFERENCE/'contract.json', REFERENCE/'comparison.json'):
        assets[str(p)] = digest(p)
    plan = dict(revision='rough_holding_reference_candidate_v1', training_contract_revision=49,
        assets=assets, selected_change='Add executed speed-reference tracking only during sensor-cue holding',
        target_scale=.70, weight='Existing velocity weight/sigma; no global weight changes',
        steps=20480, training_seed=17000,
        initialization='Same original fresh actor initialization; fresh critic/optimizer; zero counter',
        scoring=source_plan['scoring'], quality_gate=source_plan['quality_gate'],
        evaluation_seeds=list(range(17100,17105)), terrain='Unchanged fixed half-relief E1 nominal',
        inference='Free PPO speed target, unchanged ramp; no scripted action override',
        reference_result_sha256=digest(REFERENCE/'comparison.json'), training_started=False,
        qualification='Evidence-selected candidate; holding coefficient/value not optimized or validated by learning',
        optuna_held=True)
    immutable(manifest, json.dumps(plan, indent=2)+'\n')
    return plan


def verify(plan):
    subprocess.run([sys.executable, str(Path(__file__).with_name('verify_rough_observable_pilot.py')),
                    '--snapshot', str(OUTPUT)], check=True)
    sys.path.insert(0, str(OUTPUT/'python'))
    import gymnasium as gym
    import numpy as np
    import torch
    from stable_baselines3 import PPO
    from nino_rl.policies import policy_spec
    from nino_rl.core import RobotState
    from nino_rl.training_contract import training_contract, validate_resume
    from nino_rl.reactive_reward import compute_reward
    oldspec = importlib.util.spec_from_file_location('unchanged_reward', SOURCE/'python/nino_rl/reactive_reward.py')
    oldmodule = importlib.util.module_from_spec(oldspec); oldspec.loader.exec_module(oldmodule)
    old = yaml.safe_load((SOURCE/'config.yaml').read_text())
    new = yaml.safe_load((OUTPUT/'config.yaml').read_text())
    class Dummy(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,shape=(360,),dtype=np.float32)
        action_space=gym.spaces.Box(-1.,1.,shape=(1,),dtype=np.float32)
        def reset(self,*,seed=None,options=None): return np.zeros(360,dtype=np.float32),{}
        def step(self,action): return np.zeros(360,dtype=np.float32),0.,False,False,{}
    def fresh(cfg):
        cls,kwargs=policy_spec(cfg);p=cfg['ppo']
        return PPO(cls,Dummy(),policy_kwargs=kwargs,use_sde=True,sde_sample_freq=p['sde_sample_freq'],
                   n_steps=p['n_steps'],batch_size=p['batch_size'],seed=cfg['seed'],device='cpu')
    torch.set_num_threads(2)
    before,after=fresh(old),fresh(new)
    for k,v in before.policy.state_dict().items(): assert torch.equal(v,after.policy.state_dict()[k]),k
    assert not before.policy.optimizer.state and not after.policy.optimizer.state
    assert before.num_timesteps==after.num_timesteps==0
    assert training_contract(new)['revision']==49
    before.nino_training_contract=deepcopy(training_contract(old));before.nino_training_contract['revision']=48
    try: validate_resume(before,new)
    except ValueError: pass
    else: raise AssertionError('Old optimizer resume accepted')
    previous=SimpleNamespace(distance_remaining=10.)
    current=SimpleNamespace(distance_remaining=9.964,lateral_error=0.,heading_error=0.)
    state=RobotState(ground_linear_velocity=.36,left_wheel_velocity=5.76,right_wheel_velocity=5.76)
    args=(previous,current,state,[0.],[0.],[0.,0.],.1,dict(square_integral=.1))
    ref=SimpleNamespace(valid=True,desired_linear_velocity=.4)
    checks={}
    for holding in (False,True):
        checks[str(holding)]={}
        for scale in (.70,.76,.96,1.):
            kw=dict(reference=ref,elapsed=10.,reactive_holding=holding,
                    executed_scale=scale,previous_executed_scale=.96)
            _,a=oldmodule.compute_reward(*args,old['reward_v2'],**kw)
            _,b=compute_reward(*args,new['reward_v2'],**kw)
            for k in a: np.testing.assert_allclose(a[k],b[k],atol=1e-12)
            expected=-.1*.25*((scale-.7)*.4/.1)**2 if holding else 0.
            np.testing.assert_allclose(b['holding_reference'],expected,atol=1e-12)
            checks[str(holding)][str(scale)]=b['holding_reference']
    result=json.loads((OUTPUT/'verification.json').read_text())
    result.update(single_conditional_cost=True,all_previous_reward_terms_identical=True,
        fresh_actor_critic_identical=True,fresh_optimizer=True,old_optimizer_resume_rejected=True,
        holding_reference_checks=checks,training_started=False)
    (OUTPUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Prepared and verified revision 49: only holding-reference cost added; no training started.')


if __name__=='__main__':
    verify(prepare())
