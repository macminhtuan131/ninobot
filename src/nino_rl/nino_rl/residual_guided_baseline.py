"""Bounded V3 Gazebo baseline: causal wheel/IMU estimator -> follower -> PI.

No actor/checkpoint/optimizer is loaded. Truth is reset/evaluation only. Old
factory/V2 code and scientific artifacts remain unchanged.
"""
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
from nino_control.residual_velocity import ReferenceLimits, ResidualReference
from .core import load_config, wrap_angle
from .causal_planar_estimator import CausalPlanarEstimator
from .factory_velocity_backend import simulation_seconds
from .residual_factory_workflow import repo
from .residual_guidance import GuidanceReference, PoseSample, apply_guidance, contract as guidance_contract
from . import residual_sim_task as v2
from .residual_sim_pilot import prepare_worlds, describe
from .residual_experiment import make_environment, experiment_contract, source_fingerprint
from .residual_workflow import save, emit, json_value, latest, runtime_versions

ACTION='sim-v3-baselines'


def protocol():
    p=load_config(repo()/'src/nino_rl/config/residual_guided_baseline_v3.yaml')
    expected={(arm,angle,repeat) for arm in ('constant','guided') for angle in (-5.,5.) for repeat in (0,1)}
    actual=[(r['arm'],r['path_bearing_deg'],r['repeat']) for r in p['order']]
    if set(actual)!=expected or len(actual)!=8 or (p['maximum_transitions'],p['training_transitions'],p['hardware_actions'])!=(1120,0,0):
        raise ValueError('New baseline budget/conditions need a versioned protocol')
    if (p['steps_per_rollout'],p['horizon_s'],p['command_until_s'],p['initial_pose_m_rad'])!=(140,14.,8.,[0.,0.,0.]):
        raise ValueError('V3 fixed horizon/source/declared initial pose mismatch')
    return p


def fingerprint():
    paths=[Path(__file__),Path(__file__).with_name('causal_planar_estimator.py'),
        repo()/'src/nino_rl/config/residual_guided_baseline_v3.yaml',repo()/'src/nino_rl/scripts/residual_guided_baseline.sh']
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    guidance=guidance_contract(load_config(repo()/'src/nino_rl/config/residual_guidance_v1.yaml'))
    return hashlib.sha256(json.dumps(dict(files=files,guidance=guidance,frozen_task_parent=v2.fingerprint()),sort_keys=True).encode()).hexdigest()


def configuration(condition,p):
    c=v2.config();c['purpose']=p['protocol_id'];c['reward_weights']={}
    c['backend'].update(scenario_id='clear_box_guidance_v3',horizon_s=p['horizon_s'],command_until_s=p['command_until_s'],max_episodes=1)
    c['simulation_authority']=0.;c['hardware_authority']=0.
    g=load_config(repo()/'src/nino_rl/config/residual_guidance_v1.yaml')
    angle=math.radians(condition['path_bearing_deg']);length=p['path_length_m']
    g.update(baseline_id='nino_guided_zero_residual_v3_'+condition['arm'],clock_id='gazebo_simulation_clock',
             path_points_m=[[0.,0.],[length*math.cos(angle),length*math.sin(angle)]])
    return c,g


