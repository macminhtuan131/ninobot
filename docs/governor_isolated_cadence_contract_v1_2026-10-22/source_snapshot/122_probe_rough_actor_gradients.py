#!/usr/bin/env python3
"""Frozen stochastic policy rollouts, raw action likelihoods and backward-only audit."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'rl_runs/rough_holding_reference_candidate_v1'
OUTPUT=ROOT/'docs/rough_actor_formulation_audit_2026-10-12'
sys.path[:0]=[str(SOURCE/'python'),str(Path(__file__).parent)]

def capture():
    import numpy as np
    import torch
    import yaml
    from stable_baselines3 import PPO
    from nino_rl.evaluation import prepare_evaluation_config
    from nino_rl.ros_env import NinoGazeboEnv
    from prepare_rough_foundations import digest
    from inspect_flat_critic import gradient_audit
    torch.set_num_threads(2)
    config=yaml.safe_load((SOURCE/'config.yaml').read_text())
    path=Path(json.loads((SOURCE/'comparison.json').read_text())['ppo']['model'])
    sha=digest(path);model=PPO.load(path,device='cpu');model.policy.set_training_mode(False)
    parameters={n:p.detach().clone() for n,p in model.policy.named_parameters()}
    env=NinoGazeboEnv(prepare_evaluation_config(config),total_training_steps=1)
    data={k:[] for k in ('observations','actions','values','log_probs','rewards','dones','scales','previous_scales','phases','seeds')}
    episodes=[]
    try:
        for seed in (17100,17101,17102):
            torch.manual_seed(seed);obs,_=env.reset(seed=seed);step=0;previous=1.
            while True:
                if step%model.sde_sample_freq==0:model.policy.reset_noise(1)
                with torch.no_grad():
                    action,value,logp=model.policy(torch.as_tensor(obs[None],dtype=torch.float32,device=model.device))
                raw=action.cpu().numpy()[0]
                data['observations'].append(obs.copy());data['actions'].append(raw.copy())
                data['values'].append(float(value.item()));data['log_probs'].append(float(logp.item()))
                data['seeds'].append(seed)
                obs,reward,terminated,truncated,info=env.step(np.clip(raw,-1,1))
                data['rewards'].append(reward*config['training_reward_scale']);data['dones'].append(terminated or truncated)
                data['scales'].append(env.longitudinal_scale);data['previous_scales'].append(previous)
                data['phases'].append(env.reward_cue_trace['cue_phase']);previous=env.longitudinal_scale;step+=1
                if terminated or truncated:
                    episodes.append(info['episode_metrics']);print('Frozen probe',seed,info['episode_metrics']['termination'],flush=True);break
    finally:env.close()
    data={k:np.asarray(v) for k,v in data.items()};np.savez_compressed(OUTPUT/'stochastic_probe.npz',**data)
    report=gradient_audit(model,data)
    raw=data['actions'].flatten();target=.775+.225*np.clip(raw,-1,1)
    report.update(samples=len(raw),episodes=episodes,training_updates=0,
        raw_action_clipped_fraction=float(np.mean(abs(raw)>=1)),
        speed_ramp_limited_fraction=float(np.mean(abs(target-data['previous_scales'])>.040001)),
        phase_label_caveat='Probe phase labels are post-action; gradient likelihoods use exact pre-action observations',
        interpretation='Frozen final policy probe with original gSDE refresh; not historical training minibatch gradients')
    if digest(path)!=sha or any(not torch.equal(parameters[n],p) for n,p in model.policy.named_parameters()):
        raise ValueError('Read-only audit changed model')
    (OUTPUT/'gradient_probe.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('Backward-only gradient audit saved',flush=True)

def launch():
    from run_rough_trial8_validation import Validation,write
    from run_rough_hardware_confirmation import OUTPUT as CONFIRM,make_processes,verify
    from run_hardware_sensor_preflight import OUTPUT as SENSOR
    from train_rough_curriculum import assert_isolated
    OUTPUT.mkdir(parents=True,exist_ok=True)
    confirmation=json.loads((CONFIRM/'confirmation_contract.json').read_text());verify(confirmation)
    plan=json.loads((SOURCE/'pilot_contract.json').read_text())
    from run_rough_holding_pilot import verify as verify_pilot
    verify_pilot(plan)
    validation=Validation(OUTPUT/'workflow')
    write(validation.output/'correction_contract.json',dict(snapshot_assets=plan['assets']))
    env=validation.base_env.copy();env['PYTHONPATH']=str(SOURCE/'python')+os.pathsep+env.get('PYTHONPATH','')
    directory=OUTPUT/'probe'
    processes=make_processes(env,confirmation['profiles']['nominal']['launch'],SENSOR/'imu_bridge.yaml')
    try:
        assert_isolated(78,'nino_rough_78');validation.check(SOURCE/'python')
        processes.launch(confirmation['world'],directory)
        live=deepcopy(validation.old_contract['comparable_trials']);live['world']=confirmation['world']
        live['assets'].update(plan['assets']);live['assets'].update(confirmation['assets'])
        validation.assert_inputs(live,live=True)
        processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',SOURCE/'config.yaml',
            '--timeout','60'],directory/'profile.log',timeout=65)
        processes.run([sys.executable,Path(__file__),'--capture'],directory/'capture.log',timeout=600)
    finally:processes.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--capture',action='store_true');args=parser.parse_args()
    os.chdir(ROOT)
    capture() if args.capture else launch()
