"""Bounded TD3 smoke on the actual factory mesh and Nino/ROS velocity PI.

One fixed map, 48 preflight + 128 learning transitions, no hardware I/O.
All failures are retained. No old fixture checkpoint is resumed or promoted.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import time
import xml.etree.ElementTree as ET
import numpy as np
from .core import load_config
from .factory_velocity_backend import FactoryVelocityBackend
from .residual_experiment import experiment_contract,make_environment,build_model,source_fingerprint
from .residual_workflow import save,emit,json_value,runtime_versions
from nino_control.residual_actor import export_actor,PortableActor

ACTION='factory-td3'


def repo():return Path(__file__).resolve().parents[3]


def factory_sources():
    root=repo();description=root/'src/nino_description';control=root/'src/nino_control'
    files=[Path(__file__),Path(__file__).with_name('factory_velocity_backend.py'),
        root/'src/nino_rl/config/residual_factory_td3_smoke.yaml',root/'src/nino_rl/scripts/residual_factory_smoke.sh',
        root/'src/nino_rl/launch/training_sim.launch.py',description/'launch/sim.launch.py',
        description/'scripts/gz_sim_clean',description/'urdf/nino.urdf.xacro',
        description/'config/bridge.yaml',description/'worlds/factory_floor_mixed.sdf',description/'worlds/factory_floor_mixed.json',
        control/'config/effort_drive.yaml',control/'config/controllers.yaml']
    files += [control/'nino_control'/name for name in ('effort_drive.py','kinematics.py','velocity_pi.py','control_timing.py')]
    files += list((description/'meshes').glob('*.STL'))
    world=ET.parse(description/'worlds/factory_floor_mixed.sdf')
    for uri in world.findall('.//uri'):
        if (uri.text or '').startswith('model://nino_description/'):
            files.append(description/uri.text.removeprefix('model://nino_description/'))
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}


def factory_fingerprint():
    return hashlib.sha256(json.dumps(factory_sources(),sort_keys=True).encode()).hexdigest()


def prepare(out):
    from ament_index_python.packages import get_package_share_directory
    config=load_config(repo()/'src/nino_rl/config/residual_factory_td3_smoke.yaml')
    if config['smoke']['learning_transitions']!=128 or config['smoke']['validation_transitions']!=48:
        raise ValueError('Changing this smoke budget requires a new reviewed protocol')
    description=repo()/'src/nino_description';installed=Path(get_package_share_directory('nino_description'))
    control=repo()/'src/nino_control';installed_control=Path(get_package_share_directory('nino_control'))
    for src,dest in [(description/'urdf/nino.urdf.xacro',installed/'urdf/nino.urdf.xacro'),
                     (description/'config/bridge.yaml',installed/'config/bridge.yaml'),
                     (description/'launch/sim.launch.py',installed/'launch/sim.launch.py'),
                     (description/'scripts/gz_sim_clean',Path(get_package_share_directory('nino_description')).parents[1]/'lib/nino_description/gz_sim_clean'),
                     (control/'config/effort_drive.yaml',installed_control/'config/effort_drive.yaml'),
                     (control/'config/controllers.yaml',installed_control/'config/controllers.yaml')]:
        if src.read_bytes()!=dest.read_bytes():raise ValueError('Installed package stale: '+str(dest))
    for src in (description/'meshes').glob('*.STL'):
        if src.read_bytes()!=(installed/'meshes'/src.name).read_bytes():raise ValueError('Installed robot mesh stale: '+src.name)
    source=description/'worlds/factory_floor_mixed.sdf';tree=ET.parse(source);world=tree.getroot().find('world')
    if world.get('name')!='factory_floor_lab':raise ValueError('Factory world name mismatch')
    # Add only contact instrumentation; never put a box beneath the depressions.
    if world.find("plugin[@name='gz::sim::systems::Contact']") is None:
        ET.SubElement(world,'plugin',filename='gz-sim-contact-system',name='gz::sim::systems::Contact')
    for uri in tree.findall('.//uri'):
        text=uri.text or ''
        if text.startswith('model://nino_description/'):
            relative=text.removeprefix('model://nino_description/')
            if (installed/relative).read_bytes()!=(description/relative).read_bytes():raise ValueError('Factory asset install stale')
    target=out/'factory_floor_mixed_td3_smoke.sdf';tree.write(target,encoding='utf-8',xml_declaration=True)
    save(out/'input_sources.json',factory_sources());save(out/'config.json',config)
    save(out/'contract.json',experiment_contract(config))
    return config,target


def environment(config,directory,world):
    import gymnasium as gym
    env=make_environment(config,FactoryVelocityBackend(config,directory,repo(),world))
    class PhysicalFailure(gym.Wrapper):
        def __init__(self,inner):super().__init__(inner);self.backend=inner.backend
        def step(self,action):
            obs,reward,terminal,truncated,info=self.env.step(action)
            if terminal and info.get('termination_reason')=='physical_envelope_failure':
                reward=-float(config.get('failure_penalty',10.));info=dict(info,reward_terms={'physical_failure':reward})
            return obs,reward,terminal,truncated,info
    return PhysicalFailure(env)


def preflight(out,config,world):
    env=environment(config,out/'validation_backend',world);rows=[]
    try:
        observation,_=env.reset(seed=7)
        for i in range(48):
            proposal=np.array([.65,-.35] if i>=12 else [0.,0.],dtype=np.float32)
            observation,reward,terminal,truncated,info=env.step(proposal)
            row=dict(step=i,reward=reward,terminated=terminal,truncated=truncated,**info);rows.append(row)
            with (out/'validation_trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
            if not env.observation_space.contains(observation):raise ValueError('Factory observation space violated')
            if terminal or truncated:raise RuntimeError('Factory preflight terminated before its 48-step gate')
            if (i+1)%8==0:emit(ACTION,'Factory preflight '+str(i+1)+'/48',(i+1)/48*.25)
        displacement=rows[-1]['truth_pose_m_rad'][0]-rows[0]['truth_pose_m_rad'][0]
        if displacement<.02:raise RuntimeError('Factory body did not move in preflight; no learning release')
        if not any(max(abs(x) for x in row['reference_trace']['accepted_policy_delta_wheel_m_s'])>1e-5 for row in rows):
            raise RuntimeError('Residual never reached accepted factory reference')
        if not any(max(abs(x) for x in row['feedback_wheel_rad_s'])>.1 for row in rows):raise RuntimeError('Factory wheel response absent')
        contract=experiment_contract(config)
        result=dict(contract_id=contract['id'],features=contract['features'],history_frames=contract['history_frames'],
            abi_sha256=contract['abi_sha256'],source_fingerprint=source_fingerprint(),backend_kind=FactoryVelocityBackend.kind,
            backend_configuration=config['backend'],backend_validated=True,integration_pass=True,
            factory_fingerprint=factory_fingerprint(),validation_transitions=len(rows),truth_forward_displacement_m=displacement,
            actual_robot='Nino URDF with passive swivel casters',world='factory_floor_mixed.sdf',
            evidence_level='Gazebo_factory_software_integration_only',calibrated_to_hardware=False,
            useful_physical_benefit_verified=False)
        save(out/'validation.json',result);return result
    finally:env.close()


def train(out,config,world):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    torch.set_num_threads(1);config=deepcopy(config)
    config['training']=dict(allowed=True,backend_validation_artifact=str(out/'validation.json'),budget_transitions=128)
    from .td3_config import apply_profile
    release=deepcopy(config['training'])
    config=apply_profile(config,'nino_td3_smoke_h5_v1');config['training']=release
    save(out/'training_config.json',config)
    env=environment(config,out/'training_backend',world);model=build_model(config,env,seed=7)
    before=[p.detach().clone() for p in model.actor.parameters()]
    class Trace(BaseCallback):
        def _on_step(self):
            for index,info in enumerate(self.locals['infos']):
                done=bool(self.locals['dones'][index])
                next_obs=info['terminal_observation'] if done else self.locals['new_obs'][index]
                row=dict(timestep=self.num_timesteps,recorded_next_observation=next_obs,
                    recorded_reward=float(self.locals['rewards'][index]),recorded_done=done,**info)
                with (out/'training_trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
            if self.num_timesteps%8==0:emit(ACTION,'Factory TD3 learning '+str(self.num_timesteps)+'/128',.25+.65*self.num_timesteps/128)
            return True
    try:
        model.learn(total_timesteps=128,callback=Trace());model.save(out/'model.zip');model.save_replay_buffer(out/'replay_buffer.pkl')
        change=float(sum((p-old).abs().sum().item() for p,old in zip(model.actor.parameters(),before)))
        if not math_is_positive(change):raise RuntimeError('No finite actor parameter update')
        parity=export_actor(model,'TD3',out,experiment_contract(config),purpose='factory_software_smoke')
        return dict(transitions=int(model.num_timesteps),optimizer_updates=int(model._n_updates),actor_parameter_l1_change=change,
            portable_export=parity)
    except BaseException:
        # Quarantine only; never resume/promote a partial integration attempt.
        model.save(out/'partial_model_failed.zip');model.save_replay_buffer(out/'partial_replay_failed.pkl')
        save(out/'partial_training_failed.json',dict(status='failed',transitions=int(model.num_timesteps),
            optimizer_updates=int(model._n_updates),resume_allowed=False,hardware_authorized=False))
        raise
    finally:env.close()


def math_is_positive(value):return bool(np.isfinite(value) and value>0)


def audit(out,config):
    import torch
    from stable_baselines3 import TD3
    model=TD3.load(out/'model.zip',device='cpu');model.load_replay_buffer(out/'replay_buffer.pkl');b=model.replay_buffer
    rows=[json.loads(line) for line in (out/'training_trace.jsonl').read_text().splitlines()]
    if len(rows)!=128 or b.size()!=128 or model.num_timesteps!=128:raise ValueError('Factory smoke/replay budget mismatch')
    if not all(torch.isfinite(p).all().item() for p in model.policy.parameters()):raise ValueError('Nonfinite factory checkpoint')
    if not model.actor.optimizer.state or not model.critic.optimizer.state:raise ValueError('Factory optimizer states missing')
    actor=PortableActor(out,experiment_contract(config)['abi_sha256']);max_parity=0.
    for i,row in enumerate(rows):
        for actual,expected in [(b.observations[i,0],row['reference_trace']['observation']),
                                (b.next_observations[i,0],row['recorded_next_observation']),
                                (b.actions[i,0],row['policy_proposal']),([b.rewards[i,0]],[row['recorded_reward']])]:
            np.testing.assert_allclose(actual,expected,atol=2e-6,rtol=0)
        if bool(b.dones[i,0])!=row['recorded_done'] or bool(b.timeouts[i,0])!=row['TimeLimit.truncated']:
            raise ValueError('Factory replay terminal/timeout semantics mismatch')
        obs=np.asarray(row['reference_trace']['observation'],dtype=np.float32);expected,_=model.predict(obs,deterministic=True)
        max_parity=max(max_parity,float(np.max(np.abs(actor(obs)-expected))))
        d=row['drive_diagnostics']
        if abs(d['left_residual_nm'])>1e-9 or abs(d['right_residual_nm'])>1e-9:raise ValueError('Unexpected torque residual in velocity experiment')
    if max_parity>1e-5:raise ValueError('Factory portable inference mismatch')
    poses=np.asarray([r['truth_pose_m_rad'] for r in rows])
    result=dict(replay_transitions_checked=128,portable_actor_max_error=max_parity,
        truth_x_range_m=[float(poses[:,0].min()),float(poses[:,0].max())],
        truth_y_range_m=[float(poses[:,1].min()),float(poses[:,1].max())],
        terminals=sum(r['recorded_done'] for r in rows),world='factory_floor_mixed.sdf',
        factory_fingerprint=factory_fingerprint(),calibrated_to_hardware=False,physical_benefit_verified=False,
        hardware_authorized=False,scope='bounded integration training; not successful full-route traversal or comparative benefit')
    save(out/'audit.json',result);return result


def run(root):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    with (root/'.job.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_factory-td3');out.mkdir()
        fingerprint=factory_fingerprint();status='running';error=None;result=None;start=time.monotonic()
        emit(ACTION,'Prepare actual factory map + Nino velocity PI',0.,directory=str(out))
        def timeout(signum,frame):raise TimeoutError('Factory smoke wall deadline; retain partial artifacts')
        previous=signal.signal(signal.SIGALRM,timeout);signal.alarm(900)
        try:
            config,world=prepare(out);preflight(out,config,world);result=train(out,config,world);result.update(audit(out,config))
            if factory_fingerprint()!=fingerprint:raise RuntimeError('Factory sources changed during smoke')
            save(out/'factory_result.json',result);status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,previous)
            save(out/'job.json',dict(action=ACTION,status=status,error=error,wall_s=time.monotonic()-start,hardware_actions=0))
            save(out/'manifest.json',dict(action=ACTION,status=status,source_fingerprint=source_fingerprint(),
                factory_fingerprint=fingerprint,runtime=runtime_versions(),hardware_actions=0,
                files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}))
            state_path=root/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else dict(schema_version=1,latest={},runs=[])
            state['runs'].append(dict(action=ACTION,path=out.name,status=status,error=error))
            if status=='completed':state['latest'][ACTION]=out.name
            save(state_path,state);emit(ACTION,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    try:run(a.output)
    except (Exception,KeyboardInterrupt) as exc:
        print('Factory smoke failed/retained:',exc,flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
