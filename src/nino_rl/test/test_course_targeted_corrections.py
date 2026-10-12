"""Protect single-variable flat correction and geometry-preserving rough repair."""
import importlib.util
from pathlib import Path
from copy import deepcopy

import pytest
import yaml

ROOT = Path(__file__).parents[3]
spec = importlib.util.spec_from_file_location("targeted_courses", ROOT / "src/nino_rl/scripts/run_course_targeted_corrections.py")
targeted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(targeted)


def test_flat_only_slip_weight_changes():
    original = yaml.safe_load((ROOT / "rl_runs/flat_value_scaled_seed43_v1/pilot.yaml").read_text())
    candidate = deepcopy(original)
    candidate["reward_v2"]["slip_weight"] *= 1.5
    assert targeted.flat_change(original, candidate) == candidate
    assert original["reward_v2"]["slip_weight"] != candidate["reward_v2"]["slip_weight"]
    candidate["ppo"]["learning_rate"] *= 2
    with pytest.raises(ValueError, match="only increase slip"):
        targeted.flat_change(original, candidate)


def test_rough_preserves_geometry_estimator_gates_and_e1_s1():
    original = yaml.safe_load((ROOT / "rl_runs/rough_trial8_validation_v1/correction.yaml").read_text())
    override = yaml.safe_load((ROOT / "src/nino_rl/config/rough_n1_alignment_override.yaml").read_text())
    candidate = targeted.rough_change(original, override)
    assert candidate["routes"]["stop_align_route_ids"] == ["N1", "S1"]
    for key in original:
        if key != "routes":
            assert candidate[key] == original[key]
    for key in original["routes"]:
        if key not in ("revision", "stop_align_route_ids"):
            assert candidate["routes"][key] == original["routes"][key]
    override["routes"]["gate_radius_m"] = 1.
    with pytest.raises(ValueError, match="Only the declared"):
        targeted.rough_change(original, override)


def test_new_flat_contract_rejects_original_optimizer_resume():
    import sys
    sys.path.insert(0, str(ROOT / "src/nino_rl"))
    original_path = ROOT / "rl_runs/flat_value_scaled_seed43_v1/python/nino_rl/training_contract.py"
    spec = importlib.util.spec_from_file_location("old_flat_contract", original_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    config = yaml.safe_load((ROOT / "rl_runs/flat_value_scaled_seed43_v1/pilot.yaml").read_text())
    candidate = deepcopy(config)
    candidate["reward_v2"]["slip_weight"] *= 1.5
    namespace = {}
    exec(original_path.read_text().replace('contract["revision"] = 38', 'contract["revision"] = 40'), namespace)
    model = type("Saved", (), {"nino_training_contract": old.training_contract(config)})()
    assert namespace["training_contract"](candidate)["revision"] == 40
    with pytest.raises(ValueError, match="differs"):
        namespace["validate_resume"](model, candidate)


def test_rough_changed_profile_rejects_old_optimizer_resume():
    source = ROOT / "rl_runs/rough_wall_recovery_v16/python/nino_rl/training_contract.py"
    namespace = {}
    exec(source.read_text(), namespace)
    original = yaml.safe_load((ROOT / "rl_runs/rough_trial8_validation_v1/correction.yaml").read_text())
    override = yaml.safe_load((ROOT / "src/nino_rl/config/rough_n1_alignment_override.yaml").read_text())
    candidate = targeted.rough_change(original, override)
    model = type("Saved", (), {"nino_training_contract": namespace["training_contract"](original)})()
    with pytest.raises(ValueError, match="differs"):
        namespace["validate_resume"](model, candidate)
