"""True below-floor adaptive geometry, without ROS or privileged actor inputs."""
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np


POTHOLE_Y_RADIUS_RATIO = .84


def sample_pothole_in_cable_gap(rng, cables, radius, zone_x, y_range,
                               clearance=.03, max_attempts=512, footprint_padding=0.):
    """Sample a full elliptical hole between actual episode cable cylinders.

    Cable tuples are (x at y=0, radius, yaw in radians), matching _cable_sdf.
    Its horizontal axis has normal (cos(yaw), sin(yaw)). Clearance is measured
    from the entire hole footprint to the cable surface, not between centers.
    Optional padding covers the carved mesh's interpolation at the hole edge.
    """
    cables = np.asarray(sorted(cables), dtype=float)
    if (cables.ndim != 2 or cables.shape[1] != 3 or len(cables) < 2
            or not np.isfinite(cables).all()
            or np.any(np.diff(cables[:, 0]) <= 0)
            or np.any(cables[:, 1] <= 0)
            or np.any(np.abs(cables[:, 2]) >= np.pi / 2)):
        raise ValueError("Gap placement requires at least two ordered episode cables")
    x_min, x_max = map(float, zone_x)
    y_min, y_max = map(float, y_range)
    if (not np.isfinite([radius, clearance, footprint_padding, x_min, x_max, y_min, y_max]).all()
            or radius <= 0 or clearance < 0 or footprint_padding < 0 or not x_min < x_max
            or not y_min < y_max or max_attempts < 1):
        raise ValueError("Invalid pothole gap placement bounds or clearance")
    cosines, sines = np.cos(cables[:, 2]), np.sin(cables[:, 2])
    support = radius * np.sqrt(cosines**2 + (POTHOLE_Y_RADIUS_RATIO * sines)**2)
    offset = (support + footprint_padding + cables[:, 1] + clearance) / cosines
    for _ in range(max_attempts):
        gap = int(rng.integers(len(cables) - 1))
        y = float(rng.uniform(y_min, y_max))
        centers = cables[:, 0] - sines / cosines * y
        # Check every cable on each side, including nonadjacent angled cables.
        low = max(x_min, float(np.max((centers + offset)[:gap + 1])))
        high = min(x_max, float(np.min((centers - offset)[gap + 1:])))
        if high > low:
            return float(rng.uniform(low, high)), y
    raise ValueError(
        "No sampled cable gap fits the full pothole with the requested clearance; "
        "check cable angles, spacing and pothole size"
    )


def negative_items(features, config):
    items = []
    for index, (kind, x, y, size) in enumerate(features):
        if kind not in ("pothole", "groove"):
            continue
        if not np.all(np.isfinite([x, y, size])) or size <= 0:
            raise ValueError("Invalid adaptive depression")
        depth = float(config.get(f"{kind}_depth_m", .018 if kind == "pothole" else .010))
        if not 0 < depth <= .04:
            raise ValueError("Shallow depression depth must be in (0, 40 mm]")
        shape = config.get("pothole_shape", "round_bowl") if kind == "pothole" else "groove"
        if kind == "pothole" and shape not in ("round_bowl", "flat_bottom_bowl"):
            raise ValueError("Pothole shape must be round_bowl or flat_bottom_bowl")
        items.append(dict(id=f"feature_{index}_{kind}", kind=kind, x=float(x), y=float(y),
            rx=float(size), ry=(POTHOLE_Y_RADIUS_RATIO*float(size) if kind == "pothole"
                               else .5*float(config.get("groove_length_m", .70))), depth=depth,
            shape=shape))
    return items


def grouped_bounds(items, spacing):
    """Merge overlapping rectangles, so no mesh/floor layers overlap."""
    groups = [(r["x"]-r["rx"]-2*spacing, r["x"]+r["rx"]+2*spacing,
               r["y"]-r["ry"]-2*spacing, r["y"]+r["ry"]+2*spacing) for r in items]
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(groups):
            for j in range(i+1, len(groups)):
                b = groups[j]
                if max(a[0], b[0]) <= min(a[1], b[1]) and max(a[2], b[2]) <= min(a[3], b[3]):
                    groups[i] = (min(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]))
                    groups.pop(j)
                    changed = True
                    break
            if changed:
                break
    return groups


