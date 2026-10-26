"""Transfer an actor to a new task without importing an obsolete value model."""

from __future__ import annotations

from copy import deepcopy


ACTOR_PREFIXES = (
    "pi_features_extractor.",
    "mlp_extractor.policy_net.",
    "action_net.",
)


def initialize_actor(target, source) -> tuple[str, ...]:
    """Copy the Gaussian action policy and leave critic/optimizer fresh.

    The source and target must already have matching observation/action spaces
    and action meanings. A strict key/shape check prevents partial transfer.
    """
    destination = target.policy.state_dict()
    original = source.policy.state_dict()
    actor_keys = tuple(
        key for key in destination
        if key == "log_std" or key.startswith(ACTOR_PREFIXES)
    )
    if set(destination) != set(original) or not actor_keys:
        raise ValueError("Source and target policy architectures differ")
    if any(destination[key].shape != original[key].shape for key in destination):
        raise ValueError("Source and target policy tensor shapes differ")
    transferred = deepcopy(destination)
    for key in actor_keys:
        transferred[key] = original[key].clone()
    target.policy.load_state_dict(transferred, strict=True)
    return actor_keys


def initialize_speed_yaw_actor(target, source) -> tuple[str, ...]:
    """Reuse a torque actor's encoder/speed head; never copy its torque outputs."""
    from nino_rl.control_v2 import validate_model, validate_action_mode
    size = target.observation_space.shape[0]
    validate_model(target, size, 2)
    source_actions = source.action_space.shape[0]
    if source_actions not in (2, 3):
        raise ValueError('Speed transfer requires a two- or three-action source')
    validate_model(source, size, source_actions)
    source_config = {'action_mode': 'speed_yaw_reference' if source_actions == 2 else 'wheel_torque'}
    source_config['navigation'] = deepcopy(getattr(source, 'nino_training_contract', {}).get('navigation', {}))
    validate_action_mode(source, source_config)
    destination, original = target.policy.state_dict(), source.policy.state_dict()
    head = {"action_net.weight", "action_net.bias", "log_std"}
    if set(destination) != set(original) or any(
            destination[key].shape != original[key].shape for key in destination if key not in head):
        raise ValueError("Speed transfer requires matching history/actor/critic architecture")
    trunk = tuple(key for key in destination if key.startswith(ACTOR_PREFIXES[:2]))
    if not trunk:
        raise ValueError("No compatible actor feature tensors")
    transferred = deepcopy(destination)
    for key in trunk:
        transferred[key] = original[key].clone()
    for key in ("action_net.weight", "action_net.bias"):
        transferred[key][0].copy_(original[key][0])
        transferred[key][1].zero_()  # New yaw mean starts at straight driving.
    transferred["log_std"][0].copy_(original["log_std"][0])
    target.policy.load_state_dict(transferred, strict=True)
    return trunk + ("action_net.weight[speed]", "action_net.bias[speed]", "log_std[speed]")
