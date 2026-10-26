#!/usr/bin/env python3
"""Live actuator sequence and stochastic categorical exposure; no PPO updates."""
import argparse,json
from pathlib import Path
import numpy as np
import yaml
from stable_baselines3 import PPO
from nino_rl.rate_actions import RateEnv,policy_spec
from nino_rl.ros_env import NinoGazeboEnv
from probe_rough_observable_exploration import response

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    config=yaml.safe_load(args.config.read_text());config['evaluation_control_trace']=True
    env=RateEnv(NinoGazeboEnv(config,total_training_steps=1));args.output.mkdir(parents=True,exist_ok=True)
    try:
        obs,_=env.reset(seed=17009);actual=[]
        for action in [0]*8+[1]*4+[2]*8:
            obs,_,terminated,truncated,info=env.step(action)
            actual.append(dict(action=action,scale=info['speed_scale'],trace=info['control_trace']))
            if terminated or truncated:raise ValueError('Scripted execution terminated early')
        np.testing.assert_allclose([r['scale'] for r in actual][7:12],.68,atol=1e-6)
        np.testing.assert_allclose(actual[-1]['scale'],1.,atol=1e-6)
        cls,kw=policy_spec(config);p=config['ppo']
        model=PPO(cls,env,policy_kwargs=kw,use_sde=False,n_steps=p['n_steps'],batch_size=p['batch_size'],seed=17000,device='cuda')
        attempts=[]
        for seed in (17010,17011,17012):
            obs,_=env.reset(seed=seed);rows=[]
            while True:
                action,_=model.predict(obs,deterministic=False)
                obs,_,terminated,truncated,info=env.step(action);t=info['control_trace']
                rows.append(dict(action=int(action),scale=info['speed_scale'],elapsed_s=t['elapsed_s'],
                    cue={k:v for k,v in t.items() if k.startswith('cue_')}))
                if terminated or truncated:break
            metric=info['episode_metrics']
            physical=bool(metric['success'] and metric['truth_endpoint_error_m']<=config['goal_tolerance_m']+1e-6
                and metric['route_gates_passed']==metric['route_gates_total'] and metric['truth_path_rmse_m']<=.05
                and metric['odom_truth_position_error_m']<=.1 and metric['termination']!='rollover')
            attempts.append(dict(seed=seed,physical_passed=physical,response=response(rows),metrics=metric,rows=rows))
            print(seed,physical,attempts[-1]['response'],flush=True)
        # Execution is the prerequisite requested for this formulation pilot.
        # Exposure is reported independently; it is not evidence of learning.
        result=dict(execution_passed=True,scripted_execution=actual,num_timesteps=0,
            exposure_attempts=attempts,exposure_qualified_attempts=sum(x['response']['sustained_disturbance_slowdown_then_recovery'] for x in attempts),
            physical_passed=all(x['physical_passed'] for x in attempts),optuna_held=True)
        (args.output/'execution.json').write_text(json.dumps(result,indent=2)+'\n')
        if not result['physical_passed']:raise SystemExit('Live categorical actuator feasibility failed; pilot held')
    finally:env.close()

if __name__=='__main__':main()
