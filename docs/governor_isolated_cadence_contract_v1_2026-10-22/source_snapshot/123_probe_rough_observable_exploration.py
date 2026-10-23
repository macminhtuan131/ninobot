#!/usr/bin/env python3
"""Gate actual sustained gSDE slowdown/recovery with an untrained fresh actor."""
import argparse
import json
from pathlib import Path
import numpy as np
import yaml


def response(rows):
    qualified=[]
    for i in range(len(rows)-2):
        segment=rows[i:i+3]
        low=all(r['scale']<=.85 for r in segment)
        disturbed=any(r['cue']['cue_disturbed'] or r['cue']['cue_phase']=='holding' for r in segment)
        after=[r for r in rows[i+3:] if r['elapsed_s']-rows[i+2]['elapsed_s']<=5.]
        recovered=any(r['scale']>=.95 for r in after)
        if low and disturbed and recovered:
            qualified.append(rows[i]['elapsed_s'])
    return dict(sustained_disturbance_slowdown_then_recovery=bool(qualified),
        event_start_times_s=qualified, minimum_scale=min(r['scale'] for r in rows),
        maximum_scale=max(r['scale'] for r in rows),
        mean_scale=float(np.mean([r['scale'] for r in rows])))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    from stable_baselines3 import PPO
    from nino_rl.policies import policy_spec
    from nino_rl.ros_env import NinoGazeboEnv
    config=yaml.safe_load(args.config.read_text())
    config['evaluation_control_trace']=True
    env=NinoGazeboEnv(config,total_training_steps=1)
    cls,kw=policy_spec(config);c=config['ppo']
    model=PPO(cls,env,policy_kwargs=kw,use_sde=True,sde_sample_freq=c['sde_sample_freq'],
        learning_rate=c['learning_rate'],n_steps=c['n_steps'],batch_size=c['batch_size'],
        seed=config['seed'],device='cuda')
    results=[]
    try:
        for seed in (17010,17011,17012):
            obs,_=env.reset(seed=seed)
            rows=[];step=0
            while True:
                if step % c['sde_sample_freq']==0:model.policy.reset_noise(1)
                action,_=model.predict(obs,deterministic=False)
                obs,reward,terminated,truncated,info=env.step(action)
                trace=info['control_trace']
                rows.append(dict(scale=info['speed_scale'],elapsed_s=trace['elapsed_s'],
                    cue={k:v for k,v in trace.items() if k.startswith('cue_')}))
                step+=1
                if terminated or truncated:break
            metric=info['episode_metrics']
            success=bool(metric['success'] and metric['truth_endpoint_error_m']<=config['goal_tolerance_m']+1e-6
                and metric['route_gates_passed']==metric['route_gates_total']
                and metric['truth_path_rmse_m']<=.05 and metric['odom_truth_position_error_m']<=.1
                and metric['termination']!='rollover')
            results.append(dict(seed=seed,physical_passed=success,response=response(rows),metrics=metric))
            print(seed,success,results[-1]['response'],flush=True)
        # This checks exploration exposure, not learned adaptation or quality.
        passed=all(r['physical_passed'] for r in results) and sum(
            r['response']['sustained_disturbance_slowdown_then_recovery'] for r in results)>=2
        result=dict(passed=passed,training_steps=0,fresh_actor=True,results=results,
            criteria='3/3 physical passes; >=2/3 runs have >=0.3s executed scale<=.85 during a cue, then >=.95 within5s',
            qualification='Stochastic untrained actor demonstrates exposure, not successful learned response',optuna_held=True)
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/'exposure_gate.json').write_text(json.dumps(result,indent=2)+'\n')
        if not passed:raise SystemExit('Exposure gate failed; pilot held')
    finally:env.close()


if __name__=='__main__':main()
