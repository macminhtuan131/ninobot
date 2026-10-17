"""Pre-run checks for scenario integrity and the instrumentation decision gate."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from run_frozen_governor_confirmation import ROOT, make_world, clearance_time, timestamps, evaluate_results


def test_scenario_changes_only_the_two_cable_poses(tmp_path):
    path = tmp_path/"scenario.sdf"
    scenario = dict(id="s0", x_m=2.5, angle_deg=-10, seeds=[76900,76901])
    make_world(path, scenario)
    source = ET.parse(ROOT/"src/nino_description/worlds/factory_floor_cable_box_capsule_contact_lab.sdf")
    new = ET.parse(path)
    for kind in ("collision", "visual"):
        query = f"world/model[@name='cable_bumps']/link/{kind}/pose"
        pose = new.getroot().find(query)
        values = list(map(float,pose.text.split()))
        assert values[0] == 2.5
        assert np.isclose(values[5], -np.pi/18)
        pose.text = source.getroot().find(query).text
    assert ET.tostring(source.getroot()) == ET.tostring(new.getroot())
    assert json.loads(path.with_suffix(".json").read_text())["cables"][0]["angle_deg"] == -10


def test_clearance_is_perpendicular_to_cable_and_missing_is_not_zero():
    ground = np.array([[0., .4, 0., 3.4, 0.], [1., .4, 0., 3.41, 0.]])
    assert clearance_time(ground, 0., dict(x_m=2.9, angle_deg=0)) == 0.
    assert clearance_time(ground, 0., dict(x_m=2.9, angle_deg=10)) == 1.
    assert clearance_time(ground, 0., dict(x_m=3.3, angle_deg=10)) is None


def test_timestamp_gate_rejects_stale_future_and_missing_data():
    row = dict(slip_joint_stamp_s=1., slip_ground_truth_stamp_s=1., slip_joint_age_s=.002,
               slip_ground_truth_age_s=.02, slip_joint_minus_ground_stamp_s=.018)
    assert timestamps([row])["passed"]
    assert not timestamps([{**row,"slip_joint_age_s":.012}])["passed"]
    assert not timestamps([{**row,"slip_ground_truth_age_s":-.002}])["passed"]
    assert not timestamps([{}])["passed"]


def complete_rows():
    rows = []
    for i in range(8):
        for profile in ("full","reactive"):
            value = 1. if profile=="full" else .9
            metric = dict(available=True, rms=value, slip_square_per_m=value, slip_square_integral_s=value)
            rows.append(dict(seed=i, scenario=f"s{i//2}", profile=profile, available=True,
                physical_pass=True, physical_success=True, native_replay=dict(matches_native=True),
                timestamps=dict(passed=True), time_s=17., physical_rmse_m=.01,
                native_slip_rms=value, whole_vertical_rms=1., whole_vertical_peak=2.,
                provenance={k:"same" for k in ("robot_description_sha256","governor_core_sha256","effort_drive_sha256","control_timing_sha256")},
                world_sha256=f"world{i//2}", primary=dict(whole_route=dict(metric),crossing=dict(metric)),
                shifted=dict(whole_route=dict(metric),crossing=dict(metric))))
    return rows


def test_decision_keeps_failures_and_missing_data_and_never_starts_tuning():
    rows = complete_rows()
    result = evaluate_results(rows)
    assert result["decision"].startswith("eligible")
    assert not result["tuning_started"]
    rows[1].update(physical_pass=False,physical_success=False)
    result = evaluate_results(rows)
    assert result["physical_failures"] == 1
    assert result["decision"] == "one_saved_trace_audit_before_continue_or_stop"
    rows[0]["available"] = False
    assert evaluate_results(rows)["decision"] == "measurement_first_no_tuning"


def test_repeated_grid_reversals_override_a_favorable_mean():
    rows = complete_rows()
    for r in rows:
        if r["profile"]=="reactive" and r["seed"]<2:
            r["shifted"]["whole_route"]["rms"] = 1.1
    result = evaluate_results(rows)
    assert result["grid_reversal_pairs"] == 2
    assert result["decision"] == "measurement_first_no_tuning"
