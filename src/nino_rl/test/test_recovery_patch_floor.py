from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import yaml

from nino_rl.recovery_bank import configuration, sample_layout, write_world
from nino_rl.carved_floor import coalesced_tiles, level_tiles, floor_model


DTYPE = np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attribute', '<u2')])


def actual_mesh(collision):
    uri = urlparse(collision.findtext('geometry/mesh/uri'))
    assert uri.scheme == 'file'
    path = Path(unquote(uri.path))
    data = path.read_bytes()
    count = int.from_bytes(data[80:84], 'little')
    assert len(data) == 84+50*count
    rows = np.frombuffer(data, dtype=DTYPE, count=count, offset=84)
    pose = np.asarray(list(map(float, collision.findtext('pose').split())))
    np.testing.assert_array_equal(pose[3:], 0.)
    return rows['vertices'].astype(float)+pose[:3], rows['normal'].astype(float)


def ray_heights(triangles, x, y):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    dx, dy = b[:, 0]-a[:, 0], b[:, 1]-a[:, 1]
    ex, ey = c[:, 0]-a[:, 0], c[:, 1]-a[:, 1]
    denominator = dx*ey-dy*ex
    u = ((x-a[:, 0])*ey-(y-a[:, 1])*ex)/denominator
    v = (dx*(y-a[:, 1])-dy*(x-a[:, 0]))/denominator
    mask = (u >= -1e-6) & (v >= -1e-6) & (u+v <= 1+1e-6)
    return a[mask, 2]+u[mask]*(b[mask, 2]-a[mask, 2])+v[mask]*(c[mask, 2]-a[mask, 2])


def rectangle_overlap(a, b):
    return max(0., min(a[1], b[1])-max(a[0], b[0])) * max(0., min(a[3], b[3])-max(a[2], b[2]))


@pytest.fixture(params=[(family, stage) for family in ('pothole', 'mixed') for stage in range(3)])
def generated_floor(tmp_path, request):
    family, stage = request.param
    source = tmp_path/'source.sdf'
    source.write_text('<sdf><world name="test"><model name="controlled_box_floor"/>'
        '<model name="sentinel"><static>true</static><pose>9 9 0 0 0 0</pose>'
        '</model></world></sdf>')
    sentinel = ET.tostring(ET.parse(source).find("world/model[@name='sentinel']"))
    layout = sample_layout(configuration(), family, 1511+stage, stage)
    target = tmp_path/'generated.sdf'
    paths = write_world(source, target, layout, tmp_path/'meshes')
    world = ET.parse(target).find('world')
    assert ET.tostring(world.find("model[@name='sentinel']")) == sentinel
    assert world.find("model[@name='controlled_box_floor']") is None
    floor = world.find("model[@name='factory_contact_floor']")
    boxes, meshes = [], []
    for collision in floor.findall('.//collision'):
        if collision.find('geometry/mesh') is not None:
            meshes.append(actual_mesh(collision))
        else:
            size = np.asarray(list(map(float, collision.findtext('geometry/box/size').split())))
            pose = np.asarray(list(map(float, collision.findtext('pose').split())))
            assert pose[2]+size[2]/2 == pytest.approx(0., abs=1e-12)
            boxes.append([pose[0]-size[0]/2, pose[0]+size[0]/2,
                          pose[1]-size[1]/2, pose[1]+size[1]/2])
    assert paths and meshes
    return layout, world, boxes, meshes


def test_default_depression_representation_is_local_patches():
    assert configuration()['families']['pothole']['floor_representation'] == 'tiles_and_patches'


@pytest.mark.parametrize('value', ['continuous_mesh', 'unknown', None])
def test_unqualified_depression_representation_is_rejected(tmp_path, value):
    config = deepcopy(configuration())
    config['families']['pothole']['floor_representation'] = value
    path = tmp_path/'unqualified.yaml'
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        configuration(path)


