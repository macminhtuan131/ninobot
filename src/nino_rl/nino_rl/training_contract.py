"""Prevent silent PPO/reward changes when continuing a checkpoint."""
from copy import deepcopy


def training_contract(config):
    revision = {"rocky_tracking": 31, "combined_course": 32}.get(config.get("task"), 30)
    contract = {"revision": revision,
            "phase_schedule": {key: deepcopy(config.get("curriculum", {}).get(key))
                               for key in ("enabled", "phase_steps", "phase_order")},
            **{key: deepcopy(value) for key, value in config.items()
            if key not in ("device", "seed", "curriculum", "terrain_curriculum", "reward")}}
    if config.get("task") == "combined_course":
        contract["dynamic_cables_enabled"] = bool(
            config.get("terrain_curriculum", {}).get("enabled", True))
    if config.get("rough_curriculum", {}).get("enabled", False):
        contract["revision"] = 33
        # These are selections inside the same declared curriculum. Terrain
        # bank contents, route definitions, reward and PPO remain immutable.
        runtime = contract.pop("rough_runtime", {})
        contract["rough_bank_digest"] = runtime.get("bank_digest")
    if config.get("action_mode") == "speed_yaw_reference":
        contract["revision"] = 34
        contract["action_interface"] = {
            "outputs": ["speed_scale", "yaw_reference"],
            "additive_torque": False,
            "history": "60 values; zero residual torque; previous speed/zero/yaw slots",
        }
    if config.get("odometry_assistance", {}).get("enabled", False):
        contract["revision"] = 35
        contract["estimated_pose_source"] = "imu_encoder_odometry"
        if config['odometry_assistance'].get('corridor_lidar', {}).get('enabled', False):
            contract['estimated_pose_source'] = 'imu_encoder_lidar_odometry'
    if config.get('navigation', {}).get('path_feedback', {}).get('enabled', False):
        if config.get('action_mode') != 'speed_yaw_reference':
            raise ValueError('Flat path feedback requires the two-action speed/yaw reference mode')
        contract['revision'] = 36
        contract['action_interface']['outputs'] = ['speed_scale', 'yaw_residual']
        contract['action_interface']['yaw_baseline'] = 'estimated_pose_pure_pursuit'
    if config.get('drive_controller', {}).get('parameters'):
        contract['revision'] = 37
    return contract


def validate_resume(model, config):
    expected = training_contract(config)
    saved = deepcopy(getattr(model, "nino_training_contract", None))
    # Revision 30 adds wheel-span lateral placement and a traversable road
    # groove while retaining the goal-first reward and lockstep corrections.
    if saved != expected:
        raise ValueError(
            "Checkpoint reward/policy/PPO contract differs or predates this patch. "
            "Start a NEW run without --resume. Resuming requires the same code "
            "revision and the matching run's --config. "
            "Curriculum --phase changes are allowed; old v2 models still support inference.")
    model.nino_training_contract = expected
