"""Offline-prepared PI contrast. No physics, learner or hardware release."""
import math

CONTEXT_ID='nino_sim_pi_screen_context_v1_2026_11_07'
SUPPORTED_KI=(.10,.15)


def require_ki(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or value not in SUPPORTED_KI:
        raise ValueError('PI screen accepts exactly Ki 0.10 or 0.15')
    return float(value)


def expected_parameters(ki):
    return dict(accept_torque=False,accept_cmd_vel=True,use_sim_time=True,
        pi_integrator_profile='conditional_v1',wheel_radius=.0625,wheel_separation=.34273666,
        control_rate=500.,velocity_kp=.3,velocity_ki=require_ki(ki),
        max_wheel_torque=4.,max_velocity_control_torque=4.,max_effort_rate=10.,
        max_wheel_acceleration=12.,max_wheel_speed=12.,sim_common_gain=1.,integral_limit=4.,
        command_timeout=.5,torque_command_timeout=.25,odom_publish_rate=50.,torque_status_publish_rate=50.)


def require_parameters(actual,ki):
    expected=expected_parameters(ki)
    if set(actual)!=set(expected):raise ValueError('PI screen parameter schema mismatch')
    for key,value in expected.items():
        got=actual[key]
        if isinstance(value,(bool,str)):
            valid=type(got) is type(value) and got==value
        else:
            valid=(not isinstance(got,bool) and isinstance(got,(int,float))
                and math.isfinite(got) and got==value)
        if not valid:raise ValueError('PI screen parameter readback mismatch: '+key)
    return actual


def require_simulation_environment(environment):
    if (environment.get('ROS_DOMAIN_ID')!='129'
            or environment.get('NINO_ROS_DOMAIN_ID')!='129'
            or environment.get('NINO_SIM_PI_SCREEN_CONTEXT')!=CONTEXT_ID
            or environment.get('ROS_AUTOMATIC_DISCOVERY_RANGE')!='LOCALHOST'
            or not environment.get('GZ_PARTITION','').startswith('nino_factory_td3_')):
        raise ValueError('PI screen requires isolated simulation context/domain/partition')


def runtime_audit(driver):
    """Report cached values actually used by the kernel, never requested condition."""
    return dict(sim_time_s=driver.last_control_ns*1e-9,velocity_kp=driver.kp,velocity_ki=driver.ki,
        control_rate=driver.control_rate,max_wheel_torque=driver.max_torque,
        max_velocity_control_torque=driver.max_velocity_torque,max_effort_rate=driver.max_effort_rate,
        max_wheel_acceleration=driver.max_wheel_acceleration,max_wheel_speed=driver.max_wheel_speed,
        common_gain=driver.sim_common_gain,wheel_radius=driver.wheel_radius,wheel_separation=driver.wheel_separation)


def require_audit(audit,ki):
    expected=expected_parameters(ki)
    fields=dict(velocity_kp='velocity_kp',velocity_ki='velocity_ki',control_rate='control_rate',
        max_wheel_torque='max_wheel_torque',max_velocity_control_torque='max_velocity_control_torque',
        max_effort_rate='max_effort_rate',max_wheel_acceleration='max_wheel_acceleration',
        max_wheel_speed='max_wheel_speed',common_gain='sim_common_gain',wheel_radius='wheel_radius',
        wheel_separation='wheel_separation')
    if set(audit)!=set(fields)|{'sim_time_s'}:raise ValueError('PI audit schema mismatch')
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
               for v in audit.values()):raise ValueError('Nonfinite PI audit')
    for key,param in fields.items():
        if audit[key]!=expected[param]:raise ValueError('PI audit mismatch: '+key)
    return audit
