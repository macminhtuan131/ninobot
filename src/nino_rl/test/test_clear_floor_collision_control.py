"""Protect the single-variable mesh/box physical comparison."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest

ROOT=Path(__file__).resolve().parents[3]
WORLDS=ROOT/"src/nino_description/worlds"
SELECT="world/model[@name='factory_contact_floor']/link[@name='terrain']/collision[@name='terrain_collision']"


@pytest.mark.parametrize("variant",["clear","cable"])
def test_box_control_changes_only_collision_pose_and_geometry(variant):
    mesh=ET.parse(WORLDS/f"factory_floor_{variant}_contact_lab.sdf").getroot()
    box=ET.parse(WORLDS/f"factory_floor_{variant}_box_contact_lab.sdf").getroot()
    for tree in (mesh,box):
        collision=tree.find(SELECT)
        collision.remove(collision.find("geometry"))
        collision.remove(collision.find("pose"))
    assert ET.tostring(mesh)==ET.tostring(box)


@pytest.mark.parametrize("variant",["clear","cable"])
def test_box_has_same_floor_extent_and_top_without_a_second_support_plane(variant):
    tree=ET.parse(WORLDS/f"factory_floor_{variant}_box_contact_lab.sdf")
    collision=tree.find(SELECT)
    size=[float(v) for v in collision.find("geometry/box/size").text.split()]
    pose=[float(v) for v in collision.find("pose").text.split()]
    assert size==[10.,7.,.1] and pose==[3.,0.,-.05,0.,0.,0.]
    assert pose[2]+size[2]/2==0.
    assert [pose[0]-size[0]/2,pose[0]+size[0]/2,pose[1]-size[1]/2,pose[1]+size[1]/2]==[-2.,8.,-3.5,3.5]
    assert len(tree.findall("world/model[@name='factory_contact_floor']/link/collision"))==1
    assert collision.find("geometry/mesh") is None


@pytest.mark.parametrize("variant",["clear","cable"])
def test_control_metadata_identifies_exact_parent_and_remains_unvalidated(variant):
    metadata=json.loads((WORLDS/f"factory_floor_{variant}_box_contact_lab.json").read_text())
    control=metadata["diagnostic_control"]
    assert metadata["variant"]==variant+"_box"
    assert control["parent_world_sha256"]==hashlib.sha256((WORLDS/control["parent_world"]).read_bytes()).hexdigest()
    assert not control["validated"] and control["not_for_depression_worlds"]
    parent=json.loads((WORLDS/control["parent_world"]).with_suffix(".json").read_text())
    assert metadata["cables"]==parent["cables"]


def test_box_profile_preserves_all_controller_estimator_and_scoring_settings():
    from nino_rl.core import load_config
    configs=ROOT/"src/nino_rl/config"
    mesh=load_config(configs/"factory_floor_stability_pi_check.yaml")
    box=load_config(configs/"factory_floor_clear_box_pi_check.yaml")
    assert box["simulation_model"].pop("floor_collision_control")["shape"]=="box"
    assert mesh==box


def test_cable_box_keeps_controller_and_physical_scoring():
    from nino_rl.core import load_config
    configs=ROOT/"src/nino_rl/config"
    clear=load_config(configs/"factory_floor_clear_box_pi_check.yaml")
    cable=load_config(configs/"factory_floor_single_cable_box_pi_check.yaml")
    clear["simulation_model"]["floor_collision_control"].pop("validation_scope")
    cable["simulation_model"]["floor_collision_control"].pop("validation_scope")
    for cfg in (clear,cable): cfg.pop("research_map")
    assert clear==cable


@pytest.mark.parametrize("variant",["mixed","pothole","groove"])
def test_generator_rejects_worlds_with_negative_terrain(variant,tmp_path):
    import runpy
    generate=runpy.run_path(str(ROOT/"src/nino_description/scripts/create_clear_floor_box_control.py"))["generate"]
    with pytest.raises(ValueError,match="never depressions"):
        generate(root=tmp_path,variant=variant)
    assert not list(tmp_path.iterdir())
