"""Protect the independent-seed repeat and unchanged qualification criteria."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/run_flat_seed_repeat.py"
spec = importlib.util.spec_from_file_location("flat_seed_repeat", SCRIPT)
repeat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repeat)


def test_only_training_seed_and_provenance_change():
    original = {"seed": 42, "reward_v2": {"slip_weight": .2}, "ppo": {"learning_rate": 1e-5},
                "drive_controller": {"velocity_kp": .3}, "reward_alignment_experiment": {"old": True}}
    updated = repeat.repeat_config(original, 43)
    assert updated == {key: (43 if key == "seed" else value) for key, value in original.items()
                       if key != "reward_alignment_experiment"}
    assert original["seed"] == 42
    updated["reward_v2"]["slip_weight"] = .9
    assert original["reward_v2"]["slip_weight"] == .2


@pytest.mark.parametrize("seed", [42, -1])
def test_same_or_invalid_seed_rejected(seed):
    with pytest.raises(ValueError, match="different nonnegative"):
        repeat.repeat_config({"seed": 42}, seed)


def test_optional_trace_change_does_not_change_reward_or_control():
    original = Path(__file__).parents[3] / "rl_runs/flat_value_scaled_pilot_v1/python/nino_rl/ros_env.py"
    code = original.read_text()
    modified = repeat.trace_snapshot(code)
    extras = ('                "slip_left": slip_left, "slip_right": slip_right,\n'
              '                "imu_square_integral": imu["square_integral"],\n')
    assert modified.replace(extras, "") == code
    compile(modified, "traced_ros_env.py", "exec")


def test_quality_gate_rejects_slip_regression_despite_smoother_ride():
    result = {"ppo": {"report": {"success_rate": 1.}}, "comparison": {"metrics": {
        "rms_vertical_acceleration_m_s2": {"candidate": 2., "baseline": 3.},
        "rms_wheel_slip": {"candidate": .21, "baseline": .2},
        "time_seconds": {"candidate": 18., "baseline": 17.5},
        "truth_path_rmse_m": {"candidate": .03, "baseline": .03}}}}
    plan = {"promotion_gates": {"comfort_or_slip_ratio_max": .9, "other_metric_ratio_max": 1.,
        "mean_completion_seconds": 18.5, "physical_rmse_ratio_max": 1.05}}
    gates = repeat.promotion_gates(result, plan)
    assert gates["physical_arrival"] and gates["completion"] and gates["tracking"]
    assert not gates["quality"]
    result["comparison"]["metrics"]["rms_wheel_slip"]["candidate"] = .2
    assert repeat.promotion_gates(result, plan)["quality"]
