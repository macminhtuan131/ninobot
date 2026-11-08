"""Exercise the complete four-cell coordinator on synthetic interfaces only.

No ROS init/physics. Metrics/closure are mocked explicitly; fixture outcomes
cannot establish either Ki's plant response or observer/launch integration.
"""
import argparse
from copy import deepcopy
import json
import shutil
from pathlib import Path
from unittest.mock import patch
from . import pi_stop_validation_runner as job
from .residual_workflow import save


def fixture_backend(c):
    # Unlike the frozen selection fixture (hardcoded8s), this explicitly
    # exercises the stop6 source. It is not a Ki plant-response model.
    from .gain_reference_map import target_map,map_audit
    from .pi_screen_contract import CONTEXT_ID,runtime_audit
    from .gain_drive_fixture import fixture
    backend=job.context.parent.parent.frozen.offline.fixture_backend(c,6.)
    original=backend.advance_reference
    def advance(*args,**kwargs):
        view,labels,term,trunc,info=original(*args,**kwargs)
        _,record=target_map(*info['final_ros_reference'],c['nominal_geometry']['radius_l'],
            c['nominal_geometry']['separation'],1.)
        audit=map_audit(record,stamp_s=info['sensor_clock_s'],
            targets=info['applied_target_rad_s'],max_speed=12.,calls=1)
        driver=fixture(1.);driver.ki=c['backend']['pi_ki']
        driver.last_control_ns=round(info['sensor_clock_s']*1e9)
        info.update(gain_map_audit=audit,pi_screen_context=CONTEXT_ID,
            evaluation_ki=driver.ki,pi_screen_audit=runtime_audit(driver),
            drive_diagnostics=dict(sim_time_s=info['sensor_clock_s'],
                executed_linear_m_s=info['final_ros_reference'][0],
                executed_yaw_rad_s=info['final_ros_reference'][1],
                left_applied_nm=0.,right_applied_nm=0.,
                left_target_rad_s=info['applied_target_rad_s'][0],
                right_target_rad_s=info['applied_target_rad_s'][1]),
            source_lags_s=dict(imu=0.,wheel=0.),guidance_audit=dict(fault=False),
            truth_used_for_guidance=False,fixture_only=True,
            synthetic_pi_audit=True,ki_dynamics_not_modeled=True)
        return view,labels,term,trunc,info
    backend.advance_reference=advance
    return backend


class SyntheticLifecycle:
    residual_contract_id=job.EpisodeLifecycle.residual_contract_id
    kind='synthetic_PI_runner_interface_not_Gazebo'
    calibrated_to_hardware=False
    instances=[]
    def __init__(self,c,directory,world,g,task,bc,lp,backend_factory=None):
        if backend_factory.func is not job.PiScreenBackend or backend_factory.keywords!={'allow_physics':True}:
            raise ValueError('Runner did not select the prepared PI backend')
        self.config=deepcopy(c);self.directory=Path(directory);self.directory.mkdir(parents=True)
        self.namespace=None;self.current=None;self.calls=0;self.closed=False
        self.instances.append(self)
    def reset(self,seed=None):
        self.namespace='synthetic_episode_0';(self.directory/self.namespace).mkdir()
        c=deepcopy(self.config)
        c['backend'].update(wheel_gain=[1.,1.],motor_lag_s=[.16,.16],imu_noise_std=0.)
        self.current=fixture_backend(c)
        return self.current.reset(seed=seed)
    def view(self):return deepcopy(self.current.last_view)
    def advance_reference(self,*args,**kwargs):
        self.calls+=1
        return self.current.advance_reference(*args,**kwargs)
    def __getattr__(self,name):
        current=self.__dict__.get('current')
        if current is None:raise AttributeError(name)
        return getattr(current,name)
    def close(self):
        self.closed=True
        if self.current is not None:self.current.close()


def synthetic_summary(rows,target):
    return dict(steps=len(rows),functional_proposal_pass=True,nominal_velocity_rmse_m_s=.01,
        summary_is_fixture_not_measured=True)


def synthetic_timing(*args):
    return dict(valid=True,header_grid={'0.0':dict(rmse_m_s=.01),'0.01':dict(rmse_m_s=.01)},
        timing_is_fixture_not_measured=True)


def fixture_patches():
    return (patch.object(job,'EpisodeLifecycle',SyntheticLifecycle),
        patch.object(job.parent.frozen,'prepare_worlds',lambda out:dict(clear_box='synthetic_no_world')),
        patch.object(job.parent.frozen.baseline,'summarize',synthetic_summary),
        patch.object(job.parent.frozen.timing,'timestamp_diagnostic',synthetic_timing))


def software_report(path):
    import xml.etree.ElementTree as ET
    root=ET.parse(path).getroot();suites=list(root.iter('testsuite'))
    cases=list(root.iter('testcase'))
    if (not suites or any(int(s.get(k,'0')) for s in suites for k in ('errors','failures','skipped'))
            or sum('test_pi_stop_validation_runner' in c.get('classname','') for c in cases)<15
            or sum('test_pi_stop_validation_context' in c.get('classname','') for c in cases)<12):
        raise ValueError('Complete passing validation context/runner software report required')
    return len(cases)


