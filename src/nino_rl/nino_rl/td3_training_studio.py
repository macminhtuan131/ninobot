"""User-budgeted guided TD3 jobs for the native training GUI; simulation only."""
import argparse
from collections import deque
from datetime import datetime,timezone
import fcntl
import json
import math
from pathlib import Path
import signal
import time
import traceback
import uuid
import numpy as np
from . import residual_guided_td3 as guided
from . import residual_guided_baseline as baseline
from .guided_td3_contract import zero_initialize,require_identity
from .residual_experiment import build_model,experiment_contract,source_fingerprint
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import save,emit,json_value,runtime_versions
from .td3_studio_contract import validate_request,configuration,identity,require_resume,digest,CHECKPOINT_KIND

ACTION='td3-studio'

class Cancelled(Exception):pass

def engine_sources():
    paths=[Path(__file__),Path(__file__).with_name('td3_studio_contract.py'),guided.repo()/'src/nino_rl/scripts/residual_training_studio.sh']
    return {p.name:digest(p) for p in paths}

def append(path,value):
    with path.open('a') as stream:stream.write(json.dumps(value,default=json_value,allow_nan=False)+'\n')

def checkpoint(model,directory,ident,request,reason):
    """Publish an atomic complete bundle only at a stored-transition boundary."""
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/(f'step_{model.num_timesteps:012d}_'+reason)
    pending=directory/('.pending_'+uuid.uuid4().hex);pending.mkdir()
    model.save(pending/'model.zip');model.save_replay_buffer(pending/'replay_buffer.pkl')
    save(pending/'resume_identity.json',ident);save(pending/'task_checkpoint.json',guided.identity())
    save(pending/'checkpoint.json',dict(identity=ident,global_steps=int(model.num_timesteps),
        optimizer_updates=int(model._n_updates),replay_size=int(model.replay_buffer.size()),reason=reason,
        engine_sources=engine_sources(),
        episode_state_restored=False,rng_state_restored=False,continuation='model/targets/optimizers/replay; new simulator episode, not bit-exact trajectory'))
    files={p.name:digest(p) for p in pending.iterdir() if p.is_file()}
    save(pending/'manifest.json',dict(kind=CHECKPOINT_KIND,status='resumable',runtime=runtime_versions(),files=files,hardware_actions=0))
    pending.rename(target)
    return target

def audit_tail(buffer,rows,start_pos,start_steps):
    """Audit the current job's last replay window, including wrapped buffers."""
    selected=list(rows)[-min(len(rows),buffer.buffer_size):]
    for row in selected:
        index=row['timestep']-start_steps-1
        slot=(start_pos+index)%buffer.buffer_size
        for actual,expected in [(buffer.actions[slot,0],row['policy_proposal']),
            (buffer.observations[slot,0],row['reference_trace']['observation']),
            (buffer.next_observations[slot,0],row['next_observation']),([buffer.rewards[slot,0]],[row['reward']])]:
            np.testing.assert_allclose(actual,expected,atol=2e-6,rtol=0)
        if bool(buffer.dones[slot,0])!=row['done'] or bool(buffer.timeouts[slot,0])!=row['TimeLimit.truncated']:
            raise ValueError('Replay terminal/timeout mismatch')
    return dict(rows_checked=len(selected),scope='Last up to 256 job rows still present in replay; full trace retained on disk',action_semantics='normalized policy proposal including exploration; not projected command')

