"""Gravity-aligned downward lidar preview; no simulated pose or terrain oracle.

Height is relative to the nominal axle plane, not absolute world elevation.
An IMU cannot measure heave: this is relief evidence, not a full height map.
"""
from collections import deque
from math import cos, sin, isfinite
import bisect

import numpy as np

REVISION = 'calibrated_gravity_preview_v1'


def rotation(rpy):
    r, p, y = rpy
    cr, sr, cp, sp, cy, sy = cos(r), sin(r), cos(p), sin(p), cos(y), sin(y)
    return np.array([[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                     [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr],
                     [-sp, cp*sr, cp*cr]])


def calibration_from_urdf(xml):
    """Require the actual fixed sensor transform and nominal axle height."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    def origin(joint):
        node = root.find(f"joint[@name='{joint}']/origin")
        if node is None:
            raise ValueError('Missing calibrated joint: ' + joint)
        return {key: [float(x) for x in node.get(key, '0 0 0').split()]
                for key in ('xyz', 'rpy')}
    mount, base = origin('terrain_laser_to_base_link'), origin('base_footprint_joint')
    if base['xyz'][:2] != [0., 0.] or base['rpy'] != [0., 0., 0.]:
        raise ValueError('Unexpected nominal axle transform')
    return dict(revision=REVISION, translation_m=mount['xyz'], rotation_rpy=mount['rpy'],
                nominal_axle_height_m=base['xyz'][2], max_attitude_gap_s=.04,
                range_m=1.5, half_width_m=.50, distance_band_m=.10)


def project(ranges, angle_min, angle_increment, range_min, range_max, roll, pitch,
            calibration, threshold=.006):
    """Return [left distance, height, valid, right distance, height, valid, valid].

    All-invalid, upward-facing or out-of-footprint returns are invalid.
    A sampled flat floor is valid. Each side has its own distance and validity;
    a rolled single-plane fan cannot observe both wheels at a shared distance.
    """
    if not all(isfinite(x) for x in (angle_min, angle_increment, range_min, range_max,
                                     roll, pitch, threshold)) or range_max <= range_min:
        return [0.]*7
    values = np.asarray(ranges, dtype=float)
    angles = angle_min + np.arange(len(values))*angle_increment
    mask = np.isfinite(values) & (values >= range_min) & (values < range_max)
    if not np.any(mask):
        return [0.]*7
    rays = np.column_stack((values[mask]*np.cos(angles[mask]),
                            values[mask]*np.sin(angles[mask]), np.zeros(mask.sum())))
    attitude = rotation((roll, pitch, 0.))
    mount = rotation(calibration['rotation_rpy'])
    points = (rays @ mount.T + calibration['translation_m']) @ attitude.T
    directions = rays @ mount.T @ attitude.T
    height = points[:, 2] + calibration['nominal_axle_height_m']
    forward, lateral = points[:, 0], points[:, 1]
    useful = ((directions[:, 2] < 0.) & (forward > 0.) &
              (forward <= calibration['range_m']) &
              (np.abs(lateral) <= calibration['half_width_m']))
    def side_preview(side):
        seen = useful & side
        if not seen.any():
            return [0., 0., 0.]
        relief = seen & (np.abs(height) >= threshold)
        if not relief.any():
            return [1., 0., 1.]
        nearest = float(forward[relief].min())
        band = relief & (forward <= nearest + calibration['distance_band_m'])
        indices = np.flatnonzero(band)
        chosen = indices[np.argmax(np.abs(height[band]))]
        return [float(forward[chosen])/calibration['range_m'], float(height[chosen])/.1, 1.]
    left, right = side_preview(lateral >= 0.), side_preview(lateral < 0.)
    return left + right + [left[-1]*right[-1]]


class PreviewBuffer:
    """Timestamp interpolation, bounded extrapolation, explicit reset epoch."""
    def __init__(self, calibration):
        self.calibration = calibration
        self.attitudes = deque(maxlen=100)
        self.epoch = -float('inf')
        self.pending = None
        self.value = [0.]*7

    def reset(self, stamp):
        self.epoch = stamp
        self.attitudes.clear()
        self.pending = None
        self.value = [0.]*7

    def add_attitude(self, stamp, roll, pitch, valid):
        if stamp <= self.epoch:
            return False
        if not valid or not all(isfinite(x) for x in (stamp, roll, pitch)):
            self.attitudes.clear()
            self.pending = None
            self.value = [0.]*7
            return False
        if self.attitudes and stamp <= self.attitudes[-1][0]:
            return False
        self.attitudes.append((stamp, roll, pitch))
        return self._compute()

    def scan(self, message, threshold):
        stamp = message.header.stamp.sec + message.header.stamp.nanosec*1e-9
        if stamp <= self.epoch:
            return False
        self.pending = (stamp, message, threshold)
        self.value = [0.]*7
        return self._compute()

    def _compute(self):
        if not self.pending or not self.attitudes:
            return False
        stamp, message, threshold = self.pending
        samples = list(self.attitudes)
        index = bisect.bisect_left([s[0] for s in samples], stamp)
        nearest = min(samples, key=lambda s: abs(s[0]-stamp))
        gap = self.calibration['max_attitude_gap_s']
        if abs(nearest[0]-stamp) > gap:
            self.value = [0.]*7
            return False
        r, p = nearest[1:]
        if 0 < index < len(samples):
            a, b = samples[index-1:index+1]
            if max(stamp-a[0], b[0]-stamp) <= gap:
                f = (stamp-a[0])/(b[0]-a[0])
                r, p = ((1-f)*a[j]+f*b[j] for j in (1, 2))
        self.value = project(message.ranges, message.angle_min, message.angle_increment,
                             message.range_min, message.range_max, r, p,
                             self.calibration, threshold)
        # An IMU callback must not re-label an already consumed scan as fresh.
        self.pending = None
        return True


def patch_interface(code, calibration):
    """Clone-only patch; fail if frozen source anchors do not match."""
    def replace(old, new):
        nonlocal code
        if code.count(old) != 1:
            raise ValueError('Unexpected interface anchor: ' + old[:80])
        code = code.replace(old, new)
    replace('        self._preview = (0.0, 0.0, 0.0)',
            '        from nino_rl.terrain_preview_foundation import PreviewBuffer\n'
            f'        self._gravity_preview = PreviewBuffer({calibration!r})\n'
            '        self._preview = (0.0, 0.0, 0.0)\n        self._preview_valid = False')
    replace('            self._mark_received("imu")',
            '            self._mark_received("imu")\n'
            '            valid = isfinite(norm) and norm >= 1.e-12 and message.orientation_covariance[0] >= 0\n'
            '            if self._gravity_preview.add_attitude(stamp, roll, pitch, valid):\n'
            '                self._store_gravity_preview()\n'
            '            elif not valid:\n                self._preview_valid = False')
    start = code.index('    def _terrain_scan_callback(')
    end = code.index('    def terrain_preview(', start)
    code = code[:start] + '''    def _store_gravity_preview(self):
        value = self._gravity_preview.value
        self._calibrated_preview = value
        self._preview_valid = bool(value[-1])
        self._preview_received_at = monotonic()
        self._mark_received("terrain")
        import os, json
        audit = os.environ.get("NINO_PREVIEW_AUDIT")
        if audit:
            with open(audit, "a") as stream:
                stream.write(json.dumps(dict(stamp_s=self._preview_scan_stamp,
                    imu_stamp_s=self._state.imu_stamp_s, roll=self._state.roll,
                    pitch=self._state.pitch, preview=value)) + "\\n")

    def _terrain_scan_callback(self, message):
        with self._lock:
            stamp = message.header.stamp.sec + message.header.stamp.nanosec*1e-9
            if stamp <= self._gravity_preview.epoch:
                return
            self._preview_scan_stamp = stamp
            if self._gravity_preview.scan(message, self.terrain_height_threshold):
                self._store_gravity_preview()
            else:
                self._preview_valid = False

''' + code[end:]
    start = code.index('    def _preview_callback(')
    end = code.index('    def _store_gravity_preview(', start)
    code = code[:start] + ('    def _preview_callback(self, message):\n'
        '        # Legacy triples have no calibrated frame, attitude or validity.\n'
        '        return\n\n') + code[end:]
    replace('                timeout is not None\n                and monotonic() - self._preview_received_at > timeout',
            '                not self._preview_valid or (timeout is not None\n'
            '                and monotonic() - self._preview_received_at > timeout)')
    replace('                return [0.0, 0.0, 0.0, 0.0]', '                return [0.0]*7')
    start = code.index('            distance, left, right = self._preview')
    end = code.index('\n    def wait_for_terrain_preview', start)
    code = code[:start] + '            return list(self._calibrated_preview)\n' + code[end:]
    replace('            self._imu_epoch_min_stamp = paused_clock',
            '            self._imu_epoch_min_stamp = paused_clock\n'
            '            self._gravity_preview.reset(paused_clock)\n'
            '            self._preview_valid = False\n'
            '            self._received.discard("terrain")\n'
            '            self._received_at.pop("terrain", None)')
    # Preview readiness must include valid geometry, not just a callback.
    replace('            if self.sensor_stream_ready("terrain", timeout):',
            '            if self.sensor_stream_ready("terrain", timeout) and self.terrain_preview(timeout)[-1]:')
    return code
