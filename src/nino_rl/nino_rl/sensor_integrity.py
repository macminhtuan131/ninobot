"""Legacy sensor validity, separate from observation values and estimates."""
import math


SENSOR_CONTRACT = 'nino_sensor_support_v2'


def scan_valid(ranges, range_max, range_min=0.):
    if not math.isfinite(range_max) or not 0 <= range_min < range_max or not len(ranges):
        return False
    return all((math.isfinite(v) and range_min <= v <= range_max) or v == math.inf
               for v in ranges)


def require_scan(state, now_s, max_age_s, receipt_fresh):
    age = now_s - state.lidar_stamp_s
    if (not receipt_fresh or not math.isfinite(age) or not 0 <= age <= max_age_s
            or not scan_valid(state.lidar_ranges, state.lidar_range_max,
                              getattr(state, 'lidar_range_min', 0.))):
        raise RuntimeError('Required LiDAR missing, stale, future or invalid; no observation/transition')


def require_imu_support(measurement, start, end, minimum_coverage=.8):
    duration = measurement['duration']
    if (not math.isfinite(duration) or not 0 < minimum_coverage <= 1
            or duration + 1e-9 < (end-start)*minimum_coverage
            or duration > end-start+1e-9):
        raise RuntimeError('Insufficient measured IMU support; no reward/transition')
    return duration
