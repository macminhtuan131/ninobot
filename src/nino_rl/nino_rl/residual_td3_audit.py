"""Audit a trusted, locally generated TD3 smoke artifact. No ROS or robot I/O.

Check checkpoint/replay/portable inference against all recorded transitions,
then run bounded deterministic authority/governor/fault rollouts. This is a
software integration check on a reduced-order fixture, not a physical result.
Only open artifacts produced locally: SB3 checkpoints/replay use pickle.
"""
import argparse
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import fcntl
import json
from pathlib import Path
import numpy as np
from .residual_experiment import experiment_contract, make_environment, source_fingerprint
from .residual_workflow import artifact_valid, emit, latest, runtime_versions, save
from .velocity_backend import VelocityBackend
from nino_control.residual_actor import PortableActor


def require(condition, message):
    if not condition:raise AssertionError(message)


def close(actual, expected, message, tolerance=2e-6):
    a,b=np.asarray(actual),np.asarray(expected)
    require(a.shape==b.shape and np.all(np.isfinite(a)) and np.all(np.isfinite(b)),message+' shape/finite')
    error=float(np.max(np.abs(a-b))) if a.size else 0.
    require(error<=tolerance,message+': error='+str(error))
    return error


def audit(artifact, out):
    import torch
    from stable_baselines3 import TD3
    torch.set_num_threads(1)
    artifact=Path(artifact).resolve();out=Path(out)
    manifest=artifact_valid(artifact,'train-td3')
    require(manifest['runtime']==runtime_versions(),'Runtime differs from the trusted training artifact')
    config=json.loads((artifact/'config.json').read_text());contract=experiment_contract(config)
    rows=[json.loads(line) for line in (artifact/'training_trace.jsonl').read_text().splitlines()]
    require(len(rows)==128,'Smoke budget must be exactly 128 transitions')
    env=make_environment(config,VelocityBackend(config))
    try:
        model=TD3.load(artifact/'model.zip',env=env,device='cpu')
        model.load_replay_buffer(artifact/'replay_buffer.pkl')
        replay=model.replay_buffer
        require(replay.size()==len(rows) and not replay.full,'Replay size/budget mismatch')
        require(model.num_timesteps==128 and model._n_updates>0,'Optimizer did not run')
        require(bool(model.actor.optimizer.state) and bool(model.critic.optimizer.state),'Optimizer state was not reloaded')
        require(all(torch.isfinite(p).all().item() for p in model.policy.parameters()),'Nonfinite checkpoint parameter')
        actor=PortableActor(artifact,contract['abi_sha256'])
        observation,_=env.reset(seed=7);max_parity=0.;max_replay=0.;timeouts=0;reward_error=0.
        for i,row in enumerate(rows):
            require(row['timestep']==i+1,'Training timestep sequence mismatch')
            require(row['abi_sha256']==contract['abi_sha256'],'Trace ABI mismatch')
            max_replay=max(max_replay,close(replay.observations[i,0],observation,'Replay observation'),
                           close(row['reference_trace']['observation'],observation,'Recorded causal history'))
            close(replay.actions[i,0],row['policy_proposal'],'Replay normalized proposal')
            expected,_=model.predict(observation,deterministic=True)
            max_parity=max(max_parity,close(actor(observation),expected,'Portable / reloaded SB3 actor',1e-5))
            observation,reward,terminal,truncated,info=env.step(np.asarray(row['policy_proposal'],dtype=np.float32))
            max_replay=max(max_replay,close(replay.next_observations[i,0],observation,'Replay next observation'))
            close(info['reference_trace']['body_reference'],row['reference_trace']['body_reference'],'Executed reference trace')
            close(info['feedback_wheel_rad_s'],row['feedback_wheel_rad_s'],'Fixture feedback replay')
            reward_error=max(reward_error,close([replay.rewards[i,0]],[reward],'Replay reward'))
            require(bool(replay.dones[i,0])==bool(terminal or truncated),'Replay done semantics')
            require(bool(replay.timeouts[i,0])==bool(truncated and not terminal),'Replay timeout bootstrap semantics')
            require(bool(row['TimeLimit.truncated'])==bool(truncated and not terminal),'Trace timeout semantics')
            if terminal or truncated:
                close(row['terminal_observation'],observation,'Terminal observation retained before reset')
                timeouts+=int(truncated);observation,_=env.reset()
    finally:env.close()
    rollouts=[];bounds=config['reference_limits'];dt=config['control_interval_s']
    for name,authority,governor in [('alpha0',0.,False),('TD3',1.,False),('TD3_governor',1.,True)]:
        options=deepcopy(config);options['simulation_authority']=authority
        env=make_environment(options,VelocityBackend(options),governor=governor)
        observation,_=env.reset(seed=101);previous=np.zeros(2);targets=[];feedback=[];contributions=[]
        try:
            with (out/(name+'_rollout.jsonl')).open('w') as stream:
                for step in range(60):
                    proposal=actor(observation);observation,reward,terminal,truncated,info=env.step(proposal)
                    trace=info['reference_trace'];accepted=np.asarray(trace['accepted_reference_wheel_m_s'])
                    proposed=np.asarray(trace['proposed_residual_wheel_m_s']);policy=np.asarray(trace['accepted_policy_delta_wheel_m_s'])
                    require(np.max(np.abs(proposed))<=bounds['residual_wheel_m_s']+1e-8,'Per-wheel proposal bound')
                    require(np.max(np.abs(accepted))<=bounds['wheel_speed_m_s']+1e-8,'Wheel speed bound')
                    require(np.max(np.abs(accepted-previous))<=bounds['wheel_acceleration_m_s2']*dt+1e-8,'Reference acceleration bound')
                    v,yaw=trace['body_reference']
                    require(abs(v)<=bounds['forward_m_s']+1e-8 and abs(yaw)<=bounds['yaw_rad_s']+1e-8,'Body reference bound')
                    if authority==0.:close(policy,[0.,0.],'Zero authority cannot contribute')
                    if trace['original_baseline_body']==(0.,0.):close(proposed,[0.,0.],'Baseline zero cannot start from residual')
                    targets.append(info['applied_target_rad_s']);feedback.append(info['feedback_wheel_rad_s']);contributions.append(policy)
                    previous=accepted
                    stream.write(json.dumps(dict(step=step,reward=reward,terminated=terminal,truncated=truncated,**info),allow_nan=False)+'\n')
                    if terminal or truncated:break
            require(truncated and not terminal and step==59,'Bounded fixture rollout completion')
        finally:env.close()
        rollouts.append(dict(arm=name,steps=step+1,targets=np.asarray(targets),feedback=np.asarray(feedback),
                             policy_contribution_max_m_s=float(np.max(np.abs(contributions)))))
    target_effect=float(np.max(np.abs(rollouts[1]['targets']-rollouts[0]['targets'])))
    wheel_effect=float(np.max(np.abs(rollouts[1]['feedback']-rollouts[0]['feedback'])))
    require(min(target_effect,wheel_effect)>1e-6,'Trained actor has no fixture target/feedback effect')
    faults=[]
    for change in ({'permission':False},{'fault':True},{'emergency_stop':True},{'sensors_fresh':False},
                   {'command_age_s':bounds['max_age_s']+.01}):
        env=make_environment(config,VelocityBackend(config));env.reset(seed=103)
        try:
            env.pipeline.last_view.update(change)
            _,reward,terminal,truncated,info=env.step(np.array([.5,-.2],dtype=np.float32))
            require(terminal and not truncated and reward==-config.get('failure_penalty',10.),'Fault must be terminal failure')
            close(info['reference_trace']['body_reference'],[0.,0.],'Fault reference stop')
            faults.append(dict(input=change,terminal=True,reason=info['termination_reason']))
        finally:env.close()
    result=dict(status='passed',artifact=str(artifact),source_fingerprint=source_fingerprint(),abi_sha256=contract['abi_sha256'],
        transitions=128,replay_transitions_checked=128,timeout_terminals_checked=timeouts,
        optimizer_updates=int(model._n_updates),actor_optimizer_state_reloaded=True,critic_optimizer_state_reloaded=True,
        portable_actor_max_error=max_parity,replay_observation_max_error=max_replay,replay_reward_max_error=reward_error,
        rollout_steps_per_arm=60,rollout_arms=[dict(arm=r['arm'],steps=r['steps'],policy_contribution_max_m_s=r['policy_contribution_max_m_s']) for r in rollouts],
        target_effect_max_rad_s=target_effect,wheel_effect_max_rad_s=wheel_effect,fault_cases=faults,
        evidence_level='software_integration_reduced_order_only',hardware_actions=0,hardware_authorized=False,
        calibrated_to_hardware=False,physical_benefit_verified=False)
    save(out/'audit.json',result);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--artifact',type=Path,help='Trusted local train-td3 artifact; never untrusted uploads')
    source.add_argument('--workflow',action='store_true',help='Audit latest verified TD3 in --output and register GUI result')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    root=a.output.expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    with ((root/'.job.lock').open('a') if a.workflow else nullcontext()) as lock:
        if lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        artifact=latest(root,'train-td3') if a.workflow else a.artifact.expanduser().resolve()
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_td3_audit')
        out.mkdir(exist_ok=False);status='failed';error=None;result=None
        emit('audit-td3','Audit checkpoint / replay / portable actor · software only',0.,directory=str(out))
        try:
            result=audit(artifact,out);status='completed';return 0
        except (Exception,KeyboardInterrupt) as exc:
            error=str(exc) or 'operator_interrupt';status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed'
            save(out/'failure.json',dict(error=error));raise
        finally:
            save(out/'manifest.json',dict(action='audit-td3',status=status,error=error,source_fingerprint=source_fingerprint(),
                auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runtime=runtime_versions(),hardware_actions=0,
                input_artifact=str(artifact),
                input_manifest_sha256=hashlib.sha256((artifact/'manifest.json').read_bytes()).hexdigest() if (artifact/'manifest.json').exists() else None,
                files={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}))
            if a.workflow:
                state_path=root/'state.json';state=json.loads(state_path.read_text())
                state['runs'].append(dict(action='audit-td3',path=out.name,status=status,error=error))
                if status=='completed':state['latest']['audit-td3']=out.name
                save(state_path,state)
            emit('audit-td3',status,1. if status=='completed' else None,directory=str(out),result=result,error=error)


if __name__=='__main__':raise SystemExit(main())
