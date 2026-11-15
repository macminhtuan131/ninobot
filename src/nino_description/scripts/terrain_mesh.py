"""Continuous heightfield mesh utilities for factory-floor geometry."""
import numpy as np


def feature_relief(xx, yy, item):
    """Compact smooth footprint, including smooth flat-bottom transitions."""
    angle = np.deg2rad(item["angle_deg"])
    dx, dy = xx - item["x_m"], yy - item["y_m"]
    u = (np.cos(angle) * dx + np.sin(angle) * dy) / item["radius_x_m"]
    v = (-np.sin(angle) * dx + np.cos(angle) * dy) / item["radius_y_m"]
    radius_squared = u * u + v * v
    if item["kind"] in ("flat_bottom_bowl", "low_plateau"):
        t = np.clip((np.sqrt(radius_squared) - .25) / .75, 0., 1.)
        shape = 1. - (6. * t**5 - 15. * t**4 + 10. * t**3)
    else:
        shape = np.maximum(1. - radius_squared, 0.) ** 2
    if item["kind"] == "banked_mound":
        shape *= 1. + .55 * v
    return item["height_m"] * shape



def write_mesh(x, y, surface, path):
    """Write upward-facing binary STL in batches to bound memory and CPU cost."""
    xx, yy = np.meshgrid(x - (x[0] + x[-1]) / 2., y)
    points = np.stack((xx, yy, surface), axis=-1).astype("<f4")
    dtype = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)),
                      ("attribute", "<u2")])
    triangles = 2 * (len(x) - 1) * (len(y) - 1)
    with path.open("wb") as stream:
        stream.write(b"Nino continuous factory floor mesh v1".ljust(80, b"\0"))
        stream.write(np.array([triangles], dtype="<u4").tobytes())
        for row in range(0, len(y) - 1, 32):
            stop = min(row + 32, len(y) - 1)
            a, b = points[row:stop, :-1], points[row:stop, 1:]
            c, d = points[row + 1:stop + 1, :-1], points[row + 1:stop + 1, 1:]
            vertices = np.stack((np.stack((a, b, d), axis=-2),
                                 np.stack((a, d, c), axis=-2)), axis=-3).reshape(-1, 3, 3)
            records = np.zeros(len(vertices), dtype=dtype)
            normal = np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0])
            records["normal"] = normal / np.linalg.norm(normal, axis=1)[:, None]
            records["vertices"] = vertices
            stream.write(records.tobytes())