def level_tiles(bounds, patches):
    a, b, c, d = bounds
    if not np.all(np.isfinite(bounds)) or not a < b or not c < d:
        raise ValueError("Invalid carved floor bounds")
    for p in patches:
        if not a < p[0] < p[1] < b or not c < p[2] < p[3] < d:
            raise ValueError("Adaptive depression exceeds the floor bounds")
    xs = sorted({a,b, *(v for p in patches for v in p[:2])})
    ys = sorted({c,d, *(v for p in patches for v in p[2:])})
    return [(x0,x1,y0,y1) for x0,x1 in zip(xs,xs[1:]) for y0,y1 in zip(ys,ys[1:])
            if not any(p[0] < (x0+x1)/2 < p[1] and p[2] < (y0+y1)/2 < p[3] for p in patches)]


def continuous_axes(bounds, patches, spacing, flat_spacing=.04):
    """One shared grid: fine at depressions, coarse only on exactly level floor.

    All triangles share grid vertices; there are no separate floor patches or
    T junctions. A completely level world needs just two triangles.
    """
    if (not np.isfinite([spacing, flat_spacing]).all()
            or not .0025 <= spacing <= .01 or not spacing <= flat_spacing <= .10):
        raise ValueError("Invalid continuous terrain spacing")
    # Reuse bounds validation; the returned legacy tiles are not used.
    level_tiles(bounds, patches)
    axes = []
    for axis in (0, 2):
        lower, upper = bounds[axis:axis+2]
        intervals = []
        for start, stop in sorted(p[axis:axis+2] for p in patches):
            if intervals and start <= intervals[-1][1]:
                intervals[-1] = (intervals[-1][0], max(stop, intervals[-1][1]))
            else:
                intervals.append((start, stop))
        if not intervals:
            axes.append(np.array([lower, upper], dtype=float))
            continue
        cuts = sorted({lower, upper, *(value for pair in intervals for value in pair)})
        values = [lower]
        for start, stop in zip(cuts, cuts[1:]):
            middle = (start+stop)/2
            step = spacing if any(a <= middle <= b for a,b in intervals) else flat_spacing
            values.extend(np.linspace(start, stop, ceil((stop-start)/step)+1)[1:])
        axes.append(np.asarray(values))
    return tuple(axes)


def carve_on_grid(items, x, y):
    xx,yy = np.meshgrid(x,y)
    z = np.zeros_like(xx)
    for r in items:
        u,v = (xx-r["x"])/r["rx"], (yy-r["y"])/r["ry"]
        shape = (np.maximum(1-u*u-v*v,0)**2 if r["kind"] == "pothole"
                 else np.maximum(1-u*u,0)**2 * np.maximum(1-v*v,0)**2)
        if r.get("shape") == "flat_bottom_bowl":
            t = np.clip((np.sqrt(u*u+v*v)-.25)/.75,0.,1.)
            shape = 1.-(6*t**5-15*t**4+10*t**3)
        # Overlap joins two depressions without doubling their declared depth.
        z = np.minimum(z, -r["depth"]*shape)
    if any(np.any(e != 0) for e in (z[0],z[-1],z[:,0],z[:,-1])):
        raise ValueError("Carved patch does not join the level floor")
    return z


def carve(items, bounds, spacing):
    a,b,c,d = bounds
    x = np.linspace(a,b,ceil((b-a)/spacing)+1)
    y = np.linspace(c,d,ceil((d-c)/spacing)+1)
    return x,y,carve_on_grid(items,x,y)


