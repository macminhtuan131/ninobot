"""Software qualification only: actual frozen PI kernel and typed B0 wrapper."""
import argparse,ast,hashlib,inspect,json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from . import pi_screen_context as context
from . import gain_context_preflight as old_preflight
from .gain_drive_fixture import fixture,input_frame,snapshot,Sink
from .gain_effort_drive import GainEffortDrive
from .pi_screen_effort_drive import PiScreenEffortDrive
from .pi_screen_backend import PiScreenBackend
from .pi_screen_contract import require_ki,runtime_audit,require_audit
from .residual_workflow import save,json_value


def reset_ast_parity():
    """Whitelist the whole reset diff, including launch args and readback check."""
    from .gain_factory_backend import GainReadinessBackend
    import textwrap
    old=textwrap.dedent(inspect.getsource(GainReadinessBackend._reset_factory))
    expected=old.replace('training_sim_gain.launch.py','training_sim_pi_screen.launch.py')
    expected=expected.replace("'sim_common_gain:='+str(self.sim_common_gain)]",
        "'sim_common_gain:='+str(self.sim_common_gain),'velocity_ki:='+str(self.pi_ki)]")
    expected=expected.replace('velocity_ki=.1,','velocity_ki=self.pi_ki,')
    actual=textwrap.dedent(inspect.getsource(PiScreenBackend._reset_factory))
    if ast.dump(ast.parse(expected))!=ast.dump(ast.parse(actual)):
        raise ValueError('PI reset changed more than declared launch/Ki/readback contrast')
    if PiScreenBackend._reset_guided is not GainReadinessBackend._reset_guided:
        raise ValueError('Guided reset drifted')
    return dict(factory_reset_only_launch_ki_readback_changed=True,guided_reset_exact_same_callable=True)


def driver_parity():
    old=fixture(1.);baseline=fixture(1.);candidate=fixture(1.);candidate.ki=.15
    for f in (baseline,candidate):f.pi_screen_publisher=Sink()
    differences=0;trace=[]
    for i in range(1200):
        input_frame(old,i);GainEffortDrive._control_update(old)
        for f in (baseline,candidate):
            before=f.applied_effort.copy();targets=f.target_velocity.copy()
            input_frame(f,i);PiScreenEffortDrive._control_update(f)
            if max(map(abs,f.applied_effort))>4.+1e-12 or max(map(abs,f.target_velocity))>12.+1e-12:
                raise ValueError('PI fixture torque/speed envelope violated')
            if max(abs(a-b) for a,b in zip(before,f.applied_effort))>.020000001:
                raise ValueError('Effort slew changed')
            if f.have_wheel_state and max(abs(a-b) for a,b in zip(targets,f.target_velocity))>.024000001:
                raise ValueError('Target ramp changed')
            if f.pi_screen_publisher.rows:
                msg=f.pi_screen_publisher.rows[-1]
                require_audit(dict(zip(msg['fields'][0].split(','),msg['data'])),f.ki)
            # Frozen kernel retains target/integral during missing feedback;
            # it requests zero effort through the existing slew limiter.
            # Do not invent a reset or alter that behavior in this contrast.
            if not f.have_wheel_state and f.gain_map_calls!=0:
                raise ValueError('Target map executed without wheel feedback')
        if snapshot(old)!=snapshot(baseline):raise ValueError('Baseline Ki 0.10 changed frozen PI behavior')
        if baseline.gain_publisher.rows!=old.gain_publisher.rows:raise ValueError('Gain-one telemetry drift')
        if baseline.target_velocity!=candidate.target_velocity or baseline.odom!=candidate.odom:
            raise ValueError('Ki contrast changed mapping/odometry on held feedback')
        changed=baseline.applied_effort!=candidate.applied_effort;differences+=int(changed)
        trace.append(dict(index=i,baseline_applied=baseline.applied_effort.copy(),
            candidate_applied=candidate.applied_effort.copy(),target=baseline.target_velocity.copy(),
            baseline_integral=baseline.error_integral.copy(),candidate_integral=candidate.error_integral.copy(),
            fresh=(old.now_ns-old.last_cmd_ns)*1e-9<=.5,have_wheel_state=old.have_wheel_state))
    if not differences:raise ValueError('Candidate Ki did not reach actual PI kernel')
    return dict(synthetic_callbacks=3600,callbacks_per_condition=1200,
        baseline_exact_state_effort_diagnostics_odometry=True,candidate_effort_different_callbacks=differences,
        held_feedback_not_plant_response=True,limits_watchdog_missing_feedback_included=True),trace


