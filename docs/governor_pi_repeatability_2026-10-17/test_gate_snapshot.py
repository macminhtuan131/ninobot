from types import SimpleNamespace
from dataclasses import replace
import json

import pytest

from nino_rl.reset_standstill import StandstillGate,ResetReadinessError,run_gate
from nino_rl.core import RobotState
from nino_rl.ros_interface import RosRobotInterface


def sample(t,boundary=10.):
    return dict(time_s=t,v_m_s=0.,yaw_rate_rad_s=0.,left_wheel_m_s=0.,right_wheel_m_s=0.,
        command_v=0.,command_w=0.,executed_v=0.,executed_w=0.,feedback_stamp_s=t-.001,
        ground_stamp_s=t-.001,joint_stamp_s=t-.001,imu_stamp_s=t-.001,odom_stamp_s=t-.001,have_wheel_state=1.)


@pytest.mark.parametrize("key,value",[("ground_stamp_s",10.),("joint_stamp_s",10.),
    ("imu_stamp_s",10.03),("feedback_stamp_s",9.9),("v_m_s",float("nan")),
    ("command_v",.1),("executed_v",.1),("have_wheel_state",0.)])
def test_bad_feedback_never_contributes_to_quiet_window(key,value):
    gate=StandstillGate(10.)
    s=sample(10.02);s[key]=value
    with pytest.raises(ResetReadinessError):gate.update(s)
    assert not gate.samples


def test_motion_restarts_quiet_duration_not_the_reset_transaction():
    gate=StandstillGate(10.)
    for i in range(1,11):assert not gate.update(sample(10.+i*.02))
    moving=sample(10.22);moving["left_wheel_m_s"]=.02
    assert not gate.update(moving) and gate.quiet_start is None
    for i in range(12,37):assert not gate.update(sample(10.+i*.02))
    assert gate.update(sample(10.74))
    assert gate.quiet_start==pytest.approx(10.24)


class FakeRos:
    physics_step_seconds=.001
    def __init__(self,mode="quiet"):
        self.t=10.;self.mode=mode;self.steps=0;self.commands=[]
    def publish_straight_command(self,v):self.commands.append(v)
    def publish_control(self,*args):pass
    def advance_world(self,n,**kwargs):
        assert n==20 and kwargs["min_completion_fraction"]==1.
        self.t+=.02;self.steps+=1
    def wait_for_clock_quiescence(self,**kwargs):return self.t
    def wait_for_motion_state(self,*args,**kwargs):pass
    def post_reset_standstill_sample(self,boundary,end,**kwargs):
        if self.mode=="missing":raise TimeoutError("no drive feedback")
        s=sample(end)
        if self.mode=="moving":s["v_m_s"]=.02
        return s


def test_lockstep_gate_releases_only_after_continuous_half_second():
    ros=FakeRos();reports=[]
    release=run_gate(ros,10.,1.,1.,reports.append)
    assert release==pytest.approx(10.52)
    assert ros.steps==26 and all(v==0. for v in ros.commands)
    assert reports[-1]["passed"] and reports[-1]["reset_retries"]==0


@pytest.mark.parametrize("mode,steps",[("moving",250),("missing",1)])
def test_bounded_failure_preserves_report_without_retry(mode,steps):
    ros=FakeRos(mode);reports=[]
    with pytest.raises((ResetReadinessError,TimeoutError)):
        run_gate(ros,10.,1.,1.,reports.append)
    assert ros.steps==steps and reports[-1]["status"]=="failed"
    assert reports[-1]["wait_sim_seconds"]<=5.+1e-9
    json.dumps(reports[-1],allow_nan=False)


def test_ros_snapshot_before_boundary_is_not_accepted_as_post_reset():
    state=RobotState(ground_truth_stamp_s=9.99,joint_stamp_s=10.019,imu_stamp_s=10.019,odom_stamp_s=10.019)
    ros=SimpleNamespace(snapshot=lambda:state)
    with pytest.raises(TimeoutError,match="Post-reset sensors"):
        RosRobotInterface.post_reset_standstill_sample(ros,10.,10.02,timeout=.001)
