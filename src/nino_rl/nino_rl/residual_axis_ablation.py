"""Six-run frozen V3 action ablation; no learning or hardware operations."""
from datetime import datetime, timezone
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import time
import numpy as np
from nino_control.residual_actor import PortableActor
from .core import load_config
from . import residual_guided_td3 as learner
from . import residual_guided_baseline as v3
from .guided_td3_contract import require_identity
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_experiment import source_fingerprint
from .residual_workflow import save, emit, json_value, latest, runtime_versions

ACTION='sim-axis-ablation'
CHECKPOINT_ROOT=Path.home()/'nino_research/sim_guided_td3_v3'

def protocol():
    p=load_config(repo()/'src/nino_rl/config/residual_axis_ablation_v1.yaml')
    expected=[('B0',0),('TD3_full',0),('TD3_common_only',0),('TD3_common_only',1),('TD3_full',1),('B0',1)]
    if [(r['arm'],r['repeat']) for r in p['order']]!=expected:
        raise ValueError('Ablation conditions/order need a new protocol')
    if (p['maximum_transitions'],p['steps_per_rollout'],p['training_transitions'],p['optimizer_updates'],p['hardware_actions'],p['scenario'])!=(840,140,0,0,0,'clear_box'):
        raise ValueError('Frozen ablation budget/scenario mismatch')
    if learner.fingerprint()!=p['checkpoint_task_fingerprint']:
        raise ValueError('Frozen V3 learner source changed')
    return p

def fingerprint():
    paths=[Path(__file__),repo()/'src/nino_rl/config/residual_axis_ablation_v1.yaml',repo()/'src/nino_rl/scripts/residual_axis_ablation.sh']
    return hashlib.sha256(json.dumps(dict(files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        frozen_learner_fingerprint=learner.fingerprint()),sort_keys=True).encode()).hexdigest()

def checkpoint(check_runtime=True):
    p=protocol();d=learner.validated_latest(CHECKPOINT_ROOT,'sim-v3-train',check_runtime=check_runtime)
    if d.name!=p['checkpoint_run'] or hashlib.sha256((d/'manifest.json').read_bytes()).hexdigest()!=p['checkpoint_manifest_sha256']:
        raise ValueError('Frozen checkpoint manifest mismatch; do not silently choose another policy')
    require_identity(json.loads((d/'task_checkpoint.json').read_text()),learner.identity())
    return d

def select_proposal(arm,actor,observation):
    if arm=='B0':return None,np.zeros(2,dtype=np.float32)
    if arm not in ('TD3_full','TD3_common_only'):raise ValueError('Unknown ablation arm')
    raw=np.asarray(actor(observation),dtype=np.float32)
    if raw.shape!=(2,) or not np.all(np.isfinite(raw)) or np.max(np.abs(raw))>1.:
        raise ValueError('Finite bounded actor proposal required; no silent repair')
    controlled=raw.copy()
    if arm=='TD3_common_only':controlled[1]=0.
    return raw.copy(),controlled

