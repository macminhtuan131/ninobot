"""Only obstacle collision primitive may change in the contact-numerics A/B."""
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
path = ROOT/"src/nino_description/scripts/create_cable_capsule_control.py"
spec = importlib.util.spec_from_file_location("capsule_control", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_capsule_preserves_local_section_and_every_other_world_element(tmp_path):
    worlds = tmp_path/"worlds"
    worlds.mkdir()
    source = ROOT/"src/nino_description/worlds/factory_floor_cable_box_contact_lab.sdf"
    for suffix in (".sdf", ".json"):
        (worlds/source.with_suffix(suffix).name).write_bytes(source.with_suffix(suffix).read_bytes())
    result = module.generate(tmp_path)
    original, candidate = ET.parse(source).getroot(), ET.parse(result).getroot()
    old = original.find(".//collision[@name='C1_collision']/geometry/cylinder")
    new = candidate.find(".//collision[@name='C1_collision']/geometry/capsule")
    assert old is not None and new is not None
    assert old.findtext("radius") == new.findtext("radius") == "0.011"
    assert old.findtext("length") == new.findtext("length") == "4.0"
    new.tag = "cylinder"
    assert ET.tostring(original) == ET.tostring(candidate)
    data = json.loads(result.with_suffix(".json").read_text())
    assert not data["cable_collision_control"]["validated"]
    assert not data["cable_collision_control"]["deployment_default_changed"]
