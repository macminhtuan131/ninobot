"""Offline parity of the real PI kernel and103D wrapper. Never starts ROS/Gazebo."""
import argparse,ast,hashlib,json,textwrap
from copy import deepcopy
from pathlib import Path
import numpy as np
from . import gain_context as context
from .gain_reference_map import target_map,map_audit
from .residual_workflow import save,json_value


def kernel_ast_parity():
    base=context.benchmark.repo()
    old=ast.parse((base/'src/nino_control/nino_control/effort_drive.py').read_text())
    cls=next(n for n in old.body if isinstance(n,ast.ClassDef) and n.name=='EffortDrive')
    old=deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_control_update'))
    old.name='gain_control_update';count=0
    for node in ast.walk(old):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='wheel_angular_targets':
            node.func=ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr='gain_target_map',ctx=ast.Load());count+=1
    new=ast.parse((base/'src/nino_rl/nino_rl/gain_drive_kernel.py').read_text())
    new=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='gain_control_update')
    if count!=1 or ast.dump(old,include_attributes=False)!=ast.dump(new,include_attributes=False):
        raise ValueError('Gain kernel changed more than its single target-map call')
    return dict(only_one_wheel_target_map_call_changed=True,frozen_kernel_unchanged=True)


def fixture_backend(c):
    parent=context.parent.parent.frozen.offline.fixture_backend(c,8.)
    original=parent.advance_reference
    def advance(*args,**kwargs):
        view,labels,term,trunc,info=original(*args,**kwargs)
        # Synthetic instrumentation on the gain-one software fixture only.
        _,record=target_map(*info['final_ros_reference'],c['nominal_geometry']['radius_l'],
            c['nominal_geometry']['separation'],1.)
        audit=map_audit(record,stamp_s=info['sensor_clock_s'],targets=info['applied_target_rad_s'],max_speed=12.,calls=1)
        info.update(gain_map_audit=audit,gain_context=context.CONTEXT_ID,
            drive_diagnostics=dict(sim_time_s=info['sensor_clock_s'],executed_linear_m_s=info['final_ros_reference'][0],
                executed_yaw_rad_s=info['final_ros_reference'][1],left_applied_nm=0.,right_applied_nm=0.,
                left_target_rad_s=info['applied_target_rad_s'][0],right_target_rad_s=info['applied_target_rad_s'][1]),
            source_lags_s=dict(imu=0.,wheel=0.),guidance_audit=dict(fault=False),
            truth_used_for_guidance=False,fixture_only=True,synthetic_gain_audit=True)
        return view,labels,term,trunc,info
    parent.advance_reference=advance
    return parent


def wrapper_parity():
    results=[];traces=[];ident=context.identity()
    for arm in ('B0','Classical_scheduled','Causal_gain_candidate'):
        c,g,task,condition=context.configuration(1.)
        # Balance fixture dynamics; this is not Nino parameter calibration.
        c['backend'].update(wheel_gain=[1.,1.],motor_lag_s=[.16,.16],imu_noise_std=0.)
        old=context.contract.environment(c,fixture_backend(c),task,condition)
        new=context.environment(c,fixture_backend(c),task,condition)
        previous=None;rows=[]
        try:
            a,old_info=old.reset(seed=701);b,new_info=new.reset(seed=701)
            context.require_identity(new_info['gain_context_identity'])
            for step in range(140):
                np.testing.assert_array_equal(a,b)
                action=context.request(arm,b,c['nominal_geometry'])
                a,r1,t1,u1,i1=old.step(action);b,r2,t2,u2,i2=new.step(action)
                np.testing.assert_array_equal(a,b)
                if (r1,t1,u1)!=(r2,t2,u2):raise ValueError('Gain-one wrapper changed reward/termination')
                for name in ('reference_trace','plan_projection','applied_target_rad_s','final_ros_reference'):
                    if i1[name]!=i2[name]:raise ValueError('Gain-one reference/telemetry parity failed')
                row=dict(step=step,reward=r2,terminated=t2,truncated=u2,done=t2 or u2,**i2,
                    qualification_condition=dict(arm=arm,source_stop_s=8.,gain=1.),
                    **{'TimeLimit.truncated':bool(u2 and not t2)})
                epoch=row['sensor_clock_s']-row['task']['elapsed_s'] if previous is None else epoch
                context.verify_transition(row,previous,epoch,1.,expected_identity=ident)
                rows.append(row);previous=row
            if not rows[-1]['terminated'] or rows[-1]['truncated']:raise ValueError('Fixture terminal changed')
        finally:old.close();new.close()
        results.append(dict(arm=arm,paired_fixture_decisions=140,old_and_new_transitions=280,
            observations_rewards_projection_terminal_exact=True,new_identity_old_checkpoint_incompatible=True,
            synthetic_fixture_only=True))
        traces.append(rows)
    return results,traces


