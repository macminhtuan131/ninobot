"""Opt-in 20 ms governor inside the unchanged 100 ms evaluator interval.

Only the motion reference is updated at sub-boundaries. This module never
increments score counters, integrates a reward, changes physics, or reads GT
or contact identity for a decision. No ROS import until publishing a message.
"""
from bisect import bisect_right
from math import isclose, isfinite

from nino_rl.governor_adapter import frame_from_state

KEYS = ("phase", "scale", "events", "armed", "hold_seconds", "quiet_seconds", "fault",
        "disturbed", "trigger_ratio", "filtered_vertical_m_s2", "wheel_error_m_s",
        "wheel_error_threshold_m_s", "target_scale", "wheel_stall_seconds",
        "elapsed_seconds", "trigger_elapsed_s", "brake_onset_elapsed_s", "delay_remaining_seconds")


def validate_settings(config):
    c = config["governor"]["cadence_experiment"]
    expected = dict(enabled=True, update_seconds=.02, imu_window_seconds=.1,
                    target_acceleration_window_seconds=.1, scoring_seconds=.1)
    if c != expected or config["control_hz"] != 10. or config["governor"].get("world_chunk_seconds") != .02:
        raise ValueError("Cadence experiment requires 20ms updates and fixed100ms windows/scoring")
    if (not config.get("evaluation_baseline") or not config["governor"].get("enabled")
            or config["governor"]["parameters"]["profile"] != "reactive"
            or config["policy_v2"].get("require_terrain_preview", False)
            or not config["policy_v2"].get("imu_strict_coverage")
            or config["domain_randomization"].get("enabled")):
        raise ValueError("Cadence experiment is strict sensor-only PI evaluation, no preview/randomization")
    if not isclose(config["policy_v2"]["simulation_physics_step_seconds"], .001):
        raise ValueError("Keep the 1ms physical integration step")
    return c


def chunk_steps(advanced_s, requested_steps, physics_dt=.001, period=.02):
    """Split existing world transactions only; never add physics or score steps."""
    count = int(round(advanced_s / physics_dt))
    period_steps = int(round(period / physics_dt))
    if (not isclose(count * physics_dt, advanced_s, abs_tol=1e-8)
            or not isclose(period_steps * physics_dt, period, abs_tol=1e-8)
            or requested_steps < 1):
        raise ValueError("Nonintegral/missing cadence physics support")
    return min(requested_steps, period_steps-count % period_steps)


