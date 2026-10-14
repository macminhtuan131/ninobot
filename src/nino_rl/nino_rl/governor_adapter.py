"""Explicit hardware-field boundary between simulation evaluator and governor."""
from math import hypot,sqrt
from math import isfinite
from nino_control.governor_core import GovernorFrame,vertical_acceleration


def frame_from_state(state,feedback,imu,includes_gravity):
    duration=float(imu.get("duration",0.))
    return GovernorFrame(
        vertical_acceleration((state.accel_x,state.accel_y,state.accel_z),state.roll,state.pitch,includes_gravity),
        hypot(state.gyro_x,state.gyro_y),state.left_wheel_velocity,state.right_wheel_velocity,
        feedback["left_target_rad_s"],feedback["right_target_rad_s"],feedback["executed_linear_m_s"],
        sqrt(max(0.,imu.get("square_integral",0.))/duration) if duration else 0.,
        float(imu.get("peak",0.)))


def stamped_reference_valid(state,end,command_stamp,dt):
    """Paused lockstep uses measurement time, not wall time spent rendering.

    Existing world-step clock and fresh-callback barriers still apply. This
    helper is only for the new governor evaluator, never a live ROS watchdog.
    """
    return all(isfinite(stamp) and -.005<=end-stamp<=max(.10,dt+.005)
               for stamp in (state.odom_stamp_s,state.joint_stamp_s,state.imu_stamp_s,command_stamp))