class GuidedBackend(v2.TaskBackend):
    def __init__(self,c,directory,world,guidance,p,condition):
        self.estimator=None;self.guidance=None;self.active=False;self.cached_view=None
        self.gconf=deepcopy(guidance);self.protocol=deepcopy(p);self.condition=deepcopy(condition)
        super().__init__(c,directory,repo(),world)

    def _receive(self,key,msg):
        super()._receive(key,msg)
        if key not in ('imu','wheel'):return
        try:
            with self.lock:
                if not self.active or self.estimator is None:return
                r=self.messages[key];values=[r['values'][2]] if key=='imu' else r['values']
                self.estimator.push(key,r['stamp_s'],values,r['receipt_monotonic_s'])
        except Exception as exc:
            with self.lock:self.error=repr(exc)

    def reset(self,seed=None):
        self.active=False;self.estimator=None;self.guidance=None;self.cached_view=None
        _,info=super().reset(seed=seed)
        with self.lock:
            epoch='guided_baseline_episode_'+str(self.episode)
            self.estimator=CausalPlanarEstimator(radius_l=self.config['nominal_geometry']['radius_l'],
                radius_r=self.config['nominal_geometry']['radius_r'],**self.protocol['estimator'])
            self.estimator.reset(stamp_s=simulation_seconds(self.start_time),pose=self.protocol['initial_pose_m_rad'],epoch=epoch)
            r=self.messages['wheel']
            self.estimator.push('wheel',r['stamp_s'],r['values'],r['receipt_monotonic_s'])
            self.guidance=GuidanceReference(self.gconf,epoch=epoch);self.active=True
        result=self.view();self.flush_raw()
        return result,dict(info,estimator_initialization=self.estimator.initialization,
            initial_pose_from_protocol=self.protocol['initial_pose_m_rad'],guidance_contract=self.guidance.contract,
            condition=self.condition,truth_used_for_guidance=False)

    def view(self):
        view=super().view()
        if not self.active:return view
        now=simulation_seconds(self.time)
        if self.cached_view is not None and self.cached_view['stamp_s']==now:return deepcopy(self.cached_view)
        with self.lock:
            records=self.estimator.advance(now);estimate=self.estimator.estimate()
        for record in records:self._store('estimator_update',record['stamp_s'],record)
        pose=estimate['pose']
        self.guidance.update_pose(PoseSample(*pose,estimate['stamp_s'],now,self.gconf['pose_frame_id'],
            self.gconf['pose_source'],self.gconf['clock_id'],estimate['epoch']))
        reference=self.guidance.command(now,permission=bool(view['permission']))
        reference['follower_requested_reference']=list(reference['reference'])
        elapsed=now-self.start_time
        if elapsed<self.protocol['warmup_s']-1e-8 or elapsed>=self.protocol['command_until_s']-1e-8:
            reference['reference']=[0.,0.];reference['profile_phase']='zero_warmup_or_stop'
        else:
            reference['profile_phase']='motion'
            if self.condition['arm']=='constant':reference['reference']=[self.config['backend']['cruise_m_s'],0.]
        view['clock_id']=self.gconf['clock_id'];view=apply_guidance(view,reference)
        view['estimator_audit']=estimate
        self._store('guidance_reference',now,reference)
        self.cached_view=deepcopy(view)
        return view

    def advance_reference(self,v,w,dt):
        view,labels,terminal,truncated,info=super().advance_reference(v,w,dt)
        info.update(guidance_audit=deepcopy(view['guidance_audit']),estimator_audit=deepcopy(view['estimator_audit']),
                    truth_used_for_guidance=False,condition=self.condition)
        return view,labels,terminal,truncated,info


class BaselineScore:
    def __init__(self,c,p,condition):
        self.c=c;self.p=p;self.angle=math.radians(condition['path_bearing_deg'])
        self.reference=ResidualReference(ReferenceLimits(**c['reference_limits']))
        self.quiet=0.;self.marker=False

    def update(self,info,elapsed,physical_failure):
        p=self.p;dt=self.c['control_interval_s'];stop=self.c['task']
        x,y,yaw=info['truth_pose_m_rad'];c,s=math.cos(self.angle),math.sin(self.angle)
        progress=c*x+s*y;cross=-s*x+c*y
        nominal=self.reference.compose(info['reference_trace']['original_baseline_body'],(0.,0.),dt,
            permission=True,sensors_fresh=True,history_ready=True,command_age_s=0.)['body_reference']
        e_v=info['body_speed_m_s']-nominal[0];e_w=info['body_yaw_rad_s']-nominal[1]
        estimated=info['estimator_audit']['pose']
        quiet=(elapsed>=p['command_until_s'] and max(map(abs,info['reference_trace']['accepted_reference_wheel_m_s']))<=stop['stop_reference_wheel_m_s']
            and info['body_speed_norm_m_s']<stop['stop_speed_norm_m_s'] and abs(info['body_yaw_rad_s'])<stop['stop_yaw_rad_s']
            and max(map(abs,info['feedback_wheel_rad_s']))<stop['stop_wheel_rad_s'])
        self.quiet=self.quiet+dt if quiet else 0.;self.marker|=progress>=p['functional_proposals']['local_progress_marker_m']
        deadline=elapsed>=p['horizon_s']-1e-8;stopped=self.quiet>=stop['stop_continuous_s']-1e-8
        terms=dict(velocity_tracking=-(e_v/.2)**2*dt,yaw_tracking=-(e_w/.5)**2*dt)
        return sum(terms.values()),dict(task_id=p['protocol_id'],elapsed_s=elapsed,nominal_shaped_body=nominal,
            path_progress_m=progress,cross_track_m=cross,path_heading_error_rad=wrap_angle(yaw-self.angle),
            estimator_position_error_m=math.hypot(estimated[0]-x,estimated[1]-y),estimator_yaw_error_rad=wrap_angle(estimated[2]-yaw),
            velocity_error_m_s=e_v,yaw_rate_error_rad_s=e_w,continuous_quiet_s=self.quiet,quiet_now=quiet,
            marker_reached=self.marker,stop_completed=stopped,task_deadline=deadline,
            task_success=bool(deadline and self.marker and stopped and not physical_failure),reward_terms=terms)


