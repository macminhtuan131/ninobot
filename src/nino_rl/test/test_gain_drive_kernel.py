"""Real driver code, held synthetic feedback and no ROS init/physics."""
import math,os
from types import SimpleNamespace
import pytest
from nino_control.effort_drive import EffortDrive
from nino_rl.gain_effort_drive import GainEffortDrive,require_simulation_environment
from nino_rl.gain_reference_map import target_map,CONTEXT_ID
from nino_rl.gain_drive_fixture import fixture,driver_parity
from nino_rl.gain_context_preflight import kernel_ast_parity


def test_only_target_map_call_differs_in_pi_kernel():
    assert kernel_ast_parity()['only_one_wheel_target_map_call_changed']
    assert GainEffortDrive.stop is EffortDrive.stop


def test_gain_one_real_kernel_state_effort_diagnostics_and_watchdog_parity():
    report,trace=driver_parity()
    assert report['synthetic_kernel_callbacks']==4800 and len(trace)==1200
    assert report['gain_one_exact_state_effort_diagnostics_odometry_parity']
    assert any(not r['command_fresh'] for r in trace)
    assert any(r['gain_map_calls']==0 for r in trace)


@pytest.mark.parametrize('gain',[.98,1.,1.02])
@pytest.mark.parametrize('reference',[(0.,0.),(.2,.1),(-.2,-.1),(0.,.3)])
def test_common_map_preserves_zero_yaw_and_reverse_semantics(gain,reference):
    wheels,a=target_map(*reference,.0625,.34273666,gain)
    assert .0625*(wheels[0]+wheels[1])/2==pytest.approx(gain*reference[0])
    assert .0625*(wheels[1]-wheels[0])/.34273666==pytest.approx(reference[1])


@pytest.mark.parametrize('gain',[0.,-1.,1.1,float('nan'),True])
def test_undeclared_gain_never_becomes_a_drive_target(gain):
    with pytest.raises(ValueError):target_map(.2,0.,.0625,.34273666,gain)


def test_reset_clears_map_and_inherited_controller_state():
    # A genuine subclass instance is required for super(); __new__ avoids
    # creating a ROS node/context and the injected clock/publishers stay fake.
    template=fixture(1.02);f=object.__new__(GainEffortDrive);f.__dict__.update(template.__dict__)
    f.target_velocity=[2.,2.];f.error_integral=[1.,1.]
    f.last_gain_map={'stale':True};f.gain_map_calls=12
    response=GainEffortDrive._reset_odometry(f,None,SimpleNamespace())
    assert response.success and f.target_velocity==[0.,0.] and f.error_integral==[0.,0.]
    assert f.last_gain_map is None and f.gain_map_calls==0


def test_node_entry_requires_simulation_context_before_ros_initialization():
    with pytest.raises(ValueError,match='isolated simulation'):require_simulation_environment({})
    require_simulation_environment(dict(ROS_DOMAIN_ID='129',NINO_SIM_GAIN_CONTEXT=CONTEXT_ID,GZ_PARTITION='nino_factory_td3_fixture'))
