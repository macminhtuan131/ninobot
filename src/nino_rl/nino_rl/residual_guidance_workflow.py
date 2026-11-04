"""Finite offline guidance/ResidualPipeline fixtures. No Gazebo, ROS or learner."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import time
from nino_control.residual_pipeline import ObservationAssembler, ResidualPipeline
from nino_control.residual_velocity import actor_contract
from .core import load_config
from .residual_factory_workflow import repo
from .residual_guidance import GuidanceReference, PoseSample, apply_guidance, contract
from .residual_sim_task import config as residual_config, dependency_record
from .residual_clear_bias import validated_latest as diagnostic_latest
from .residual_workflow import save, emit, latest, source_fingerprint, runtime_versions

ACTION = 'sim-guidance-contract'


def config(): return load_config(repo()/'src/nino_rl/config/residual_guidance_v1.yaml')


def fingerprint():
    paths=[Path(__file__),repo()/'src/nino_rl/scripts/residual_guidance_check.sh']
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(dict(files=hashes,guidance=contract(config()),residual=source_fingerprint()),sort_keys=True).encode()).hexdigest()


def fixtures(out):
    c=residual_config();gconf=config();abi=actor_contract(c)
    scenarios={'left_of_path':dict(y=.1), 'right_of_path':dict(y=-.1),
               'heading_error':dict(yaw=-.2), 'at_goal':dict(x=1.49), 'stale_pose':dict(y=.1)}
    results={}
    for case,offset in scenarios.items():
        controller=GuidanceReference(gconf,epoch='offline_fixture')
        assembler=ObservationAssembler(c['nominal_geometry']);pipeline=ResidualPipeline(c);rows=[]
        for i in range(35):
            t=i*.1
            if case!='stale_pose' or i<30:
                controller.update_pose(PoseSample(offset.get('x',0.),offset.get('y',0.),offset.get('yaw',0.),
                    t,t,gconf['pose_frame_id'],gconf['pose_source'],gconf['clock_id'],'offline_fixture'))
            for channel,payload in [('imu',[0.,0.,0.,0.,0.,9.80665]),('wheel',[1.,1.]),
                    ('baseline',[.2,0.]),('final',[.1,0.]),('status',dict(permission=True,fault=False,emergency_stop=False))]:
                assembler.push(channel,payload,t,t,gconf['command_frame_id'] if channel=='baseline' else None)
            view=assembler.view(t);view['clock_id']=gconf['clock_id'];view['actual_actuator_target']=[2.,2.]
            reference=controller.command(t,permission=True)
            guided=apply_guidance(view,reference);obs=pipeline.observe(guided);trace=pipeline.project([0.,0.],.1,0.)
            if len(obs)!=100 or guided['actual_actuator_target']!=[2.,2.]:raise ValueError('Guidance changed actor ABI/readback')
            rows.append(dict(time_s=t,reference=reference,reference_trace=trace))
        final=rows[-1]['reference_trace']['body_reference'];latched=pipeline.reference.latched
        passed=(final[1]<0 and not latched if case=='left_of_path' else final[1]>0 and not latched if case in ('right_of_path','heading_error')
                else final== (0.,0.) and not latched if case=='at_goal' else final==(0.,0.) and latched)
        save(out/(case+'.json'),rows)
        results[case]=dict(passed=bool(passed),final_reference=final,latched=latched,fixture_ticks=len(rows))
        if not passed:raise ValueError('Offline guidance fixture failed: '+case)
    return dict(baseline_contract=contract(gconf),fixtures=results,fixture_count=len(results),
        observation_size=abi['observation_size'],abi_sha256=abi['abi_sha256'],actor_pose_features_added=0,
        stage='offline_adapter_prepared_only',gazebo_guidance_connected=False,
        localization_verified=False,hardware_authorized=False,training_transitions=0,
        note='Scripted poses verify reference/clock/gate semantics, not navigation performance or model identification.')


def validated_latest(root,check_runtime=True):
    path=latest(root,ACTION,check_runtime=check_runtime)
    if json.loads((path/'manifest.json').read_text()).get('guidance_fingerprint')!=fingerprint():
        raise ValueError('Guidance source/config changed; offline artifact historical')
    dependency=diagnostic_latest(root,check_runtime=check_runtime)
    if json.loads((path/'dependencies.json').read_text())!=dependency_record(dependency):
        raise ValueError('Guidance workflow references an older diagnostic')
    return path


def run(root):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    with (root/'.job.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        dependency=diagnostic_latest(root)
        state=json.loads((root/'state.json').read_text())
        if any(r['action']==ACTION for r in state['runs']):raise ValueError('Offline batch already closed; review artifact')
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION);out.mkdir()
        current,start,status,error,result=fingerprint(),time.monotonic(),'running',None,None
        save(out/'config.json',config());save(out/'dependencies.json',dependency_record(dependency))
        emit(ACTION,'Check causal pose → follower → unchanged residual ABI, offline only',0.,directory=str(out))
        try:
            result=fixtures(out);save(out/'guidance_result.json',result)
            if fingerprint()!=current:raise ValueError('Guidance sources changed during fixtures')
            status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            save(out/'job.json',dict(action=ACTION,status=status,error=error,wall_s=time.monotonic()-start,hardware_actions=0))
            save(out/'manifest.json',dict(action=ACTION,status=status,guidance_fingerprint=current,
                source_fingerprint=source_fingerprint(),runtime=runtime_versions(),hardware_actions=0,
                files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}))
            state['runs'].append(dict(action=ACTION,path=out.name,status=status,error=error))
            if status=='completed':state['latest'][ACTION]=out.name
            save(root/'state.json',state);emit(ACTION,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    try:run(a.output)
    except (Exception,KeyboardInterrupt) as exc:print('Offline guidance failed/retained:',exc,flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
