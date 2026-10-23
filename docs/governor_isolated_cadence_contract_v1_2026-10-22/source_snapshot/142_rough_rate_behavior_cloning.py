#!/usr/bin/env python3
"""Causal reactive demonstrations, actor-only BC, and gated deterministic probe."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
import yaml
from stable_baselines3 import PPO
from prepare_rough_foundations import digest

def teacher(observation):
    extra=np.asarray(observation).reshape(5,72)[-1,-16:]
    scale=float(extra[10]);desired=.70 if extra[6]>.5 else 1.
    # Ties favor HOLD: from 1.00 the discrete ramp reaches .72, the closest
    # stable categorical approximation to the validated continuous .70.
    if scale>desired+.020001:return 0
    if scale<desired-.020001:return 2
    return 1

def physical(metrics,config):
    return bool(metrics['success'] and metrics['truth_endpoint_error_m']<=config['goal_tolerance_m']+1e-6
        and metrics['route_gates_passed']==metrics['route_gates_total'] and metrics['truth_path_rmse_m']<=.05
        and metrics['odom_truth_position_error_m']<=.1 and metrics['termination']!='rollover')

def live(config,output,seeds,model=None):
    from nino_rl.rate_actions import RateEnv
    from nino_rl.ros_env import NinoGazeboEnv
    from probe_rough_observable_exploration import response
    env=RateEnv(NinoGazeboEnv(config,total_training_steps=1));results=[]
    try:
        for seed in seeds:
            obs,_=env.reset(seed=seed);xs=[];actions=[];rows=[]
            while True:
                action=teacher(obs) if model is None else int(model.predict(obs,deterministic=True)[0])
                xs.append(obs.copy());actions.append(action)
                obs,_,ended,truncated,info=env.step(action);t=info['control_trace']
                rows.append(dict(action=action,scale=info['speed_scale'],elapsed_s=t['elapsed_s'],
                    cue={k:v for k,v in t.items() if k.startswith('cue_')}))
                if ended or truncated:break
            metric=info['episode_metrics'];passed=physical(metric,config)
            events=response(rows)
            result=dict(seed=seed,physical_passed=passed,response=events,metrics=metric,rows=rows,
                action_counts=np.bincount(actions,minlength=3).tolist())
            results.append(result)
            if model is None:np.savez_compressed(output/f'demo_{seed}.npz',observations=np.stack(xs),actions=np.array(actions,dtype=np.int64))
            print(seed,passed,events,flush=True)
    finally:env.close()
    result=dict(complete=True,episodes=results,physical_passed=all(x['physical_passed'] for x in results),
        deterministic_response_passed=all(x['response']['sustained_disturbance_slowdown_then_recovery'] for x in results),optuna_held=True)
    (output/('demonstrations.json' if model is None else 'probe.json')).write_text(json.dumps(result,indent=2)+'\n')
    return result

def fit(config,output):
    import gymnasium as gym
    from nino_rl.rate_actions import policy_spec
    from nino_rl.training_contract import training_contract
    class Dummy(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,shape=(360,),dtype=np.float32);action_space=gym.spaces.Discrete(3)
        def reset(self,*,seed=None,options=None):return np.zeros(360,dtype=np.float32),{}
        def step(self,a):return np.zeros(360,dtype=np.float32),0.,False,False,{}
    bc=config['behavior_cloning'];device='cuda';torch.set_num_threads(2)
    def load(seeds):
        pairs=[np.load(output/f'demo_{s}.npz') for s in seeds]
        return np.concatenate([x['observations'] for x in pairs]),np.concatenate([x['actions'] for x in pairs])
    x,y=load(bc['train_seeds']);vx,vy=load(bc['validation_seeds']);tx,ty=load(bc['test_seeds'])
    cls,kw=policy_spec(config);p=config['ppo']
    model=PPO(cls,Dummy(),policy_kwargs=kw,use_sde=False,n_steps=p['n_steps'],batch_size=p['batch_size'],seed=17000,device=device)
    model.nino_training_contract=training_contract(config)
    actor_modules=(model.policy.pi_features_extractor,model.policy.mlp_extractor.policy_net,model.policy.action_net)
    params=list({id(p):p for m in actor_modules for p in m.parameters()}.values())
    critic_modules=(model.policy.vf_features_extractor,model.policy.mlp_extractor.value_net,model.policy.value_net)
    critic_ids={id(p) for m in critic_modules for p in m.parameters()}
    assert not critic_ids.intersection(id(p) for p in params),'Actor and critic must have separate features'
    before={k:v.clone() for k,v in model.policy.state_dict().items() if k.startswith(('vf_features_extractor.','mlp_extractor.value_net.','value_net.'))}
    actor_ids={id(p) for p in params}
    for p in model.policy.parameters():p.requires_grad_(id(p) in actor_ids)
    optimizer=torch.optim.Adam(params,lr=3e-4)
    x=torch.as_tensor(x,device=device);y=torch.as_tensor(y,device=device)
    rng=np.random.default_rng(17000);indices=[np.flatnonzero(y.cpu().numpy()==i) for i in range(3)]
    if any(len(i)<10 for i in indices):raise ValueError('Insufficient demonstrated action class')
    def assess(xx,yy):
        with torch.no_grad():
            probs=model.policy.get_distribution(torch.as_tensor(xx,device=device)).distribution.probs.cpu().numpy()
        pred=probs.argmax(1);counts=np.zeros((3,3),dtype=int)
        for a,b in zip(yy,pred):counts[int(a),int(b)]+=1
        recall=[float(counts[i,i]/counts[i].sum()) if counts[i].sum() else 0. for i in range(3)]
        return dict(accuracy=float((pred==yy).mean()),class_recall=recall,confusion=counts.tolist(),
            normalized=bool(np.allclose(probs.sum(1),1.,atol=1e-6)))
    history=[]
    for epoch in range(1,201):
        model.policy.set_training_mode(True)
        for _ in range(max(12,len(x)//128)):
            chosen=np.concatenate([rng.choice(i,64,replace=True) for i in indices]);rng.shuffle(chosen)
            distribution=model.policy.get_distribution(x[chosen])
            loss=-distribution.log_prob(y[chosen]).mean();optimizer.zero_grad();loss.backward()
            torch.nn.utils.clip_grad_norm_(params,.5);optimizer.step()
        model.policy.set_training_mode(False);validation=assess(vx,vy)
        history.append(dict(epoch=epoch,loss=float(loss.detach().cpu()),validation=validation))
        if epoch%10==0:print(history[-1],flush=True)
        if validation['accuracy']>=.98 and min(validation['class_recall'])>=.95:break
    test=assess(tx,ty)
    for k,v in before.items():torch.testing.assert_close(model.policy.state_dict()[k],v,rtol=0,atol=0)
    for p in model.policy.parameters():p.requires_grad_(True)
    assert model.num_timesteps==0 and not model.policy.optimizer.state
    model.nino_bc_completed=True;model.nino_bc_metadata=dict(epochs=epoch,teacher=bc['teacher'],train_seeds=bc['train_seeds'])
    model.save(output/'bc_actor.zip')
    reloaded=PPO.load(output/'bc_actor.zip',device=device)
    with torch.no_grad():
        a=model.policy.get_distribution(torch.as_tensor(tx,device=device)).distribution.probs
        b=reloaded.policy.get_distribution(torch.as_tensor(tx,device=device)).distribution.probs
        torch.testing.assert_close(a,b,rtol=0,atol=0)
    result=dict(passed=validation['accuracy']>=.98 and min(validation['class_recall'])>=.95 and test['accuracy']>=.95 and min(test['class_recall'])>=.90,
        actor_sha256=digest(output/'bc_actor.zip'),epochs=epoch,validation=validation,test=test,history=history,
        num_ppo_timesteps=0,critic_unchanged=True,ppo_optimizer_empty=True,actor_only_training=True,
        episode_split=True,demonstration_hashes={str(p):digest(p) for p in sorted(output.glob('demo_*.npz'))},
        limitation='Small fixed-E1 imitation split; offline accuracy is not closed-loop validation or generalization',optuna_held=True)
    (output/'bc_verification.json').write_text(json.dumps(result,indent=2)+'\n');print(result['passed'],test,flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['collect','fit','probe']);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seeds',type=int,nargs='+');a=p.parse_args()
    config=yaml.safe_load(a.config.read_text());a.output.mkdir(parents=True,exist_ok=True)
    if a.mode=='fit':
        if not fit(config,a.output)['passed']:raise SystemExit('BC held-out classification failed; no PPO pilot')
    else:
        model=PPO.load(a.output/'bc_actor.zip',device='cuda') if a.mode=='probe' else None
        result=live(config,a.output,a.seeds,model)
        if not result['physical_passed'] or not result['deterministic_response_passed']:raise SystemExit('Demonstration/probe gate failed; no PPO pilot')
