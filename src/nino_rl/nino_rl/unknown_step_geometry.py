"""Conservative collision envelope, including complete continuous-joint sweeps."""
from itertools import product
import hashlib
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corners(bounds):
    lo, hi = np.asarray(bounds, dtype=float)
    return np.asarray(list(product(*zip(lo, hi))), dtype=float)


def rpy(values):
    r, p, y = values
    cr, cp, cy, sr, sp, sy = np.cos(r), np.cos(p), np.cos(y), np.sin(r), np.sin(p), np.sin(y)
    return np.asarray([[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                       [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr], [-sp, cp*sr, cp*cr]])


def origin(node):
    o = node.find('origin')
    xyz = [float(x) for x in o.get('xyz', '0 0 0').split()] if o is not None else [0., 0., 0.]
    angles = [float(x) for x in o.get('rpy', '0 0 0').split()] if o is not None else [0., 0., 0.]
    return np.asarray(xyz), rpy(angles)


def stl_vertices(path):
    data = Path(path).read_bytes()
    n = struct.unpack_from('<I', data, 80)[0] if len(data) >= 84 else -1
    if n >= 0 and len(data) == 84 + 50*n:
        triangles = np.frombuffer(data, dtype=np.dtype([('normal', '<f4', (3,)),
                                  ('vertices', '<f4', (3, 3)), ('attribute', '<u2')]), offset=84, count=n)
        points = triangles['vertices'].reshape(-1, 3).astype(float)
    else:
        text = data.decode('ascii')
        points = np.asarray([[float(v) for v in m] for m in re.findall(
            r'\bvertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)', text)])
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise ValueError('Finite STL vertices required: ' + str(path))
    return points


def swept_bounds(points, axis):
    """Bound every rotation of a box about an arbitrary continuous joint axis."""
    u = np.asarray(axis, dtype=float)
    if u.shape != (3,) or not np.isfinite(u).all() or np.linalg.norm(u) == 0:
        raise ValueError('Finite nonzero joint axis required')
    u /= np.linalg.norm(u)
    axial = points @ u
    radial = np.linalg.norm(points - axial[:, None]*u, axis=1)
    extent = radial[:, None]*np.sqrt(np.maximum(0., 1-u*u))
    center = axial[:, None]*u
    return np.asarray([(center-extent).min(axis=0), (center+extent).max(axis=0)])


def collision_envelope(urdf_path, package_root):
    """Root base_footprint frame, using collision geometry only, never visuals."""
    path, package_root = Path(urdf_path), Path(package_root).resolve()
    tree = ET.parse(path).getroot()
    links = {l.get('name'): l for l in tree.findall('link')}
    children = {}
    for j in tree.findall('joint'):
        children.setdefault(j.find('parent').get('link'), []).append(j)
    if 'base_footprint' not in links:
        raise ValueError('Expected truth/body frame base_footprint')
    plugin = tree.find(".//plugin[@name='gz::sim::systems::OdometryPublisher']")
    if plugin is None or plugin.findtext('robot_base_frame') != 'base_footprint':
        raise ValueError('Envelope and truth frames must be identical')
    assets, swept, collisions = {}, [], []

    def geometry(g):
        mesh = g.find('mesh')
        if mesh is not None:
            prefix = 'package://nino_description/'
            uri = mesh.get('filename')
            if not uri.startswith(prefix):
                raise ValueError('Unsupported mesh URI: ' + uri)
            file = (package_root/uri.removeprefix(prefix)).resolve()
            if not file.is_relative_to(package_root):
                raise ValueError('Mesh outside package')
            assets[str(file)] = sha(file)
            pts = stl_vertices(file)*[float(v) for v in mesh.get('scale', '1 1 1').split()]
            return corners([pts.min(axis=0), pts.max(axis=0)])
        if g.find('cylinder') is not None:
            c = g.find('cylinder');radius, half = float(c.get('radius')), float(c.get('length'))/2
            return corners([[-radius, -radius, -half], [radius, radius, half]])
        if g.find('box') is not None:
            size = np.asarray([float(v) for v in g.find('box').get('size').split()])/2
            return corners([-size, size])
        if g.find('sphere') is not None:
            radius = float(g.find('sphere').get('radius'))
            return corners([[-radius]*3, [radius]*3])
        raise ValueError('Unsupported collision geometry')

    visiting = set()
    def walk(name):
        if name in visiting:
            raise ValueError('URDF joint cycle')
        visiting.add(name)
        points = []
        for c in links[name].findall('collision'):
            xyz, rotation = origin(c)
            points.extend(geometry(c.find('geometry'))@rotation.T+xyz)
            collisions.append(name)
        for j in children.get(name, []):
            pts = walk(j.find('child').get('link'))
            if pts is None:
                continue
            if j.get('type') == 'continuous':
                axis = [float(v) for v in j.find('axis').get('xyz').split()]
                pts = corners(swept_bounds(pts, axis))
                swept.append(j.get('name'))
            elif j.get('type') != 'fixed':
                raise ValueError('Unqualified joint type: ' + j.get('type'))
            xyz, rotation = origin(j)
            points.extend(pts@rotation.T+xyz)
        visiting.remove(name)
        if not points:
            return None
        pts = np.asarray(points)
        return corners([pts.min(axis=0), pts.max(axis=0)])

    pts = walk('base_footprint')
    if pts is None or not np.isfinite(pts).all():
        raise ValueError('Missing/nonfinite collision envelope')
    # Canonical kinematics/collisions ignore unrelated comments, inertias and whitespace.
    selected = ET.Element('geometry_identity')
    for l in tree.findall('link'):
        node = ET.SubElement(selected, 'link', name=l.get('name'))
        for c in l.findall('collision'):
            node.append(c)
    for j in tree.findall('joint'):
        selected.append(j)
    canonical = ET.canonicalize(ET.tostring(selected, encoding='unicode'), strip_text=True)
    record = dict(frame='base_footprint', bounds_m=[pts.min(axis=0).tolist(), pts.max(axis=0).tolist()],
                  corners_m=pts.tolist(), swept_joints=sorted(swept), collision_links=sorted(collisions),
                  mesh_sha256=assets, kinematics_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
                  scope='conservative_sim_collision_box_all_continuous_angles_not_hardware_measurement')
    record['sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    return record
