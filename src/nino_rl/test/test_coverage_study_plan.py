"""Draft budgets and causal collection contract; no physics or optimizer."""
from copy import deepcopy
import pytest
from nino_rl.coverage_study_plan import load, validate


def test_matched_schedule_and_full_bounded_matrix():
    p = load()
    result = validate(p)
    assert not result["executable"] and not result["training_released"]
    assert result["training_transitions_maximum"] == 6144
    assert result["critic_updates_maximum"] == 5760
    assert result["actor_updates_maximum"] == 2880
    assert result["evaluation_transitions_maximum"] == 2240
    assert result["gazebo_launches_maximum"] == 64


@pytest.mark.parametrize("mutation", ["release", "resume", "hardware", "warmup", "replay",
    "duplicate_train", "duplicate_eval", "train_order", "eval_order", "extra_steps", "arithmetic", "retry", "accepted_effect"])
def test_drift_is_rejected(mutation):
    p = deepcopy(load())
    if mutation == "release": p["training_released"] = True
    elif mutation == "resume": p["resume_allowed"] = True
    elif mutation == "hardware": p["hardware_actions"] = 1
    elif mutation == "warmup": p["frozen"]["learning_starts"] = 280
    elif mutation == "replay": p["collection"]["replay_action"] = "actor_output_before_probe_override"
    elif mutation == "duplicate_train": p["training_order"][1] = p["training_order"][0]
    elif mutation == "duplicate_eval": p["evaluation_order"][1] = p["evaluation_order"][0]
    elif mutation == "train_order": p["training_order"].reverse()
    elif mutation == "eval_order": p["evaluation_order"].reverse()
    elif mutation == "extra_steps": p["budget"]["training_transitions_per_learner"] = 2048
    elif mutation == "arithmetic": p["budget"]["critic_updates_maximum"] += 1
    elif mutation == "retry": p["budget"]["retries"] = 1
    elif mutation == "accepted_effect": p["decision"]["minimum_effect_accepted"] = .05
    with pytest.raises(ValueError): validate(p)
