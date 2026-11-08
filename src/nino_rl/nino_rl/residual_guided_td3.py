"""Finite TD3 V3 guided pilot, isolated from frozen V1/V2/baseline artifacts."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import signal
import time
import numpy as np
from nino_control.residual_actor import PortableActor, export_actor
from nino_control.residual_velocity import FEATURES, CONTRACT_ID
from . import residual_guided_baseline as v3
from . import residual_guided_contact as contact
from .core import load_config
from .guided_td3_contract import zero_initialize, LearningScore, require_identity, audit_replay
from .residual_factory_workflow import repo
from .residual_experiment import make_environment, build_model, experiment_contract, source_fingerprint
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import latest, save, emit, json_value, runtime_versions

ACTIONS = ('sim-v3-contract','sim-v3-train','sim-v3-evaluate')
CONTACT_ROOT = Path.home()/'nino_research/sim_guided_contact_v1'

def protocol():
    p = load_config(repo()/'src/nino_rl/config/residual_guided_td3_v3.yaml')
    expected = {(arm,scenario,repeat) for arm in ('B0','TD3_h5') for scenario in ('clear_box','box_c1_6mm') for repeat in (0,1)}
    actual = [(r['arm'],r['scenario'],r['repeat']) for r in p['evaluation_order']]
    if (p['training_transitions'],p['training_max_episodes'],p['learner_seed'],p['hardware_actions'],p['evaluation_transitions_maximum'])!=(512,4,7,0,1120):
        raise ValueError('V3 finite budget/seed change requires a new protocol')
    if set(actual)!=expected or len(actual)!=8 or p['train_scenario']!='box_c1_6mm' or p['parameter_profile']!='nino_td3_smoke_h5_v1':
        raise ValueError('V3 fixed conditions/profile mismatch')
    if p['initialization']!='zero_final_actor_linear_and_sync_target': raise ValueError('V3 requires fresh zero-init actor')
    r=p['reward']
    if (set(r)!={'id','velocity_scale_m_s','yaw_rate_scale_rad_s','weights','penalties'}
            or set(r['weights'])!={'velocity','yaw','action','action_change'}
            or set(r['penalties'])!={'physical_failure','missing_marker','not_stopped'}):
        raise ValueError('V3 reward schema mismatch')
    if any(not math.isfinite(v) or v<=0 for v in (r['velocity_scale_m_s'],r['yaw_rate_scale_rad_s'])):
        raise ValueError('Positive finite V3 reward scales required')
    if any(not math.isfinite(v) or v<0 for v in (*r['weights'].values(),*r['penalties'].values())):
        raise ValueError('Nonnegative finite V3 reward weights/penalties required')
    return p

def fingerprint():
    paths = [Path(__file__),Path(__file__).with_name('guided_td3_contract.py'),
        repo()/'src/nino_rl/config/residual_guided_td3_v3.yaml',repo()/'src/nino_rl/scripts/residual_guided_td3.sh']
    files = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(dict(files=files,frozen_contact_parent=contact.fingerprint()),sort_keys=True).encode()).hexdigest()

def configuration(scenario='box_c1_6mm', training=False):
    p, parent = protocol(), contact.protocol()
    condition = dict(arm='guided',path_bearing_deg=0.,scenario=scenario,repeat=0)
    c,g = v3.configuration(condition,parent)
    c['purpose']=p['protocol_id']; c['simulation_authority']=1.; c['hardware_authority']=0.
    c['backend'].update(scenario_id=scenario+'_guided_td3_v3',max_episodes=4 if training else 1)
    # Keep the tested follower identity; task/reward/learner identity is separate.
    return c,g,parent,condition

def identity():
    c,g,parent,_ = configuration()
    return dict(task_id=protocol()['protocol_id'],task_fingerprint=fingerprint(),abi_sha256=experiment_contract(c)['abi_sha256'],
        baseline_id=g['baseline_id'],guidance_sha256=hashlib.sha256(json.dumps(g,sort_keys=True).encode()).hexdigest(),
        estimator=parent['estimator'],initial_pose_m_rad=parent['initial_pose_m_rad'],
        nominal_reference_rule='separate_zero_residual_shaper_on_this_trajectory_follower_reference',
        reward=protocol()['reward'],simulation_authority=1.,hardware_authorized=False)

def dependency_record(path):
    return dict(path=str(path),manifest_sha256=hashlib.sha256((path/'manifest.json').read_bytes()).hexdigest())

def validated_latest(root, action, check_runtime=True):
    path = latest(root,action,check_runtime=check_runtime)
    if json.loads((path/'manifest.json').read_text()).get('guided_td3_fingerprint')!=fingerprint():
        raise ValueError('TD3 V3 source/protocol changed; artifact historical')
    parent = contact.validated_latest(CONTACT_ROOT,check_runtime=check_runtime) if action==ACTIONS[0] else validated_latest(root,ACTIONS[ACTIONS.index(action)-1],check_runtime)
    if json.loads((path/'dependencies.json').read_text())!=dependency_record(parent):
        raise ValueError('TD3 V3 upstream dependency changed')
    return path

def environment(c,backend,parent,condition):
    import gymnasium as gym
    inner = make_environment(c,backend)
    class GuidedLearningTask(gym.Wrapper):
        def __init__(self):
            super().__init__(inner); self.backend=backend; self.steps=0; self.score=None
        def reset(self,**kwargs):
            self.score=LearningScore(c,parent,condition,protocol()['reward']); self.steps=0
            return self.env.reset(**kwargs)
        def step(self,action):
            obs,_,term,trunc,info = self.env.step(action); self.steps+=1
            reward,task = self.score.update(info,action,self.steps*c['control_interval_s'],term)
            if task['task_deadline'] and not term:
                term,trunc=True,False
                info['termination_reason']='task_success' if task['task_success'] else 'task_deadline_failure'
            return obs,reward,term,trunc,dict(info,task=task,reward_terms=task['reward_terms'])
    return GuidedLearningTask()

def offline_contract(out):
    import gymnasium as gym
    import torch
    from stable_baselines3 import TD3
    from .td3_config import validate_runtime
    torch.set_num_threads(1)
    parent = contact.validated_latest(CONTACT_ROOT)
    if not json.loads((parent/'evaluation_result.json').read_text())['baseline_functional_candidate']:
        raise ValueError('Guided contact baseline did not pass functional gate')
    save(out/'dependencies.json',dependency_record(parent))
    c,_,_,_ = configuration(); abi=experiment_contract(c)
    class NoStepFixture(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,shape=(100,),dtype=np.float32)
        action_space=gym.spaces.Box(-1.,1.,shape=(2,),dtype=np.float32)
        def reset(self,**kwargs): raise RuntimeError('Offline contract must not collect transitions')
        def step(self,action): raise RuntimeError('Offline contract must not collect transitions')
    model=TD3('MlpPolicy',NoStepFixture(),seed=7,**validate_runtime(c))
    before=[p.detach().clone() for p in model.critic.parameters()]
    init=zero_initialize(model)
    rng=np.random.default_rng(1204); observations=rng.uniform(-1,1,(12,100)).astype(np.float32)
    with torch.no_grad():
        assert not torch.count_nonzero(model.actor(torch.as_tensor(observations)))
        assert not torch.count_nonzero(model.actor_target(torch.as_tensor(observations)))
    assert all(torch.equal(p,q) for p,q in zip(before,model.critic.parameters()))
    model.nino_guided_task=identity(); model.save(out/'zero_init_model.zip')
    loaded=TD3.load(out/'zero_init_model.zip',device='cpu')
    require_identity(loaded.nino_guided_task,identity())
    with torch.no_grad():
        assert not torch.count_nonzero(loaded.actor_target(torch.as_tensor(observations)))
    for obs in observations: np.testing.assert_array_equal(loaded.predict(obs,deterministic=True)[0],[0.,0.])
    parity=export_actor(model,'TD3',out,abi,purpose=protocol()['protocol_id']+'_zero_init_fixture')
    result=dict(task_identity=identity(),zero_initialization=init,zero_action_observations=12,
        target_zero_verified=True,critic_unchanged=True,save_load_parity=True,portable_actor=parity,
        training_transitions=0,optimizer_updates=0,physics_requests=0,hardware_authorized=False,
        scope='Offline construction/serialization only, not a trained checkpoint or new backend validation')
    save(out/'contract_result.json',result); return result

def train(out,root,worlds):
    import torch
    from stable_baselines3 import TD3
    from stable_baselines3.common.callbacks import BaseCallback
    torch.set_num_threads(1)
    parent=validated_latest(root,ACTIONS[0]);save(out/'dependencies.json',dependency_record(parent))
    p=protocol();c,g,base,condition=configuration(p['train_scenario'],training=True)
    backend=v3.GuidedBackend(c,out/'backend',worlds[p['train_scenario']],g,base,condition)
    env=environment(c,backend,base,condition)
    abi=experiment_contract(c)
    # Reuse the verified parent dynamics/reference adapter. Episode allocation
    # and nonzero policy proposals are the new bounded pilot, not prior evidence.
    validation=dict(contract_id=CONTRACT_ID,features=list(FEATURES),history_frames=5,abi_sha256=abi['abi_sha256'],
        source_fingerprint=source_fingerprint(),backend_kind=backend.kind,backend_configuration=c['backend'],
        backend_validated=True,integration_pass=True,parent_contact_baseline=dependency_record(contact.validated_latest(CONTACT_ROOT)),
        scope='Frozen tested dynamics/causal guidance adapter; new policy/task/4-episode orchestration is under test')
    save(out/'validation.json',validation)
    c['training']=dict(allowed=True,backend_validation_artifact=str(out/'validation.json'),budget_transitions=512)
    save(out/'training_config.json',c);save(out/'task_identity.json',identity())
    model=build_model(c,env,p['learner_seed']);save(out/'zero_initialization.json',zero_initialize(model))
    model.nino_guided_task=identity(); before=[v.detach().clone() for v in model.actor.parameters()]
    class Trace(BaseCallback):
        def _on_step(self):
            for i,info in enumerate(self.locals['infos']):
                row=dict(timestep=self.num_timesteps,done=bool(self.locals['dones'][i]),
                    next_observation=info.get('terminal_observation',self.locals['new_obs'][i]),reward=float(self.locals['rewards'][i]),**info)
                with (out/'training_trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
                if info.get('intervention') or info.get('termination_reason')=='physical_envelope_failure':return False
            if self.num_timesteps%64==0:emit(ACTIONS[1],f'TD3 V3 {self.num_timesteps}/512',self.num_timesteps/512)
            return True
    try:
        model.learn(total_timesteps=512,callback=Trace())
        model.save(out/'model.zip');model.save_replay_buffer(out/'replay_buffer.pkl')
        rows=[json.loads(line) for line in (out/'training_trace.jsonl').read_text().splitlines()]
        if len(rows)!=512:raise ValueError('Early pilot closure; retain partial artifacts, do not retry')
        replay=audit_replay(model.replay_buffer,rows)
        change=float(sum((v.detach()-q).abs().sum().item() for v,q in zip(model.actor.parameters(),before)))
        if not math.isfinite(change) or change<=0 or model._n_updates!=496:raise ValueError('Expected finite actor update and 496 critic updates')
        parity=export_actor(model,'TD3',out,experiment_contract(c),purpose=p['protocol_id'])
        save(out/'task_checkpoint.json',identity())
        loaded=TD3.load(out/'model.zip',device='cpu');require_identity(loaded.nino_guided_task,identity())
        loaded.load_replay_buffer(out/'replay_buffer.pkl');audit_replay(loaded.replay_buffer,rows)
        for row in rows[::43]:
            obs=np.asarray(row['reference_trace']['observation'],np.float32)
            np.testing.assert_array_equal(loaded.predict(obs,deterministic=True)[0],model.predict(obs,deterministic=True)[0])
        for network in ('actor','actor_target','critic','critic_target'):
            assert all(torch.equal(a,b) for a,b in zip(getattr(model,network).parameters(),getattr(loaded,network).parameters()))
        for name in ('actor','critic'):
            actual=getattr(loaded,name).optimizer.state_dict();expected=getattr(model,name).optimizer.state_dict()
            assert actual['param_groups']==expected['param_groups']
            for key,values in expected['state'].items():
                for field,value in values.items():
                    other=actual['state'][key][field]
                    assert torch.equal(value,other) if isinstance(value,torch.Tensor) else value==other
        result=dict(task_identity=identity(),scenario=p['train_scenario'],transitions=512,optimizer_updates=int(model._n_updates),
            actor_parameter_l1_change=change,replay=replay,portable_actor=parity,save_load_model_optimizer_target_replay_verified=True,
            learner_seeds=[7],task_terminals=sum(r['done'] for r in rows),task_success_terminals=sum(r['task']['task_success'] for r in rows if r['done']),
            timeouts=sum(r['TimeLimit.truncated'] for r in rows),final_training_segment_right_censored=not rows[-1]['done'],
            benefit_verified=False,hardware_authorized=False)
        save(out/'training_result.json',result);return result
    except BaseException:
        model.save(out/'partial_model_failed.zip');model.save_replay_buffer(out/'partial_replay_failed.pkl');raise
    finally:env.close()

def rollout(out,condition,world,actor=None):
    out.mkdir();c,g,base,backend_condition=configuration(condition['scenario'])
    backend_condition['repeat']=condition['repeat']
    save(out/'config.json',c);save(out/'guidance_config.json',g)
    backend=v3.GuidedBackend(c,out/'backend',world,g,base,backend_condition);env=environment(c,backend,base,backend_condition)
    rows=[]
    try:
        obs,info=env.reset(seed=701);save(out/'reset.json',info)
        for step in range(140):
            action=actor(obs) if actor is not None else np.zeros(2,np.float32)
            obs,reward,term,trunc,info=env.step(action)
            row=dict(step=step,reward=reward,terminated=term,truncated=trunc,**info);rows.append(row)
            with (out/'trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
            if (step+1)%35==0:emit(ACTIONS[2],out.name+f' {step+1}/140')
            if term or trunc:break
    finally:env.close()
    result=v3.summarize(rows,out)
    result['condition']=condition
    moving=[r for r in rows if r['reference_trace']['original_baseline_body'][0]>0]
    pre=[r for r in moving if r['task']['elapsed_s']<3.5]
    for name,selected in [('motion',moving),('pre_manifold_window',pre)]:
        result[name+'_mean_accepted_yaw_rad_s']=float(np.mean([r['reference_trace']['body_reference'][1] for r in selected]))
        result[name+'_mean_accepted_policy_delta_wheel_m_s']=np.mean([r['reference_trace']['accepted_policy_delta_wheel_m_s'] for r in selected],axis=0).tolist()
    result['pre_manifold_window_note']='Fixed task t<3.5 s diagnostic, not a claim of first loaded contact'
    save(out/'summary.json',result);return result

def evaluate(out,root,worlds):
    trained=validated_latest(root,ACTIONS[1]);save(out/'dependencies.json',dependency_record(trained))
    require_identity(json.loads((trained/'task_checkpoint.json').read_text()),identity())
    actor=PortableActor(trained,identity()['abi_sha256']);runs=[]
    for index,condition in enumerate(protocol()['evaluation_order']):
        emit(ACTIONS[2],str(index+1)+'/8 · '+str(condition),index/8)
        name=condition['arm']+'_'+condition['scenario']+'_'+str(condition['repeat'])
        result=rollout(out/name,condition,worlds[condition['scenario']],actor if condition['arm']=='TD3_h5' else None)
        runs.append(result);save(out/'evaluation_progress.json',runs)
        if result['physical_failure'] or result['guidance_faults'] or result['steps']!=140:
            raise RuntimeError('Evaluation physical/source/guidance failure; retain data, no retry')
    result=dict(task_identity=identity(),runs=runs,checkpoint=str(trained),training_seeds=[7],
        evaluation_transitions=sum(r['steps'] for r in runs),evaluation_conditions_seen_before=True,
        independent_gazebo_seeds_verified=False,all_task_and_stop_pass=all(r['task_success'] and r['stop_completed'] for r in runs),
        all_td3_functional_proposals_pass=all(r['functional_proposal_pass'] for r in runs if r['condition']['arm']=='TD3_h5'),
        minimum_effect_accepted=None,benefit_verified=False,hardware_authorized=False,
        conclusion='Descriptive one-seed guided pilot, not convergence, generalization or learned benefit certification')
    save(out/'evaluation_result.json',result);return result

def run(root,action):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    shared=Path.home()/'nino_research/.factory_sim.lock';shared.parent.mkdir(parents=True,exist_ok=True)
    with shared.open('a') as resource,(root/'.job.lock').open('a') as lock:
        fcntl.flock(resource,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state_path=root/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else dict(schema_version=1,latest={},runs=[])
        if any(r['action']==action for r in state['runs']):raise ValueError('V3 stage already consumed; no automatic retry or reopening')
        if action!=ACTIONS[0]:validated_latest(root,ACTIONS[ACTIONS.index(action)-1])
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+action);out.mkdir()
        current,start,status,error,result=fingerprint(),time.monotonic(),'running',None,None
        save(out/'protocol.json',protocol());save(out/'task_identity.json',identity())
        def timeout(signum,frame):raise TimeoutError('TD3 V3 finite wall deadline')
        previous=signal.signal(signal.SIGALRM,timeout);signal.alarm(protocol()['wall_deadline_per_job_s'])
        emit(action,'Start bounded TD3 V3 stage',0.,directory=str(out))
        try:
            if action==ACTIONS[0]:result=offline_contract(out)
            else:
                worlds=prepare_worlds(out)
                result=train(out,root,worlds) if action==ACTIONS[1] else evaluate(out,root,worlds)
            if fingerprint()!=current:raise ValueError('TD3 V3 sources changed during job')
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,previous)
            save(out/'job.json',dict(action=action,status=status,error=error,wall_s=time.monotonic()-start,hardware_actions=0))
            save(out/'manifest.json',dict(action=action,status=status,guided_td3_fingerprint=current,
                source_fingerprint=source_fingerprint(),runtime=runtime_versions(),hardware_actions=0,
                files={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
            state['runs'].append(dict(action=action,path=out.name,status=status,error=error))
            if status=='completed':state['latest'][action]=out.name
            save(state_path,state);emit(action,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=ACTIONS)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    try:run(args.output,args.action)
    except (Exception,KeyboardInterrupt) as exc:print('TD3 V3 failed/retained:',exc,flush=True);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
