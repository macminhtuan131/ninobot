"""Fixed, reproducible software jobs for the Nino build GUI. Never contacts Pi.

The bounded training jobs verify optimizer/checkpoint/inference integration.
They do not claim calibrated physics, learned benefit, or release hardware.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import signal
import sys
import time
import numpy as np
from nino_control.residual_actor import PortableActor,export_actor
from .core import load_config
from .residual_experiment import experiment_contract,source_fingerprint,make_environment,build_model
from .velocity_backend import VelocityBackend

PREFIX='@@NINO_RESEARCH@@'
ACTIONS=('validate','train-td3','train-ppo','compare','ros-fixture','gazebo-fixture','sysid')


def json_value(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError('Unsupported trace value: '+str(type(value)))


def runtime_versions():
    versions=dict(python=platform.python_version(),machine=platform.machine())
    for name in ('numpy','torch','stable-baselines3','gymnasium','PyQt5'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    return versions


def save(path,value):
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=json_value)+'\n');temp.replace(path)


def emit(action,message,progress=None,**data):
    print(PREFIX+json.dumps(dict(action=action,message=message,progress=progress,**data),ensure_ascii=False,allow_nan=False),flush=True)


def default_config():
    path=Path(__file__).resolve().parents[1]/'config/residual_velocity_td3.yaml'
    if not path.exists():
        from ament_index_python.packages import get_package_share_directory
        path=Path(get_package_share_directory('nino_rl'))/'config/residual_velocity_td3.yaml'
    config=load_config(path);config['simulation_authority']=1.;config['hardware_authority']=0.
    config['purpose']='software_integration_fixture'
    config.setdefault('backend',dict(kind='reduced_order_velocity_fixture',horizon_s=6.,cruise_m_s=.16,
        motor_lag_s=[.16,.20],wheel_gain=[1.,.97],command_delay_s=.04,motor_acceleration_rad_s2=12.))
    config.setdefault('governor_parameters',dict(target_scale=.9,minimum_hold_seconds=.8,maximum_hold_seconds=1.,
        minimum_trigger_speed_m_s=.03,wheel_radius_m=.06,stall_recovery_enabled=False))
    return config


def artifact_valid(path,action=None):
    root=Path(path);m=json.loads((root/'manifest.json').read_text())
    if m.get('status')!='completed' or m.get('source_fingerprint')!=source_fingerprint():raise ValueError('Artifact incomplete or source changed')
    if action and m.get('action')!=action:raise ValueError('Artifact action mismatch')
    for name,digest in m['files'].items():
        f=(root/name).resolve()
        if root.resolve() not in f.parents or hashlib.sha256(f.read_bytes()).hexdigest()!=digest:raise ValueError('Artifact hash/path mismatch')
    return m


def latest(root,action,check_runtime=True):
    state=json.loads((Path(root)/'state.json').read_text())
    last=next((row for row in reversed(state.get('runs',[])) if row.get('action')==action),None)
    if last and last.get('status')!='completed':
        raise ValueError('Latest '+action+' attempt failed/cancelled; review retained artifact '+str(last.get('path')))
    entry=state.get('latest',{}).get(action)
    if not entry:raise ValueError('Run '+action+' first')
    path=(Path(root)/entry).resolve()
    if Path(root).resolve() not in path.parents:raise ValueError('Artifact path escaped workflow root')
    manifest=artifact_valid(path,action)
    if check_runtime and manifest.get('runtime')!=runtime_versions():raise ValueError('Runtime changed; revalidate in the current environment')
    return path


def validation_job(out,config):
    from stable_baselines3.common.env_checker import check_env
    contract=experiment_contract(config)
    env=make_environment(config,VelocityBackend(config));check_env(env,warn=True,skip_render_check=True);env.close()
    final=[]
    for name,proposal in [('zero',(0.,0.)),('fixture',(.65,-.35))]:
        env=make_environment(config,VelocityBackend(config));obs,_=env.reset(seed=310)
        rows=[]
        try:
            for i in range(32):
                obs,r,t,tr,info=env.step(np.asarray(proposal,dtype=np.float32))
                rows.append(dict(step=i,reward=r,terminated=t,truncated=tr,**info))
            final.append(info)
        finally:env.close()
        with (out/(name+'_trace.jsonl')).open('w') as f:
            for row in rows:f.write(json.dumps(row,allow_nan=False)+'\n')
    target_delta=float(np.linalg.norm(np.array(final[0]['applied_target_rad_s'])-final[1]['applied_target_rad_s']))
    wheel_delta=float(np.linalg.norm(np.array(final[0]['feedback_wheel_rad_s'])-final[1]['feedback_wheel_rad_s']))
    if min(target_delta,wheel_delta)<1e-5:raise RuntimeError('Intervention failed to reach fixture targets/feedback')
    # Repeatability of the software fixture, not physical repeatability.
    a=VelocityBackend(config);b=VelocityBackend(config);a.reset(seed=99);b.reset(seed=99)
    if a.advance_reference(.05,0.,.1)!=b.advance_reference(.05,0.,.1):raise RuntimeError('Fixture nondeterminism')
    a.close();b.close()
    result=dict(contract_id=contract['id'],features=contract['features'],history_frames=contract['history_frames'],
        abi_sha256=contract['abi_sha256'],source_fingerprint=source_fingerprint(),backend_kind=VelocityBackend.kind,
        backend_configuration=config.get('backend',{}),
        backend_validated=True,integration_pass=True,gym_checker_pass=True,
        target_delta_rad_s=target_delta,wheel_delta_rad_s=wheel_delta,
        evidence_level='software_integration_reduced_order_only',hardware_validated=False,
        calibrated_to_hardware=False,useful_physical_benefit_verified=False)
    save(out/'validation.json',result);save(out/'contract.json',contract)
    return result


def train_job(root,out,config,algorithm,action):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    torch.set_num_threads(1)
    validation=latest(root,'validate')/'validation.json'
    config=deepcopy(config);config['algorithm']=algorithm
    config['training']=dict(allowed=True,backend_validation_artifact=str(validation),budget_transitions=128)
    if algorithm=='TD3':
        from .td3_config import apply_profile
        release=deepcopy(config['training'])
        config=apply_profile(config,'nino_td3_smoke_h5_v1')
        config['training']=release  # fixed 128-transition job; profile itself releases nothing
    else:
        config['algorithm_parameters']={algorithm:dict(learning_rate=.0003,batch_size=32,gamma=.99,
            policy_kwargs=dict(net_arch=[32,32]),device='cpu',n_steps=32,n_epochs=2)}
    save(out/'config.json',config)
    env=make_environment(config,VelocityBackend(config));model=build_model(config,env,seed=7)
    actor=model.policy.actor if algorithm=='TD3' else model.policy
    before=[p.detach().clone() for p in actor.parameters()]
    class Progress(BaseCallback):
        def _on_step(self):
            with (out/'training_trace.jsonl').open('a') as stream:
                for info in self.locals.get('infos',[]):
                    stream.write(json.dumps(dict(timestep=self.num_timesteps,**info),allow_nan=False,default=json_value)+'\n')
            if self.num_timesteps%16==0:emit(action,'Optimizer smoke: '+str(self.num_timesteps)+'/128 transitions',self.num_timesteps/128)
            return True
    try:
        model.learn(total_timesteps=128,callback=Progress())
        change=float(sum((p.detach()-old).abs().sum().item() for p,old in zip(actor.parameters(),before)))
        if change<=0:raise RuntimeError('No optimizer parameter change')
        model.save(out/'model.zip')
        if algorithm=='TD3':model.save_replay_buffer(out/'replay_buffer.pkl')
        contract=experiment_contract(config)
        parity=export_actor(model,algorithm,out,contract,purpose='software_smoke')
        save(out/'contract.json',contract)
        result=dict(algorithm=algorithm,transitions=int(model.num_timesteps),train_seed=7,optimizer_parameter_l1_change=change,
            purpose='software_smoke',calibrated_to_hardware=False,hardware_authorized=False,
            benefit_verified=False,portable_actor=parity,training_trace_rows=int(model.num_timesteps),
            replay_action='normalized policy proposal before reference projection; requested/accepted/feedback in JSONL')
        save(out/'training_result.json',result);return result
    finally:env.close()


def compare_job(root,out,config):
    contract=experiment_contract(config);policies={}
    for algorithm in ('TD3','PPO'):
        folder=latest(root,'train-'+algorithm.lower())
        policies[algorithm]=PortableActor(folder,contract['abi_sha256'])
    rows=[]
    for name in ('B0','B1_yaw','Governor','TD3','PPO'):
        for seed in (101,102,103):
            env=make_environment(config,VelocityBackend(config),governor=name=='Governor')
            obs,_=env.reset(seed=seed);reward=0.;lat=[];heading=[];interventions=0
            try:
                for i in range(100):
                    if name in policies:action=policies[name](obs)
                    elif name=='B1_yaw':
                        f=env.view['features'];error=f['baseline_yaw_rad_s']-f['gyro_z_rad_s']
                        d=.6*error*config['nominal_geometry']['separation']/(2*config['reference_limits']['residual_wheel_m_s'])
                        action=np.array([0.,np.clip(d,-1.,1.)],dtype=np.float32)
                    else:action=np.zeros(2,dtype=np.float32)
                    obs,r,t,tr,info=env.step(action);reward+=r
                    lat.append(info['labels']['lateral_m']);heading.append(info['labels']['heading_rad'])
                    interventions+=int(info['reference_trace']['reference_modified'])
                    if t or tr:break
                rows.append(dict(arm=name,seed=seed,return_value=reward,steps=i+1,
                    lateral_rmse_m=float(np.sqrt(np.mean(np.square(lat)))),heading_rmse_rad=float(np.sqrt(np.mean(np.square(heading)))),
                    position_m_rad=info['truth_pose_m_rad'],body_final_speed_m_s=info['body_speed_m_s'],
                    reference_modifications=interventions,termination=info['termination_reason']))
            finally:env.close()
    result=dict(scope='same-evaluator software fixture comparison; NOT held-out Nino physics or hardware benefit',
        independent_training_seeds=1,evaluation_seeds=[101,102,103],rows=rows,
        seed_effect='none with default deterministic dynamics/noise; repeated seed IDs are NOT independent physics conditions',
        classical_tuning_completed=False,research_superiority_claim_allowed=False,hardware_authorized=False)
    save(out/'comparison.json',result);return result


def run_job(action,root):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    with (root/'.job.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ident=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+action
        out=root/ident;out.mkdir();config=default_config();started=time.time();status='running';result=None;error=None
        save(out/'job.json',dict(action=action,status=status,start_utc=datetime.now(timezone.utc).isoformat(),hardware_actions=0))
        emit(action,'Started '+action+' · software only',0.,directory=str(out))
        try:
            if action=='validate':result=validation_job(out,config)
            elif action in ('train-td3','train-ppo'):result=train_job(root,out,config,action[6:].upper(),action)
            elif action=='compare':result=compare_job(root,out,config)
            elif action=='ros-fixture':
                from .residual_ros import fixture_job
                result=fixture_job(root,out,config)
            elif action=='gazebo-fixture':
                from .gazebo_velocity_backend import fixture_job
                result=fixture_job(root,out,config)
            elif action=='sysid':
                from .residual_sysid import analyze_registered_data
                result=analyze_registered_data(root,out)
            else:raise ValueError('Unsupported fixed job')
            status='completed'
        except KeyboardInterrupt:
            status='cancelled';error='operator_interrupt';raise
        except BaseException as exc:
            status='failed';error=str(exc);raise
        finally:
            save(out/'job.json',dict(action=action,status=status,elapsed_wall_s=time.time()-started,error=error,hardware_actions=0))
            manifest=dict(schema_version=1,action=action,status=status,source_fingerprint=source_fingerprint(),
                          runtime=runtime_versions(),
                          hardware_actions=0,files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'})
            save(out/'manifest.json',manifest)
            state_path=root/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else dict(schema_version=1,latest={},runs=[])
            state['runs'].append(dict(action=action,path=ident,status=status,error=error))
            if status=='completed':state['latest'][action]=ident
            save(state_path,state)
            emit(action,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=ACTIONS)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    try:run_job(a.action,a.output)
    except (Exception,KeyboardInterrupt) as exc:print('Workflow failed/retained:',exc,file=sys.stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