def test_negative_depressions_survive_without_boxes_under_their_footprints(generated_floor):
    layout, _, boxes, meshes = generated_floor
    assert boxes, 'Flat terrain outside each local depression must use finite solid tiles'
    triangles = np.concatenate([mesh[0] for mesh in meshes])
    for hole in [row for row in layout['obstacles'] if row['kind'] == 'pothole']:
        x, y, radius = hole['x'], hole['y'], hole['radius_m']
        footprint = [x-radius, x+radius, y-.84*radius, y+.84*radius]
        assert all(rectangle_overlap(box, footprint) == 0. for box in boxes)
        heights = ray_heights(triangles, x, y)
        assert len(heights) and np.ptp(heights) < 1e-7
        assert float(heights.mean()) == pytest.approx(-hole['depth_m'], abs=2e-5)
        for px, py in [(x-radius-.005, y), (x+radius+.005, y),
                       (x, y-.84*radius-.005), (x, y+.84*radius+.005)]:
            assert ray_heights(triangles, px, py).mean() == pytest.approx(0., abs=1e-7)


def test_patch_triangles_face_up_and_join_the_zero_height_tiles(generated_floor):
    _, _, boxes, meshes = generated_floor
    assert boxes
    for triangles, normals in meshes:
        cross = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        assert np.isfinite(triangles).all() and (cross[:, 2] > 0.).all()
        assert (normals[:, 2] > 0.).all()
        np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1., atol=2e-7)
        vertices = np.unique(triangles.reshape(-1, 3), axis=0)
        lo, hi = vertices[:, :2].min(axis=0), vertices[:, :2].max(axis=0)
        boundary = np.any((vertices[:, :2] == lo) | (vertices[:, :2] == hi), axis=1)
        np.testing.assert_array_equal(vertices[boundary, 2], 0.)
        patch = [lo[0], hi[0], lo[1], hi[1]]
        assert max(rectangle_overlap(box, patch) for box in boxes) < 1e-7


def test_combined_tile_and_patch_surface_covers_the_complete_floor(generated_floor):
    _, _, boxes, meshes = generated_floor
    assert boxes
    rectangles = list(boxes)
    projected_triangle_area = 0.
    for triangles, _ in meshes:
        lo, hi = triangles[:, :, :2].min(axis=(0, 1)), triangles[:, :, :2].max(axis=(0, 1))
        rectangles.append([lo[0], hi[0], lo[1], hi[1]])
        cross = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        projected_triangle_area += cross[:, 2].sum()/2
    total_area = sum((b-a)*(d-c) for a, b, c, d in boxes)+projected_triangle_area
    assert total_area == pytest.approx(70., abs=2e-6)
    for i, rectangle in enumerate(rectangles):
        assert rectangle[0] >= -2.-1e-7 and rectangle[1] <= 8.+1e-7
        assert rectangle[2] >= -3.5-1e-7 and rectangle[3] <= 3.5+1e-7
        assert all(rectangle_overlap(rectangle, other) < 1e-7 for other in rectangles[i+1:])
    xs = np.unique([-2., 8., *(v for r in rectangles for v in r[:2])])
    ys = np.unique([-3.5, 3.5, *(v for r in rectangles for v in r[2:])])
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            if min(x1-x0, y1-y0) <= 2e-7:
                continue
            x, y = (x0+x1)/2, (y0+y1)/2
            assert any(a < x < b and c < y < d for a, b, c, d in rectangles)


def test_mixed_cable_geometry_is_preserved(generated_floor):
    layout, world, _, _ = generated_floor
    cables = [row for row in layout['obstacles'] if row['kind'] == 'cable']
    emitted = world.findall("model[@name='recovery_rigid_obstacles']/link/collision")
    assert len(emitted) == len(cables)
    for cable in cables:
        node = next(row for row in emitted if row.attrib['name'] == cable['id']+'_collision')
        assert float(node.findtext('geometry/cylinder/radius')) == cable['radius_m']
        assert float(node.findtext('geometry/cylinder/length')) == 2*cable['half_length_m']
        pose = list(map(float, node.findtext('pose').split()))
        np.testing.assert_allclose(pose, [cable['x'], 0., cable['radius_m'], np.pi/2, 0., cable['angle_rad']], atol=1e-12)