def evaluate(out,request,world,actor,stopped):
    results=[]
    for i,arm in enumerate(('B0','TD3')):
        if stopped():raise Cancelled('Cancelled before evaluation launch')
        emit(ACTION,'Đánh giá '+arm+' · '+str(i+1)+'/2',phase='evaluate',progress=None)
        directory=out/'evaluation'/arm;directory.mkdir(parents=True)
        c,g,parent,condition=configuration(request);c['backend']['max_episodes']=1
        backend=baseline.GuidedBackend(c,directory/'backend',world,g,parent,condition)
        env=guided.environment(c,backend,parent,condition);rows=[]
        try:
            obs,info=env.reset(seed=701);save(directory/'reset.json',info)
            for step in range(140):
                if stopped():raise Cancelled('Cancelled during evaluation')
                action=np.zeros(2,np.float32) if arm=='B0' else actor(obs)
                obs,reward,term,trunc,info=env.step(action)
                row=dict(step=step,reward=reward,terminated=term,truncated=trunc,**info)
                rows.append(row);append(directory/'trace.jsonl',row)
                if term or trunc:break
        finally:env.close()
        summary=baseline.summarize(rows,directory);summary['arm']=arm;results.append(summary)
        save(directory/'summary.json',summary)
        if summary['physical_failure'] or summary['guidance_faults'] or len(rows)!=140:
            raise RuntimeError('Evaluation physical/source failure; checkpoint retained, no retry')
    save(out/'evaluation_result.json',dict(runs=results,evaluation_transitions=280,
        scope='One fresh launch per arm on the selected seen scenario; descriptive, no benefit promotion',benefit_verified=False))
    return results

