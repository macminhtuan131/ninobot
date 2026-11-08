"""Offline draft planner only: no learner, model, rclpy or Gazebo imports."""
import argparse
import hashlib
import json
from pathlib import Path


def default_config():
    source = Path(__file__).resolve().parents[1] / "config/residual_coverage_study_v1.json"
    if source.is_file():
        return source
    # Colcon copy installs place configs in share/, outside the Python package.
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory("nino_rl")) / "config/residual_coverage_study_v1.json"


DEFAULT_CONFIG = default_config()


def validate(p):
    """Reject release, budget drift and incomplete/duplicated comparison cells."""
    if (p["status"] != "draft_not_released" or p["training_released"] is not False
            or p["resume_allowed"] is not False or p["hardware_actions"] != 0
            or p["decision"]["minimum_effect_accepted"] is not None
            or p["decision"]["application_or_hardware_promotion"] is not False):
        raise ValueError("Draft only; a separately reviewed runner/release is required")
    if p["schema_version"] != 1 or p["scenario"] != "clear_box":
        raise ValueError("Draft schema/scenario changed")
    if p['decision'] != dict(primary='whole_14s_native_velocity_rmse',
            sensitivity_grids=['GT20ms','GTshift10ms'],minimum_relative_benefit_proposed=.05,
            minimum_effect_accepted=None,minimum_open_bin_fraction_proposed=.05,
            minimum_open_bin_count_proposed=10,maximum_support_age_s=.04,
            application_or_hardware_promotion=False):
        raise ValueError('Decision/gate proposal changed; review a new protocol')
    arms, seeds, f, b = p["arms"], p["seeds"], p["frozen"], p["budget"]
    if arms != ["A_gaussian", "C_stratified_probes"] or seeds != [11, 22, 33]:
        raise ValueError("Fixed two-arm, three-seed study required")
    expected_frozen = dict(observation_size=103, action_size=1, history_frames=5,
        common_bound_m_s=.005, control_interval_s=.1, steps_per_episode=140,
        source_stops_s=[6., 8.], algorithm_source="residual_reliable_td3_v1.yaml",
        learning_starts=64, gradient_steps=1, policy_delay=2, exploration_sigma=.1,
        reward_projection_controller_physics="unchanged_parent_contract")
    if f != expected_frozen:
        raise ValueError("Frozen ABI/learning schedule changed; not this comparison")
    c = p["collection"]
    if (c["shared_uniform_warmup_transitions"] != 64
            or c["probe_every_eligible_open_decisions"] != 4
            or c["probe_bin_edges"] != [-1., -.5, 0., .5, 1.]
            or c["probe_observation_index"] != 101
            or c['rng_streams'] != ['initialization','warmup','gaussian','probe_order','probe_jitter','replay']
            or c["replay_action"] != "actual_requested_scalar_before_shared_projection"):
        raise ValueError("Causal coverage/replay contract changed")
    train = [(r["arm"], r["seed"]) for r in p["training_order"]]
    expected = {(a, s) for a in arms for s in seeds}
    if len(train) != 6 or set(train) != expected:
        raise ValueError("Training cells missing or duplicated")
    if train != [("A_gaussian", 11), ("C_stratified_probes", 11),
                 ("C_stratified_probes", 22), ("A_gaussian", 22),
                 ("A_gaussian", 33), ("C_stratified_probes", 33)]:
        raise ValueError("Fixed training order changed")
    evaluation = [(r["arm"], r.get("seed"), r["source_stop_s"]) for r in p["evaluation_order"]]
    expected_eval = {(a, s, t) for a, s in expected for t in (6., 8.)}
    expected_eval |= {(a, None, t) for a in ("B0", "Classical_scheduled") for t in (6., 8.)}
    if len(evaluation) != 16 or set(evaluation) != expected_eval:
        raise ValueError("Evaluation cells missing or duplicated")
    expected_order = [("B0", None, 6.), (arms[0], 11, 6.), (arms[1], 11, 6.),
        ("Classical_scheduled", None, 8.), (arms[1], 22, 8.), (arms[0], 22, 8.),
        (arms[0], 33, 6.), (arms[1], 33, 6.), ("Classical_scheduled", None, 6.),
        (arms[1], 11, 8.), (arms[0], 11, 8.), ("B0", None, 8.),
        (arms[0], 22, 6.), (arms[1], 22, 6.), (arms[1], 33, 8.), (arms[0], 33, 8.)]
    if evaluation != expected_order:
        raise ValueError("Fixed evaluation order changed")
    n, steps, warmup = len(train), b["training_transitions_per_learner"], f["learning_starts"]
    if steps != 1024:
        raise ValueError("No automatic longer training")
    critic = (steps - warmup) * f["gradient_steps"]
    actor = critic // f["policy_delay"]
    launches = n * ((steps + f["steps_per_episode"] - 1) // f["steps_per_episode"])
    eval_ticks = len(evaluation) * f["steps_per_episode"]
    derived = dict(training_transitions_maximum=n * steps,
        critic_updates_per_learner=critic, actor_updates_per_learner=actor,
        critic_updates_maximum=n * critic, actor_updates_maximum=n * actor,
        training_launches_maximum=launches, evaluation_launches_maximum=len(evaluation),
        evaluation_transitions_maximum=eval_ticks,
        control_transitions_maximum=n * steps + eval_ticks,
        gazebo_launches_maximum=launches + len(evaluation))
    if any(b[k] != v for k, v in derived.items()) or (b["retries"], b["extra_physics_smokes"], b["wall_deadline_s"]) != (0, 0, 10800):
        raise ValueError("Budget arithmetic or stop policy mismatch")
    for value in p["parent"].values():
        if len(value) != 64 or any(x not in "0123456789abcdef" for x in value):
            raise ValueError("Invalid parent SHA256")
    return dict(valid=True, executable=False, training_released=False, **derived)


def load(path=DEFAULT_CONFIG):
    p = json.loads(Path(path).read_text())
    validate(p)
    return p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    p = load(args.config)
    print(json.dumps(dict(validate(p), config_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest()), indent=2))


if __name__ == "__main__":
    main()
