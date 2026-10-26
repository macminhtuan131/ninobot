"""Experimental rough wall localization, loaded only in an isolated package copy.

Known outer walls + horizontal laser + IMU orientation observe XY independently
of wheels. Ground truth and terrain heights are not inputs to this estimator.
"""
from collections import deque
from math import cos, sin
import json
import os
import numpy as np
from nino_rl.assisted_odometry import ImuEncoderOdometry, wrap


def wall_position(scan, pose, config):
    ranges, angle_min, increment, range_min, range_max = scan
    angles = angle_min + np.arange(len(ranges)) * increment
    directions = np.c_[np.cos(angles), np.sin(angles), np.zeros(len(angles))]
    return wall_rays(np.asarray(ranges, float), directions, range_min, range_max, pose, config)


def cloud_position(points, pose, config):
    """Fit independent wall XY using near-horizontal world-frame 3D beams."""
    points = np.asarray(points, float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError('Rough cloud must contain sensor-frame XYZ points')
    points = points[np.isfinite(points).all(axis=1)]
    ranges = np.linalg.norm(points, axis=1)
    valid = ranges > float(config.get('cloud_range_min_m', .08))
    points, ranges = points[valid], ranges[valid]
    if not len(ranges):
        return None
    return wall_rays(ranges, points/ranges[:, None],
                     float(config.get('cloud_range_min_m', .08)),
                     float(config.get('cloud_range_max_m', 16.)), pose, config,
                     horizontal_only=True)


def wall_rays(ranges, body_directions, range_min, range_max, pose, config, horizontal_only=False):
    x, y, yaw, pitch, roll = pose
    if max(abs(pitch), abs(roll)) > float(config['max_tilt_rad']):
        return None
    bounds = np.asarray(config['bounds_xy_m'], float)
    extrinsic = np.asarray(config['laser_xyz_m'], float)
    if bounds.shape != (4,) or extrinsic.shape != (3,) or not np.isfinite(np.r_[bounds, extrinsic, pose]).all():
        raise ValueError('Invalid rough wall geometry/pose')
    if not bounds[0] < x < bounds[1] or not bounds[2] < y < bounds[3]:
        return None
    cr, sr, cp, sp, cy, sy = cos(roll), sin(roll), cos(pitch), sin(pitch), cos(yaw), sin(yaw)
    rotation = np.array([[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                         [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr],
                         [-sp, cp*sr, cp*cr]])
    offset = rotation @ extrinsic
    directions = body_directions @ rotation.T
    distances = np.full((len(ranges), 4), np.inf)
    for wall, axis in enumerate((0, 0, 1, 1)):
        with np.errstate(divide='ignore', invalid='ignore'):
            t = (bounds[wall] - (x, y)[axis] - offset[axis]) / directions[:, axis]
        distances[:, wall] = np.where(t > 0, t, np.inf)
    walls = np.argmin(distances, axis=1)
    expected = np.min(distances, axis=1)
    # Accept slightly downward rays when their observed endpoints remain above
    # the floor. Rejecting every negative-Z ray loses the nearby front wall
    # when the rear wall exceeds the laser's 12 m range near E1's goal.
    # Association also rejects the nearer terrain/robot/self returns.
    with np.errstate(invalid='ignore'):
        z = offset[2] + ranges * directions[:, 2]
    valid = (np.isfinite(ranges) & (ranges > range_min) & (ranges < range_max)
        & (z >= float(config.get('minimum_hit_height_relative_m', .10)))
        & (z < float(config.get('maximum_hit_height_relative_m', 2.5)))
        & (np.abs(ranges - expected) <= float(config['association_gate_m'])))
    if horizontal_only:
        # Coverage is supplied by actual vertical channels, not a virtual
        # levelled scan. These beams cannot reach floor/ceiling at wall ranges.
        valid &= np.abs(directions[:, 2]) <= float(config['cloud_max_vertical_direction'])
    estimates = []
    counts = []
    for axis in (0, 1):
        candidates = []
        axis_counts = []
        for wall in ((0, 1) if axis == 0 else (2, 3)):
            selected = valid & (walls == wall) & (np.abs(directions[:, axis]) > .75)
            values = bounds[wall] - offset[axis] - ranges[selected] * directions[selected, axis]
            if len(values) < int(config['minimum_rays']):
                continue
            median = float(np.median(values))
            inliers = values[np.abs(values - median) <= float(config['inlier_gate_m'])]
            if len(inliers) >= int(config['minimum_rays']):
                candidates.append(float(np.median(inliers)))
                axis_counts.append(len(inliers))
        if not candidates or np.ptp(candidates) > float(config.get('opposing_wall_agreement_m', .06)):
            return None
        estimates.append(float(np.average(candidates, weights=axis_counts)))
        counts.append(sum(axis_counts))
    return np.asarray(estimates), counts


class CorridorOdometry(ImuEncoderOdometry):
    def __init__(self, config):
        self.walls = config['corridor_lidar']
        self.max_scan_age = float(self.walls['max_age_seconds'])
        self.max_correction = float(self.walls['max_correction_m'])
        self.loss_as_terminal = bool(self.walls.get('loss_as_terminal', False))
        self.max_sensor_age = float(self.walls.get('max_sensor_age_seconds', .25))
        self.use_pointcloud = bool(self.walls.get('pointcloud_topic'))
        self.displacement_window = float(self.walls.get('displacement_window_seconds', .5))
        self.minimum_displacement_span = float(self.walls.get('minimum_displacement_span_seconds', .3))
        if not 0 < self.minimum_displacement_span <= self.displacement_window <= .6:
            raise ValueError('Invalid independent displacement window')
        if not 0 < self.max_scan_age <= .6 or not 0 < self.max_correction <= .5:
            raise ValueError('Rough scan freshness/correction bounds invalid')
        super().__init__(config)

    def reset(self, min_stamp=-float('inf')):
        super().reset(min_stamp)
        self.history = deque(maxlen=2000)
        self.scans = deque(maxlen=20)
        self.rolls = deque(maxlen=100)
        self.last_fix = self.latest_scan = -float('inf')
        self.accepted_scans = self.slip_count = 0
        self.stalled = False
        self.last_observation = None
        self.scan_velocity = None
        self.last_counts = [0, 0]
        self.positions = deque()
        self.startup_gap_restarts = 0

    def add_joint(self, stamp, left_position, right_position):
        try:
            super().add_joint(stamp, left_position, right_position)
        except RuntimeError as exc:
            # Initial discovery can deliver a first sample then a DDS backlog
            # gap. No episode exists yet. Discard that startup epoch instead
            # of integrating across it; after a finite reset boundary, fail.
            self._discard_startup_gap(exc)
            super().add_joint(stamp, left_position, right_position)

    def _discard_startup_gap(self, exc):
        if self.min_stamp != -float('inf') or 'encoder gap exceeded' not in str(exc):
            raise exc
        count = self.startup_gap_restarts + 1
        if count > 3:
            raise RuntimeError('Repeated startup encoder gaps; transport is not ready') from exc
        self.reset()
        self.startup_gap_restarts = count

    @property
    def ready(self):
        return self.last_joint is not None and np.isfinite(self.last_fix)

    @property
    def localization_valid(self):
        return self.ready and self.stamp - self.last_fix <= self.max_scan_age

    def add_imu(self, stamp, yaw, pitch, roll=0.):
        if stamp > self.min_stamp and (not self.rolls or stamp > self.rolls[-1][0]):
            self.rolls.append((stamp, roll))
        try:
            super().add_imu(stamp, yaw, pitch)
        except RuntimeError as exc:
            # An IMU callback can also release queued encoders and expose the
            # same discovery gap. Use the identical unscored-only reset rule.
            self._discard_startup_gap(exc)
            self.rolls.append((stamp, roll))
            super().add_imu(stamp, yaw, pitch)

    def _drain(self):
        before = self.x, self.y
        super()._drain()
        wheel_velocity = self.velocity
        if self.stalled:
            self.x, self.y = before
            self.velocity = self.scan_velocity if self.scan_velocity is not None else 0.
        if self.last_joint is not None and (not self.history or self.stamp > self.history[-1][0]):
            roll = next((v for t, v in reversed(self.rolls) if t <= self.stamp + 1e-9), 0.)
            self.history.append((self.stamp, self.x, self.y, self.yaw, self.last_pitch, roll, wheel_velocity))
        self._correct_scans()

    def add_scan(self, stamp, ranges, angle_min, increment, range_min, range_max):
        if self.use_pointcloud:
            return  # Keep the policy's 2D scan separate from localization.
        if not np.isfinite([stamp, angle_min, increment, range_min, range_max]).all() or increment <= 0:
            raise ValueError('Invalid rough scan metadata')
        if stamp <= self.min_stamp or stamp <= self.latest_scan:
            return
        self.latest_scan = stamp
        self.scans.append((stamp, ('scan', (ranges, angle_min, increment, range_min, range_max))))
        self._correct_scans()

    def add_pointcloud(self, stamp, points):
        points = np.asarray(points, float)
        if not np.isfinite(stamp) or points.ndim != 2 or points.shape[1] != 3:
            raise ValueError('Invalid rough point-cloud metadata')
        if stamp <= self.min_stamp or stamp <= self.latest_scan:
            return
        self.latest_scan = stamp
        self.scans.append((stamp, ('cloud', points.copy())))
        self._correct_scans()

    def _correct_scans(self):
        while self.history and self.scans and self.scans[0][0] <= self.stamp + 1e-9:
            stamp, (kind, observation_data) = self.scans.popleft()
            times = np.array([r[0] for r in self.history])
            if stamp < times[0] or self.stamp - stamp > self.max_scan_age:
                continue
            index = max(0, int(np.searchsorted(times, stamp, side='right')) - 1)
            a = np.asarray(self.history[index][1:])
            pose = a.copy()
            if index + 1 < len(times):
                b = np.asarray(self.history[index + 1][1:])
                f = (stamp - times[index]) / (times[index + 1] - times[index])
                pose = a + f * (b - a)
                pose[2] = wrap(a[2] + f * wrap(b[2] - a[2]))
            fix = (cloud_position(observation_data, pose[:5], self.walls) if kind == 'cloud'
                   else wall_position(observation_data, pose[:5], self.walls))
            if os.environ.get('NINO_ROUGH_LOCALIZATION_LOG'):
                with open(os.environ['NINO_ROUGH_LOCALIZATION_LOG'], 'a') as log:
                    log.write(json.dumps({'stamp':stamp,'pose':pose.tolist(),
                        'last_fix':self.last_fix,'fix':fix[0].tolist() if fix else None,
                        'counts':fix[1] if fix else None, 'sensor':kind,
                        'scan':([list(observation_data[0]),*observation_data[1:]] if kind=='scan' else None),
                        'cloud_points':len(observation_data) if kind=='cloud' else None})+'\n')
            if fix is None:
                continue
            observation, counts = fix
            delta = observation - pose[:2]
            if np.linalg.norm(delta) > self.max_correction:
                continue
            self._update_scan_velocity(stamp, observation, pose[5], pose[2])
            if self.stalled:
                self.velocity = self.scan_velocity
            # Full bounded wall fix; no wheel-driven drift remains at scan times.
            self.x += delta[0]
            self.y += delta[1]
            self.history = deque(((t, x+delta[0], y+delta[1], yaw, pitch, roll, v)
                for t,x,y,yaw,pitch,roll,v in self.history), maxlen=2000)
            self.last_observation = observation
            self.last_fix = stamp
            self.last_counts = counts
            self.accepted_scans += 1

    def _update_scan_velocity(self, stamp, observation, wheel_velocity, yaw):
        # Adjacent 10 Hz fixes amplify mm range noise into apparent motion.
        # Use independently observed displacement over a bounded 0.3–0.6 s
        # window, never wheel distance or physical pose, to classify a stall.
        if self.positions and stamp-self.positions[-1][0] > self.max_scan_age:
            self.positions.clear()
            self.scan_velocity = None
            self.slip_count = 0
            self.stalled = False
        self.positions.append((stamp, np.asarray(observation).copy()))
        while len(self.positions)>2 and self.positions[1][0] <= stamp-self.displacement_window+1e-9:
            self.positions.popleft()
        span = stamp-self.positions[0][0]
        if span < self.minimum_displacement_span-1e-9:
            return
        displacement = observation-self.positions[0][1]
        velocity = float(displacement @ np.array([cos(yaw),sin(yaw)])/span)
        self.scan_velocity = velocity
        suspicious = abs(wheel_velocity)>.05 and np.linalg.norm(displacement)/span<.025
        self.slip_count = self.slip_count+1 if suspicious else 0
        self.stalled = self.slip_count>=3

    def pose(self):
        if not self.localization_valid:
            if not self.loss_as_terminal or not self.ready:
                raise RuntimeError('Rough localization has no fresh accepted two-axis wall observation')
            if self.stamp - self.latest_scan > self.max_sensor_age:
                raise RuntimeError('Rough localization scan input is stale; not a policy failure')
        state = super().pose()
        # Timestamp remains the actual encoder/IMU estimate timestamp. This
        # explicit validity flag prevents control/arrival from trusting lost XY.
        state['localization_valid'] = self.localization_valid
        return state