def train(out,request,stop_requested):
    import torch
    from stable_baselines3 import TD3
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.logger import configure
    from nino_control.residual_actor import export_actor,PortableActor
    torch.set_num_threads(1)
    ident=identity(request);resumed=require_resume(request)
    if resumed:save(out/'resume_parent.json',resumed)
    parent=guided.contact.validated_latest(guided.CONTACT_ROOT)
    c,g,base,condition=configuration(request);worlds=prepare_worlds(out)
    backend=baseline.GuidedBackend(c,out/'backend',worlds[request['scenario']],g,base,condition)
    env=guided.environment(c,backend,base,condition)
    validation=dict(contract_id=c['experiment_contract'],features=list(guided.FEATURES),history_frames=5,
        abi_sha256=experiment_contract(c)['abi_sha256'],source_fingerprint=source_fingerprint(),backend_kind=backend.kind,
        backend_configuration=c['backend'],backend_validated=True,integration_pass=True,
        parent_baseline=guided.dependency_record(parent),scope='Reused tested guided adapter; new budget, no hardware calibration claim')
    save(out/'validation.json',validation)
    c['training']=dict(allowed=True,backend_validation_artifact=str(out/'validation.json'),budget_transitions=request['timesteps'])
    save(out/'training_config.json',c);save(out/'resume_identity.json',ident)
    model=None;rows=deque(maxlen=min(256,c['algorithm_parameters']['TD3']['buffer_size']))
    row_count=0;terminals=0;successes=0;safe=False;start_steps=0;start_updates=0;last_checkpoint=None;start_pos=0
    beginning=time.monotonic();last_log=beginning
    class Trace(BaseCallback):
        def _on_rollout_start(self):
            nonlocal safe
            safe=False
        def _on_step(self):
            nonlocal row_count,terminals,successes
            info=self.locals['infos'][0]
            row=dict(timestep=self.num_timesteps,done=bool(self.locals['dones'][0]),
                next_observation=info.get('terminal_observation',self.locals['new_obs'][0]),
                reward=float(self.locals['rewards'][0]),**info)
            append(out/'training_trace.jsonl',row);rows.append(row);row_count+=1
            # A physical intervention terminates this transition. Quarantine the
            # job after it has been stored; do not silently train more episodes.
            self.physical_fault=bool(info.get('intervention') or info.get('termination_reason')=='physical_envelope_failure')
            task=info['task']
            for key,value in [('reward',row['reward']),('velocity_error_m_s',task['velocity_error_m_s']),
                ('cross_track_m',task['cross_track_m']),('body_speed_m_s',info['body_speed_m_s'])]:
                self.logger.record_mean('nino/'+key,value)
            if row['done']:
                terminals+=1;successes+=bool(task['task_success'])
                emit(ACTION,'Episode kết thúc',phase='train',episode=dict(success=task['task_success'],
                    stop=task['stop_completed'],marker=task['marker_reached'],global_step=self.num_timesteps))
            return True
        def _on_rollout_end(self):
            nonlocal safe,last_checkpoint,last_log
            safe=True;completed=self.num_timesteps-start_steps
            if request['checkpoint_every'] and completed%request['checkpoint_every']==0 and completed<request['timesteps']:
                last_checkpoint=checkpoint(self.model,out/'checkpoints',ident,request,'periodic')
                emit(ACTION,'Đã lưu checkpoint',checkpoint=str(last_checkpoint),global_steps=self.num_timesteps)
            now=time.monotonic()
            if completed%16==0 or now-last_log>=5 or completed==request['timesteps']:
                self.logger.record('nino/job_steps',completed);self.logger.record('nino/global_steps',self.num_timesteps)
                self.logger.dump(self.num_timesteps);last_log=now
                emit(ACTION,f'Train {completed}/{request["timesteps"]} · global {self.num_timesteps}',
                    progress=completed/request['timesteps'],phase='train',steps=completed,total=request['timesteps'],
                    global_steps=self.num_timesteps,optimizer_updates=int(self.model._n_updates),
                    wall_s=now-beginning,steps_per_wall_s=completed/max(.001,now-beginning))
            if self.physical_fault:raise RuntimeError('Physical intervention; stored transition and checkpoint retained, no retry')
            if stop_requested():raise Cancelled('Stopped at stored-transition boundary')
            # SB3 may update optimizers after this callback returns. A timeout
            # inside that update must keep the previous complete checkpoint,
            # rather than publish a potentially half-updated optimizer state.
            safe=False
    try:
        if resumed:
            p=Path(resumed['path']);model=TD3.load(p/'model.zip',env=env,device='cpu',force_reset=True)
            require_identity(model.nino_guided_task,guided.identity());model.load_replay_buffer(p/'replay_buffer.pkl')
            if resumed['kind']=='studio':require_identity(model.nino_td3_studio_identity,ident)
            if (model.num_timesteps,model._n_updates,model.replay_buffer.size())!=(resumed['global_steps'],resumed['optimizer_updates'],resumed['replay_size']):
                raise ValueError('Loaded model/replay counters do not match checkpoint metadata')
            emit(ACTION,'Đã load model + targets + optimizers + replay; bắt đầu episode sim mới',phase='load')
        else:
            model=build_model(c,env,request['seed']);save(out/'zero_initialization.json',zero_initialize(model))
        model.nino_guided_task=guided.identity();model.nino_td3_studio_identity=ident
        start_steps=int(model.num_timesteps);start_updates=int(model._n_updates);start_pos=int(model.replay_buffer.pos)
        model.set_logger(configure(str(out/'tensorboard'),['csv','tensorboard']))
        save(out/'start_state.json',dict(global_steps=start_steps,optimizer_updates=start_updates,replay_size=int(model.replay_buffer.size()),replay_pos=start_pos))
        if stop_requested():raise Cancelled('Cancelled before learning')
        model.learn(total_timesteps=request['timesteps'],callback=Trace(),reset_num_timesteps=False,log_interval=1)
        if model.num_timesteps-start_steps!=request['timesteps'] or row_count!=request['timesteps']:
            raise ValueError('Training budget/trace mismatch')
        safe=True;replay=audit_tail(model.replay_buffer,rows,start_pos,start_steps)
        last_checkpoint=checkpoint(model,out/'checkpoints',ident,request,'final')
        emit(ACTION,'Đã lưu checkpoint cuối',checkpoint=str(last_checkpoint),global_steps=model.num_timesteps)
        parity=export_actor(model,'TD3',out,experiment_contract(c),purpose='user_budgeted_td3_studio')
        model.logger.record('nino/final_optimizer_updates',model._n_updates);model.logger.dump(model.num_timesteps)
        result=dict(mode=request['mode'],scenario=request['scenario'],profile=request['profile'],
            requested_additional_steps=request['timesteps'],transitions=row_count,starting_global_steps=start_steps,
            global_steps=int(model.num_timesteps),optimizer_updates_this_job=int(model._n_updates)-start_updates,
            optimizer_updates_total=int(model._n_updates),replay_size=int(model.replay_buffer.size()),replay_audit=replay,
            checkpoint=str(last_checkpoint),tensorboard=str(out/'tensorboard'),portable_actor=parity,
            terminal_episodes=terminals,successful_terminal_episodes=successes,
            final_segment_right_censored=bool(rows and not rows[-1]['done']),resumed_from=resumed,
            continuation_is_bit_exact=False,benefit_verified=False,hardware_authorized=False)
        save(out/'training_result.json',result)
        if request['evaluate']:
            # Training and evaluation share the private domain. Stop and flush
            # the training backend before constructing any evaluation backend.
            env.close()
            result['evaluation']=evaluate(out,request,worlds[request['scenario']],PortableActor(out,experiment_contract(c)['abi_sha256']),stop_requested)
        save(out/'result.json',result);return result
    except BaseException:
        if model is not None and safe:
            # This checkpoint may precede the next optimizer call; its counters
            # state exactly what was serialized, not an inferred update count.
            try:
                last_checkpoint=checkpoint(model,out/'checkpoints',ident,request,'interrupted')
                emit(ACTION,'Checkpoint khi dừng/lỗi đã giữ',checkpoint=str(last_checkpoint),global_steps=model.num_timesteps)
            except Exception as exc:
                (out/'checkpoint_error.txt').write_text(traceback.format_exc())
                emit(ACTION,'Không lưu được checkpoint mới: '+str(exc)+'; giữ checkpoint hoàn chỉnh trước đó')
        raise
    finally:
        try:
            if model is not None and getattr(model,'_logger',None):model.logger.close()
        finally:env.close()

