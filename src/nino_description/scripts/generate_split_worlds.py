#!/usr/bin/env python3
"""Generate an extended rough specialist and the isolated flat cable course."""

import argparse
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

from generate_rocky_world import add_floor_piece
from generate_rough_section import generate as generate_rough


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "worlds/combined_hall.sdf"
FLAT_ORIGIN_X = 6.55


def remove_floor(structure, name):
    for suffix in ("collision", "visual"):
        element = structure.find(f"*[@name='{name}_{suffix}']")
        if element is None:
            raise ValueError(f"Missing {name}_{suffix} in {SOURCE}")
        structure.remove(element)


def generate(section="both"):
    source = ET.parse(SOURCE)
    original = source.getroot().find("world")
    if original is None or original.get("name") != "combined_hall":
        raise ValueError(f"Expected combined_hall in {SOURCE}")
    sections = ("rough", "flat") if section == "both" else (section,)
    for section in sections:
        if section == "rough":
            generate_rough(source.getroot())
            continue
        root = deepcopy(source.getroot())
        world = root.find("world")
        world.set("name", f"combined_{section}_section")
        structure = world.find("model[@name='enclosed_hall']/link[@name='structure']")
        if structure is None:
            raise ValueError("Missing hall structure")
        remove_floor(structure, "flat_cable_floor")
        rough = world.find("model[@name='rough_approach_ground']")
        cables = world.find("model[@name='cable_bumps']")
        if rough is None or cables is None:
            raise ValueError("Expected rough mesh and cables in combined world")
        world.remove(rough)
        # Gazebo wheel odometry starts at x=0 after an episode reset. Use local
        # coordinates so actor observations and ground-truth reward agree.
        for element in cables.findall("link/collision") + cables.findall("link/visual"):
            pose = element.find("pose")
            coordinates = pose.text.split()
            coordinates[0] = f"{float(coordinates[0]) - FLAT_ORIGIN_X:.6f}"
            pose.text = " ".join(coordinates)
        remove_floor(structure, "spawn_floor")
        add_floor_piece(structure, "flat_cable_floor", -2.0, 32.0,
                        "0.42 0.44 0.47 1")
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        target = ROOT / "worlds" / f"combined_{section}_section.sdf"
        tree.write(target, encoding="utf-8", xml_declaration=True)
        print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=("both", "rough", "flat"), default="both")
    generate(parser.parse_args().section)
