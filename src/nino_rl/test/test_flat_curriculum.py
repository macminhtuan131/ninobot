"""The flat curriculum advances only from real goal successes at its active stage."""

from pathlib import Path
import runpy

import numpy as np
import pytest
import yaml

from nino_rl.flat_curriculum import FlatCourseCurriculum


ROOT = Path(__file__).resolve().parents[3]


def test_optuna_fixture_exports_unlocked_curriculum():
    base = yaml.safe_load((ROOT / "src/nino_rl/config/combined_flat_curriculum.yaml").read_text())
    tuning = yaml.safe_load((ROOT / "src/nino_rl/config/combined_flat_curriculum_optuna.yaml").read_text())
    export = runpy.run_path(str(ROOT / "src/nino_rl/scripts/tune_split_optuna.py"))[
        "full_curriculum_config"
    ]
    assert tuning["flat_curriculum"]["fixed_stage"] == 1
    assert tuning["flat_curriculum"]["evaluation_stage"] == 1
    unlocked = export(tuning)
    assert unlocked == base
    assert tuning["flat_curriculum"]["fixed_stage"] == 1


def test_success_gate_replay_and_checkpoint():
    config = {
        "window_episodes": 4,
        "advance_success_rate": 0.75,
        "replay_probability": 1.0 - 1e-6,
        "stages": [
            {"cable_indices": [], "angle_range_deg": [-2, 2], "adaptive_features": 0},
            {"cable_indices": [0], "angle_range_deg": [-10, 10], "adaptive_features": 1},
            {"cable_indices": [0, 1], "angle_range_deg": [-30, 30], "adaptive_features": 2},
        ],
    }
    cables = [{"x": 2.45, "radius": .013}, {"x": 4.45, "radius": .010}]
    curriculum = FlatCourseCurriculum(config, cables, max_features=2)
    assert curriculum.sample_cables(np.random.default_rng(1), 0) == []
    for outcome in (True, True, False):
        assert not curriculum.record(outcome, 0)[2]
    assert curriculum.record(True, 0) == (0.75, 4, True)
    assert curriculum.stage_index == 1
    assert curriculum.sample_stage(np.random.default_rng(3)) == 0
    assert curriculum.record(True, 0) == (0.0, 0, False)
    assert curriculum.state()["outcomes"] == []
    sampled = curriculum.sample_cables(np.random.default_rng(2), 1)
    assert len(sampled) == 1 and sampled[0][:2] == (2.45, .013)
    curriculum.record(False, 1)
    restored = FlatCourseCurriculum(config, cables, max_features=2)
    restored.restore(curriculum.state())
    assert restored.state() == curriculum.state()
    with pytest.raises(ValueError):
        restored.restore({"stage_index": 8, "outcomes": []})


def test_fixed_evaluation_stage_never_advances():
    config = {
        "fixed_stage": 1,
        "stages": [
            {"cable_indices": [], "angle_range_deg": [-2, 2], "adaptive_features": 0},
            {"cable_indices": [0], "angle_range_deg": [-30, 30], "adaptive_features": 1},
        ],
    }
    curriculum = FlatCourseCurriculum(config, [{"x": 2.45, "radius": .013}], 1)
    assert curriculum.sample_stage(np.random.default_rng(3)) == 1
    for _ in range(40):
        assert curriculum.record(True, 1) == (0.0, 0, False)
    assert curriculum.stage_index == 1
