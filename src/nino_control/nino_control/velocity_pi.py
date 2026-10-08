"""Bounded wheel-speed PI integration without a steady-speed integral leak."""

from nino_control.kinematics import clamp


def conditional_integral(integral, error, dt, kp, ki, integral_limit, torque_limit):
    """Freeze accumulation into saturation; allow error to unwind it.

    The limit applies to the PI contribution, before any RL residual. Final
    motor torque, acceleration and slew limits remain in the drive adapter.
    """
    candidate = clamp(integral + error * dt, -integral_limit, integral_limit)
    effort = kp * error + ki * candidate
    if (effort > torque_limit and error > 0.) or (effort < -torque_limit and error < 0.):
        return integral
    return candidate