def fixture_backend(c):
    # This fixture is NOT a model of Ki's effect. Only the real kernel above
    # exercises Ki. The wrapper fixture tests schema/causality/reference flow.
    backend=old_preflight.fixture_backend(c);original=backend.advance_reference
    def advance(*args,**kwargs):
        view,labels,term,trunc,info=original(*args,**kwargs)
        driver=fixture(1.);driver.ki=c['backend']['pi_ki']
        driver.last_control_ns=round(info['sensor_clock_s']*1e9)
        info.update(pi_screen_audit=runtime_audit(driver),pi_screen_context=context.CONTEXT_ID,
            evaluation_ki=driver.ki,synthetic_pi_audit=True,ki_dynamics_not_modeled=True)
        return view,labels,term,trunc,info
    backend.advance_reference=advance
    return backend


def wrapper_parity():
    results=[];traces=[];ident=context.identity()
    for ki in (.1,.15):
        c,g,task,condition=context.configuration(ki)
        c['backend'].update(wheel_gain=[1.,1.],motor_lag_s=[.16,.16],imu_noise_std=0.)
        old=context.gain_parent.environment(c,fixture_backend(c),task,condition)
        new=context.environment(c,fixture_backend(c),task,condition)
        previous=None;rows=[]
        try:
            a,_=old.reset(seed=701);b,info=new.reset(seed=701)
            context.require_identity(info['pi_screen_identity'])
            for step in range(140):
                np.testing.assert_array_equal(a,b)
                action=context.request('B0',b,c['nominal_geometry'])
                a,r1,t1,u1,i1=old.step(action);b,r2,t2,u2,i2=new.step(action)
                np.testing.assert_array_equal(a,b)
                if (r1,t1,u1)!=(r2,t2,u2):raise ValueError('Wrapper changed reward/termination')
                for key in ('reference_trace','plan_projection','applied_target_rad_s','final_ros_reference'):
                    if i1[key]!=i2[key]:raise ValueError('Wrapper changed reference/projection semantics')
                row=dict(step=step,reward=r2,terminated=t2,truncated=u2,done=t2 or u2,**i2,
                    qualification_condition=dict(arm='B0',source_stop_s=8.,ki=ki),
                    **{'TimeLimit.truncated':bool(u2 and not t2)})
                epoch=row['sensor_clock_s']-row['task']['elapsed_s'] if previous is None else epoch
                context.verify_transition(row,previous,epoch,ki,expected_identity=ident)
                rows.append(row);previous=row
            if not rows[-1]['terminated'] or rows[-1]['truncated']:raise ValueError('Fixture terminal drift')
        finally:old.close();new.close()
        results.append(dict(ki=ki,paired_fixture_decisions=140,old_and_new_transitions=280,
            observations_rewards_projection_terminal_exact=True,ki_dynamics_not_modeled=True))
        traces.append(rows)
    return results,traces


def dependency():
    from . import sim_chain_dynamics_audit_v2 as dynamics
    root=Path.home()/'nino_research/sim_chain_dynamics_audit_v2/analysis_2026_11_07'
    dynamics.verified_report(root)
    p=context.benchmark.read(context.benchmark.repo()/'src/nino_rl/config/sim_pi_screen_preparation_v1.json')
    if context.benchmark.sha(root/'manifest.json')!=p['source_dynamics_manifest_sha256']:
        raise ValueError('PI proposal source dynamics changed')
    if p['physics_released'] or p['training_released'] or p['hardware_authorized'] or p['allocated_physics_slots']:
        raise ValueError('Offline preparation cannot release physics/training/hardware')
    return root


