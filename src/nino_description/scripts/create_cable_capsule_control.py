#!/usr/bin/env python3
"""Diagnostic cylinder/capsule A/B. Never changes the deployed/default map.

Only the isolated cable collision primitive changes. The cylindrical section
has the original radius/length; rounded end caps are far outside the E1 track.
"""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def generate(root=ROOT):
    source = Path(root)/"worlds/factory_floor_cable_box_contact_lab.sdf"
    metadata = json.loads(source.with_suffix(".json").read_text())
    if metadata["variant"] != "cable_box" or len(metadata.get("cables", [])) != 1 or metadata.get("depressions"):
        raise ValueError("Capsule diagnostic is restricted to one cable on the corrected box floor")
    original = source.read_text()
    pattern = r'(<collision name="C1_collision">)(.*?)(</collision>)'
    matches = list(re.finditer(pattern, original, re.S))
    if len(matches) != 1:
        raise ValueError("Expected one C1 collision")
    match = matches[0]
    interior = match.group(2)
    if interior.count("<cylinder>") != 1:
        raise ValueError("Expected original cylinder collision")
    interior = interior.replace("<cylinder>", "<capsule>").replace("</cylinder>", "</capsule>")
    output = source.with_name("factory_floor_cable_box_capsule_contact_lab.sdf")
    output.write_text(original[:match.start(2)]+interior+original[match.end(2):])
    metadata.update(variant="cable_box_capsule", world_file=output.name,
        cable_collision_control=dict(revision="cylinder_capsule_AB_2026_10_16",
            parent_world=source.name, parent_world_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            change="Only C1 collision cylinder replaced by capsule; local radius/cylindrical-section length, pose, visuals and friction unchanged",
            radius_m=.011, cylindrical_section_length_m=4., total_capsule_length_m=4.022,
            validated=False, deployment_default_changed=False,
            qualification="Contact-numerics sensitivity control, not a deformable cable or verified physical correction"))
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2)+"\n")
    return output


if __name__ == "__main__":
    print(generate())
