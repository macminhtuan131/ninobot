"""Known ray-plane intersections test geometry independently of the projector."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from terrain_preview_foundation import PreviewBuffer, project, rotation, patch_interface

C = dict(translation_m=[.33, 0., .20], rotation_rpy=[0., .45, 0.],
         nominal_axle_height_m=.0625, range_m=1.5, half_width_m=.5,
         distance_band_m=.10, max_attitude_gap_s=.04)


def plane_ranges(roll, pitch, height=0., slope=0.):
    angles = np.linspace(-.6, .6, 91)
    R = rotation((roll, pitch, 0.))
    origin = R @ C['translation_m'] + [0., 0., C['nominal_axle_height_m']]
    rays = np.column_stack((np.cos(angles), np.sin(angles), np.zeros(len(angles))))
    rays = rays @ rotation(C['rotation_rpy']).T @ R.T
    # z = height + slope*x; analytic intersection with independent plane.
    ranges = (height + slope*origin[0]-origin[2]) / (rays[:,2]-slope*rays[:,0])
    return angles, ranges


@pytest.mark.parametrize('roll,pitch', [(0.,0.), (.12,-.1),(-.15,.08)])
def test_tilted_flat_and_signed_relief(roll, pitch):
    for height in (0., .025, -.025):
        angles, ranges = plane_ranges(roll,pitch,height)
        value = project(ranges, angles[0], angles[1]-angles[0], .02, 5., roll,pitch,C)
        assert value[-1] == 1.
        assert [value[1], value[4]] == pytest.approx([height/.1]*2, abs=1e-10)


def test_sloped_plane_and_no_return():
    angles, ranges = plane_ranges(.1, -.1, slope=.03)
    value = project(ranges,angles[0],angles[1]-angles[0],.02,5.,.1,-.1,C)
    assert value[-1] == 1. and value[1] > 0. and value[4] > 0.
    for ranges in ([np.inf]*91, [np.nan]*91, [5.]*91):
        assert project(ranges,-.6,.0133,.02,5.,0.,0.,C)[-1] == 0.


def scan(stamp):
    angles,ranges=plane_ranges(0.,0.)
    sec=int(stamp)
    return SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=sec,nanosec=round((stamp-sec)*1e9))),
        ranges=ranges,angle_min=angles[0],angle_increment=angles[1]-angles[0],range_min=.02,range_max=5.)


def test_stale_invalid_imu_and_reset_queue():
    buffer=PreviewBuffer(C)
    assert not buffer.scan(scan(1.),.006)
    assert buffer.add_attitude(1.,0.,0.,True)
    assert buffer.value[-1] == 1.
    assert not buffer.add_attitude(1.02,0.,0.,True)
    assert not buffer.scan(scan(1.2),.006)
    assert buffer.value[-1] == 0.
    assert buffer.add_attitude(1.2,0.,0.,True)
    buffer.add_attitude(1.21,0.,0.,False)
    assert buffer.value[-1] == 0.
    buffer.reset(2.)
    assert not buffer.add_attitude(1.9,0.,0.,True)
    assert not buffer.scan(scan(1.9),.006)
    assert buffer.value[-1] == 0.


def test_frozen_overlay_compiles_and_does_not_change_timing_checks():
    source=Path(__file__).parents[3]/'rl_runs/rough_n1_heading_braking_v20/python/nino_rl/ros_interface.py'
    code=patch_interface(source.read_text(), C)
    compile(code,str(source),'exec')
    assert 'No downward terrain preview scan was received' in code
    assert 'self._gravity_preview.reset(paused_clock)' in code
    assert 'timeout is not None' in code
