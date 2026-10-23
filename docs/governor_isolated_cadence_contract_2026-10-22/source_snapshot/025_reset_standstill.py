"""Opt-in simulation initialization gate; never a governor or scoring input."""
import math


class ResetReadinessError(RuntimeError):
    pass


class StandstillGate:
    observe_seconds=.5
    maximum_wait_seconds=5.

    def __init__(self,boundary):
        if not math.isfinite(boundary):raise ValueError("Invalid reset boundary")
        self.boundary=boundary
        self.quiet_start=None
        self.previous=None
        self.samples=[]

    def update(self,sample):
        fields=("time_s","v_m_s","yaw_rate_rad_s","left_wheel_m_s","right_wheel_m_s",
                "command_v","command_w","executed_v","executed_w","feedback_stamp_s",
                "ground_stamp_s","joint_stamp_s","imu_stamp_s","odom_stamp_s","have_wheel_state")
        if not all(k in sample and math.isfinite(sample[k]) for k in fields):
            raise ResetReadinessError("missing_or_nonfinite_feedback")
        t=sample["time_s"]
        if not self.boundary<t<=self.boundary+self.maximum_wait_seconds+1e-9:
            raise ResetReadinessError("outside_post_reset_budget")
        if self.previous is not None and not 0<t-self.previous<=.050000001:
            raise ResetReadinessError("measurement_gap_or_repeated_boundary")
        for key in ("ground_stamp_s","joint_stamp_s","imu_stamp_s","odom_stamp_s","feedback_stamp_s"):
            age=t-sample[key]
            limit=.1 if key=="feedback_stamp_s" else .04
            if sample[key]<=self.boundary or not -1e-9<=age<=limit+1e-9:
                raise ResetReadinessError("pre_reset_stale_or_future_"+key)
        if sample["have_wheel_state"]<.5:raise ResetReadinessError("missing_wheel_state")
        if any(abs(sample[k])>1e-12 for k in ("command_v","command_w","executed_v","executed_w")):
            raise ResetReadinessError("nonzero_reference_during_reset_gate")
        self.previous=t
        quiet=(max(abs(sample[k]) for k in ("v_m_s","left_wheel_m_s","right_wheel_m_s"))<=.01
               and abs(sample["yaw_rate_rad_s"])<=.03)
        if not quiet:self.quiet_start=None
        elif self.quiet_start is None:self.quiet_start=t
        elapsed=t-self.quiet_start if self.quiet_start is not None else 0.
        self.samples.append(dict(sample,quiet=quiet,quiet_seconds=elapsed))
        return quiet and elapsed>=self.observe_seconds-1e-9


def run_gate(ros,boundary,step_timeout,sensor_timeout,record):
    """Advance one request at a time; missing data aborts, never resets/retries."""
    gate=StandstillGate(boundary)
    report=dict(revision="post_reset_zero_standstill_v1",status="waiting",reset_boundary_s=boundary,
        observe_seconds=.5,maximum_wait_sim_seconds=5.,samples=gate.samples,passed=False,
        attempts=1,reset_retries=0,privileged_GT_is_initialization_diagnostic_only=True)
    record(report)
    try:
        steps=round(.02/ros.physics_step_seconds)
        if steps<1 or abs(steps*ros.physics_step_seconds-.02)>1e-9:
            raise ResetReadinessError("physics_step_cannot_represent_20ms")
        current=boundary
        for _ in range(250):
            ros.publish_straight_command(0.)
            ros.publish_control(1.,0.,0.)
            ros.advance_world(steps,timeout=step_timeout,min_completion_fraction=1.)
            end=ros.wait_for_clock_quiescence(timeout=sensor_timeout)
            if abs((end-current)-.02)>.5*ros.physics_step_seconds+1e-9:
                raise ResetReadinessError("standstill_clock_divergence")
            current=end
            ros.wait_for_motion_state(end,timeout=sensor_timeout,max_lag=.04)
            sample=ros.post_reset_standstill_sample(boundary,end,timeout=sensor_timeout)
            if gate.update(sample):
                report.update(status="passed",passed=True,released_sim_s=end,
                              wait_sim_seconds=end-boundary,quiet_start_s=gate.quiet_start)
                record(report)
                return end
        raise ResetReadinessError("not_still_within_5_sim_seconds")
    except Exception as error:
        report.update(status="failed",error=f"{type(error).__name__}: {error}",
            observed_until_s=gate.previous,wait_sim_seconds=(gate.previous-boundary) if gate.previous is not None else 0.)
        record(report)
        ros.publish_straight_command(0.)
        ros.publish_control(1.,0.,0.)
        raise
