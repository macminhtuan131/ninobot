"""Bounded actual-Nino simulation branch: baselines -> TD3 -> held-out rollouts.

Controlled solid-box worlds isolate actuator/low-step feasibility from the
original mixed factory's 22 mm C1. No original world or physical controller is
modified. One seed and one rollout per arm are descriptive, not a benefit test.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import signal
import time
import xml.etree.ElementTree as ET
import numpy as np
from .core import load_config
from .factory_velocity_backend import FactoryVelocityBackend
from .residual_factory_workflow import repo,prepare as prepare_factory,environment,factory_fingerprint
from .residual_experiment import experiment_contract,build_model,source_fingerprint
from .residual_workflow import save,emit,json_value,runtime_versions,latest
from .td3_config import apply_profile
from nino_control.residual_actor import PortableActor,export_actor

ACTIONS=('sim-baselines','sim-train','sim-evaluate')


def fingerprint():
    paths=[Path(__file__),repo()/'src/nino_rl/config/residual_sim_pilot_v1.yaml',
           repo()/'src/nino_rl/scripts/residual_sim_pilot.sh']
    content={str(p.relative_to(repo())):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(dict(files=content,factory=factory_fingerprint(),source=source_fingerprint()),sort_keys=True).encode()).hexdigest()


def config():
    c=load_config(repo()/'src/nino_rl/config/residual_sim_pilot_v1.yaml')
    p=c['pilot']
    if p['training_transitions']!=256 or p['policy_steps_per_rollout']!=100 or c['hardware_authority']!=0:
        raise ValueError('A changed pilot budget/authority requires a new versioned protocol')
    return apply_profile(c,'nino_td3_smoke_h5_v1')


def prepare_worlds(out):
    """Preserve original collisions; controlled variants are new standalone worlds."""
    original=out/'original';original.mkdir()
    _,source=prepare_factory(original)
    paths={'mixed_original_22mm':source}
    source_tree=ET.parse(source)
    for scenario in ('clear_box','box_c1_6mm'):
        tree=deepcopy(source_tree);world=tree.getroot().find('world')
        # Keep factory hall and lighting. Remove all original terrain/items;
        # a box is never placed beneath the original pothole/groove mesh.
        for model in list(world.findall('model')):
            if model.get('name')!='enclosed_hall':world.remove(model)
        ground=ET.SubElement(world,'model',name='controlled_box_floor')
        ET.SubElement(ground,'static').text='true';link=ET.SubElement(ground,'link',name='ground')
        for tag in ('collision','visual'):
            node=ET.SubElement(link,tag,name='floor_'+tag);ET.SubElement(node,'pose').text='3 0 -0.05 0 0 0'
            geom=ET.SubElement(node,'geometry');box=ET.SubElement(geom,'box');ET.SubElement(box,'size').text='10 7 0.1'
            if tag=='collision':
                surface=ET.SubElement(node,'surface');friction=ET.SubElement(surface,'friction');ode=ET.SubElement(friction,'ode')
                ET.SubElement(ode,'mu').text='1.0';ET.SubElement(ode,'mu2').text='1.0'
        if scenario=='box_c1_6mm':
            model=ET.SubElement(world,'model',name='cable_bumps');ET.SubElement(model,'static').text='true'
            link=ET.SubElement(model,'link',name='cables')
            for tag in ('collision','visual'):
                node=deepcopy(source_tree.find('.//'+tag+"[@name='C1_"+tag+"']"))
                node.find('pose').text='0.65 0 0.003 1.57079632679 0 0'
                node.find('geometry/cylinder/radius').text='0.003';link.append(node)
        path=out/(scenario+'.sdf');tree.write(path,encoding='utf-8',xml_declaration=True);paths[scenario]=path
    save(out/'worlds.json',{k:dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for k,p in paths.items()})
    return paths


def scenario_config(c,name):
    result=deepcopy(c);result['backend']['scenario_id']=name
    result['backend']['world']=name+'.sdf'
    return result


def describe(rows,raw_paths):
    if not rows:raise ValueError('No valid transitions')
    poses=np.asarray([r['truth_pose_m_rad'] for r in rows]);body=np.asarray([r['body_speed_m_s'] for r in rows])
    target=np.asarray([r['applied_target_rad_s'] for r in rows]);wheel=np.asarray([r['feedback_wheel_rad_s'] for r in rows])
    final=np.asarray([r['final_ros_reference'][0] for r in rows])
    x=poses[:,0];marker=.95
    crossing=next((r['sensor_clock_s']-rows[0]['reference_trace']['input_stamp_s'] for r in rows if r['truth_pose_m_rad'][0]>=marker),None)
    contact_counts={};cable_contacts={};source_times={}
    for path in raw_paths:
        for line in path.read_text().splitlines():
            sample=json.loads(line);key=sample['channel']
            source_times.setdefault(key,[]).append(sample['stamp_s'])
            if key.startswith('contact_'):
                contact_counts[key]=contact_counts.get(key,0)+1
                for item in sample['values']:
                    if 'C1_collision' in item['collision1'] or 'C1_collision' in item['collision2']:
                        cable_contacts[key]=cable_contacts.get(key,0)+1
    gaps={k:max(np.diff(t)).item() if len(t)>1 else None for k,t in source_times.items() if not k.startswith('contact_')}
    moving=[r for r in rows if r['reference_trace']['original_baseline_body'][0]>0]
    return dict(steps=len(rows),return_value=float(sum(r['reward'] for r in rows)),
        final_x_m=float(x[-1]),forward_displacement_m=float(x[-1]-x[0]),maximum_x_m=float(x.max()),
        local_marker_x_m=marker,local_marker_reached=bool(x.max()>=marker),local_marker_time_s=crossing,
        lateral_rmse_m=float(np.sqrt(np.mean(poses[:,1]**2))),yaw_rmse_rad=float(np.sqrt(np.mean(poses[:,2]**2))),
        body_to_executed_reference_rmse_m_s=float(np.sqrt(np.mean((body-final)**2))),
        wheel_target_rmse_rad_s=np.sqrt(np.mean((target-wheel)**2,axis=0)).tolist(),
        maximum_abs_wheel_rad_s=float(np.max(np.abs(wheel))),maximum_abs_body_speed_m_s=float(np.max(np.abs(body))),
        final_body_speed_m_s=float(body[-1]),final_wheel_rad_s=wheel[-1].tolist(),
        physical_failure=any(r['terminated'] for r in rows),time_limit_truncations=sum(r['truncated'] for r in rows),
        reference_modifications=sum(bool(r['reference_trace']['reference_modified']) for r in rows),
        accepted_residual_samples=sum(max(map(abs,r['reference_trace']['accepted_policy_delta_wheel_m_s']))>1e-6 for r in rows),
        motion_source_steps=len(moving),contact_callback_counts=contact_counts,c1_manifold_callback_counts=cable_contacts,
        max_observed_source_gap_s=gaps,
        caveats=['Contact counts are manifolds, not force/load/severity.','Body reference is simulation truth, not a deployable input.',
                 'Max gaps/counts are not a proof of full acquisition coverage.','A fresh launch is not an exact-state paired counterfactual.'])


def rollout(out,c,world,arm,actor=None):
    out.mkdir();env=environment(c,out/'backend',world);rows=[]
    try:
        obs,_=env.reset(seed=701)  # learner/evaluator seed, not a claimed Gazebo noise seed
        for step in range(c['pilot']['policy_steps_per_rollout']):
            if actor is not None:proposal=actor(obs)
            elif arm=='B1_yaw':
                features=env.unwrapped.view['features'];error=features['baseline_yaw_rad_s']-features['gyro_z_rad_s']
                scale=c['pilot']['yaw_baseline_gain']*error*c['nominal_geometry']['separation']/(2*c['reference_limits']['residual_wheel_m_s'])
                proposal=np.asarray([0.,np.clip(scale,-1.,1.)],dtype=np.float32)
            else:proposal=np.zeros(2,dtype=np.float32)
            obs,reward,term,trunc,info=env.step(proposal)
            row=dict(step=step,reward=reward,terminated=term,truncated=trunc,**info);rows.append(row)
            with (out/'trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
            if (step+1)%20==0:emit('sim-evaluate',arm+' '+c['backend']['scenario_id']+' '+str(step+1)+'/100')
            if term or trunc:break
    finally:env.close()
    summary=describe(rows,sorted((out/'backend').glob('episode_*/raw_samples.jsonl')))
    save(out/'summary.json',dict(arm=arm,scenario=c['backend']['scenario_id'],**summary));return summary


def baselines(out,c,worlds):
    results={}
    for scenario in c['pilot']['baseline_scenarios']:
        emit('sim-baselines','B0 functional screen: '+scenario)
        results[scenario]=rollout(out/scenario,scenario_config(c,scenario),worlds[scenario],'B0')
        save(out/'baseline_progress.json',results)
        if results[scenario]['physical_failure']:raise RuntimeError('Physical envelope failure in '+scenario+'; no automatic retry')
    clear=results['clear_box']
    if clear['forward_displacement_m']<c['pilot']['functional_forward_gate_m']:
        raise RuntimeError('B0 clear floor lacks functional body response; inspect backend before learning')
    selected='box_c1_6mm' if results['box_c1_6mm']['local_marker_reached'] else 'clear_box'
    sc=scenario_config(c,selected);contract=experiment_contract(sc)
    save(out/'validation.json',dict(contract_id=contract['id'],features=contract['features'],history_frames=contract['history_frames'],
        abi_sha256=contract['abi_sha256'],source_fingerprint=source_fingerprint(),backend_kind=FactoryVelocityBackend.kind,
        backend_configuration=sc['backend'],backend_validated=True,integration_pass=True,
        scope='functional simulation feasibility only, not calibrated or useful learned benefit',calibrated_to_hardware=False))
    result=dict(selected_scenario=selected,results=results,selection_rule='6 mm if classical reaches local marker; otherwise clear floor only',
                original_mixed_preserved=True,benefit_verified=False,hardware_authorized=False)
    save(out/'baseline_result.json',result);return result


def validated_latest(root,action):
    path=latest(root,action)
    manifest=json.loads((path/'manifest.json').read_text())
    if manifest.get('pilot_fingerprint')!=fingerprint():raise ValueError('Pilot source/protocol changed; prior artifact is historical')
    return path


def train(out,c,worlds,root):
    import torch
    from stable_baselines3.common.callbacks import BaseCallback
    torch.set_num_threads(1)
    baseline=validated_latest(root,'sim-baselines');selection=json.loads((baseline/'baseline_result.json').read_text())['selected_scenario']
    c=scenario_config(c,selection);c['training']=dict(allowed=True,backend_validation_artifact=str(baseline/'validation.json'),budget_transitions=256)
    save(out/'training_config.json',c);save(out/'dependencies.json',dict(baseline=str(baseline),manifest_sha256=hashlib.sha256((baseline/'manifest.json').read_bytes()).hexdigest()))
    env=environment(c,out/'backend',worlds[selection]);model=build_model(c,env,seed=c['pilot']['learner_seed'])
    before=[p.detach().clone() for p in model.actor.parameters()]
    class Trace(BaseCallback):
        def _on_step(self):
            for i,info in enumerate(self.locals['infos']):
                row=dict(timestep=self.num_timesteps,done=bool(self.locals['dones'][i]),
                         next_observation=self.locals['infos'][i].get('terminal_observation',self.locals['new_obs'][i]),
                         reward=float(self.locals['rewards'][i]),**info)
                with (out/'training_trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
            if self.num_timesteps%32==0:emit('sim-train','TD3 '+str(self.num_timesteps)+'/256',self.num_timesteps/256)
            return True
    try:
        model.learn(total_timesteps=256,callback=Trace())
        model.save(out/'model.zip');model.save_replay_buffer(out/'replay_buffer.pkl')
        change=float(sum((p.detach()-q).abs().sum().item() for p,q in zip(model.actor.parameters(),before)))
        if not math.isfinite(change) or change<=0:raise ValueError('No finite actor update')
        parity=export_actor(model,'TD3',out,experiment_contract(c),purpose='bounded_sim_pilot_not_promoted')
        b=model.replay_buffer;rows=[json.loads(line) for line in (out/'training_trace.jsonl').read_text().splitlines()]
        if len(rows)!=256 or b.size()!=256:raise ValueError('Training/replay budget mismatch')
        for i,row in enumerate(rows):
            for actual,expected in [(b.actions[i,0],row['policy_proposal']),(b.observations[i,0],row['reference_trace']['observation']),
                                    (b.next_observations[i,0],row['next_observation']),([b.rewards[i,0]],[row['reward']])]:
                np.testing.assert_allclose(actual,expected,rtol=0,atol=2e-6)
            if bool(b.dones[i,0])!=row['done'] or bool(b.timeouts[i,0])!=row['TimeLimit.truncated']:
                raise ValueError('Replay done/timeout mismatch')
        result=dict(scenario=selection,transitions=256,optimizer_updates=int(model._n_updates),learner_seed=7,
            actor_parameter_l1_change=change,replay_rows_checked=256,portable_actor=parity,benefit_verified=False,hardware_authorized=False)
        save(out/'training_result.json',result);return result
    except BaseException:
        model.save(out/'partial_model_failed.zip');model.save_replay_buffer(out/'partial_replay_failed.pkl');raise
    finally:env.close()


def evaluate(out,c,worlds,root):
    trained=validated_latest(root,'sim-train');train_result=json.loads((trained/'training_result.json').read_text());scenario=train_result['scenario']
    c=scenario_config(c,scenario);actor=PortableActor(trained,experiment_contract(c)['abi_sha256'])
    results={}
    for arm in c['pilot']['evaluation_arms']:
        results[arm]=rollout(out/arm,c,worlds[scenario],arm,actor if arm=='TD3_h5' else None)
        save(out/'evaluation_progress.json',results)
    result=dict(scenario=scenario,arms=results,checkpoint=str(trained),learner_seeds=1,evaluation_runs_per_arm=1,
        inference='deterministic actor; fresh launch per arm; no exploration at evaluation',
        baseline='B0 same shaping; B1 predefined yaw P, not a tuned optimal controller',
        conclusion='descriptive pilot only; no accepted effect threshold or independent-seed confidence interval',
        benefit_verified=False,hardware_authorized=False,full_factory_generalization=False)
    save(out/'evaluation_result.json',result);return result


def run(root,action):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    with (root/'.job.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+action);out.mkdir()
        current=fingerprint();started=time.monotonic();status='running';error=None;result=None
        c=config();save(out/'protocol.json',c['pilot']);save(out/'config.json',c)
        def timeout(signum,frame):raise TimeoutError('Bounded sim pilot deadline; retain partial data')
        previous=signal.signal(signal.SIGALRM,timeout);signal.alarm(c['pilot']['wall_deadline_per_job_s'])
        emit(action,'Start bounded sim branch',0.,directory=str(out))
        try:
            worlds=prepare_worlds(out)
            result=baselines(out,c,worlds) if action=='sim-baselines' else train(out,c,worlds,root) if action=='sim-train' else evaluate(out,c,worlds,root)
            if fingerprint()!=current:raise RuntimeError('Pilot sources changed during run')
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,previous)
            save(out/'job.json',dict(action=action,status=status,error=error,wall_s=time.monotonic()-started,hardware_actions=0))
            save(out/'manifest.json',dict(action=action,status=status,pilot_fingerprint=current,source_fingerprint=source_fingerprint(),
                runtime=runtime_versions(),hardware_actions=0,files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}))
            state_path=root/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else dict(schema_version=1,latest={},runs=[])
            state['runs'].append(dict(action=action,path=out.name,status=status,error=error))
            if status=='completed':state['latest'][action]=out.name
            save(state_path,state);emit(action,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=ACTIONS);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args(argv)
    try:run(args.output,args.action)
    except (Exception,KeyboardInterrupt) as exc:print('Sim pilot failed/retained:',exc,flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
