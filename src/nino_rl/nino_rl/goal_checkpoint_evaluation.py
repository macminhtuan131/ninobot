"""Bounded, inference-only Goal100 checkpoint comparison on the frozen dev bank.

The source training job remains raw-QC-failed. Fresh per-slot measurement QC
governs this separate evaluation. No model.learn, replay write or promotion.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import random
import shutil
import signal
import time
import traceback

import numpy as np

from . import goal_studio_contract as goal
from . import unknown_step_runner as short
from .residual_workflow import save, runtime_versions

PROTOCOL = Path(__file__).resolve().parents[1]/'config/goal_checkpoint_evaluation_2026_11_14_v1.json'
ARMS = ('B0','TD3_10k','TD3_15k','TD3_20k')
LAYOUTS = ('dev_clear','dev_early','dev_late')


class EvaluationDeadline(TimeoutError):
    pass


def read(path):return json.loads(Path(path).read_text())
def now():return datetime.now(timezone.utc).isoformat()


def evaluator_sources():
    paths=(Path(__file__),PROTOCOL,Path(__file__).resolve().parents[1]/'scripts/evaluate_goal_checkpoints.sh')
    return {str(p):short.sha(p) for p in paths}


def protocol(path=PROTOCOL):
    p=read(path)
    if (p.get('id')!='nino_goal100_checkpoint_comparison_2026_11_14_v1'
            or p['arms']!=list(ARMS) or p['layouts']!=list(LAYOUTS)
            or p['repetitions']!=2 or p['maximum_rollouts']!=24
            or p['maximum_steps_per_rollout']!=250 or p['maximum_transitions']!=6000
            or p['raw_gap_limit_s']!=.04 or p['deterministic'] is not True
            or p['new_training_steps']!=0 or p['hardware_actions']!=0
            or p['automatic_retries']!=0 or p['controller_promotion'] is not False):
        raise ValueError('Changed scope requires a new explicit evaluation protocol')
    return p


def matrix(p):
    rng=random.Random(p['order_seed']);rows=[]
    for block in range(p['repetitions']):
        layouts=list(LAYOUTS);rng.shuffle(layouts)
        if block==0:layouts.remove('dev_clear');layouts.insert(0,'dev_clear')
        for layout in layouts:
            arms=list(ARMS);rng.shuffle(arms)
            if block==0 and layout=='dev_clear':arms.remove('B0');arms.insert(0,'B0')
            for arm in arms:
                rows.append(dict(slot=len(rows)+1,block=block+1,layout=layout,arm=arm,
                    reset_seed=p['reset_seeds'][block],status='not_run'))
    assert len(rows)==p['maximum_rollouts']
    return rows


def policy_signature(model):
    h=hashlib.sha256()
    for name,value in sorted(model.policy.state_dict().items()):
        a=value.detach().cpu().contiguous().numpy()
        if not np.isfinite(a).all():raise ValueError('Nonfinite policy parameter')
        h.update(name.encode());h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.tobytes())
    return dict(parameters_sha256=h.hexdigest(),global_steps=int(model.num_timesteps),
                optimizer_updates=int(model._n_updates))


def preflight(p):
    root=Path(p['training_root']).resolve();job=read(root/'job.json')
    if job['status']!='failed' or job['error']!='Goal training raw QC failed; retain checkpoint':
        raise ValueError('This protocol names the reviewed raw-QC-failed research20k candidate')
    qualified=goal.require_qualification();bank=short.require_inputs(qualified)
    expected=goal.identity(job['request']);records={}
    for arm,step in zip(ARMS[1:],(10000,15000,20000)):
        cp=root/'checkpoints'/f'step_{step:012d}_{"final" if step==20000 else "periodic"}'
        item=goal.inspect_checkpoint(cp,verify_files=True,check_runtime=True)
        if item['identity']!=expected or item['global_steps']!=step:
            raise ValueError('Checkpoint ABI/source/profile/bank identity mismatch')
        records[arm]=dict(path=str(cp),global_steps=step,optimizer_updates=item['optimizer_updates'],
            manifest_sha256=short.sha(cp/'manifest.json'),model_sha256=short.sha(cp/'model.zip'))
    if {r['id'] for r in bank['layouts'] if r['split']=='development'}!=set(LAYOUTS):
        raise ValueError('Development layouts changed')
    reserve=p['required_free_bytes'];free=shutil.disk_usage(root).free
    if free<reserve:raise ValueError('Not enough disk space for bounded evaluation')
    return dict(status='ready',qualified=str(qualified),checkpoints=records,
        sources=short.sources(),bank_sha256=short.sha(qualified/'inputs/bank.json'),
        evaluator_sources=evaluator_sources(),
        runtime=runtime_versions(),free_bytes=free,required_free_bytes=reserve,
        source_training_status='failed_unchanged',model_identity=expected,
        inference_only=True,hardware_actions=0,new_training_steps=0)


def rollout(out,bank,slot,model=None,*,env_factory=None,qc_factory=None,stopping=lambda:False):
    """Fresh epoch, retain failures, no auto reset after terminal outcome."""
    out=Path(out);out.mkdir()
    # BankEnvironment's launch budget must be local to this independent slot,
    # rather than counting previous slots in the parent comparison ledger.
    save(out/'ledger.json',dict(status='running',scope='single_fresh_evaluation_slot',maximum_launches=1))
    factory=env_factory or short.BankEnvironment
    qc_func=qc_factory or short.raw_qc
    env=factory(out,bank,[slot['layout']],launches=1,budget=250,global_launch_limit=1)
    rows=[];error=None;initial=None
    try:
        obs,initial=env.reset(seed=slot['reset_seed'])
        for n in range(250):
            if stopping():raise KeyboardInterrupt('Evaluation stopped by user')
            a=model.predict(obs,deterministic=True)[0] if model is not None else np.zeros(1,np.float32)
            obs,reward,term,trunc,info=env.step(a)
            rows.append(env.last)
            if (n+1)%50==0:
                print(json.dumps(dict(event='tick',slot=slot['slot'],arm=slot['arm'],layout=slot['layout'],steps=n+1)),flush=True)
            if term or trunc:break
    except BaseException as exc:
        error=repr(exc);(out/'error.txt').write_text(traceback.format_exc())
        if isinstance(exc,(KeyboardInterrupt,EvaluationDeadline)):raise
    finally:
        env.close()
    qc=None
    try:qc=qc_func(out)
    except (KeyboardInterrupt,EvaluationDeadline):raise
    except BaseException as exc:
        error=(error+'; ' if error else '')+'raw QC: '+repr(exc)
    final=rows[-1]['task'] if rows else None
    complete=bool(rows and rows[-1]['done'])
    measurement_valid=bool(error is None and complete and qc and qc['valid'])
    value=dict(**{k:v for k,v in slot.items() if k!='status'},status='valid' if measurement_valid else 'invalid',
        error=error,steps=len(rows),complete=complete,measurement_valid=measurement_valid,
        outcome=final,source_qc=qc,episode_return=sum(r['reward'] for r in rows),
        initial_physical_sample=initial.get('physical_sample') if initial else None,
        reset_seed_scope='Gym/reset metadata only; Gazebo RNG and physical start are not exact state branches',
        split='development',held_out=False,benefit_verified=False,hardware_actions=0)
    save(out/'summary.json',value)
    save(out/'ledger.json',dict(status=value['status'],scope='single_fresh_evaluation_slot',maximum_launches=1))
    return value


def summary(rows):
    arms={}
    for arm in ARMS:
        cells={}
        for layout in LAYOUTS:
            attempted=[r for r in rows if r['arm']==arm and r['layout']==layout and r['status']!='not_run']
            valid=[r for r in attempted if r.get('measurement_valid')]
            good=[r for r in valid if r['outcome']['task_success']]
            cells[layout]=dict(attempts=len(attempted),valid=len(valid),successes=len(good),
                failures=dict(Counter(r['outcome']['termination_reason'] for r in valid if not r['outcome']['task_success'])),
                path_rmse_mean_all_m=float(np.mean([r['outcome']['cross_track_rmse_m'] for r in valid])) if valid else None,
                successful_time_mean_s=float(np.mean([r['outcome']['elapsed_s'] for r in good])) if good else None,
                maximum_cross_track_m=max((r['outcome']['maximum_cross_track_m'] for r in valid),default=None))
        arms[arm]=cells
    contrasts=[]
    for r in rows:
        if r['arm']=='B0' or not r.get('measurement_valid'):continue
        b=next((b for b in rows if b['arm']=='B0' and b['block']==r['block'] and b['layout']==r['layout'] and b.get('measurement_valid')),None)
        if b:
            contrasts.append(dict(block=r['block'],layout=r['layout'],arm=r['arm'],
                baseline_task_success=b['outcome']['task_success'],candidate_task_success=r['outcome']['task_success'],
                delta_path_rmse_m=r['outcome']['cross_track_rmse_m']-b['outcome']['cross_track_rmse_m'],
                delta_elapsed_s_successes_only=r['outcome']['elapsed_s']-b['outcome']['elapsed_s']
                    if r['outcome']['task_success'] and b['outcome']['task_success'] else None,
                exact_physical_pair=False))
    return dict(status='completed_pilot_not_benefit' if len(rows)==24 and all(r.get('measurement_valid') for r in rows) else 'incomplete_or_measurement_unknown',
        arms=arms,within_block_contrasts=contrasts,attempts=sum(r['status']!='not_run' for r in rows),
        measurement_valid=sum(bool(r.get('measurement_valid')) for r in rows),
        task_successes=sum(bool(r.get('measurement_valid') and r['outcome']['task_success']) for r in rows),
        uncertainty='Two fresh launches per arm/layout only; reset variation is not exact-state pairing. Report both contrasts/ranges, no population-level superiority claim.',
        independent_training_seeds=1,development_only=True,benefit_verified=False,
        controller_promotion=False,new_training_steps=0,hardware_actions=0)


def run(output,protocol_path=PROTOCOL):
    import torch
    from stable_baselines3 import TD3
    p=protocol(protocol_path);ready=preflight(p)
    output=Path(output).expanduser().resolve();output.mkdir(parents=True,exist_ok=False)
    with (Path.home()/'nino_research/.factory_sim.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        shutil.copytree(Path(ready['qualified'])/'inputs',output/'inputs')
        bank=short.require_inputs(output);slots=matrix(p)
        save(output/'protocol.json',p);save(output/'preflight.json',ready)
        save(output/'ledger.json',dict(status='running',slots=slots));save(output/'job.json',dict(status='running',kind=p['id'],new_training_steps=0))
        models={};signatures={};stopped=False;status='running';error=None
        def stop(*_):
            nonlocal stopped
            stopped=True
        old={s:signal.signal(s,stop) for s in (signal.SIGINT,signal.SIGTERM)}
        alarm=signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(EvaluationDeadline('Evaluation wall deadline')))
        signal.alarm(p['wall_deadline_s']);started=time.monotonic()
        try:
            torch.set_num_threads(1)
            for arm,record in ready['checkpoints'].items():
                models[arm]=TD3.load(Path(record['path'])/'model.zip',device='cpu')
                if (models[arm].observation_space.shape!=(100,) or models[arm].action_space.shape!=(1,)
                        or models[arm].num_timesteps!=record['global_steps']
                        or models[arm]._n_updates!=record['optimizer_updates']):
                    raise ValueError('Loaded policy shape/counters differ from checkpoint metadata')
                signatures[arm]=policy_signature(models[arm])
            save(output/'frozen_policy_signatures.json',signatures)
            for i,slot in enumerate(slots):
                if stopped:raise KeyboardInterrupt('Stopped before next evaluation slot')
                if shutil.disk_usage(output).free<p['reserve_bytes']:raise ValueError('Disk reserve reached')
                if short.sources()!=ready['sources']:raise ValueError('Controller/backend source changed')
                if evaluator_sources()!=ready['evaluator_sources']:raise ValueError('Evaluation runner/protocol changed')
                slot['status']='running';save(output/'ledger.json',dict(status='running',slots=slots))
                print(json.dumps(dict(event='start',**slot)),flush=True)
                target=output/f"slot_{slot['slot']:02d}_{slot['arm']}_{slot['layout']}_b{slot['block']}"
                result=rollout(target,bank,slot,models.get(slot['arm']),stopping=lambda:stopped)
                result['directory']=str(target);slots[i]=result
                if any(policy_signature(m)!=signatures[a] for a,m in models.items()):raise ValueError('Inference changed policy/counters')
                save(output/'evaluation_progress.json',slots);save(output/'ledger.json',dict(status='running',slots=slots))
                save(output/'comparison.json',summary(slots))
                print(json.dumps(dict(event='finish',slot=result['slot'],arm=result['arm'],layout=result['layout'],
                    measurement_valid=result['measurement_valid'],steps=result['steps'],
                    task_success=result['outcome']['task_success'] if result['outcome'] else None,
                    termination=result['outcome']['termination_reason'] if result['outcome'] else None,
                    path_rmse_m=result['outcome']['cross_track_rmse_m'] if result['outcome'] else None)),flush=True)
                # A measurement-invalid slot is retained, never replaced. Remaining
                # prespecified independent slots are still measured; benefit stays
                # unknown wherever coverage is missing. Closure errors raise above.
            if short.sources()!=ready['sources'] or evaluator_sources()!=ready['evaluator_sources']:
                raise ValueError('Evaluation sources changed')
            status='completed' if all(r.get('measurement_valid') for r in slots) else 'measurement_failed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=repr(exc)
            (output/'error.txt').write_text(traceback.format_exc())
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,alarm)
            for sig,handler in old.items():signal.signal(sig,handler)
            save(output/'comparison.json',summary(slots))
            save(output/'ledger.json',dict(status=status,slots=slots))
            save(output/'job.json',dict(status=status,error=error,wall_s=time.monotonic()-started,
                kind=p['id'],new_training_steps=0,hardware_actions=0,completed_utc=now()))
            save(output/'manifest.json',dict(kind=p['id'],status=status,
                files={str(f.relative_to(output)):short.sha(f) for f in output.rglob('*') if f.is_file() and f!=output/'manifest.json'}))
        return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,default=PROTOCOL);parser.add_argument('--output',type=Path)
    parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    if args.preflight:
        print(json.dumps(preflight(protocol(args.protocol)),indent=2));return 0
    if args.output is None:parser.error('--output required for execution')
    return 0 if run(args.output,args.protocol)=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
