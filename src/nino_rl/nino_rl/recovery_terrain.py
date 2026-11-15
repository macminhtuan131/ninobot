from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from .carved_floor import (carve_on_grid, continuous_axes, geometry_pair,
                           grouped_bounds, negative_items, write_stl)


@dataclass(frozen=True)
class ConnectedRamp:
    start_x_m: float
    rise_length_m: float
    plateau_length_m: float
    peak_grade_rad: float
    blend_fraction: float = .25

    def __post_init__(self):
        if (not np.isfinite(list(asdict(self).values())).all()
                or min(self.start_x_m, self.rise_length_m, self.plateau_length_m) <= 0
                or not 0 < self.peak_grade_rad <= math.radians(5.)
                or not 0 < self.blend_fraction <= .5):
            raise ValueError('Invalid connected ramp dimensions or grade')

    @property
    def end_x_m(self):
        return self.start_x_m + 2*self.rise_length_m + self.plateau_length_m

    @property
    def height_m(self):
        return math.tan(self.peak_grade_rad)*self.rise_length_m*(1-self.blend_fraction)

    @property
    def joins_m(self):
        length, blend = self.rise_length_m, self.blend_fraction
        return tuple(self.start_x_m + offset for offset in (
            0., blend*length, (1-blend)*length, length, length+self.plateau_length_m,
            (1+blend)*length+self.plateau_length_m,
            (2-blend)*length+self.plateau_length_m, 2*length+self.plateau_length_m))

    def _ascent(self, distance, derivative=False):
        u = np.clip(distance/self.rise_length_m, 0., 1.)
        blend = self.blend_fraction
        left, right = np.clip(u/blend, 0., 1.), np.clip((1-u)/blend, 0., 1.)
        if derivative:
            smooth = lambda t: t**3*(10+t*(-15+6*t))
            value = np.where(u < blend, smooth(left),
                             np.where(u > 1-blend, smooth(right), 1.))
            return math.tan(self.peak_grade_rad)*value
        integral = lambda t: t**4*(2.5+t*(-3+t))
        value = np.where(u < blend, blend*integral(left),
                         np.where(u > 1-blend, 1-blend-blend*integral(right), u-blend/2))
        return math.tan(self.peak_grade_rad)*self.rise_length_m*value

    def height(self, x):
        x = np.asarray(x, dtype=float)
        distance = x-self.start_x_m
        descent = distance-self.rise_length_m-self.plateau_length_m
        z = np.where(distance < self.rise_length_m, self._ascent(distance),
                     np.where(descent <= 0., self.height_m, self.height_m-self._ascent(descent)))
        return float(z) if z.ndim == 0 else z

    def slope(self, x):
        x = np.asarray(x, dtype=float)
        distance = x-self.start_x_m
        descent = distance-self.rise_length_m-self.plateau_length_m
        gradient = np.where((distance > 0.) & (distance < self.rise_length_m),
                            self._ascent(distance, derivative=True),
                            np.where((descent > 0.) & (x < self.end_x_m),
                                     -self._ascent(descent, derivative=True), 0.))
        return float(gradient) if gradient.ndim == 0 else gradient


def connected_floor_model(ramp, features, config, cache):
    bounds = tuple(float(v) for v in config['floor_bounds_xy_m'])
    if len(bounds) != 4 or not bounds[0] < ramp.start_x_m < ramp.end_x_m < bounds[1]:
        raise ValueError('Connected ramp must fit inside the complete floor')
    spacing = float(config.get('mesh_spacing_m', .005))
    flat_spacing = float(config.get('flat_mesh_spacing_m', .08))
    items = negative_items(features, config)
    groups = grouped_bounds(items, spacing)
    x, y = continuous_axes(bounds, groups, spacing, flat_spacing)
    ramp_x = [np.linspace(a, b, math.ceil((b-a)/spacing)+1)
              for a, b in zip(ramp.joins_m, ramp.joins_m[1:]) if b > a]
    x = np.unique(np.concatenate([x, *ramp_x]))
    x = np.unique((x-(bounds[0]+bounds[1])/2).astype('<f4')).astype(float)+(bounds[0]+bounds[1])/2
    y = np.unique((y-(bounds[2]+bounds[3])/2).astype('<f4')).astype(float)+(bounds[2]+bounds[3])/2
    z = ramp.height(x)[None, :] + carve_on_grid(items, x, y)
    key = sha256(json.dumps(dict(version='connected_recovery_floor_v2', ramp=asdict(ramp),
        items=items, bounds=bounds, mesh_spacing_m=spacing, flat_mesh_spacing_m=flat_spacing),
        sort_keys=True).encode()).hexdigest()
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache/f'terrain_{key}.stl'
    if not path.exists():
        write_stl(x, y, z, path)
    root = ET.Element('sdf', version='1.9')
    model = ET.SubElement(root, 'model', name='factory_contact_floor')
    ET.SubElement(model, 'static').text = 'true'
    link = ET.SubElement(model, 'link', name='terrain')
    geometry = ET.Element('geometry')
    ET.SubElement(ET.SubElement(geometry, 'mesh'), 'uri').text = path.as_uri()
    geometry_pair(link, 'terrain', f'{(x[0]+x[-1])/2:.9f} {(y[0]+y[-1])/2:.9f} 0 0 0 0',
                  geometry, config.get('terrain_material'))
    return ET.tostring(root, encoding='unicode'), [str(path)]