def write_stl(x,y,z,path):
    """Same upward-facing two-triangle grid convention as rough terrain."""
    xx,yy = np.meshgrid(x-(x[0]+x[-1])/2,y-(y[0]+y[-1])/2)
    points = np.stack((xx,yy,z),axis=-1).astype("<f4")
    dtype = np.dtype([("normal","<f4",(3,)),("vertices","<f4",(3,3)),("attribute","<u2")])
    with Path(path).open("wb") as stream:
        stream.write(b"Nino true carved adaptive floor v2".ljust(80,b"\0"))
        stream.write(np.array([2*(len(x)-1)*(len(y)-1)],dtype="<u4").tobytes())
        for row in range(0,len(y)-1,32):
            stop = min(row+32,len(y)-1)
            a,b = points[row:stop,:-1],points[row:stop,1:]
            c,d = points[row+1:stop+1,:-1],points[row+1:stop+1,1:]
            vertices = np.stack((np.stack((a,b,d),axis=-2),np.stack((a,d,c),axis=-2)),axis=-3).reshape(-1,3,3)
            records = np.zeros(len(vertices),dtype=dtype)
            normals = np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0])
            records["normal"] = normals/np.linalg.norm(normals,axis=1)[:,None]
            records["vertices"] = vertices
            stream.write(records.tobytes())


def geometry_pair(link, name, pose, geometry, colors=None):
    for kind in ("collision","visual"):
        element = ET.SubElement(link,kind,name=f"{name}_{kind}")
        ET.SubElement(element,"pose").text = pose
        element.append(ET.fromstring(ET.tostring(geometry)))
        if kind == "collision":
            ode = ET.SubElement(ET.SubElement(ET.SubElement(element,"surface"),"friction"),"ode")
            ET.SubElement(ode,"mu").text = "1.0"
            ET.SubElement(ode,"mu2").text = "1.0"
        else:
            material = ET.SubElement(element,"material")
            for channel in ("ambient","diffuse"):
                ET.SubElement(material,channel).text = (colors or {}).get(channel, "0.42 0.44 0.47 1")


def add_level_apron_visuals(model, bounds, terrain_bounds):
    """Show a rough-style terrain panel without adding a second collision floor."""
    if terrain_bounds is None:
        return
    a,b,c,d = bounds
    x0,x1,y0,y1 = map(float, terrain_bounds)
    if not np.isfinite([x0,x1,y0,y1]).all() or not a <= x0 < x1 <= b or not c <= y0 < y1 <= d:
        raise ValueError("Terrain view bounds must fit inside the floor")
    rectangles = [(a,x0,c,d),(x1,b,c,d),(x0,x1,c,y0),(x0,x1,y1,d)]
    link = ET.SubElement(model,"link",name="level_apron_visuals")
    for i,(left,right,bottom,top) in enumerate(rectangles):
        if right <= left or top <= bottom:
            continue
        visual = ET.SubElement(link,"visual",name=f"apron_{i}")
        ET.SubElement(visual,"pose").text = f"{(left+right)/2:.9f} {(bottom+top)/2:.9f} 0.0002 0 0 0"
        plane = ET.SubElement(ET.SubElement(visual,"geometry"),"plane")
        ET.SubElement(plane,"normal").text = "0 0 1"
        ET.SubElement(plane,"size").text = f"{right-left:.9f} {top-bottom:.9f}"
        material = ET.SubElement(visual,"material")
        for channel in ("ambient","diffuse"):
            ET.SubElement(material,channel).text = "0.43 0.48 0.55 1"


def add_goal_hall_visuals(model, bounds, halls):
    """Paint level goal halls on the shared mesh, without duplicate collisions."""
    if not halls:
        return
    a, b, c, d = bounds
    link = ET.SubElement(model, "link", name="goal_hall_visuals")
    for hall in halls:
        left, right, bottom, top = map(float, hall["bounds_xy_m"])
        gx, gy, heading = map(float, hall["goal_pose"])
        if (not np.isfinite([left, right, bottom, top, gx, gy, heading]).all()
                or not a <= left < right <= b or not c <= bottom < top <= d
                or not left < gx < right or not bottom < gy < top):
            raise ValueError("Goal hall and goal must fit inside the physical floor")
        visual = ET.SubElement(link, "visual", name=f"hall_{hall['id']}")
        ET.SubElement(visual, "pose").text = f"{(left+right)/2:g} {(bottom+top)/2:g} 0.0004 0 0 0"
        plane = ET.SubElement(ET.SubElement(visual, "geometry"), "plane")
        ET.SubElement(plane, "normal").text = "0 0 1"
        ET.SubElement(plane, "size").text = f"{right-left:g} {top-bottom:g}"
        material = ET.SubElement(visual, "material")
        for channel in ("ambient", "diffuse"):
            ET.SubElement(material, channel).text = "0.45 0.51 0.44 1"


