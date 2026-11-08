"""Real old/new PI kernels on identical synthetic clocks/feedback; no ROS init."""
from types import SimpleNamespace
import math
from nino_control.control_timing import ControlTimingWindow
from nino_control.effort_drive import EffortDrive
from .gain_effort_drive import GainEffortDrive
from .gain_reference_map import target_map


class Sink:
    def __init__(self):self.rows=[]
    def publish(self,message):
        self.rows.append(dict(fields=[d.label for d in message.layout.dim],data=list(message.data)))


def fixture(gain):
    f=SimpleNamespace(now_ns=1_000_000_000,last_control_ns=998_000_000,
        control_timing=ControlTimingWindow(),wheel_state_stamp_ns=1_000_000_000,
        accept_torque=False,last_torque_ns=0,torque_timeout=.25,
        control_rate=500.,have_wheel_state=True,accept_cmd_vel=True,
        last_cmd_ns=1_000_000_000,command_timeout=.5,requested_linear=0.,requested_angular=0.,
        v2_active=False,speed_scale=1.,filtered_speed_scale=1.,
        pi_integrator_profile='conditional_v1',error_integral=[0.,0.],
        wheel_radius=.0625,wheel_separation=.34273666,max_wheel_acceleration=12.,
        max_wheel_speed=12.,target_velocity=[0.,0.],wheel_velocity=[0.,0.],
        kp=.3,ki=.1,integral_limit=4.,max_velocity_torque=4.,override_torque=[0.,0.],
        applied_effort=[0.,0.],max_torque=4.,max_effort_rate=10.,
        effort_publisher=Sink(),applied_torque_publisher=Sink(),diagnostic_publisher=Sink(),
        gain_publisher=Sink(),torque_status_publish_rate=50.,last_torque_status_publish_ns=0,
        x=0.,y=0.,yaw=0.,odom_publish_rate=50.,last_odom_publish_ns=0,
        sim_common_gain=gain,last_gain_map=None,gain_map_calls=0,odom=[])
    f.get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=f.now_ns))
    f._publish_odometry=lambda stamp,v,w:f.odom.append([stamp.nanoseconds,v,w])
    def targets(v,w,r,b):
        result,f.last_gain_map=target_map(v,w,r,b,gain);f.gain_map_calls+=1
        return result
    f.gain_target_map=targets
    return f


def snapshot(f):
    return dict(target=list(f.target_velocity),integral=list(f.error_integral),
        applied=list(f.applied_effort),pose=[f.x,f.y,f.yaw],
        effort=f.effort_publisher.rows[-1],diagnostics=list(f.diagnostic_publisher.rows),odom=list(f.odom))


def input_frame(f,index):
    f.now_ns=1_000_000_000+index*2_000_000;f.wheel_state_stamp_ns=f.now_ns
    f.have_wheel_state=not 300<=index<340
    # This is held feedback, not a dynamics model or response claim.
    f.wheel_velocity=[3.*math.sin(index/90.),2.8*math.sin(index/90.+.1)]
    if 700<=index<740:f.wheel_velocity=[14.,14.]
    if not 600<=index<1000:
        f.last_cmd_ns=f.now_ns
        f.requested_linear=(0. if index<100 or index>=1100 else .2 if index<340 else -.2 if index<500 else 0. if index<600 else 2.)
        f.requested_angular=0. if index<100 or index>=1100 else .1 if index<340 else -.1 if index<500 else .3 if index<600 else 0.


def driver_parity():
    old=fixture(1.);new={g:fixture(g) for g in (.98,1.,1.02)}
    counts={str(g):0 for g in new};trace=[]
    for i in range(1200):
        input_frame(old,i);EffortDrive._control_update(old)
        for gain,f in new.items():
            before=f.applied_effort.copy();input_frame(f,i);GainEffortDrive._control_update(f)
            if f.have_wheel_state:
                if f.gain_map_calls!=1:raise ValueError('Map applied more than once or missing')
            elif f.gain_map_calls!=0:raise ValueError('Map ran without wheel state')
            if max(map(abs,f.target_velocity))>12.+1e-12 or max(map(abs,f.applied_effort))>4.+1e-12:
                raise ValueError('Frozen drive limits not retained')
            if max(abs(a-b) for a,b in zip(before,f.applied_effort))>.020000001:
                raise ValueError('Frozen effort slew not retained')
            counts[str(gain)]+=1
        if snapshot(old)!=snapshot(new[1.]):raise ValueError('Gain-one changed frozen driver behavior')
        trace.append(dict(index=i,sim_fixture_s=old.now_ns*1e-9,legacy_applied=old.applied_effort.copy(),
            gain_one_applied=new[1.].applied_effort.copy(),gain_one_targets=new[1.].target_velocity.copy(),
            gain_map_calls=new[1.].gain_map_calls,command_fresh=(old.now_ns-old.last_cmd_ns)*1e-9<=.5))
    return dict(gain_one_exact_state_effort_diagnostics_odometry_parity=True,
        synthetic_kernel_callbacks=4800,gain_callbacks=counts,old_callbacks=1200,
        no_ros_init=True,gazebo_launches=0,hardware_actions=0,
        missing_feedback_and_watchdog_included=True,speed_ramp_torque_slew_retained=True),trace
