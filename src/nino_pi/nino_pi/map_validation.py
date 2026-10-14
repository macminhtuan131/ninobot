"""Reject absent maps and simulator worlds before starting navigation."""
from pathlib import Path
import yaml


def validate_map(filename):
    path = Path(filename).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Map YAML does not exist: {path}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data,dict) or not isinstance(data.get("image"),str):
        raise ValueError("Navigation needs an occupancy-map YAML with an image; an SDF world is not a navigation map")
    image = Path(data["image"]).expanduser()
    if not image.is_absolute():
        image = path.parent/image
    if not image.is_file():
        raise ValueError(f"Map image does not exist: {image}")
    if not isinstance(data.get("resolution"),(int,float)) or data["resolution"] <= 0:
        raise ValueError("Map resolution must be positive")
    if not isinstance(data.get("origin"),list) or len(data["origin"]) != 3:
        raise ValueError("Map origin must contain x, y and yaw")
    return str(path)