def floor_model(features, config, cache):
    """Return a COMPLETE replacement floor SDF and its immutable mesh paths."""
    cache = Path(cache)
    cache.mkdir(parents=True,exist_ok=True)
    spacing = float(config.get("mesh_spacing_m",.005))
    if not .0025 <= spacing <= .01:
        raise ValueError("Carved floor spacing must be 2.5–10 mm")
    items = negative_items(features,config)
    groups = grouped_bounds(items,spacing)
    bounds = tuple(float(v) for v in config["floor_bounds_xy_m"])
    tiles = level_tiles(bounds,groups)
    root = ET.Element("sdf",version="1.9")
    model = ET.SubElement(root,"model",name="factory_contact_floor")
    ET.SubElement(model,"static").text = "true"
    representation = config.get("floor_representation", "tiles_and_patches")
    if representation == "continuous_mesh":
        x,y = continuous_axes(bounds,groups,spacing,float(config.get("flat_mesh_spacing_m", .04)))
        z = carve_on_grid(items,x,y)
        key = sha256(json.dumps(["continuous_mesh_v1",items,bounds,spacing,
                                config.get("flat_mesh_spacing_m",.04)],sort_keys=True).encode()).hexdigest()
        path = cache/f"terrain_{key}.stl"
        if not path.exists():
            write_stl(x,y,z,path)
        link = ET.SubElement(model,"link",name="terrain")
        geometry = ET.Element("geometry")
        ET.SubElement(ET.SubElement(geometry,"mesh"),"uri").text = path.resolve().as_uri()
        geometry_pair(link,"terrain",f"{(x[0]+x[-1])/2:.9f} {(y[0]+y[-1])/2:.9f} 0 0 0 0",
                      geometry,config.get("terrain_material"))
        add_level_apron_visuals(model,bounds,config.get("terrain_view_bounds_xy_m"))
        add_goal_hall_visuals(model,bounds,config.get("goal_halls"))
        return ET.tostring(root,encoding="unicode"), [str(path.resolve())]
    if representation != "tiles_and_patches":
        raise ValueError("Unknown carved floor representation")
    link = ET.SubElement(model,"link",name="flat_tiles")
    for i,(a,b,c,d) in enumerate(tiles):
        geometry = ET.Element("geometry")
        ET.SubElement(ET.SubElement(geometry,"box"),"size").text = f"{b-a:.9f} {d-c:.9f} .1"
        geometry_pair(link,f"floor_{i:03d}",f"{(a+b)/2:.9f} {(c+d)/2:.9f} -.05 0 0 0",geometry)
    paths = []
    for i,bounds in enumerate(groups):
        x,y,z = carve(items,bounds,spacing)
        key = sha256(json.dumps([items,bounds,spacing],sort_keys=True).encode()).hexdigest()
        path = cache/f"patch_{key}.stl"
        if not path.exists():
            write_stl(x,y,z,path)
        paths.append(str(path.resolve()))
        link = ET.SubElement(model,"link",name=f"carved_patch_{i}")
        geometry = ET.Element("geometry")
        ET.SubElement(ET.SubElement(geometry,"mesh"),"uri").text = path.resolve().as_uri()
        geometry_pair(link,f"patch_{i}",f"{(x[0]+x[-1])/2:.9f} {(y[0]+y[-1])/2:.9f} 0 0 0 0",geometry)
    return ET.tostring(root,encoding="unicode"), paths
