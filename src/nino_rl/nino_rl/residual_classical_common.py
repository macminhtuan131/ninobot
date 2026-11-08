"""Finite classical planned-stop compensation comparison, no learning/hardware."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import signal
import time
import numpy as np
from nino_control.residual_actor import PortableActor
from nino_control.residual_velocity import ReferenceLimits,ResidualReference
from . import residual_axis_ablation as ablation
from . import residual_guided_td3 as learner
from . import residual_guided_baseline as baseline
from .core import load_config
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_experiment import source_fingerprint
from .residual_workflow import save,emit,json_value,latest,runtime_versions

ACTION='sim-classical-common'
PARENT_ROOT=Path.home()/'nino_research/sim_axis_ablation_v1'

def protocol():
    p=load_config(repo()/'src/nino_rl/config/residual_classical_common_v1.yaml')
    order=[('B0',0),('Classical_scheduled',0),('TD3_common_only',0),('TD3_common_only',1),('Classical_scheduled',1),('B0',1)]
    if [(r['arm'],r['repeat']) for r in p['order']]!=order:raise ValueError('New conditions/order require a new protocol')
    if (p['scenario'],p['maximum_transitions'],p['steps_per_rollout'],p['training_transitions'],p['optimizer_updates'],p['hardware_actions'])!=('clear_box',840,140,0,0,0):
        raise ValueError('Classical common budget/scenario mismatch')
    if (p['common_compensation_m_s'],p['residual_scale_m_s'],p['nominal_steady_m_s'],p['withdraw_at_task_s'],p['planned_source_stop_s'])!=(.005,.04,.2,7.5,8.):
        raise ValueError('Fixed development candidate changed; no tuning inside this batch')
    if ablation.fingerprint()!=p['ablation_fingerprint']:raise ValueError('Frozen ablation parent changed')
    return p

def fingerprint():
    paths=[Path(__file__),repo()/'src/nino_rl/config/residual_classical_common_v1.yaml',repo()/'src/nino_rl/scripts/residual_classical_common.sh']
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(dict(files=files,parent=ablation.fingerprint()),sort_keys=True).encode()).hexdigest()

def parents(check_runtime=True):
    p=protocol();parent=ablation.validated_latest(PARENT_ROOT,check_runtime=check_runtime)
    result=json.loads((parent/'evaluation_result.json').read_text())
    if result['evaluation_transitions']!=840:raise ValueError('Prior ablation did not close all six conditions')
    return parent,ablation.checkpoint(check_runtime)

class ClassicalCommonProfile:
    """Planned reference schedule only; no truth, contact, body-speed or actor input."""
    def __init__(self,config,p):
        self.p=p;self.dt=config['control_interval_s'];self.nominal=ResidualReference(ReferenceLimits(**config['reference_limits']))
        if config['reference_limits']['residual_wheel_m_s']!=p['residual_scale_m_s'] or self.dt!=.1:
            raise ValueError('Candidate must use the frozen scale and control interval')

    def proposal(self,elapsed,view,history_ready,*,done=False,latched=False):
        if not math.isfinite(elapsed) or elapsed<0:raise ValueError('Finite nonnegative decision clock required')
        # Match the evaluator's independent zero-residual nominal shaper. This
        # consumes only this trajectory's causal follower reference, never GT.
        source=view['baseline'];age=view['command_age_s']
        nominal=self.nominal.compose(source,(0.,0.),self.dt,permission=True,sensors_fresh=True,history_ready=True,command_age_s=0.)['body_reference']
        healthy=(view['permission'] and view['sensors_fresh'] and not view['fault'] and not view['emergency_stop']
            and history_ready and not done and not latched and math.isfinite(age) and 0<=age<=self.nominal.limits.max_age_s)
        if not healthy:reason='invalid_history_source_or_permission'
        elif elapsed>=self.p['withdraw_at_task_s']-1e-8:reason='planned_withdrawal'
        elif source[0]<=0:reason='source_not_forward'
        elif abs(nominal[0]-self.p['nominal_steady_m_s'])>1e-8:reason='nominal_not_steady'
        else:reason='steady_compensation'
        value=self.p['common_compensation_m_s'] if reason=='steady_compensation' else 0.
        action=np.array([value/self.p['residual_scale_m_s'],0.],np.float32)
        return action,dict(decision_task_s=elapsed,nominal_shaped_body=nominal,requested_common_m_s=value,
            normalized_proposal=action.tolist(),reason=reason,planned_source_stop_s=self.p['planned_source_stop_s'],
            withdraw_at_task_s=self.p['withdraw_at_task_s'],clock='task decision ticks, not GT/contact timing',truth_input=False)

def rollout(out,condition,world,actor):
    out.mkdir();p=protocol();c,g,parent,backend_condition=learner.configuration('clear_box')
    c['purpose']=p['protocol_id'];c['backend']['scenario_id']='clear_box_classical_common_planned_stop_v1'
    backend_condition['repeat']=condition['repeat'];save(out/'config.json',c);save(out/'guidance_config.json',g)
    backend=baseline.GuidedBackend(c,out/'backend',world,g,parent,backend_condition)
    env=learner.environment(c,backend,parent,backend_condition);profile=ClassicalCommonProfile(c,p);rows=[]
    try:
        obs,info=env.reset(seed=701);save(out/'reset.json',info)
        for step in range(p['steps_per_rollout']):
            arm=condition['arm'];audit=None
            if arm=='Classical_scheduled':
                pipeline=env.env.pipeline
                controlled,audit=profile.proposal(step*c['control_interval_s'],pipeline.last_view,pipeline.history.ready,latched=pipeline.reference.latched)
                raw=None
            else:raw,controlled=ablation.select_proposal(arm,actor,obs)
            obs,reward,term,trunc,info=env.step(controlled)
            row=dict(step=step,reward=reward,terminated=term,truncated=trunc,**info,
                actor_raw_proposal=raw,controller_proposal=controlled,classical_profile_audit=audit,comparison_condition=condition)
            rows.append(row)
            with (out/'trace.jsonl').open('a') as stream:stream.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
            if audit is not None:
                np.testing.assert_allclose(audit['nominal_shaped_body'],info['task']['nominal_shaped_body'],atol=1e-10,rtol=0)
            if (step+1)%35==0:emit(ACTION,out.name+f' {step+1}/140')
            if term or trunc:break
    finally:env.close()
    result=baseline.summarize(rows,out);result['condition']=dict(condition,scenario='clear_box')
    phases={}
    for label in ('steady','deceleration'):
        selected=[r for r in rows if r['reference_trace']['original_baseline_body'][0]>0 and abs(r['task']['nominal_shaped_body'][0]-.2)<1e-8] if label=='steady' else [r for r in rows if r['reference_trace']['original_baseline_body'][0]==0 and r['task']['nominal_shaped_body'][0]>1e-9]
        phases[label]=dict(samples=len(selected),velocity_rmse_m_s=float(np.sqrt(np.mean([r['task']['velocity_error_m_s']**2 for r in selected])))) if selected else None
    active=[r['classical_profile_audit']['decision_task_s'] for r in rows if r['classical_profile_audit'] and r['classical_profile_audit']['requested_common_m_s']>0]
    result.update(phases=phases,phase_metrics='Predeclared diagnostic, primary remains the whole 14s task',
        compensation_active_ticks=len(active),compensation_first_decision_s=min(active) if active else None,
        compensation_last_decision_s=max(active) if active else None,actor_inference_calls=sum(r['actor_raw_proposal'] is not None for r in rows),
        training_dataset_compatible=False,training_transitions=0,optimizer_updates=0)
    save(out/'summary.json',result);return result

def evaluate(out):
    p=protocol();parent,trained=parents();save(out/'dependencies.json',dict(parent=learner.dependency_record(parent),checkpoint=learner.dependency_record(trained)))
    save(out/'comparison_contract.json',dict(protocol=p,fingerprint=fingerprint(),frozen_learner_identity=learner.identity(),
        actor_raw_field='actor_raw_proposal',controller_field='controller_proposal',environment_field='policy_proposal',
        planning_preview='Known source stop8s, withdrawal7.5s; no unknown-obstacle preview claim',
        reward_note='Inherited scorer sees actual controller proposal; return not used to select arm',training_dataset_compatible=False))
    actor=PortableActor(trained,learner.identity()['abi_sha256']);worlds=prepare_worlds(out);runs=[]
    for index,condition in enumerate(p['order']):
        emit(ACTION,f'{index+1}/6 · '+str(condition),index/6)
        r=rollout(out/(condition['arm']+'_'+str(condition['repeat'])),condition,worlds['clear_box'],actor)
        runs.append(r);save(out/'evaluation_progress.json',runs)
        if r['physical_failure'] or r['guidance_faults'] or r['steps']!=140:raise RuntimeError('Physical/source/guidance failure; keep data, no retry')
    arms={arm:[r for r in runs if r['condition']['arm']==arm] for arm in ('B0','Classical_scheduled','TD3_common_only')}
    separation=all(max(r['nominal_velocity_rmse_m_s'] for r in arms['Classical_scheduled'])<min(r['nominal_velocity_rmse_m_s'] for r in arms[other]) for other in ('B0','TD3_common_only'))
    result=dict(protocol_id=p['protocol_id'],runs=runs,evaluation_transitions=sum(r['steps'] for r in runs),
        actor_inference_calls=sum(r['actor_inference_calls'] for r in runs),descriptive_velocity_separation=separation,
        all_task_and_stop_pass=all(r['task_success'] and r['stop_completed'] for r in runs),
        all_functional_proposals_pass=all(r['functional_proposal_pass'] for r in runs),
        training_transitions=0,optimizer_updates=0,minimum_effect_accepted=None,benefit_verified=False,hardware_authorized=False,
        conclusion='Seen-scenario development comparison; not exact-state branching, factory acceptance or learned benefit')
    save(out/'evaluation_result.json',result);return result

def validated_latest(root,check_runtime=True):
    out=latest(root,ACTION,check_runtime=check_runtime)
    if json.loads((out/'manifest.json').read_text()).get('classical_common_fingerprint')!=fingerprint():raise ValueError('Classical candidate source/protocol changed')
    parent,trained=parents(check_runtime)
    if json.loads((out/'dependencies.json').read_text())!=dict(parent=learner.dependency_record(parent),checkpoint=learner.dependency_record(trained)):
        raise ValueError('Frozen parent/checkpoint dependency changed')
    return out

def run(root):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    shared=Path.home()/'nino_research/.factory_sim.lock';shared.parent.mkdir(parents=True,exist_ok=True)
    with shared.open('a') as resource,(root/'.job.lock').open('a') as lock:
        fcntl.flock(resource,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'state.json').exists():raise ValueError('Classical comparison already consumed; no retry/reopening')
        protocol();parents()
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION);out.mkdir()
        ledger=dict(schema_version=1,latest={},runs=[dict(action=ACTION,path=out.name,status='running',error=None)])
        save(root/'state.json',ledger);save(out/'protocol.json',protocol())
        current,started,status,error,result=fingerprint(),time.monotonic(),'running',None,None
        def timeout(signum,frame):raise TimeoutError('Finite classical comparison wall deadline')
        previous=signal.signal(signal.SIGALRM,timeout);signal.alarm(protocol()['wall_deadline_s'])
        emit(ACTION,'Start fixed classical common / B0 / frozen common-only',0.,directory=str(out))
        try:
            result=evaluate(out)
            if fingerprint()!=current:raise ValueError('Source changed during batch')
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,previous)
            save(out/'job.json',dict(action=ACTION,status=status,error=error,wall_s=time.monotonic()-started,hardware_actions=0))
            save(out/'manifest.json',dict(action=ACTION,status=status,classical_common_fingerprint=current,source_fingerprint=source_fingerprint(),
                runtime=runtime_versions(),hardware_actions=0,files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p!=out/'manifest.json'}))
            ledger['runs'][0].update(status=status,error=error)
            if status=='completed':ledger['latest'][ACTION]=out.name
            save(root/'state.json',ledger);emit(ACTION,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    try:run(args.output)
    except (Exception,KeyboardInterrupt) as exc:print('Classical comparison failed/retained:',exc,flush=True);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