def run(output,test_report):
    from contextlib import ExitStack
    tests=software_report(test_report)
    dependencies=job.source(False);current=job.fingerprint()
    output=Path(output).expanduser().resolve();output.mkdir(parents=True,exist_ok=False)
    instances=[]
    try:
        shutil.copyfile(test_report,output/'software_tests.xml')
        save(output/'protocol.json',job.protocol());save(output/'dependencies.json',dependencies)
        from .pi_stop_validation_context import wrapper_parity
        parity=wrapper_parity()
        save(output/'wrapper_parity.json',parity)
        with ExitStack() as stack:
            for item in fixture_patches():stack.enter_context(item)
            stack.enter_context(patch.object(SyntheticLifecycle,'instances',instances))
            # Identity is immutable during this process; validate source again
            # after closure instead of rehashing it at every fixture reset.
            ident=job.context.identity()
            stack.enter_context(patch.object(job.context,'identity',lambda:deepcopy(ident)))
            result=job.execute(output,dependencies)
        # Separate declared physical budget from executed software decisions.
        save(output/'evaluation_result.json',dict(result,gazebo_launches=0,evaluation_transitions=0,
            synthetic_interface_only=True,synthetic_cells=4,synthetic_decisions=560,
            runner_declared_budget_counts=dict(gazebo_launches=result['gazebo_launches'],
                evaluation_transitions=result['evaluation_transitions'])))
        if len(instances)!=4 or any(not x.closed or x.calls!=140 for x in instances):
            raise ValueError('Synthetic coordinator did not close four140-decision cells')
        if job.fingerprint()!=current or job.source(False)!=dependencies:
            raise ValueError('PI stop6 validation sources/dependencies drifted during preflight')
        report=dict(status='offline_PI_stop6_validation_qualified_not_physics_released',
            fingerprint=current,protocol_sha256=job.parent.sha(job.parent.frozen.repo()/'src/nino_rl/config/sim_pi_stop_validation_protocol_v1.json'),
            synthetic_cells=4,synthetic_decisions=560,synthetic_backend_closures=4,
            synthetic_comparison=result['comparison']['decision'],
            summary_timing_closure_are_synthetic=True,Ki_plant_response_modeled=False,
            software_tests_passed=tests,wrapper_parity=parity,
            source_entry_and_install_checked=True,new_Gazebo_launches=0,new_physics_steps=0,
            actor_loads=0,training_transitions=0,optimizer_updates=0,hardware_actions=0,
            physics_released=False,benefit_verified=False,
            remaining_gate='separate review/release of four-cell stop6 validation; no automatic training or hardware')
        save(output/'qualification.json',report)
        save(output/'manifest.json',dict(fingerprint=current,status='completed',
            files={str(f.relative_to(output)):job.parent.sha(f) for f in output.rglob('*') if f.is_file()}))
        return report
    except BaseException as exc:
        save(output/'failure.json',dict(error=repr(exc),retain=True,physics=0,training=0));raise


def verified_report(output):
    output=Path(output).resolve();m=job.parent.read(output/'manifest.json')
    if m['status']!='completed' or m['fingerprint']!=job.fingerprint():
        raise ValueError('PI stop6 validation offline sources/completion changed')
    files={str(f.relative_to(output)) for f in output.rglob('*') if f.is_file() and f.name!='manifest.json'}
    if files!=set(m['files']) or not {'qualification.json','evaluation_result.json','protocol.json','dependencies.json',
            'software_tests.xml','wrapper_parity.json'}<=files:
        raise ValueError('PI stop6 validation offline inventory changed')
    for name,value in m['files'].items():
        path=(output/name).resolve()
        if not path.is_relative_to(output) or job.parent.sha(path)!=value:
            raise ValueError('PI stop6 validation offline artifact changed')
    r=job.parent.read(output/'qualification.json')
    if (software_report(output/'software_tests.xml')!=r['software_tests_passed']
            or job.parent.read(output/'wrapper_parity.json')!=r['wrapper_parity']):
        raise ValueError('Software or parity report mismatch')
    if job.parent.read(output/'dependencies.json')!=job.source(False):
        raise ValueError('PI stop6 validation offline dependencies changed')
    if (r['fingerprint']!=job.fingerprint() or r['physics_released'] or r['benefit_verified']
            or r['synthetic_cells']!=4 or r['synthetic_decisions']!=560
            or not r['summary_timing_closure_are_synthetic'] or r['Ki_plant_response_modeled']):
        raise ValueError('PI stop6 validation fixture scope drift')
    for name in ('new_Gazebo_launches','new_physics_steps','actor_loads','training_transitions','optimizer_updates','hardware_actions'):
        if r[name]!=0:raise ValueError('Offline proof cannot contain runtime work')
    if job.parent.read(output/'protocol.json')!=job.protocol():raise ValueError('PI protocol drift')
    result=job.parent.read(output/'evaluation_result.json')
    if (not result['synthetic_interface_only'] or result['gazebo_launches']!=0
            or result['evaluation_transitions']!=0 or result['synthetic_decisions']!=560):
        raise ValueError('Synthetic runner artifact cannot claim physical outcomes')
    return r


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--test-report',type=Path,required=True)
    args=parser.parse_args();result=run(args.output,args.test_report)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