def run(root,request):
    request=validate_request(request);root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    lock_path=Path.home()/'nino_research/.factory_sim.lock';lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Một job sim khác đang chạy; chờ job đó đóng trước')
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+request['mode']);out.mkdir()
        sources=engine_sources()
        save(out/'request.json',request);save(out/'engine_sources.json',sources)
        save(out/'job.json',dict(status='running',request=request,hardware_actions=0))
        emit(ACTION,'Chuẩn bị guided TD3 · chỉ Gazebo local',progress=0.,directory=str(out),phase='prepare')
        started=time.monotonic();stop=[False];status='running';error=None;result=None
        def cancel(signum,frame):
            stop[0]=True
        def timeout(signum,frame):raise TimeoutError('Đã hết wall-time budget; giữ checkpoint hợp lệ trước đó')
        handlers={sig:signal.signal(sig,cancel) for sig in (signal.SIGINT,signal.SIGTERM)}
        handlers[signal.SIGALRM]=signal.signal(signal.SIGALRM,timeout);signal.alarm(request['wall_minutes']*60)
        try:
            result=train(out,request,lambda:stop[0])
            if engine_sources()!=sources:raise ValueError('Studio source changed during the job; retain artifacts')
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,(Cancelled,KeyboardInterrupt)) else 'failed';error=str(exc)
            (out/'error.txt').write_text(traceback.format_exc())
        finally:
            signal.alarm(0)
            for sig,old in handlers.items():signal.signal(sig,old)
            save(out/'job.json',dict(status=status,error=error,wall_s=time.monotonic()-started,request=request,hardware_actions=0))
            save(out/'manifest.json',dict(kind='nino_td3_studio_job_v1',status=status,runtime=runtime_versions(),
                source_fingerprint=source_fingerprint(),frozen_guided_fingerprint=guided.fingerprint(),hardware_actions=0,
                files={str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file() and p!=out/'manifest.json'}))
            emit(ACTION,status,progress=1. if status=='completed' else None,directory=str(out),error=error,result=result)
        return out,status

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:_,status=run(args.output,json.loads(args.request.read_text()));return 0 if status=='completed' else 2 if status=='cancelled' else 1
    except (Exception,KeyboardInterrupt) as exc:print('TD3 Studio:',exc,flush=True);traceback.print_exc();return 1

if __name__=='__main__':raise SystemExit(main())
