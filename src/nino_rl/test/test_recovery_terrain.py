from copy import deepcopy
from dataclasses import asdict, replace
import math
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import yaml

from nino_rl.recovery_bank import configuration, sample_layout, write_world
from nino_rl.recovery_contract import CONTRACT_ID
from nino_rl.recovery_curriculum import FAMILIES
from nino_rl.recovery_terrain import ConnectedRamp, connected_floor_model


def ramp(grade=5.):
    return ConnectedRamp(1., .6, .3, math.radians(grade), .25)


def mesh_config(**changes):
    return dict(floor_bounds_xy_m=[-2., 8., -3.5, 3.5], mesh_spacing_m=.005,
                flat_mesh_spacing_m=.08, pothole_depth_m=.006, **changes)


def emitted_mesh(sdf):
    root = ET.fromstring(sdf)
    collisions = root.findall('.//collision')
    assert len(collisions) == 1
    collision = collisions[0]
    uri = urlparse(collision.findtext('geometry/mesh/uri'))
    assert uri.scheme == 'file'
    path = Path(unquote(uri.path))
    assert path.is_absolute()
    data = path.read_bytes()
    dtype = np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attribute', '<u2')])
    count = int(np.frombuffer(data, dtype='<u4', count=1, offset=80)[0])
    assert len(data) == 84+50*count
    records = np.frombuffer(data, dtype=dtype, count=count, offset=84)
    pose = np.asarray([float(v) for v in collision.findtext('pose').split()])
    np.testing.assert_array_equal(pose[3:], 0.)
    return path, records['vertices'].astype(float)+pose[:3], records['normal'].astype(float)


def surface_height(triangles, x, y):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    dx, dy = b[:, 0]-a[:, 0], b[:, 1]-a[:, 1]
    ex, ey = c[:, 0]-a[:, 0], c[:, 1]-a[:, 1]
    denominator = dx*ey-dy*ex
    u = ((x-a[:, 0])*ey-(y-a[:, 1])*ex)/denominator
    v = (dx*(y-a[:, 1])-dy*(x-a[:, 0]))/denominator
    selected = (u >= -1e-6) & (v >= -1e-6) & (u+v <= 1+1e-6)
    heights = a[selected, 2]+u[selected]*(b[selected, 2]-a[selected, 2])+v[selected]*(c[selected, 2]-a[selected, 2])
    assert len(heights)
    assert np.ptp(heights) < 1e-7
    return float(heights.mean())


@pytest.mark.parametrize('grade,height', [(3., .023583500677368545),
                                         (4., .03146706537457968),
                                         (5., .0393698985866658)])
def test_ramp_has_declared_height_flat_aprons_and_continuous_derivative(grade, height):
    r = ramp(grade)
    assert r.end_x_m == pytest.approx(2.5)
    assert r.height_m == pytest.approx(height)
    assert r.height(1.75) == pytest.approx(height)
    np.testing.assert_array_equal(r.height([-1., .9, 2.6, 5.]), 0.)
    np.testing.assert_array_equal(r.slope([.9, 1., 1.6, 1.75, 1.9, 2.5, 3.]), 0.)
    assert r.slope(1.3) == pytest.approx(math.tan(math.radians(grade)))
    assert r.slope(2.2) == pytest.approx(-math.tan(math.radians(grade)))
    for x in r.joins_m:
        assert abs(r.height(x+1e-8)-r.height(x-1e-8)) < 2e-9
        assert abs(r.slope(x+1e-8)-r.slope(x-1e-8)) < 1e-12
    x = np.linspace(.95, 2.55, 1001)
    derivative = (r.height(x+1e-6)-r.height(x-1e-6))/2e-6
    np.testing.assert_allclose(derivative, r.slope(x), atol=2e-9)


@pytest.mark.parametrize('field,value', [('start_x_m', 0.), ('rise_length_m', -1.),
    ('plateau_length_m', 0.), ('peak_grade_rad', math.radians(5.01)),
    ('peak_grade_rad', 0.), ('blend_fraction', .51), ('blend_fraction', 0.),
    ('start_x_m', math.nan), ('rise_length_m', math.inf)])
def test_ramp_rejects_invalid_physical_parameters(field, value):
    with pytest.raises(ValueError):
        replace(ramp(), **{field: value})


def test_actual_stl_has_world_heights_upward_normals_and_shared_joins(tmp_path):
    r = ramp()
    sdf, meshes = connected_floor_model(r, [], mesh_config(), tmp_path/'meshes')
    path, triangles, normals = emitted_mesh(sdf)
    assert meshes == [str(path)]
    assert ET.fromstring(sdf).find('.//collision/geometry/plane') is None
    assert ET.fromstring(sdf).find('.//collision/geometry/box') is None
    assert (normals[:, 2] > 0.).all()
    area = np.linalg.norm(np.cross(triangles[:, 1]-triangles[:, 0],
                                   triangles[:, 2]-triangles[:, 0]), axis=1)
    assert np.isfinite(triangles).all() and (area > 0.).all()
    np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1., atol=1e-7)
    grades = np.arctan2(np.abs(normals[:, 0]), normals[:, 2])
    assert grades.max() <= math.radians(5.)+2e-6
    changes = np.arccos(np.clip(np.sum(normals[:-1]*normals[1:], axis=1), -1., 1.))
    assert changes.max() < .006
    for x in np.r_[r.joins_m, np.linspace(.5, 3., 87)]:
        for y in (-3.4, 0., 3.4):
            assert surface_height(triangles, x, y) == pytest.approx(r.height(x), abs=5e-6)
    assert surface_height(triangles, .9, 0.) == 0.
    assert surface_height(triangles, 2.6, 0.) == 0.
    actual_x = np.unique(triangles[:, :, 0])
    for join in r.joins_m:
        assert np.min(abs(actual_x-join)) < 1.2e-7
    region = actual_x[(actual_x >= 1.+1e-6) & (actual_x <= 2.5-1e-6)]
    assert np.diff(region).max() <= .005001
    vertices, counts = np.unique(triangles.reshape(-1, 3), axis=0, return_counts=True)
    assert len(vertices) < triangles.size/3
    assert (counts <= 6).all()


