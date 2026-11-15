"""Request-driven goal100 trainer. Importing/preflighting never calls .learn()."""
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import signal
import time
import traceback

import numpy as np

from . import goal_studio_contract as contract
from . import unknown_step_runner as short
from .common_training_studio_v2 import build_model, actor_steps
from .residual_workflow import save, emit, runtime_versions
from .studio_deferred_reset import DeferredResetVecEnv

ACTION='td3-unknown-goal100'


def checkpoint(model, target, ident):
    short.checkpoint(model,target,ident)
    c=json.loads((target/'checkpoint.json').read_text())
    c.update(engine=contract.ENGINE,purpose='goal100_request_training_not_promoted')
    save(target/'checkpoint.json',c)
    files={p.name:short.sha(p) for p in target.iterdir() if p.is_file() and p.name!='manifest.json'}
    save(target/'manifest.json',dict(kind=contract.CHECKPOINT_KIND,status='resumable',
                                    runtime=runtime_versions(),files=files))


def run(root, raw):
    import torch
    from stable_baselines3 import TD3
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.logger import configure
    from stable_baselines3.common.monitor import Monitor
    r=contract.validate_request(raw);qualified=contract.require_qualification()
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    plan=contract.require_disk(root,r);ident=contract.identity(r)
    with (Path.home()/'nino_research/.factory_sim.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_unknown_goal100_'+r['mode']);out.mkdir()
        shutil.copytree(qualified/'inputs',out/'inputs')
        save(out/'request.json',dict(r,engine=contract.ENGINE));save(out/'effective_profile.json',ident['effective_profile'])
        save(out/'ledger.json',dict(status='running',scope='explicit_request_goal_training',plan=plan))
        save(out/'job.json',dict(status='running',request=r,engine=contract.ENGINE))
        bank=short.require_inputs(out)
        env=short.BankEnvironment(out,bank,short.plan.protocol()['bank']['training_layout_order'],
            launches=plan['training_launches_max'],budget=r['timesteps'],
            global_launch_limit=plan['training_launches_max']+plan['evaluation_launches'])
        vec=DeferredResetVecEnv(Monitor(env));model=None;safe=False;stopped=False
        status,error,result='running',None,None;start=time.monotonic()
        old_int=signal.signal(signal.SIGINT,lambda *_: stop())
        old_term=signal.signal(signal.SIGTERM,lambda *_: stop())
        old_alarm=signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('Goal training wall deadline')))
        signal.alarm(r['wall_minutes']*60)
        def stop():
            nonlocal stopped
            stopped=True
        traces=[];saved=[]
        start_steps=start_updates=start_actor=start_pos=0

        class Trace(BaseCallback):
            def _on_rollout_start(self):
                nonlocal safe
                safe=False
            def _on_step(self):
                row=dict(env.last,timestep=self.num_timesteps)
                row['episode_world']=dict(path=env.layout['world'],sha256=env.layout['world_sha256'],episode=env.episode)
                row['next_observation']=self.locals['infos'][0].get('terminal_observation',self.locals['new_obs'][0])
                np.testing.assert_allclose(self.locals['actions'][0],row['replay_action'],atol=2e-6,rtol=0)
                short.append(out/'training_trace.jsonl',row);traces.append(row)
                if len(traces)>256:traces.pop(0)
                if env.steps%32==0 or row['done']:
                    save(out/'coverage.json',dict(total=env.steps,global_steps=self.num_timesteps))
                    emit(ACTION,f'Goal TD3 {env.steps}/{r["timesteps"]} · global {self.num_timesteps} · critic {model._n_updates}',
                         env.steps/r['timesteps'],directory=str(out),phase='train',global_steps=int(self.num_timesteps))
                return True
            def _on_rollout_end(self):
                nonlocal safe
                safe=True
                if r['checkpoint_every'] and env.steps%r['checkpoint_every']==0 and env.steps<r['timesteps']:
                    target=out/'checkpoints'/f'step_{model.num_timesteps:012d}_periodic';target.parent.mkdir(exist_ok=True)
                    checkpoint(model,target,ident);saved.append(str(target))
                    emit(ACTION,'Checkpoint saved',checkpoint=str(target))
                if stopped:raise KeyboardInterrupt('User stopped at stored transition boundary')
                if env.steps<r['timesteps']:vec.reset_after_store(model)

        try:
            torch.set_num_threads(1)
            if r['resume']:
                cp=contract.inspect_checkpoint(r['resume'])
                if cp['identity']!=ident:raise ValueError('Goal resume identity/profile/bank/source mismatch')
                model=TD3.load(Path(cp['path'])/'model.zip',env=vec,device='cpu',force_reset=True)
                model.load_replay_buffer(Path(cp['path'])/'replay_buffer.pkl')
                if (model.num_timesteps,model._n_updates,model.replay_buffer.size())!=(cp['global_steps'],cp['optimizer_updates'],cp['replay_size']):
                    raise ValueError('Loaded goal model/replay counters differ from checkpoint metadata')
            else:model=build_model(vec,r)
            start_steps,start_updates,start_actor=int(model.num_timesteps),int(model._n_updates),actor_steps(model)
            start_pos=int(model.replay_buffer.pos)
            model.set_logger(configure(str(out/'tensorboard'),['tensorboard']))
            emit(ACTION,'Start explicitly requested goal-task job',0.,directory=str(out),phase='prepare')
            model.learn(total_timesteps=r['timesteps'],callback=Trace(),reset_num_timesteps=not bool(r['resume']))
            if not all(torch.isfinite(v).all() for v in model.policy.parameters()):
                raise ValueError('Nonfinite goal-task checkpoint')
            if model.num_timesteps!=start_steps+r['timesteps']:
                raise ValueError('Goal training global counter differs from explicit budget')
            if contract.identity(r)!=ident:
                raise ValueError('Qualified task/profile/source changed during goal training')
            for row in traces:
                b=model.replay_buffer;i=(start_pos+row['step']-1)%b.buffer_size
                for actual,expected in [(b.observations[i,0],row['observation']),
                        (b.next_observations[i,0],row['next_observation']),
                        (b.actions[i,0],row['replay_action']),([b.rewards[i,0]],[row['reward']])]:
                    np.testing.assert_allclose(actual,expected,atol=2e-6,rtol=0)
                if bool(b.dones[i,0])!=row['done'] or bool(b.timeouts[i,0])!=bool(row['truncated'] and not row['terminated']):
                    raise ValueError('Goal replay done/truncation differs from trace')
            target=out/'checkpoints'/f'step_{model.num_timesteps:012d}_final';target.parent.mkdir(exist_ok=True)
            checkpoint(model,target,ident);saved.append(str(target))
            result=dict(engine=contract.ENGINE,transitions=env.steps,starting_global_steps=start_steps,
                global_steps=int(model.num_timesteps),optimizer_updates_this_job=int(model._n_updates)-start_updates,
                actor_updates_this_job=actor_steps(model)-start_actor,replay_size=int(model.replay_buffer.size()),
                optimizer_updates_total=int(model._n_updates),actor_updates_total=actor_steps(model),
                checkpoint=str(target),checkpoints=saved,final_segment_right_censored=not env.last['done'],
                tensorboard=str(out/'tensorboard'),
                replay_rows_checked=len(traces),
                complete_training_episodes=env.completed,benefit_verified=False,hardware_authorized=False)
            save(out/'training_result.json',result)
            vec.close()
            qc=short.raw_qc(out)
            if not qc['valid']:raise ValueError('Goal training raw QC failed; retain checkpoint')
            if r['evaluate']:
                (out/'evaluation').mkdir()
                evaluation=[];before=[p.detach().clone() for p in model.policy.parameters()]
                for arm in ('B0','TD3'):
                    for layout in short.plan.protocol()['bank']['development']:
                        if stopped:raise KeyboardInterrupt('Stopped before evaluation launch')
                        emit(ACTION,'Development '+arm+' '+layout['id'],phase='evaluate',directory=str(out))
                        item=short.rollout(out/'evaluation'/f'{arm}_{layout["id"]}',bank,layout['id'],model=model if arm=='TD3' else None)
                        item['arm']=arm;evaluation.append(item);save(out/'evaluation_progress.json',evaluation)
                        if not item['source_qc']['valid']:raise ValueError('Evaluation measurement QC failed')
                if any(not torch.equal(p.detach(),q) for p,q in zip(model.policy.parameters(),before)):
                    raise ValueError('Evaluation changed model')
                result['goal_evaluation']=evaluation
                save(out/'training_result.json',result)
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc)
            (out/'error.txt').write_text(traceback.format_exc())
            if model is not None and safe:
                target=out/'checkpoints'/f'step_{model.num_timesteps:012d}_interrupted';target.parent.mkdir(exist_ok=True)
                checkpoint(model,target,ident)
        finally:
            try:vec.close()
            finally:
                signal.alarm(0);signal.signal(signal.SIGINT,old_int);signal.signal(signal.SIGTERM,old_term);signal.signal(signal.SIGALRM,old_alarm)
                save(out/'job.json',dict(status=status,error=error,request=r,engine=contract.ENGINE,wall_s=time.monotonic()-start))
                save(out/'manifest.json',dict(kind='nino_unknown_goal_job_v1',status=status,identity=ident,
                    files={str(f.relative_to(out)):short.sha(f) for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
                emit(ACTION,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
        return out,status