def rollout(out,condition,world,actor):
    out.mkdir();c,g,parent,backend_condition=learner.configuration('clear_box')
    c['purpose']=protocol()['protocol_id'];c['backend']['scenario_id']='clear_box_frozen_axis_ablation_v1'
    backend_condition['repeat']=condition['repeat']
    save(out/'config.json',c);save(out/'guidance_config.json',g)
    backend=v3.GuidedBackend(c,out/'backend',world,g,parent,backend_condition)
    env=learner.environment(c,backend,parent,backend_condition);rows=[]
    try:
        obs,info=env.reset(seed=701);save(out/'reset.json',info)
        for step in range(protocol()['steps_per_rollout']):
            raw,controlled=select_proposal(condition['arm'],actor,obs)
            obs,reward,term,trunc,info=env.step(controlled)
            row=dict(step=step,reward=reward,terminated=term,truncated=trunc,**info,
                actor_raw_proposal=raw,controller_proposal=controlled,ablation_condition=condition,
                proposal_semantics='policy_proposal is the actual controller proposal after ablation mask; actor_raw_proposal remains separate')
            rows.append(row)
            with (out/'trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
            if (step+1)%35==0:emit(ACTION,out.name+f' {step+1}/140')
            if term or trunc:break
    finally:env.close()
    result=v3.summarize(rows,out);result['condition']=dict(condition,scenario='clear_box')
    motion=[r for r in rows if r['reference_trace']['original_baseline_body'][0]>0]
    raw=[r['actor_raw_proposal'] for r in motion if r['actor_raw_proposal'] is not None]
    accepted=np.asarray([r['reference_trace']['accepted_policy_delta_wheel_m_s'] for r in motion])
    result.update(actor_raw_motion_mean=np.mean(raw,axis=0).tolist() if raw else None,
        controller_motion_mean=np.mean([r['controller_proposal'] for r in motion],axis=0).tolist(),
        policy_yaw_delta_motion_mean_rad_s=float(np.mean((accepted[:,1]-accepted[:,0])/c['nominal_geometry']['separation'])),
        accepted_yaw_motion_mean_rad_s=float(np.mean([r['reference_trace']['body_reference'][1] for r in motion])),
        actor_inference_calls=sum(r['actor_raw_proposal'] is not None for r in rows),
        training_dataset_compatible=False,training_transitions=0,optimizer_updates=0)
    save(out/'summary.json',result);return result

def evaluate(out):
    p=protocol();trained=checkpoint();save(out/'dependencies.json',learner.dependency_record(trained))
    save(out/'ablation_contract.json',dict(protocol_id=p['protocol_id'],ablation_fingerprint=fingerprint(),
        frozen_learner_identity=learner.identity(),actor_raw_field='actor_raw_proposal',controller_field='controller_proposal',
        environment_field='policy_proposal',mask_rule='common-only sets normalized differential residual to zero before projection; baseline yaw retained',
        reward_note='Inherited scorer sees controller proposal after mask; return not used for comparison/promotion',
        training_dataset_compatible=False,hardware_authorized=False))
    actor=PortableActor(trained,learner.identity()['abi_sha256']);worlds=prepare_worlds(out);runs=[]
    for index,condition in enumerate(p['order']):
        emit(ACTION,f'{index+1}/6 · '+str(condition),index/6)
        r=rollout(out/(condition['arm']+'_'+str(condition['repeat'])),condition,worlds['clear_box'],actor)
        runs.append(r);save(out/'evaluation_progress.json',runs)
        if r['physical_failure'] or r['guidance_faults'] or r['steps']!=140:
            raise RuntimeError('Ablation physical/source/guidance failure; retain data, no retry')
    arm=lambda name:[r for r in runs if r['condition']['arm']==name]
    separated=max(r['cross_track_rmse_m'] for r in arm('TD3_common_only'))<min(r['cross_track_rmse_m'] for r in arm('TD3_full'))
    result=dict(protocol_id=p['protocol_id'],runs=runs,checkpoint=str(trained),checkpoint_manifest_sha256=p['checkpoint_manifest_sha256'],
        evaluation_transitions=sum(r['steps'] for r in runs),actor_inference_calls=sum(r['actor_inference_calls'] for r in runs),
        all_task_and_stop_pass=all(r['task_success'] and r['stop_completed'] for r in runs),
        all_functional_proposals_pass=all(r['functional_proposal_pass'] for r in runs),
        descriptive_path_separation_common_vs_full=separated,training_transitions=0,optimizer_updates=0,
        independent_gazebo_seeds_verified=False,minimum_effect_accepted=None,benefit_verified=False,hardware_authorized=False,
        conclusion='Frozen action ablation with feedback histories changing under intervention; descriptive, not exact-state branching or learned benefit proof')
    save(out/'evaluation_result.json',result);return result

def validated_latest(root,check_runtime=True):
    d=latest(root,ACTION,check_runtime=check_runtime)
    if json.loads((d/'manifest.json').read_text()).get('ablation_fingerprint')!=fingerprint():
        raise ValueError('Ablation source/protocol changed; artifact historical')
    if json.loads((d/'dependencies.json').read_text())!=learner.dependency_record(checkpoint(check_runtime)):
        raise ValueError('Frozen ablation checkpoint dependency changed')
    return d

def run(root):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    shared=Path.home()/'nino_research/.factory_sim.lock';shared.parent.mkdir(parents=True,exist_ok=True)
    with shared.open('a') as resource,(root/'.job.lock').open('a') as lock:
        fcntl.flock(resource,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'state.json').exists():raise ValueError('Ablation batch already consumed; no reopening or retry')
        protocol();checkpoint()
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION);out.mkdir()
        current,start,status,error,result=fingerprint(),time.monotonic(),'running',None,None
        save(out/'protocol.json',protocol())
        def timeout(signum,frame):raise TimeoutError('Finite ablation wall deadline')
        previous=signal.signal(signal.SIGALRM,timeout);signal.alarm(protocol()['wall_deadline_s'])
        emit(ACTION,'Start frozen full/common-only/B0 clear-floor ablation',0.,directory=str(out))
        try:
            result=evaluate(out)
            if fingerprint()!=current:raise ValueError('Ablation sources changed during job')
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,previous)
            save(out/'job.json',dict(action=ACTION,status=status,error=error,wall_s=time.monotonic()-start,hardware_actions=0))
            save(out/'manifest.json',dict(action=ACTION,status=status,ablation_fingerprint=current,
                source_fingerprint=source_fingerprint(),runtime=runtime_versions(),hardware_actions=0,
                files={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
            save(root/'state.json',dict(schema_version=1,latest={ACTION:out.name} if status=='completed' else {},
                runs=[dict(action=ACTION,path=out.name,status=status,error=error)]))
            emit(ACTION,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    try:run(args.output)
    except (Exception,KeyboardInterrupt) as exc:print('Ablation failed/retained:',exc,flush=True);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