def test_post_hole_flat_apron_does_not_split_a_drive_tyre_at_an_artificial_y_seam(tmp_path):
    config = configuration()
    layout = sample_layout(config, 'pothole', 1511, 0)
    source, target = tmp_path/'source.sdf', tmp_path/'floor.sdf'
    source.write_text('<sdf><world name="test"><model name="controlled_box_floor"/></world></sdf>')
    write_world(source, target, layout, tmp_path/'meshes')
    collisions = ET.parse(target).findall("world/model[@name='factory_contact_floor']//collision")
    tyre_y_intervals = [(-.1935, -.1465), (.1465, .1935)]
    for x in (0., .4, 1.86, 1.936, 3., 4.):
        supporting_boxes = []
        for collision in collisions:
            size_text = collision.findtext('geometry/box/size')
            if size_text is None:
                continue
            sx, sy, _ = map(float, size_text.split())
            px, py, *_ = map(float, collision.findtext('pose').split())
            if px-sx/2 < x < px+sx/2:
                supporting_boxes.append((py-sy/2, py+sy/2))
        for lower, upper in tyre_y_intervals:
            assert any(a <= lower and upper <= b for a, b in supporting_boxes), (
                'Flat apron must support the full tyre width on one coplanar box')


@pytest.mark.parametrize('patches', [[(.8, 1., .005, .165)],
    [(.8, 1., .005, .165), (2., 2.2, -.3, -.1), (3., 3.2, -.1, .15)]])
def test_flat_tile_merging_is_deterministic_idempotent_and_preserves_the_union(patches):
    bounds = (-2., 8., -3.5, 3.5)
    original = level_tiles(bounds, patches)
    merged = coalesced_tiles(original)
    assert merged == coalesced_tiles(list(reversed(original)))
    assert merged == coalesced_tiles(merged)
    assert len(merged) < len(original)
    area = lambda tiles: sum((b-a)*(d-c) for a, b, c, d in tiles)
    assert area(merged) == pytest.approx(area(original), abs=1e-12)
    for i, tile in enumerate(merged):
        assert all(rectangle_overlap(tile, other) == 0. for other in merged[i+1:])
    xs = sorted({bounds[0], bounds[1], *(value for patch in patches for value in patch[:2])})
    ys = sorted({bounds[2], bounds[3], *(value for patch in patches for value in patch[2:])})
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            x, y = (x0+x1)/2, (y0+y1)/2
            covered = lambda tiles: sum(a < x < b and c < y < d for a, b, c, d in tiles)
            assert covered(original) == covered(merged)


def test_merging_does_not_bridge_a_nonzero_gap():
    tiles = [(0., 1., 0., .5), (0., 1., .50000000000001, 1.)]
    assert coalesced_tiles(tiles) == tiles


def test_historical_floor_model_default_remains_unmerged(tmp_path):
    config = dict(floor_bounds_xy_m=[-2., 8., -3.5, 3.5], mesh_spacing_m=.005,
                  floor_representation='tiles_and_patches', pothole_depth_m=.003)
    features = [('pothole', .9, .085, .083)]
    first = floor_model(features, config, tmp_path/'meshes')
    assert floor_model(features, dict(config, merge_flat_tiles=False), tmp_path/'meshes') == first
    unmerged = ET.fromstring(first[0]).findall('.//collision/geometry/box')
    merged = ET.fromstring(floor_model(features, dict(config, merge_flat_tiles=True),
                                     tmp_path/'meshes')[0]).findall('.//collision/geometry/box')
    assert len(merged) < len(unmerged)
    with pytest.raises(ValueError):
        floor_model(features, dict(config, merge_flat_tiles=1), tmp_path/'meshes')