def environment(c,backend,p,condition):
    import gymnasium as gym
    inner=make_environment(c,backend)
    class BaselineTask(gym.Wrapper):
        def __init__(self):super().__init__(inner);self.backend=backend;self.score=None;self.steps=0
        def reset(self,**kwargs):
            self.score=BaselineScore(c,p,condition);self.steps=0
            return self.env.reset(**kwargs)
        def step(self,action):
            if np.any(np.asarray(action)!=0):raise ValueError('V3 baseline protocol forbids nonzero residual proposals')
            obs,_,term,trunc,info=self.env.step(action);self.steps+=1
            reward,task=self.score.update(info,self.steps*c['control_interval_s'],term)
            if task['task_deadline'] and not term:
                term,trunc=True,False;info['termination_reason']='task_success' if task['task_success'] else 'task_deadline_failure'
            return obs,reward,term,trunc,dict(info,task=task,reward_terms=task['reward_terms'])
    return BaselineTask()


def summarize(rows,directory):
    result=describe(rows,sorted((directory/'backend').glob('episode_*/raw_samples.jsonl')))
    task=rows[-1]['task'];p=protocol()
    rms=lambda name:float(np.sqrt(np.mean([r['task'][name]**2 for r in rows])))
    max_abs=lambda name:max(abs(r['task'][name]) for r in rows)
    result.update(physical_failure=any(r.get('intervention') or r['termination_reason']=='physical_envelope_failure' for r in rows),
        cross_track_rmse_m=rms('cross_track_m'),maximum_cross_track_m=max_abs('cross_track_m'),
        final_cross_track_m=task['cross_track_m'],final_path_heading_error_rad=task['path_heading_error_rad'],
        nominal_velocity_rmse_m_s=rms('velocity_error_m_s'),nominal_yaw_rate_rmse_rad_s=rms('yaw_rate_error_rad_s'),
        maximum_estimator_position_error_m=max_abs('estimator_position_error_m'),maximum_estimator_yaw_error_rad=max_abs('estimator_yaw_error_rad'),
        task_success=task['task_success'],stop_completed=task['stop_completed'],continuous_quiet_s=task['continuous_quiet_s'],
        progress_marker_reached=task['marker_reached'],final_path_progress_m=task['path_progress_m'],
        guidance_faults=sum(r['guidance_audit']['fault'] for r in rows),
        residual_proposals_nonzero=sum(any(abs(v)>0 for v in r['policy_proposal']) for r in rows),
        condition=rows[-1]['condition'],estimator_initialization=rows[0]['estimator_audit']['initialization'],
        initial_truth_pose=rows[0]['truth_pose_m_rad'],final_estimated_pose=rows[-1]['estimator_audit']['pose'],
        truth_used_for_guidance=False,benefit_verified=False,hardware_authorized=False)
    proposals=p['functional_proposals']
    result['functional_proposal_pass']=bool(task['task_success'] and result['guidance_faults']==0
        and result['maximum_estimator_position_error_m']<=proposals['maximum_estimator_position_error_m']
        and result['maximum_estimator_yaw_error_rad']<=proposals['maximum_estimator_yaw_error_rad'])
    if rows[-1]['condition']['arm']=='guided':
        result['functional_proposal_pass'] &= result['maximum_cross_track_m']<=proposals['maximum_guided_cross_track_m']
    return result


