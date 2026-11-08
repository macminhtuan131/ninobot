"""Versioned frozen PI kernel copy: only the wheel-target map call changes.

Parity tests compare the AST to the unchanged source and run both kernels.
"""
from nino_control.effort_drive import (clamp,conditional_integral,limit_effort_commands,
    Float64MultiArray,MultiArrayDimension,integrate_wheel_odometry)

def gain_control_update(self) -> None:
    """Run baseline velocity PI control and add fresh RL residual torque."""
    now = self.get_clock().now()
    now_ns = now.nanoseconds

    dt = (now_ns - self.last_control_ns) * 1.0e-9
    self.control_timing.observe(dt,(now_ns-self.wheel_state_stamp_ns)*1.e-9
        if self.wheel_state_stamp_ns is not None else None)
    self.last_control_ns = now_ns

    if dt <= 0.0 or dt > 0.25:
        dt = 1.0 / self.control_rate

    # ---------------------------------------------------------
    # Is the RL residual torque command fresh?
    # ---------------------------------------------------------
    residual_torque_active = (
        self.accept_torque
        and self.last_torque_ns > 0
        and (now_ns - self.last_torque_ns) * 1.0e-9
        <= self.torque_timeout
    )
    linear = angular = 0.0
    command_is_fresh = False
    base_efforts = [0.0, 0.0]

    # ---------------------------------------------------------
    # Without wheel feedback, do not drive the robot.
    # ---------------------------------------------------------
    if not self.have_wheel_state:
        efforts = [0.0, 0.0]

    else:
        # -----------------------------------------------------
        # 1. Nav2 baseline controller
        # -----------------------------------------------------
        command_is_fresh = (
            self.accept_cmd_vel
            and self.last_cmd_ns > 0
            and (now_ns - self.last_cmd_ns) * 1.0e-9
            <= self.command_timeout
        )

        linear = (
            self.requested_linear
            if command_is_fresh
            else 0.0
        )
        angular = (
            self.requested_angular
            if command_is_fresh
            else 0.0
        )

        if self.v2_active:
            # A lost policy heartbeat stops the reference, never resumes
            # full-speed baseline. Reset service releases v2 ownership.
            scale = self.speed_scale if residual_torque_active else 0.0
            # Preserve in-place Nav2 turns except explicit stop/watchdog.
            if abs(linear) < 1e-6 and abs(angular) > 1e-6 and scale > 0.0:
                scale = max(scale, 0.25)
            if scale == 0.0:
                self.filtered_speed_scale = 0.0
            else:
                self.filtered_speed_scale += clamp(
                    scale - self.filtered_speed_scale, -2.0 * dt, 2.0 * dt)
            linear *= self.filtered_speed_scale
            angular *= self.filtered_speed_scale
            if self.filtered_speed_scale < 1.0 and self.pi_integrator_profile == "legacy":
                # Bleed accumulated PI torque while the policy slows down.
                self.error_integral = [i * max(0.0, 1.0 - 5.0 * dt)
                                       for i in self.error_integral]

        if (
            abs(linear) < 1.0e-9
            and abs(angular) < 1.0e-9
        ):
            # Do not let stored integral torque push the robot
            # after Nav2 stops or the command becomes stale.
            self.error_integral = [0.0, 0.0]

        requested_targets = self.gain_target_map(
            linear,
            angular,
            self.wheel_radius,
            self.wheel_separation,
        )

        max_step = self.max_wheel_acceleration * dt
        base_efforts = []

        for index, requested in enumerate(
            requested_targets
        ):
            requested = clamp(
                requested,
                -self.max_wheel_speed,
                self.max_wheel_speed,
            )

            delta = clamp(
                requested - self.target_velocity[index],
                -max_step,
                max_step,
            )

            self.target_velocity[index] += delta

            error = (
                self.target_velocity[index]
                - self.wheel_velocity[index]
            )

            if self.pi_integrator_profile == "conditional_v1":
                self.error_integral[index] = conditional_integral(
                    self.error_integral[index], error, dt, self.kp, self.ki,
                    self.integral_limit, self.max_velocity_torque)
            else:
                self.error_integral[index] = clamp(
                    self.error_integral[index] + error * dt,
                    -self.integral_limit, self.integral_limit)

            effort = (
                self.kp * error
                + self.ki * self.error_integral[index]
            )

            base_efforts.append(
                clamp(
                    effort,
                    -self.max_velocity_torque,
                    self.max_velocity_torque,
                )
            )

        # -----------------------------------------------------
        # 2. RL residual torque
        #
        # tau_motor = tau_nav2_baseline + delta_tau_RL
        # -----------------------------------------------------
        nav_is_commanding_motion = (
            command_is_fresh
            and (
                abs(linear) > 1.0e-6
                or abs(angular) > 1.0e-6
            )
        )

        if (
            residual_torque_active
            and nav_is_commanding_motion
        ):
            efforts = [
                base_efforts[0]
                + self.override_torque[0],
                base_efforts[1]
                + self.override_torque[1],
            ]
        else:
            efforts = base_efforts

    # ---------------------------------------------------------
    # Final torque/rate/speed safety limits
    # ---------------------------------------------------------
    requested_efforts = list(efforts)
    efforts = limit_effort_commands(
        efforts,
        self.applied_effort,
        self.wheel_velocity,
        dt,
        self.max_torque,
        self.max_effort_rate,
        self.max_wheel_speed,
    )

    self.applied_effort = efforts

    # ---------------------------------------------------------
    # Publish wheel torque
    # ---------------------------------------------------------
    command = Float64MultiArray()
    command.data = efforts
    self.effort_publisher.publish(command)

    torque_status_period_ns = int(
        1.0e9 / self.torque_status_publish_rate
    )

    if (
        now_ns - self.last_torque_status_publish_ns
        >= torque_status_period_ns
    ):
        self.applied_torque_publisher.publish(command)
        fields = (
            "sim_time_s", "requested_linear_m_s", "requested_yaw_rad_s",
            "executed_linear_m_s", "executed_yaw_rad_s", "speed_scale",
            "filtered_speed_scale", "left_target_rad_s", "right_target_rad_s",
            "left_actual_rad_s", "right_actual_rad_s", "left_pi_nm", "right_pi_nm",
            "left_residual_nm", "right_residual_nm", "left_requested_effort_nm",
            "right_requested_effort_nm", "left_applied_nm", "right_applied_nm",
            "left_limited", "right_limited", "cmd_fresh", "policy_fresh",
            "have_wheel_state")
        timing=self.control_timing.take()
        timing.update(control_configured_period_s=1./self.control_rate,
                      command_received_sim_s=self.last_cmd_ns*1.e-9)
        fields=(*fields,*timing)
        diagnostic = Float64MultiArray()
        diagnostic.layout.dim = [MultiArrayDimension(
            label=",".join(fields), size=len(fields), stride=len(fields))]
        diagnostic.data = [float(value) for value in (
            now_ns * 1e-9, self.requested_linear, self.requested_angular,
            linear, angular, self.speed_scale, self.filtered_speed_scale,
            *self.target_velocity, *self.wheel_velocity, *base_efforts,
            *self.override_torque, *requested_efforts, *efforts,
            abs(requested_efforts[0] - efforts[0]) > 1e-9,
            abs(requested_efforts[1] - efforts[1]) > 1e-9,
            command_is_fresh, residual_torque_active, self.have_wheel_state,*timing.values())]
        self.diagnostic_publisher.publish(diagnostic)
        self.last_torque_status_publish_ns = now_ns

    # ---------------------------------------------------------
    # Wheel odometry
    # ---------------------------------------------------------
    if self.have_wheel_state:
        (
            self.x,
            self.y,
            self.yaw,
            odom_linear,
            odom_angular,
        ) = integrate_wheel_odometry(
            self.x,
            self.y,
            self.yaw,
            self.wheel_velocity[0],
            self.wheel_velocity[1],
            self.wheel_radius,
            self.wheel_separation,
            dt,
        )

        odom_period_ns = int(
            1.0e9 / self.odom_publish_rate
        )

        if (
            now_ns - self.last_odom_publish_ns
            >= odom_period_ns
        ):
            self._publish_odometry(
                now,
                odom_linear,
                odom_angular,
            )
            self.last_odom_publish_ns = now_ns
