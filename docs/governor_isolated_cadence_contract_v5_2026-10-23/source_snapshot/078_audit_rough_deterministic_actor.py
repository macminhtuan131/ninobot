#!/usr/bin/env python3
"""Replay exact saved actor inputs; audit clipping, cue sensitivity and learning units."""
import json
from pathlib import Path
import sys
import math

ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'rl_runs/rough_holding_reference_candidate_v1'
OUTPUT=ROOT/'docs/rough_actor_formulation_audit_2026-10-12'
sys.path[:0]=[str(SOURCE/'python'),str(Path(__file__).parent)]

def captures(path):
    import numpy as np
    observations=[];records=[]
    for p in sorted(path.glob('chunk_*.npz')):
        with np.load(p,allow_pickle=False) as block:
            observations.extend(block['observations'])
            records.extend(json.loads(str(r)) for r in block['records'])
    return np.asarray(observations),records

def distribution(model,obs):
    import torch
    import numpy as np
    means=[];stds=[];values=[]
    with torch.no_grad():
        for start in range(0,len(obs),256):
            t=torch.as_tensor(obs[start:start+256],dtype=torch.float32,device=model.device)
            d=model.policy.get_distribution(t).distribution
            means.extend(d.mean.cpu().numpy().flatten());stds.extend(d.stddev.cpu().numpy().flatten())
            values.extend(model.policy.predict_values(t).cpu().numpy().flatten())
    return np.asarray(means),np.asarray(stds),np.asarray(values)

def main():
    import numpy as np
    import torch
    from stable_baselines3 import PPO
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    from inspect_flat_critic import gae_targets
    torch.set_num_threads(2)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    comparison=json.loads((SOURCE/'comparison.json').read_text())
    path=Path(comparison['ppo']['model']);model=PPO.load(path,device='cpu');model.policy.set_training_mode(False)
    obs,records=captures(SOURCE/'evaluation/ppo/actor_capture')
    if obs.shape[1]!=360:raise ValueError('Wrong hardware history')
    means,stds,values=distribution(model,obs)
    actions=np.asarray([r['action'] for r in records]);scales=np.asarray([r['scale'] for r in records])
    replay_error=float(np.max(abs(np.clip(means,-1,1)-actions)))
    if replay_error>1e-4:raise ValueError('Replay differs from saved actions')
    phases=np.asarray([r['cue']['cue_phase'] for r in records])
    def stats(mask):
        m=means[mask];s=stds[mask]
        tail=[.5*math.erfc((1-a)/(b*math.sqrt(2)))+.5*math.erfc((a+1)/(b*math.sqrt(2))) for a,b in zip(m,s)]
        return dict(samples=int(sum(mask)),raw_mean=float(m.mean()),raw_min=float(m.min()),raw_max=float(m.max()),
            deterministic_clip_fraction=float(np.mean(abs(m)>=1)),
            marginal_stochastic_clip_probability=float(np.mean(tail)),mean_std=float(s.mean()),
            requested_scale_mean=float(np.mean(.775+.225*np.clip(m,-1,1))),
            executed_scale_mean=float(np.mean(scales[mask])))
    result=dict(source_model=str(path),training_updates=0,optuna_held=True,
        cpu_replay_max_action_error=replay_error,
        phases={p:stats(phases==p) for p in sorted(set(phases))},all=stats(np.ones(len(obs),dtype=bool)),
        limitations=['Counterfactual cue edits measure network sensitivity, not a physical intervention.',
            'Marginal Gaussian clipping probabilities do not imply independent gSDE samples.',
            'Saved old rollout values/log-probabilities are unavailable; exact original training gradients cannot be recovered.'])
    sensitivity={}
    for name,indices in [('latest_phase',[0]),('all_history_phase',list(range(5)))]:
        responses={}
        for phase in ('ready','holding','recovering','cooldown'):
            changed=obs.copy().reshape(-1,5,72)
            for index in indices:
                changed[:,index,62:65]=0
                if phase!='ready':changed[:,index,{'holding':62,'recovering':63,'cooldown':64}[phase]]=1
                changed[:,index,65]=.5 if phase!='ready' else 0
            altered,_,_=distribution(model,changed.reshape(-1,360))
            responses[phase]=dict(mean_requested_scale=float(np.mean(.775+.225*np.clip(altered,-1,1))),
                raw_mean_change=float(np.mean(altered-means)),
                mean_scale_change=float(np.mean(.225*(np.clip(altered,-1,1)-np.clip(means,-1,1)))))
        sensitivity[name]=responses
    result['cue_counterfactuals']=sensitivity
    terms={}
    for phase in sorted(set(phases)):
        chosen=[r for r in records if r['cue']['cue_phase']==phase]
        keys=set().union(*(r['reward_terms'] for r in chosen))
        terms[phase]={k:sum(r['reward_terms'].get(k,0) for r in chosen)/5 for k in sorted(keys)}
    result['mean_raw_reward_contributions_per_episode']=terms
    rewards=np.asarray([sum(r['reward_terms'].values())*.1 for r in records]);dones=np.asarray([bool(r['terminal']) for r in records])
    target=gae_targets(rewards,values,dones,model.gamma,model.gae_lambda)
    from stable_baselines3.common.utils import explained_variance
    result['current_critic_saved_deterministic_paths']=dict(explained_variance=float(explained_variance(values,target)),
        prediction_mean=float(values.mean()),prediction_std=float(values.std()),target_mean=float(target.mean()),
        target_std=float(target.std()),mse=float(np.mean((target-values)**2)),reward_multiplier=.1,
        caveat='Fixed final critic on deterministic evaluation trajectories; not original stochastic PPO training targets')
    events=EventAccumulator(str(path.parent/'tensorboard/PPO_1'));events.Reload()
    result['training_curves']={k:[dict(step=x.step,value=x.value) for x in events.Scalars(k)] for k in events.Tags()['scalars']
        if k.startswith('train/') and ('value' in k or 'target' in k or 'variance' in k or 'clip' in k or 'policy' in k or 'std' in k)}
    np.savez_compressed(OUTPUT/'deterministic_replay.npz',observations=obs,raw_means=means,stds=stds,values=values,actions=actions,
        phases=phases,scales=scales,learner_rewards=rewards,dones=dones,targets=target)
    (OUTPUT/'audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k in ('phases','cue_counterfactuals','current_critic_saved_deterministic_paths')},indent=2))

if __name__=='__main__':main()
