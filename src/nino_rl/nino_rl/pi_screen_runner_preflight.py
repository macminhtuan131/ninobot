"""Exercise the complete four-cell coordinator on synthetic interfaces only.

No ROS init/physics. Metrics/closure are mocked explicitly; fixture outcomes
cannot establish either Ki's plant response or observer/launch integration.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
from . import pi_screen_runner as job
from . import pi_screen_preflight as software
from .residual_workflow import save


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
        self.current=software.fixture_backend(c)
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


def run(output):
    from contextlib import ExitStack
    dependencies=job.source(False);current=job.fingerprint()
    output=Path(output).expanduser().resolve();output.mkdir(parents=True,exist_ok=False)
    instances=[]
    try:
        save(output/'protocol.json',job.protocol());save(output/'dependencies.json',dependencies)
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
            raise ValueError('PI runner sources/dependencies drifted during preflight')
        report=dict(status='offline_PI_runner_qualified_not_physics_released',
            fingerprint=current,protocol_sha256=job.parent.sha(job.parent.frozen.repo()/'src/nino_rl/config/sim_pi_screen_protocol_v1.json'),
            synthetic_cells=4,synthetic_decisions=560,synthetic_backend_closures=4,
            synthetic_comparison=result['comparison']['decision'],
            summary_timing_closure_are_synthetic=True,Ki_plant_response_modeled=False,
            source_entry_and_install_checked=True,new_Gazebo_launches=0,new_physics_steps=0,
            actor_loads=0,training_transitions=0,optimizer_updates=0,hardware_actions=0,
            physics_released=False,benefit_verified=False,
            remaining_gate='separate review/release of four-cell screen; no automatic training or hardware')
        save(output/'qualification.json',report)
        save(output/'manifest.json',dict(fingerprint=current,status='completed',
            files={str(f.relative_to(output)):job.parent.sha(f) for f in output.rglob('*') if f.is_file()}))
        return report
    except BaseException as exc:
        save(output/'failure.json',dict(error=repr(exc),retain=True,physics=0,training=0));raise


def verified_report(output):
    output=Path(output).resolve();m=job.parent.read(output/'manifest.json')
    if m['status']!='completed' or m['fingerprint']!=job.fingerprint():
        raise ValueError('PI runner offline sources/completion changed')
    files={str(f.relative_to(output)) for f in output.rglob('*') if f.is_file() and f.name!='manifest.json'}
    if files!=set(m['files']) or not {'qualification.json','evaluation_result.json','protocol.json','dependencies.json'}<=files:
        raise ValueError('PI runner offline inventory changed')
    for name,value in m['files'].items():
        path=(output/name).resolve()
        if not path.is_relative_to(output) or job.parent.sha(path)!=value:
            raise ValueError('PI runner offline artifact changed')
    r=job.parent.read(output/'qualification.json')
    if job.parent.read(output/'dependencies.json')!=job.source(False):
        raise ValueError('PI runner offline dependencies changed')
    if (r['fingerprint']!=job.fingerprint() or r['physics_released'] or r['benefit_verified']
            or r['synthetic_cells']!=4 or r['synthetic_decisions']!=560
            or not r['summary_timing_closure_are_synthetic'] or r['Ki_plant_response_modeled']):
        raise ValueError('PI runner fixture scope drift')
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
    result=run(parser.parse_args().output)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