def test_plateau_hole_is_below_macro_surface_without_hidden_support(tmp_path):
    r = ramp()
    sdf, _ = connected_floor_model(r, [('pothole', 1.75, .23, .075)],
                                   mesh_config(), tmp_path/'meshes')
    _, triangles, normals = emitted_mesh(sdf)
    assert surface_height(triangles, 1.75, .23) == pytest.approx(r.height_m-.006, abs=2e-5)
    assert surface_height(triangles, 1.75, 0.) == pytest.approx(r.height_m, abs=1e-8)
    assert (normals[:, 2] > 0.).all()
    assert not np.any(np.all(triangles[:, :, 2] == 0., axis=1)
                      & np.all((triangles[:, :, 0] > 1.6) & (triangles[:, :, 0] < 1.9), axis=1))


def test_geometry_cache_identity_covers_ramp_relief_bounds_and_spacing(tmp_path):
    config = mesh_config()
    sdf, paths = connected_floor_model(ramp(), [], config, tmp_path/'meshes')
    first_bytes = Path(paths[0]).read_bytes()
    assert connected_floor_model(ramp(), [], config, tmp_path/'meshes') == (sdf, paths)
    assert Path(paths[0]).read_bytes() == first_bytes
    variants = [connected_floor_model(ramp(4.), [], config, tmp_path/'meshes')[1],
        connected_floor_model(ramp(), [('pothole', 1.75, 0., .075)], config, tmp_path/'meshes')[1],
        connected_floor_model(ramp(), [], dict(config, floor_bounds_xy_m=[-1., 8., -3.5, 3.5]), tmp_path/'meshes')[1],
        connected_floor_model(ramp(), [], dict(config, mesh_spacing_m=.006), tmp_path/'meshes')[1]]
    assert len({paths[0], *(value[0] for value in variants)}) == 5


def test_slope_bank_is_deterministic_one_whole_width_interval(tmp_path):
    config = configuration()
    assert FAMILIES == ('clean', 'short_obstacle', 'pothole', 'mixed', 'slope')
    assert config['schema_version'] == 3 and config['contract_id'] == CONTRACT_ID
    for stage, grade in enumerate((3., 4., 5.)):
        layout = sample_layout(config, 'slope', 1511, stage)
        assert layout == sample_layout(config, 'slope', 1511, stage)
        assert layout['id'] != sample_layout(config, 'slope', 1511, stage, 'test')['id']
        r = ConnectedRamp(**layout['macro_ramp'])
        assert math.degrees(r.peak_grade_rad) == pytest.approx(grade)
        assert layout['obstacles'] == [dict(id='macro_ramp', kind='slope', near_m=1., far_m=2.5)]
        assert not layout['metadata_actor_input'] and not layout['physics_qualified']
        source, target = tmp_path/f'source_{stage}.sdf', tmp_path/f'slope_{stage}.sdf'
        source.write_text('<sdf><world name="test"><model name="controlled_box_floor"><link name="floor">'
                          '<collision name="floor"><geometry><box><size>10 7 .1</size></box></geometry>'
                          '</collision></link></model></world></sdf>')
        meshes = write_world(source, target, layout, tmp_path/'meshes')
        root = ET.parse(target).getroot()
        assert root.find('.//model[@name="controlled_box_floor"]') is None
        assert root.findall('.//collision/geometry/box') == []
        _, triangles, _ = emitted_mesh(ET.tostring(root, encoding='unicode'))
        assert meshes and surface_height(triangles, 1.75, 0.) == pytest.approx(r.height_m, abs=1e-8)


@pytest.mark.parametrize('key,value', [('peak_grade_deg_by_stage', [3., 4., 6.]),
    ('peak_grade_deg_by_stage', [3., 5.]), ('peak_grade_deg_by_stage', [5., 4., 3.]),
    ('mesh_spacing_m', float('nan')), ('mesh_spacing_m', .02),
    ('start_x_m', 3.), ('blend_fraction', 0.)])
def test_configuration_rejects_invalid_slope_contract(tmp_path, key, value):
    config = deepcopy(configuration())
    config['families']['slope'][key] = value
    path = tmp_path/'bad.yaml'
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        configuration(path)


def test_recovery_world_paces_physics_without_changing_step_or_geometry(tmp_path):
    source, target = tmp_path/'source.sdf', tmp_path/'paced.sdf'
    source.write_text('<sdf><world name="test"><physics name="native">'
        '<max_step_size>0.001</max_step_size><real_time_factor>1</real_time_factor>'
        '</physics><model name="floor"/></world></sdf>')
    config = configuration()
    layout = sample_layout(config,'clean',1511,0)
    write_world(source,target,layout,tmp_path/'meshes',scheduling=config['simulation_scheduling'])
    world = ET.parse(target).getroot().find('world')
    assert world.findtext('physics/max_step_size') == '0.001'
    assert world.findtext('physics/real_time_factor') == '0.2'
    assert world.find('model').attrib == {'name':'floor'}