def rollout(out,p,condition,world):
    out.mkdir();c,g=configuration(condition,p);save(out/'config.json',c);save(out/'guidance_config.json',g)
    backend=GuidedBackend(c,out/'backend',world,g,p,condition);env=environment(c,backend,p,condition);rows=[]
    try:
        obs,reset=env.reset(seed=701);save(out/'reset.json',reset)
        for step in range(p['steps_per_rollout']):
            obs,reward,term,trunc,info=env.step(np.zeros(2,dtype=np.float32))
            row=dict(step=step,reward=reward,terminated=term,truncated=trunc,**info);rows.append(row)
            with (out/'trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
            if (step+1)%35==0:emit(ACTION,out.name+' '+str(step+1)+'/140')
            if term or trunc:break
    finally:env.close()
    summary=summarize(rows,out);save(out/'summary.json',summary);return summary


def evaluate(out,p):
    worlds=prepare_worlds(out);results=[]
    for index,condition in enumerate(p['order']):
        emit(ACTION,f'{index+1}/8 · '+str(condition),index/8)
        name=condition['arm']+'_'+str(condition['path_bearing_deg'])+'_'+str(condition['repeat'])
        r=rollout(out/name,p,condition,worlds['clear_box']);results.append(r);save(out/'evaluation_progress.json',results)
        if r['physical_failure'] or r['guidance_faults'] or r['steps']!=140:
            raise RuntimeError('V3 physical/guidance/coverage failure; retain batch, no automatic retry')
    separated={}
    for angle in (-5.,5.):
        guided=[r['cross_track_rmse_m'] for r in results if r['condition']['arm']=='guided' and r['condition']['path_bearing_deg']==angle]
        constant=[r['cross_track_rmse_m'] for r in results if r['condition']['arm']=='constant' and r['condition']['path_bearing_deg']==angle]
        separated[str(angle)]=max(guided)<min(constant)
    passed=all(r['functional_proposal_pass'] for r in results if r['condition']['arm']=='guided') and all(separated.values())
    result=dict(protocol_id=p['protocol_id'],runs=results,descriptive_separation_by_bearing=separated,
        baseline_functional_candidate=bool(passed),training_transitions=0,actor_loaded=False,
        truth_used_for_guidance=False,guidance_connected_to_gazebo=True,hardware_authorized=False,
        calibrated_to_hardware=False,benefit_verified=False,
        conclusion='Finite classical baseline screen, not statistical benefit or factory acceptance; inspect drift and stop individually.')
    save(out/'evaluation_result.json',result);return result


def validated_latest(root,check_runtime=True):
    path=latest(root,ACTION,check_runtime=check_runtime)
    if json.loads((path/'manifest.json').read_text()).get('baseline_fingerprint')!=fingerprint():
        raise ValueError('V3 source/protocol changed; artifact historical')
    return path


def run(root):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    shared=Path.home()/'nino_research/.factory_sim.lock';shared.parent.mkdir(parents=True,exist_ok=True)
    with shared.open('a') as resource,(root/'.job.lock').open('a') as lock:
        fcntl.flock(resource,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'state.json').exists():raise ValueError('V3 baseline batch already closed; do not reuse slots')
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION);out.mkdir()
        p=protocol();save(out/'protocol.json',p);current,start,status,error,result=fingerprint(),time.monotonic(),'running',None,None
        def timeout(signum,frame):raise TimeoutError('V3 finite wall deadline')
        previous=signal.signal(signal.SIGALRM,timeout);signal.alarm(p['wall_deadline_s'])
        emit(ACTION,'Start zero-residual guided baseline V3',0.,directory=str(out))
        try:
            result=evaluate(out,p)
            if fingerprint()!=current:raise ValueError('V3 sources changed during run')
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,previous)
            save(out/'job.json',dict(action=ACTION,status=status,error=error,wall_s=time.monotonic()-start,hardware_actions=0))
            save(out/'manifest.json',dict(action=ACTION,status=status,baseline_fingerprint=current,source_fingerprint=source_fingerprint(),
                runtime=runtime_versions(),hardware_actions=0,files={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest()
                    for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
            save(root/'state.json',dict(schema_version=1,latest={ACTION:out.name} if status=='completed' else {},
                runs=[dict(action=ACTION,path=out.name,status=status,error=error)]))
            emit(ACTION,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    try:run(args.output)
    except (Exception,KeyboardInterrupt) as exc:print('V3 baseline failed/retained:',exc,flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
