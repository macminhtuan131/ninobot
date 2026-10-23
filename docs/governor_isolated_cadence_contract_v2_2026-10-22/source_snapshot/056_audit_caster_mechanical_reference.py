#!/usr/bin/env python3
"""Offline nominal geometry/mass reference; never edits a robot or run.

Input must be expanded URDF, not xacro. All movable joints are evaluated at
zero, with base_footprint on z=0. This is not loaded/contact geometry or a
traversability test. Binary STL only; fail explicitly for other formats.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET


IDENTITY = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def matvec(matrix, vector):
    return tuple(sum(a * b for a, b in zip(row, vector)) for row in matrix)


def compose(first, second):
    ra, pa = first
    rb, pb = second
    rotation = tuple(tuple(sum(ra[i][k] * rb[k][j] for k in range(3))
                           for j in range(3)) for i in range(3))
    position = tuple(a + b for a, b in zip(pa, matvec(ra, pb)))
    return rotation, position


def origin(element):
    if element is None:
        return IDENTITY, (0., 0., 0.)
    r, p, y = map(float, element.get("rpy", "0 0 0").split())
    cr, sr, cp, sp, cy, sy = (math.cos(r), math.sin(r), math.cos(p),
                             math.sin(p), math.cos(y), math.sin(y))
    rotation = ((cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr),
                (sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr),
                (-sp, cp*sr, cp*cr))
    return rotation, tuple(map(float, element.get("xyz", "0 0 0").split()))


def binary_stl_vertices(path):
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"Not a binary STL: {path}")
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * count or count == 0:
        raise ValueError(f"Expected nonempty binary STL: {path}")
    for index in range(count):
        values = struct.unpack_from("<9f", data, 84 + 50 * index + 12)
        for offset in (0, 3, 6):
            point = values[offset:offset + 3]
            if not all(math.isfinite(x) for x in point):
                raise ValueError(f"Nonfinite STL vertex: {path}")
            yield point


def audit(urdf, package):
    robot = ET.parse(urdf).getroot()
    links = {link.get("name"): link for link in robot.findall("link")}
    parents = {j.find("child").get("link"): j for j in robot.findall("joint")}

    def transform(link):
        if link == "base_footprint":
            return IDENTITY, (0., 0., 0.)
        joint = parents[link]
        return compose(transform(joint.find("parent").get("link")),
                       origin(joint.find("origin")))

    masses = []
    for name, link in links.items():
        inertial = link.find("inertial")
        if inertial is not None:
            masses.append(dict(link=name, mass_kg=float(inertial.find("mass").get("value")),
                               com_m=compose(transform(name), origin(inertial.find("origin")))[1]))
    total = sum(item["mass_kg"] for item in masses)
    com = [sum(item["mass_kg"] * item["com_m"][i] for item in masses) / total
           for i in range(3)]
    casters, inputs = {}, {str(urdf.resolve()): hashlib.sha256(urdf.read_bytes()).hexdigest()}
    for side in ("left", "right"):
        bracket = links[f"caster_bracket_{side}_link"]
        collision = bracket.find("collision")
        mesh = collision.find("geometry/mesh")
        prefix = "package://nino_description/"
        filename = mesh.get("filename")
        if not filename.startswith(prefix):
            raise ValueError(f"Unsupported mesh URI: {filename}")
        path = package / filename[len(prefix):]
        inputs[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
        scale = tuple(map(float, mesh.get("scale", "1 1 1").split()))
        rotation, position = compose(transform(bracket.get("name")), origin(collision.find("origin")))
        points = [tuple(a + b for a, b in zip(position, matvec(rotation,
                  tuple(x * s for x, s in zip(point, scale)))))
                  for point in binary_stl_vertices(path)]
        wheel_name = f"caster_{side}_wheel_link"
        wheel = links[wheel_name].find("collision")
        cylinder = wheel.find("geometry/cylinder")
        radius, width = float(cylinder.get("radius")), float(cylinder.get("length"))
        wheel_rotation, center = compose(transform(wheel_name), origin(wheel.find("origin")))
        axis_z = wheel_rotation[2][2]
        vertical_extent = radius * math.sqrt(max(0., 1. - axis_z**2)) + width/2 * abs(axis_z)
        casters[side] = dict(
            bracket_bounds_m=[[min(p[i] for p in points) for i in range(3)],
                              [max(p[i] for p in points) for i in range(3)]],
            bracket_lowest_nominal_mm=1000 * min(p[2] for p in points),
            wheel_diameter_mm=2000 * radius, wheel_width_mm=1000 * width,
            wheel_center_m=center, wheel_lowest_nominal_mm=1000 * (center[2] - vertical_extent),
            swivel_origin_m=transform(bracket.get("name"))[1],
            visual_collision_mesh_aligned=(bracket.find("visual/geometry/mesh").attrib == mesh.attrib
                                           and origin(bracket.find("visual/origin")) ==
                                           origin(collision.find("origin"))))
    return dict(reference_frame="base_footprint", configuration="All movable joints zero; level nominal pose",
                hardware_verified=False, inputs_sha256=inputs, casters=casters,
                modeled_mass_kg=total, nominal_aggregate_com_m=com, link_masses=masses,
                limitations=["Nominal STL vertex bounds do not prove the physics engine contact representation.",
                             "Clearance is not a maximum traversable obstacle height.",
                             "No real mass, dimensions, payload, friction or motor limits measured here."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--description-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.urdf, args.description_package)
    # Preserve any earlier report rather than silently replacing it.
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Saved offline mechanical reference: {args.output}")


if __name__ == "__main__":
    main()
