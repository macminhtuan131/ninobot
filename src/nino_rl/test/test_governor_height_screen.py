"""The height contrast must not silently change floor, material or trial budget."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from run_governor_height_screen import make_height_world, PARENT, PLAN, ROOT


class HeightWorldTest(unittest.TestCase):
    def test_both_heights_have_expected_geometry_and_preserve_other_models(self):
        original=ET.parse(PARENT).getroot()
        with tempfile.TemporaryDirectory() as directory:
            for height in (.006,.022):
                path=Path(directory)/f"height_{height}.sdf"
                make_height_world(path,height)
                actual=ET.parse(path).getroot()
                for model in original.findall("world/model"):
                    if model.get("name")!="cable_bumps":
                        self.assertEqual(ET.tostring(model),ET.tostring(actual.find(
                            "world/model[@name='"+model.get("name")+"']")))
                for kind in ("collision","visual"):
                    item=actual.find("world/model[@name='cable_bumps']/link/"+kind)
                    parent=original.find("world/model[@name='cable_bumps']/link/"+kind)
                    pose=list(map(float,item.find("pose").text.split()))
                    self.assertEqual(pose[:3],[3.1,0.,height/2])
                    self.assertAlmostEqual(pose[5],math.radians(8.))
                    self.assertEqual(pose[3:5],list(map(float,parent.find("pose").text.split()))[3:5])
                    self.assertEqual(float(item.find("geometry/*/radius").text),height/2)
                    self.assertEqual(float(item.find("geometry/*/length").text),4.)
                    self.assertEqual(ET.tostring(item.find("surface")) if item.find("surface") is not None else None,
                                     ET.tostring(parent.find("surface")) if parent.find("surface") is not None else None)
                sidecar=json.loads(path.with_suffix(".json").read_text())
                self.assertEqual(sidecar["cables"][0]["radius_m"],height/2)

    def test_22mm_world_identical_to_previous_frozen_reference(self):
        previous=ROOT/"rl_runs/governor_frozen_repeats_2026-10-16/attempt_01/confirmation/repeat/scenario.sdf"
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"world.sdf"
            make_height_world(path,.022)
            self.assertEqual(path.read_bytes(),previous.read_bytes())

    def test_unplanned_height_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):make_height_world(Path(directory)/"world.sdf",.010)

    def test_protocol_retains_both_heights_and_controllers_for_each_seed(self):
        protocol=json.loads(PLAN.read_text())
        cases=protocol["case_order"]
        self.assertEqual(len(cases),protocol["maximum_attempts"])
        self.assertEqual(len(cases),8)
        self.assertEqual({tuple(row) for row in cases},
                         {(s,h,c) for s in (77310,77311) for h in (.006,.022) for c in ("full","reactive")})


if __name__=="__main__":unittest.main()