class GovernorCadence:
    def __init__(self, env):
        self.env = env
        self.settings = validate_settings(env.config)
        self.reset()

    def reset(self):
        self.history = []
        self.updates = []
        self.first_time = None
        self.epoch = None
        self.reference = None
        self.last_command_time = None

    def begin(self, linear, angular, now):
        self.reference = (linear, angular)  # follower remains at100ms in all arms
        self.updates = []
        self.outer_start = now
        if self.first_time is None:
            self.first_time = now
        value = self.command(now)
        # Keep coarse control_trace's original start-boundary semantics. Full
        # intermediate commands go to their own CSV, never replace native rows.
        self.env.governor_trace = dict(self.updates[0])
        return value

    def chunk(self, advanced, requested, physics_dt):
        return chunk_steps(advanced, requested, physics_dt, self.settings["update_seconds"])

    def boundary(self, now, advanced):
        if advanced >= self.env.control_dt-1e-8:
            if not isclose(advanced, self.env.control_dt, abs_tol=1e-8):
                raise RuntimeError("Cadence cannot extend the scoring interval")
            return
        ticks = advanced / self.settings["update_seconds"]
        if not isclose(ticks, round(ticks), abs_tol=1e-7):
            return
        linear, angular, _ = self.command(now)
        self.env.ros.publish_motion_command(linear, angular)

    def command(self, now):
        e, ros, c = self.env, self.env.ros, self.settings
        p = e.config["policy_v2"]
        timeout = p.get("sensor_wait_timeout_seconds", 2.)
        if self.last_command_time is not None and not isclose(now-self.last_command_time, .02, abs_tol=1e-8):
            raise RuntimeError("Skipped/duplicate governor tick")
        try:
            ros.wait_for_motion_state(now, timeout=timeout, max_lag=p.get("motion_max_lag_seconds", .04))
            rows = ros.wait_for_drive_diagnostics(now-.1, now, timeout=timeout)
            feedback = rows[-1]
            sensor = ros.snapshot()
            stamps = (sensor.imu_stamp_s, sensor.joint_stamp_s, feedback["sim_time_s"])
            if any(not isfinite(t) or t > now+1e-9 or now-t > .1+1e-9 for t in stamps):
                raise RuntimeError("Stale/future hardware feedback")
            imu = ({} if now == self.first_time else ros.wait_for_impact(now-.1, now,
                   e.config["reward_v2"]["impact_acceleration_sigma_m_s2"],
                   p.get("imu_wait_timeout_seconds", .5), p.get("imu_min_coverage", .8),
                   p.get("imu_max_latest_lag_seconds", .1)))
            targets = (feedback["left_target_rad_s"], feedback["right_target_rad_s"])
            old = bisect_right([t for t,_ in self.history], now-.1+1e-9)-1
            support = self.history[old] if old >= 0 else None
            # Initialization lasts <100ms, well before fixed800ms startup.
            # It is explicitly marked, never passed off as a measured zero.
            if support is None and now-self.first_time > .1+1e-8:
                raise RuntimeError("Missing fixed100ms target history")
            accel = (max(abs(a-b) for a,b in zip(targets,support[1])) * e.governor.settings.wheel_radius_m/.1
                     if support else 0.)
            self.history.append((now, targets))
            self.history = [(t,v) for t,v in self.history if t >= now-.3]
            decision = e.governor.update(frame_from_state(sensor, feedback, imu, ros.imu_includes_gravity),
                .02, *self.reference, fresh=feedback.get("have_wheel_state", 0.) > .5,
                target_acceleration_m_s2=accel)
        except BaseException:
            ros.publish_motion_command(0., 0.)
            raise  # no extra world steps, retry or stale fallback
        if self.epoch is None:
            self.epoch = now-e.governor.elapsed
        trace = {"governor_"+k: decision.get(k) for k in KEYS}
        for event in ("trigger", "brake_onset"):
            t = decision.get(event+"_elapsed_s")
            trace["governor_"+event+"_time_s"] = self.epoch+t if t is not None else None
        trace.update(governor_input_time_s=now,
                     governor_requested_linear_m_s=self.reference[0], governor_requested_yaw_rad_s=self.reference[1],
                     governor_feedback_stamp_s=feedback["sim_time_s"], governor_feedback_age_s=now-feedback["sim_time_s"],
                     cadence_update_seconds=.02, imu_window_start_s=now-.1, imu_window_end_s=now,
                     imu_window_bootstrap=now == self.first_time,
                     target_history_ready=support is not None,
                     target_history_support_s=support[0] if support else None,
                     target_acceleration_window_seconds=.1,
                     target_acceleration_m_s2=accel,
                     imu_stamp_s=sensor.imu_stamp_s, joint_stamp_s=sensor.joint_stamp_s)
        self.updates.append(trace)
        self.last_command_time = now
        e.governor_reference_sim_s = now
        linear, angular = (x*decision["scale"] for x in self.reference)
        payload = dict(time_s=now, governed_linear_m_s=linear, governed_yaw_rad_s=angular, **trace)
        if hasattr(e, "cadence_emit"):  # injected offline sink, no physics
            e.cadence_emit(payload)
        else:
            import json
            from std_msgs.msg import String
            e.governor_state_publisher.publish(String(data=json.dumps(payload, allow_nan=False)))
        return linear, angular, decision["scale"]