def run(output):
    from .gain_drive_fixture import driver_parity
    output=Path(output).expanduser().resolve()
    # Validate the sealed design before writing a derived software artifact.
    source=Path.home()/'nino_research/sim_benchmark_decision_v1/decision_2026_11_06_verified'
    context.benchmark.verified_report(source)
    output.mkdir(parents=True,exist_ok=False)
    current=context.fingerprint();save(output/'identity.json',context.identity())
    ast_check=kernel_ast_parity();drive,driver_trace=driver_parity();runs,traces=wrapper_parity()
    save(output/'driver_fixture_trace.json',driver_trace)
    for i,rows in enumerate(traces):
        with (output/f'wrapper_fixture_{i}.jsonl').open('w') as f:
            for row in rows:f.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
    result=dict(status='offline_gain_context_parity_passed_not_Gazebo_qualified',
        context_id=context.CONTEXT_ID,abi_sha256=context.identity()['abi_sha256'],
        ast_parity=ast_check,driver=drive,wrapper_runs=runs,
        synthetic_driver_callbacks=4800,synthetic_wrapper_transitions=840,
        same_observation_shape_old_checkpoint_compatible=False,
        gain_parameter_is_evaluation_only=True,nominal_final_reference_not_gain_normalized=True,
        new_gazebo_launches=0,new_physics_steps=0,actor_loads=0,new_training_transitions=0,
        new_optimizer_updates=0,hardware_actions=0,physics_released=False,benefit_verified=False,
        source_decision_artifact=str(source),source_decision_manifest_sha256=context.benchmark.sha(source/'manifest.json'),
        remaining_gate='fresh nine-cell Gazebo baseline qualification needs separate runner/release; first cells are integration checks')
    if context.fingerprint()!=current:raise ValueError('Gain context source changed during offline qualification')
    save(output/'qualification.json',result)
    save(output/'manifest.json',dict(fingerprint=current,
        files={p.name:context.benchmark.sha(p) for p in output.iterdir() if p.is_file()}))
    return result


def verified_report(output):
    output=Path(output);m=context.benchmark.read(output/'manifest.json')
    if m['fingerprint']!=context.fingerprint():raise ValueError('Gain context sources changed')
    for name,value in m['files'].items():
        path=(output/name).resolve()
        if path.parent!=output.resolve() or context.benchmark.sha(path)!=value:raise ValueError('Gain preflight artifact changed')
    result=context.benchmark.read(output/'qualification.json')
    source=Path(result['source_decision_artifact'])
    context.benchmark.verified_report(source)
    if context.benchmark.sha(source/'manifest.json')!=result['source_decision_manifest_sha256']:
        raise ValueError('Benchmark decision changed')
    if result['abi_sha256']!=context.identity()['abi_sha256'] or result['physics_released']:
        raise ValueError('Offline gain identity/release mismatch')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();result=run(args.output)
    print(json.dumps(dict(status=result['status'],output=str(args.output),physics=0,training=0),indent=2))


if __name__=='__main__':main()
