"""Known rectangular-wall scan correction for local encoder/IMU odometry.

Map coordinates and laser extrinsics are explicit inputs. No simulator pose,
goal location, cable placement, or ground-truth topic is used for localization.
"""
from collections import deque
from math import cos, sin
import numpy as np
from nino_rl.assisted_odometry import ImuEncoderOdometry, wrap


def wall_position(scan, pose, config):
    ranges, angle_min, increment, range_min, range_max = scan
    x, y, yaw, pitch, roll = pose
    if max(abs(pitch), abs(roll)) > float(config.get('max_tilt_rad', .05)):
        return None
    bounds = np.asarray(config['bounds_xy_m'], float)
    extrinsic = np.asarray(config['laser_xyz_m'], float)
    if bounds.shape != (4,) or extrinsic.shape != (3,) or not np.isfinite(np.r_[bounds, extrinsic]).all():
        raise ValueError('Corridor bounds/extrinsics must be finite')
    if not bounds[0] < x < bounds[1] or not bounds[2] < y < bounds[3]:
        return None
    # body -> world orientation, preserving range as a 3D ray length.
    cr, sr, cp, sp, cy, sy = cos(roll), sin(roll), cos(pitch), sin(pitch), cos(yaw), sin(yaw)
    rotation = np.array([[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                         [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr],
                         [-sp, cp*sr, cp*cr]])
    offset = rotation @ extrinsic
    angles = angle_min + np.arange(len(ranges)) * increment
    directions = np.c_[np.cos(angles), np.sin(angles), np.zeros(len(angles))] @ rotation.T
    ranges = np.asarray(ranges, float)
    distances = np.full((len(ranges), 4), np.inf)
    for wall, axis in enumerate((0, 0, 1, 1)):
        with np.errstate(divide='ignore', invalid='ignore'):
            t = (bounds[wall] - (x, y)[axis] - offset[axis]) / directions[:, axis]
        distances[:, wall] = np.where(t > 0, t, np.inf)
    walls = np.argmin(distances, axis=1)
    expected = np.min(distances, axis=1)
    valid = (np.isfinite(ranges) & (ranges > range_min) & (ranges < range_max)
             & (np.abs(ranges - expected) <= float(config.get('association_gate_m', .5))))
    estimates = []
    for axis in (0, 1):
        estimates_axis = []
        for wall in ((0, 1) if axis == 0 else (2, 3)):
            selected = valid & (walls == wall) & (np.abs(directions[:, axis]) > .8)
            values = bounds[wall] - offset[axis] - ranges[selected] * directions[selected, axis]
            if len(values) < int(config.get('minimum_rays', 8)):
                continue
            median = float(np.median(values))
            inliers = values[np.abs(values - median) <= float(config.get('inlier_gate_m', .03))]
            if len(inliers) >= int(config.get('minimum_rays', 8)):
                estimates_axis.append(float(np.median(inliers)))
        if not estimates_axis or np.ptp(estimates_axis) > .06:
            return None
        estimates.append(float(np.mean(estimates_axis)))
    return np.asarray(estimates)


class CorridorOdometry(ImuEncoderOdometry):
    def __init__(self, config):
        self.walls = config['corridor_lidar']
        # Validate at startup, before opening a live episode.
        wall_position(([2.]*360, -np.pi, 2*np.pi/359, .08, 12.), (0., 0., 0., 0., 0.), self.walls)
        self.max_scan_age = float(self.walls.get('max_age_seconds', .6))
        self.gain = float(self.walls.get('correction_gain', .5))
        if not np.isfinite([self.max_scan_age, self.gain]).all() or self.max_scan_age <= 0 or not 0 < self.gain <= 1:
            raise ValueError('Invalid corridor correction gain or scan freshness')
        super().__init__(config)

    def reset(self, min_stamp=-float('inf')):
        super().reset(min_stamp)
        self.history = deque(maxlen=2000)
        self.scans = deque(maxlen=10)
        self.rolls = deque(maxlen=100)
        self.last_fix = self.latest_scan = -float('inf')
        self.accepted_scans = 0

    @property
    def ready(self):
        return self.last_joint is not None and np.isfinite(self.last_fix)

    def add_imu(self, stamp, yaw, pitch, roll=0.):
        if stamp > self.min_stamp and (not self.rolls or stamp > self.rolls[-1][0]):
            self.rolls.append((stamp, roll))
        super().add_imu(stamp, yaw, pitch)

    def _drain(self):
        super()._drain()
        if self.last_joint is not None and (not self.history or self.stamp > self.history[-1][0]):
            roll = next((v for t, v in reversed(self.rolls) if t <= self.stamp + 1e-9), 0.)
            self.history.append((self.stamp, self.x, self.y, self.yaw, self.last_pitch, roll))
        self._correct_scans()

    def add_scan(self, stamp, ranges, angle_min, increment, range_min, range_max):
        if not np.isfinite([stamp, angle_min, increment, range_min, range_max]).all() or increment <= 0:
            raise ValueError('Invalid corridor scan metadata')
        if stamp <= self.min_stamp or stamp <= self.latest_scan:
            return
        self.latest_scan = stamp
        self.scans.append((stamp, (ranges, angle_min, increment, range_min, range_max)))
        self._correct_scans()

    def _correct_scans(self):
        while self.history and self.scans and self.scans[0][0] <= self.stamp + 1e-9:
            stamp, scan = self.scans.popleft()
            times = np.array([row[0] for row in self.history])
            if stamp < times[0] or self.stamp - stamp > self.max_scan_age:
                continue
            index = max(0, int(np.searchsorted(times, stamp, side='right')) - 1)
            a = np.asarray(self.history[index][1:])
            pose = a.copy()
            if index + 1 < len(times):
                b = np.asarray(self.history[index+1][1:])
                f = (stamp - times[index]) / (times[index+1] - times[index])
                pose = a + f * (b - a)
                pose[2] = wrap(a[2] + f * wrap(b[2] - a[2]))
            observation = wall_position(scan, pose, self.walls)
            if observation is None:
                continue
            delta = observation - pose[:2]
            if np.linalg.norm(delta) > float(self.walls.get('max_correction_m', .4)):
                continue
            delta *= self.gain
            self.x += delta[0]
            self.y += delta[1]
            # Correct stored past poses too: delayed scans must not repeatedly
            # apply a correction already included in the current state.
            self.history = deque(((t, x+delta[0], y+delta[1], yaw, pitch, roll)
                for t,x,y,yaw,pitch,roll in self.history), maxlen=2000)
            self.last_fix = stamp
            self.accepted_scans += 1

    def pose(self):
        if self.stamp - self.last_fix > self.max_scan_age:
            raise RuntimeError('Corridor localization has no fresh accepted wall scan')
        return super().pose()
