"""Timestamp-aligned encoder/IMU odometry, independent of ROS and ground truth."""
from bisect import bisect_right
from collections import deque
from math import atan2, cos, isfinite, sin
from random import Random


def wrap(value):
    return atan2(sin(value), cos(value))


class ImuEncoderOdometry:
    def __init__(self, config):
        self.radius = float(config.get('wheel_radius_m', .0625))
        self.pitch_projection = bool(config.get('pitch_projection', True))
        self.imu_gap = float(config.get('max_imu_gap_seconds', .10))
        self.encoder_gap = float(config.get('max_encoder_gap_seconds', .25))
        self.delay = float(config.get('imu_delay_seconds', 0.))
        self.yaw_noise = float(config.get('imu_yaw_noise_std_rad', 0.))
        self.pitch_noise = float(config.get('imu_pitch_noise_std_rad', 0.))
        if any(not isfinite(v) or v <= 0 for v in (self.radius, self.imu_gap, self.encoder_gap)):
            raise ValueError('Assisted odometry requires positive finite radius and gap limits')
        if any(not isfinite(v) or v < 0 for v in (self.delay, self.yaw_noise, self.pitch_noise)):
            raise ValueError('Assisted odometry perturbations must be finite and nonnegative')
        self.rng = Random(int(config.get('noise_seed', 42)))
        self.reset()

    def reset(self, min_stamp=-float('inf')):
        self.min_stamp = min_stamp
        self.imus = deque()
        self.joints = deque()
        self.latest_joint = -float('inf')
        self.last_joint = None
        self.anchor_yaw = None
        self.x = self.y = self.yaw = self.velocity = self.yaw_rate = 0.
        self.stamp = -float('inf')

    @property
    def ready(self):
        return self.last_joint is not None

    def add_imu(self, stamp, yaw, pitch):
        if not all(isfinite(v) for v in (stamp, yaw, pitch)):
            raise ValueError('Invalid assisted odometry IMU measurement')
        if stamp <= self.min_stamp or (self.imus and stamp <= self.imus[-1][0]):
            return
        yaw = wrap(yaw + self.rng.gauss(0., self.yaw_noise))
        pitch += self.rng.gauss(0., self.pitch_noise)
        self.imus.append((stamp, yaw, pitch))
        self._drain()
        # Keep a bounded history plus one interpolation predecessor.
        while len(self.imus) > 2 and self.imus[1][0] < stamp - max(1., self.delay + .5):
            self.imus.popleft()

    def add_joint(self, stamp, left_position, right_position):
        if not all(isfinite(v) for v in (stamp, left_position, right_position)):
            raise ValueError('Invalid assisted odometry encoder measurement')
        if stamp <= self.min_stamp or stamp <= self.latest_joint:
            return
        self.latest_joint = stamp
        self.joints.append((stamp, left_position, right_position))
        if len(self.joints) > 4096:
            raise RuntimeError('Assisted odometry IMU backlog exceeded its bound')
        self._drain()

    def _drain(self):
        if not self.imus:
            return
        available = [row for row in self.imus if row[0] <= self.imus[-1][0] - self.delay + 1e-9]
        if not available:
            return
        times = [row[0] for row in available]
        while self.joints and self.joints[0][0] <= times[-1] + 1e-9:
            joint = self.joints.popleft()
            stamp, left, right = joint
            if stamp < times[0] - 1e-9:
                continue
            index = max(0, bisect_right(times, stamp + 1e-9) - 1)
            a = available[index]
            if abs(stamp - a[0]) <= 1e-9:
                yaw, pitch = a[1:]
            else:
                b = available[index + 1]
                if b[0] - a[0] > self.imu_gap + 1e-9:
                    raise RuntimeError('Assisted odometry cannot interpolate across an IMU gap')
                f = (stamp - a[0]) / (b[0] - a[0])
                yaw = wrap(a[1] + f * wrap(b[1] - a[1]))
                pitch = a[2] + f * (b[2] - a[2])
            if self.anchor_yaw is None:
                self.anchor_yaw = yaw
            heading = wrap(yaw - self.anchor_yaw)
            if self.last_joint is not None:
                dt = stamp - self.stamp
                if dt > self.encoder_gap + 1e-9:
                    raise RuntimeError('Assisted odometry encoder gap exceeded its bound')
                distance = .5 * self.radius * ((left - self.last_joint[1]) + (right - self.last_joint[2]))
                turn = wrap(heading - self.yaw)
                midpoint = self.yaw + .5 * turn
                if self.pitch_projection:
                    distance *= cos(.5 * (pitch + self.last_pitch))
                self.x += distance * cos(midpoint)
                self.y += distance * sin(midpoint)
                self.velocity = distance / dt
                self.yaw_rate = turn / dt
            self.yaw, self.last_pitch = heading, pitch
            self.stamp, self.last_joint = stamp, joint

    def pose(self):
        if not self.ready:
            raise RuntimeError('No synchronized encoder/IMU odometry after reset')
        return dict(x=self.x, y=self.y, yaw=self.yaw, linear_velocity=self.velocity,
                    yaw_rate=self.yaw_rate, odom_stamp_s=self.stamp)
