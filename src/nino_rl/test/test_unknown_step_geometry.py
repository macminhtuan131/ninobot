from itertools import product
import math
import struct
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from nino_rl.unknown_step_geometry import collision_envelope, corners, swept_bounds
from nino_rl.unknown_step_plan import protocol


def test_swept_envelope_contains_arbitrary_continuous_joint_rotations():
    pts = corners([[-.05, -.02, -.01], [.10, .03, .04]])
    u = np.array([1., 2., -1.]);u /= np.linalg.norm(u)
    lo, hi = swept_bounds(pts, u)
    for angle in np.linspace(-math.pi, math.pi, 181):
        rotated = (pts*math.cos(angle)+np.cross(u, pts)*math.sin(angle)
                   +np.outer(pts@u, u)*(1-math.cos(angle)))
        assert np.all(rotated >= lo-1e-10) and np.all(rotated <= hi+1e-10)


def test_urdf_full_caster_sweep_and_fixed_origin_are_included(tmp_path):
    urdf = tmp_path/'robot.urdf'
    urdf.write_text('''<robot name="fixture">
      <link name="base_footprint"/><link name="body"><collision><geometry><box size="0.2 0.2 0.1"/></geometry></collision></link>
      <joint name="root" type="fixed"><parent link="base_footprint"/><child link="body"/><origin xyz="0 0 0.1"/></joint>
      <link name="caster"><collision><origin xyz="0.2 0 0"/><geometry><box size="0.1 0.1 0.1"/></geometry></collision></link>
      <joint name="swivel" type="continuous"><parent link="body"/><child link="caster"/><origin xyz="0.3 0 0"/><axis xyz="0 0 1"/></joint>
      <gazebo><plugin name="gz::sim::systems::OdometryPublisher"><robot_base_frame>base_footprint</robot_base_frame></plugin></gazebo>
    </robot>''')
    r = collision_envelope(urdf, tmp_path)
    radius = math.hypot(.25, .05)
    assert r['bounds_m'][1][0] == pytest.approx(.3+radius)
    assert r['bounds_m'][0][1] == pytest.approx(-radius)
    assert r['swept_joints'] == ['swivel'] and len(r['corners_m']) == 8
    bad = urdf.read_text().replace('base_footprint</robot_base_frame>', 'base_link</robot_base_frame>')
    urdf.write_text(bad)
    with pytest.raises(ValueError, match='frames'):
        collision_envelope(urdf, tmp_path)


def test_reserved_bank_positions_are_disjoint_and_long_train_is_closed():
    p = protocol()
    assert not p['budget']['long_training_allowed']
    assert p['budget']['smoke_training_transitions'] == 384
    assert p['bank']['metadata_actor_input'] is False
    sets = [{r['bump_x_m'] for r in p['bank'][name]} for name in (
        'development', 'validation_reserved_not_run', 'test_reserved_not_run')]
    assert all(not sets[i] & sets[j] for i,j in product(range(3),repeat=2) if i<j)
