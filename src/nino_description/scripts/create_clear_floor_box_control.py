#!/usr/bin/env python3
"""Generate a flat-floor box control for clear/cable labs; preserve obstacles."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def generate(root=ROOT,variant="clear"):
    if variant not in ("clear","cable"):
        raise ValueError("Box floor is restricted to flat clear/cable worlds, never depressions")
    source=Path(root)/f"worlds/factory_floor_{variant}_contact_lab.sdf"
    metadata=json.loads(source.with_suffix(".json").read_text())
    if metadata.get("depressions"):
        raise ValueError("Cannot cover carved depressions with a flat box")
    original=source.read_text()
    pattern=r'(<collision name="terrain_collision">)(.*?)(</collision>)'
    matches=list(re.finditer(pattern,original,re.S))
    if len(matches)!=1: raise ValueError("Expected exactly one clear terrain collision")
    match=matches[0]
    interior=match.group(2)
    interior,count=re.subn(r"<pose>.*?</pose>","<pose>3.000000000 0.000000000 -0.050000000 0 0 0</pose>",interior,count=1,flags=re.S)
    if count!=1: raise ValueError("Missing terrain collision pose")
    interior,count=re.subn(r"<mesh>.*?</mesh>","<box>\n              <size>10.000000000 7.000000000 0.100000000</size>\n            </box>",interior,count=1,flags=re.S)
    if count!=1: raise ValueError("Expected clear mesh geometry")
    candidate=original[:match.start(2)]+interior+original[match.end(2):]
    output=source.with_name(f"factory_floor_{variant}_box_contact_lab.sdf")
    output.write_text(candidate)
    metadata.update(variant=variant+"_box",world_file=output.name,
        diagnostic_control=dict(revision="clear_mesh_vs_box_v1_2026_10_15",
            parent_world=source.name,parent_world_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            change="Only terrain collision mesh and its pose replaced; visuals and surface parameters retained",
            collision_kind="solid_box",size_m=[10.,7.,.1],center_xyz_m=[3.,0.,-.05],top_z_m=0.,
            validated=False,not_for_depression_worlds=True))
    output.with_suffix(".json").write_text(json.dumps(metadata,indent=2)+"\n")
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant",choices=["clear","cable"],default="clear")
    args=parser.parse_args()
    print(generate(variant=args.variant))