def run(output):
    source=dependency();output=Path(output).expanduser().resolve()
    output.mkdir(parents=True,exist_ok=False);current=context.fingerprint()
    try:
        ast_check=old_preflight.kernel_ast_parity();reset_check=reset_ast_parity()
        drive,trace=driver_parity();wrappers,rows=wrapper_parity()
        save(output/'identity.json',context.identity());save(output/'driver_fixture_trace.json',trace)
        for index,values in enumerate(rows):
            with (output/f'wrapper_fixture_{index}.jsonl').open('w') as f:
                for row in values:f.write(json.dumps(row,default=json_value,allow_nan=False)+'\n')
        report=dict(status='offline_pi_screen_parity_passed_not_Gazebo_qualified',
            context_id=context.CONTEXT_ID,abi_sha256=context.identity()['abi_sha256'],
            kernel_ast=ast_check,reset_ast=reset_check,driver=drive,wrapper_runs=wrappers,
            synthetic_kernel_callbacks=3600,synthetic_wrapper_transitions=560,
            new_gazebo_launches=0,new_physics_steps=0,actor_loads=0,optimizer_updates=0,
            training_transitions=0,hardware_actions=0,physics_released=False,benefit_verified=False,
            candidate_ki_response_identified=False,old_checkpoint_compatible=False,
            source_dynamics_artifact=str(source),source_dynamics_manifest_sha256=context.benchmark.sha(source/'manifest.json'),
            next_gate='separate bounded runner/protocol/release before four fresh Gazebo cells; no learner release')
        if context.fingerprint()!=current:raise ValueError('PI preparation source changed during run')
        save(output/'qualification.json',report)
        save(output/'manifest.json',dict(fingerprint=current,status='completed',
            files={f.name:context.benchmark.sha(f) for f in output.iterdir() if f.is_file()}))
        return report
    except BaseException as exc:
        save(output/'failure.json',dict(error=repr(exc),physics=0,training=0));raise


def verified_report(output):
    output=Path(output).resolve();m=context.benchmark.read(output/'manifest.json')
    if m['status']!='completed' or m['fingerprint']!=context.fingerprint():
        raise ValueError('PI screen preparation source/completion changed')
    required={'identity.json','qualification.json','driver_fixture_trace.json',
              'wrapper_fixture_0.jsonl','wrapper_fixture_1.jsonl'}
    if (set(m['files'])!=required
            or {f.name for f in output.iterdir() if f.is_file()}!=required|{'manifest.json'}):
        raise ValueError('PI preparation artifact inventory changed')
    for name,value in m['files'].items():
        path=(output/name).resolve()
        if path.parent!=output or context.benchmark.sha(path)!=value:raise ValueError('PI preparation artifact changed')
    report=context.benchmark.read(output/'qualification.json');source=dependency()
    if (report['source_dynamics_artifact']!=str(source)
            or report['source_dynamics_manifest_sha256']!=context.benchmark.sha(source/'manifest.json')
            or report['abi_sha256']!=context.identity()['abi_sha256'] or report['physics_released']):
        raise ValueError('PI preparation dependency/identity/release drift')
    for key in ('new_gazebo_launches','new_physics_steps','actor_loads','optimizer_updates',
                'training_transitions','hardware_actions'):
        if report[key]!=0:raise ValueError('Offline qualification contains runtime work: '+key)
    if report['benefit_verified'] or report['candidate_ki_response_identified'] or report['old_checkpoint_compatible']:
        raise ValueError('Software fixture cannot establish physical benefit or checkpoint compatibility')
    context.require_identity(context.benchmark.read(output/'identity.json'))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(args.output)
    print(json.dumps(dict(status=result['status'],output=str(args.output),physics=0,training=0),indent=2))


if __name__=='__main__':main()
