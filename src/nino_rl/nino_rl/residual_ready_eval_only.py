"""Six fixed eval-only runs with drive-ready reset; no learn/resume/hardware."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import fcntl,hashlib,json,pickle,signal,time,traceback
from pathlib import Path
import numpy as np
from . import residual_drive_readiness as qualified
from .coverage_reset_readiness import require_uninhibited_transition
from .drive_readiness_candidate import DriveReadinessBackend
from .reliable_episode import EpisodeLifecycle
from .residual_workflow import save,emit,latest,runtime_versions
from .residual_experiment import source_fingerprint

parent=qualified.parent
ACTION='sim-ready-eval-only'
PROTOCOL_ID='nino_ready_A_eval_only_v1_2026_11_06'
QUAL_MANIFEST='0c569728eb935dd2d6f6bd3ac1b1a0ca92fbfda313fff553e894473e57564aeb'
MODEL_SHA='40f676c7464a94440d57cda34c6eb277ba67d6fb7a87760f8bc363af253a6166'


def protocol():
    order=[dict(arm=a,source_stop_s=t,**({'seed':11} if a=='A_gaussian' else {})) for a,t in
        [('B0',6.),('A_gaussian',6.),('Classical_scheduled',6.),
         ('Classical_scheduled',8.),('A_gaussian',8.),('B0',8.)]]
    return dict(protocol_id=PROTOCOL_ID,evaluation_order=order,maximum_launches=6,
        steps_per_launch=140,maximum_eval_ticks=840,wall_deadline_s=1800,
        training_transitions=0,optimizer_updates=0,probes=0,retries=0,extra_smokes=0,hardware_actions=0,
        primary='whole_14s_native_velocity_rmse',grids=['GT20ms','GTshift10ms'],
        minimum_relative_effect_proposed=.05,application_minimum_effect_accepted=None,
        scope='single_checkpoint_screening_not_coverage_or_generalization')


def fingerprint():
    base=parent.frozen.repo()/'src/nino_rl'
    files=['nino_rl/residual_ready_eval_only.py','scripts/residual_ready_eval_only.sh',
        'test/test_ready_eval_only.py']
    return hashlib.sha256(json.dumps(dict(qualified=qualified.fingerprint(),
        files={f:parent.sha(base/f) for f in files}),sort_keys=True).encode()).hexdigest()


def source(check_runtime=True):
    q=qualified.validated_latest(Path.home()/'nino_research/sim_drive_readiness_v1',check_runtime)
    if parent.sha(q/'manifest.json')!=QUAL_MANIFEST:raise ValueError('Qualification manifest changed')
    qr=parent.read(q/'qualification_result.json')
    if not qr['qualification_pass'] or qr['zero_control_ticks']!=20:raise ValueError('Reset qualification not passed')
    study=qualified.source(check_runtime);model=study/'A_gaussian_seed_11/model.zip'
    if parent.sha(model)!=MODEL_SHA:raise ValueError('Frozen A checkpoint changed')
    tr=parent.read(model.parent/'training_result.json')
    if ((tr['training_transitions'],tr['critic_updates'],tr['actor_updates'])!=(1024,960,480)
            or not tr['model_optimizer_target_replay_parity']):
        raise ValueError('A checkpoint not from completed/parity-checked learner')
    return dict(qualification=str(q),qualification_manifest_sha256=QUAL_MANIFEST,
        training_artifact=str(study),training_manifest_sha256=qualified.PARENT_MANIFEST,
        checkpoint=str(model),checkpoint_sha256=MODEL_SHA)


def actor_state(actor):
    if actor is None:return None
    return dict(parent.full_snapshot(actor),
        sampler_sha256=hashlib.sha256(pickle.dumps(actor.nino_sampler.__dict__)).hexdigest())


def evaluate(out,condition,world,checkpoint):
    if condition not in protocol()['evaluation_order']:raise ValueError('Undeclared evaluation condition')
    out.mkdir();arm=condition['arm'];actor=None
    if arm=='A_gaussian':
        from .coverage_td3 import CoverageTD3
        actor=CoverageTD3.load(checkpoint,device='cpu')
        parent.require_identity(actor.nino_coverage_identity,'A_gaussian',11)
    before=actor_state(actor);save(out/'actor_before.json',before)
    c,g,task,bc=parent.configuration(condition['source_stop_s'])
    c['purpose']=task['protocol_id']=PROTOCOL_ID
    lp=parent.lifecycle_protocol(True);lp['protocol_id']=PROTOCOL_ID
    backend=EpisodeLifecycle(c,out/'episodes',world,g,task,bc,lp,backend_factory=DriveReadinessBackend)
    env=parent.frozen.contract.environment(c,backend,task,bc)
    rows=[];epoch=None;error=None
    save(out/'config.json',dict(config=c,guidance=g,task=task,condition=condition))
    try:
        obs,reset=env.reset(seed=701);save(out/'reset.json',reset)
        if not backend.namespace or backend.current is None:raise ValueError('Fresh evaluation epoch required')
        initial=backend.view();save(out/'initial_view.json',initial);qualified.require_ready(initial)
        for step in range(140):
            qualified.require_ready(backend.view())
            request=(actor.predict(obs,deterministic=True)[0] if actor is not None else
                parent.frozen.contract.classical_request(obs) if arm=='Classical_scheduled' else np.zeros(1,np.float32))
            parent.frozen.append(out/'control_attempts.jsonl',dict(step=step,requested=np.asarray(request).tolist()))
            obs,reward,term,trunc,info=env.step(request)
            row=dict(step=step,reward=reward,terminated=term,truncated=trunc,done=bool(term or trunc),
                **info,qualification_condition=condition,episode_namespace=backend.namespace)
            row['TimeLimit.truncated']=bool(trunc and not term)
            parent.frozen.append(out/'trace.jsonl',row)
            require_uninhibited_transition(row)
            epoch=epoch if epoch is not None else row['sensor_clock_s']-row['task']['elapsed_s']
            parent.frozen.qualified.verify_transition(row,rows[-1] if rows else None,epoch,lp['abi_sha256'])
            parent.frozen.feasibility(row,.04);rows.append(row)
            if term or trunc:break
    except BaseException as exc:
        error=exc;save(out/'failure.json',dict(error=repr(exc),traceback=traceback.format_exc(),valid_rows=len(rows)));raise
    finally:
        try:env.close()
        except BaseException as exc:
            save(out/'cleanup_failure.json',dict(error=repr(exc),original=repr(error)))
            if error is None:raise
        finally:save(out/'actor_after.json',actor_state(actor))
    after=actor_state(actor)
    if before!=after:raise ValueError('Evaluation changed policy/targets/optimizer/counters or sampler')
    target=backend.directory/backend.namespace
    result=parent.frozen.baseline.summarize(rows,target)
    diagnostic=parent.frozen.timing.timestamp_diagnostic(target,rows)
    result.update(evaluation_condition=condition,timestamp_diagnostic=diagnostic,
        actor_unchanged=True,exploration_unchanged=True,probes_during_evaluation=0,
        optimizer_updates_in_job=0,reset_backend='drive_ack_and_physical_quiet_v1')
    save(out/'summary.json',result)
    if len(rows)!=140 or not result['functional_proposal_pass'] or not diagnostic['valid']:
        raise ValueError('Evaluation task/measurement failure')
    return result


def compare(runs):
    def metric(r):
        g=r['timestamp_diagnostic']['header_grid']
        return np.array([r['nominal_velocity_rmse_m_s'],g['0.0']['rmse_m_s'],g['0.01']['rmse_m_s']])
    indexed={(r['evaluation_condition']['arm'],r['evaluation_condition']['source_stop_s']):r for r in runs}
    if set(indexed)!={(a,t) for a in ('B0','A_gaussian','Classical_scheduled') for t in (6.,8.)} or len(runs)!=6:
        raise ValueError('Six fixed complete conditions required')
    pairs=[]
    for stop in (6.,8.):
        a,b,c=(metric(indexed[(arm,stop)]) for arm in ('A_gaussian','B0','Classical_scheduled'))
        if not np.isfinite(np.concatenate((a,b,c))).all():
            return dict(decision='unknown_nonfinite_metric',benefit_verified=False,pairs=pairs)
        if np.any(b<=0) or np.any(c<=0):return dict(decision='unknown_zero_denominator',benefit_verified=False,pairs=pairs)
        pairs.append(dict(stop_s=stop,A=a.tolist(),B0=b.tolist(),classical=c.tolist(),
            relative_A_vs_B0=((a-b)/b).tolist(),relative_A_vs_classical=((a-c)/c).tolist()))
    dc=np.array([r['relative_A_vs_classical'] for r in pairs]);db=np.array([r['relative_A_vs_B0'] for r in pairs])
    sensitive=any(np.any(v<0) and np.any(v>0) for group in (dc,db) for v in group)
    decision=('unknown_grid_sensitive' if sensitive else
        'descriptive_candidate_requires_separate_holdout' if np.all(dc<=-.05) and np.all(db<=-.05) else
        'no_go_expand_this_checkpoint_clear_known_stop' if np.all(dc>=0) else
        'unknown_small_or_condition_dependent_effect')
    return dict(decision=decision,pairs=pairs,benefit_verified=False,one_training_seed_only=True,
        paired_conditions_not_exact_state_branching=True,minimum_effect_proposed=.05,application_minimum_effect_accepted=None)


def execute(out,dependencies):
    import torch
    torch.set_num_threads(1)
    worlds=parent.frozen.prepare_worlds(out);runs=[]
    checkpoint=Path(dependencies['checkpoint']);before=parent.sha(checkpoint)
    try:
        for i,condition in enumerate(protocol()['evaluation_order']):
            emit(ACTION,f'Eval {i+1}/6: {condition}',i/6)
            runs.append(evaluate(out/f'eval_{i:02d}',condition,worlds['clear_box'],checkpoint))
            if parent.sha(checkpoint)!=before:raise ValueError('Frozen checkpoint changed during evaluation')
            save(out/'evaluation_progress.json',dict(runs=runs,remaining_slots_closed=False))
    except BaseException as exc:
        save(out/'evaluation_progress.json',dict(runs=runs,error=repr(exc),remaining_slots_closed=True));raise
    ticks=sum(r['steps'] for r in runs)
    if ticks!=840:raise ValueError('Exact evaluation tick budget mismatch')
    result=dict(runs=runs,comparison=compare(runs),gazebo_launches=6,evaluation_transitions=ticks,
        training_transitions=0,optimizer_updates=0,probes=0,hardware_actions=0,checkpoint_unchanged=True,
        remaining_slots_closed=True,benefit_verified=False)
    save(out/'evaluation_result.json',result);return result


def release_record():return parent.read(parent.frozen.repo()/'src/nino_rl/config/ready_eval_only_release_v1.json')


def release_ready(root):
    r=release_record()
    if (r.get('released') is not True or r.get('fingerprint')!=fingerprint()
            or r.get('protocol_id')!=PROTOCOL_ID or r.get('hardware_authorized') is not False
            or r.get('scope')!='eval_only_6_launches_840_ticks_no_updates'
            or Path(r['result_root']).resolve()!=Path(root).resolve()):raise ValueError('Ready eval-only not released for these sources/root')
    report=Path(r['software_test_report'])
    if parent.sha(report)!=r['software_test_report_sha256']:raise ValueError('Software test report changed')
    import xml.etree.ElementTree as ET
    suites=list(ET.parse(report).getroot().iter('testsuite'))
    if not suites or any(int(s.get(k,'0')) for s in suites for k in ('failures','errors','skipped')):raise ValueError('Software gate not passed')
    return r


def validated_latest(root,check_runtime=True):
    out=latest(root,ACTION,check_runtime=check_runtime)
    if parent.read(out/'manifest.json')['ready_eval_fingerprint']!=fingerprint():raise ValueError('Ready eval sources changed')
    if parent.read(out/'dependencies.json')!=source(check_runtime):raise ValueError('Ready eval dependencies changed')
    return out


def retained_failure(root):
    root=Path(root).resolve()
    try:
        row=parent.read(root/'state.json')['runs'][-1]
        if row['action']!=ACTION or row['status'] not in ('failed','cancelled'):return None
        out=(root/row['path']).resolve();m=parent.read(out/'manifest.json')
        if out.parent!=root or m['ready_eval_fingerprint']!=fingerprint() or m['status']!=row['status']:return None
        for name,value in m['files'].items():
            path=(out/name).resolve()
            if not path.is_relative_to(out) or parent.sha(path)!=value:return None
        if parent.read(out/'dependencies.json')!=source(False):return None
        return dict(state='retained_failure',path=str(out),label='EVAL-ONLY ĐÃ ĐÓNG DO LỖI · KHÔNG RETRY',error=row['error'])
    except (OSError,ValueError,KeyError,TypeError,IndexError):return None


def run(root):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    shared=Path.home()/'nino_research/.factory_sim.lock';shared.parent.mkdir(parents=True,exist_ok=True)
    with shared.open('a') as resource,(root/'.job.lock').open('a') as lock:
        fcntl.flock(resource,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'state.json').exists():raise ValueError('Ready eval-only budget already consumed; no retry/foreign root')
        release=release_ready(root);deps=source();current=fingerprint()
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION);out.mkdir()
        row=dict(action=ACTION,path=out.name,status='running',error=None);state=dict(schema_version=1,latest={},runs=[row])
        save(root/'state.json',state);save(out/'protocol.json',protocol());save(out/'release.json',release);save(out/'dependencies.json',deps)
        status,error,result='running',None,None;started=time.monotonic()
        def timeout(*args):raise TimeoutError('Ready eval-only wall deadline')
        old=signal.signal(signal.SIGALRM,timeout);signal.alarm(1800)
        try:
            emit(ACTION,'Six fresh evaluations; no learning or exploration')
            result=execute(out,deps)
            if fingerprint()!=current or source()!=deps:raise ValueError('Sources/dependencies changed during evaluation')
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc)
            save(out/'failure.json',dict(error=repr(exc),traceback=traceback.format_exc()));raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,old)
            save(out/'job.json',dict(action=ACTION,status=status,error=error,wall_s=time.monotonic()-started,hardware_actions=0))
            save(out/'manifest.json',dict(action=ACTION,status=status,ready_eval_fingerprint=current,
                source_fingerprint=source_fingerprint(),runtime=runtime_versions(),hardware_actions=0,
                files={str(f.relative_to(out)):parent.sha(f) for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
            row.update(status=status,error=error)
            if status=='completed':state['latest'][ACTION]=out.name
            save(root/'state.json',state);emit(ACTION,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    try:run(args.output)
    except (Exception,KeyboardInterrupt) as exc:print('Ready eval-only failed/retained:',exc,flush=True);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
