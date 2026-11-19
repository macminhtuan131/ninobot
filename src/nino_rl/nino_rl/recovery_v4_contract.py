"""Opt-in software contract. No ROS adapter, actor observation, or training release."""
from dataclasses import asdict, dataclass, fields
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml

CONTRACT_ID = "nino_recovery_slowdown_v4_software_contract"
NEUTRAL_ACTION = -1.0
RELEASE = "software_contract_only"


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _positive(instance):
    for field in fields(instance):
        value = getattr(instance, field.name)
        if not _number(value) or value <= 0:
            raise ValueError(f"{field.name} must be finite and positive")


def _strict(data, names):
    if not isinstance(data, dict) or set(data) != set(names):
        raise ValueError(f"Expected exactly these fields: {sorted(names)}")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class SlowdownSettings:
    max_slowdown_m_s: float = .02
    wheel_speed_m_s: float = .4
    forward_m_s: float = .4
    yaw_rad_s: float = .5
    wheel_acceleration_m_s2: float = .1
    separation_m: float = .34273666
    maximum_source_age_s: float = .04
    maximum_command_age_s: float = .2
    maximum_interval_s: float = .15
    history_frames: int = 5

    def __post_init__(self):
        _positive(self)
        if type(self.history_frames) is not int:
            raise ValueError("history_frames must be an integer")
        if self.max_slowdown_m_s > min(self.forward_m_s, self.wheel_speed_m_s):
            raise ValueError("Slowdown bound must fit the reference envelope")


@dataclass(frozen=True)
class ProjectionState:
    baseline_wheel_m_s: tuple[float, float] = (0., 0.)
    final_wheel_m_s: tuple[float, float] = (0., 0.)
    baseline_latched: bool = False
    final_latched: bool = False

    def __post_init__(self):
        for pair in (self.baseline_wheel_m_s, self.final_wheel_m_s):
            if type(pair) is not tuple or len(pair) != 2 or not all(_number(x) and x >= 0 for x in pair):
                raise ValueError("Wheel state must be a finite nonnegative pair")
        if type(self.baseline_latched) is not bool or type(self.final_latched) is not bool:
            raise ValueError("Latch fields must be booleans")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data, settings=SlowdownSettings()):
        _strict(data, (f.name for f in fields(cls)))
        try:
            state = cls(tuple(data["baseline_wheel_m_s"]), tuple(data["final_wheel_m_s"]), data["baseline_latched"], data["final_latched"])
        except (TypeError, KeyError) as error:
            raise ValueError("Malformed projection state") from error
        if not _state_in_envelope(state, settings):
            raise ValueError("Restored state exceeds projection envelope")
        if any(latch and pair != (0., 0.) for latch, pair in ((state.baseline_latched, state.baseline_wheel_m_s), (state.final_latched, state.final_wheel_m_s))):
            raise ValueError("Latched reference must be zero")
        return state


def _state_in_envelope(state, settings):
    for pair in (state.baseline_wheel_m_s, state.final_wheel_m_s):
        if max(pair) > settings.wheel_speed_m_s or sum(pair)/2 > settings.forward_m_s or abs(pair[1]-pair[0])/settings.separation_m > settings.yaw_rad_s:
            return False
    delta = tuple(b-f for b,f in zip(state.baseline_wheel_m_s, state.final_wheel_m_s))
    return abs(delta[0]-delta[1]) <= 1e-12 and min(delta) >= -1e-12 and max(delta) <= settings.max_slowdown_m_s+1e-12


@dataclass(frozen=True)
class Health:
    permission: bool
    emergency_stop: bool
    fault: bool
    imu_age_s: float
    wheel_age_s: float
    command_age_s: float
    history_real_frames: int


@dataclass(frozen=True)
class ProjectionResult:
    next_state: ProjectionState
    proposed_action: float
    requested_slowdown_m_s: float
    accepted_slowdown_m_s: float
    nominal_body_reference: tuple[float, float]
    final_body_reference: tuple[float, float]
    reason: str
    learning_eligible: bool


def project_slowdown(settings, state, nominal_body_reference, action, dt_s, health):
    """Shape nominal independently, then intersect the equal-wheel slowdown interval.

    Ordinary output obeys per-wheel slew. A latched reference STOP overrides
    slew and says nothing about measured physical braking. Reset is a new state.
    """
    def stop(reason):
        stopped = ProjectionState((0., 0.), (0., 0.), True, True)
        return ProjectionResult(stopped, action, 0., 0., (0., 0.), (0., 0.), reason, False)

    if not _state_in_envelope(state, settings):
        return stop("invalid_state")
    if state.baseline_latched or state.final_latched:
        return stop("stop_latched")
    valid_health = (
        all(type(x) is bool for x in (health.permission, health.emergency_stop, health.fault))
        and all(_number(x) and x >= 0 for x in (health.imu_age_s, health.wheel_age_s, health.command_age_s))
        and type(health.history_real_frames) is int and health.history_real_frames >= 0)
    valid_input = (
        _number(action) and -1 <= action <= 1 and _number(dt_s) and 0 < dt_s <= settings.maximum_interval_s
        and isinstance(nominal_body_reference, tuple) and len(nominal_body_reference) == 2
        and all(_number(x) for x in nominal_body_reference))
    if not valid_health or not valid_input:
        return stop("invalid_input")
    if not health.permission or health.emergency_stop or health.fault:
        return stop("authority_or_fault")
    if max(health.imu_age_s, health.wheel_age_s) > settings.maximum_source_age_s or health.command_age_s > settings.maximum_command_age_s:
        return stop("stale_source")
    v, yaw = nominal_body_reference
    half = yaw * settings.separation_m / 2
    if v < 0 or abs(yaw) > settings.yaw_rad_s or v < abs(half) or abs(half) > settings.wheel_speed_m_s:
        return stop("outside_forward_envelope")
    v = min(v, settings.forward_m_s, settings.wheel_speed_m_s - abs(half))
    if v < abs(half):
        return stop("infeasible_nominal")
    requested_nominal = (v - half, v + half)
    slew = settings.wheel_acceleration_m_s2 * dt_s
    differences = tuple(a-b for a,b in zip(requested_nominal, state.baseline_wheel_m_s))
    factor = min(1., slew / max(map(abs, differences))) if any(differences) else 1.
    baseline = tuple(b + factor*d for b,d in zip(state.baseline_wheel_m_s, differences))
    common = sum(baseline)/2
    half = (baseline[1]-baseline[0])/2
    warmup = health.history_real_frames < settings.history_frames
    requested = settings.max_slowdown_m_s * (action+1)/2
    desired = common if warmup else max(0., common-requested)
    low = max(abs(half), common-settings.max_slowdown_m_s,
              state.final_wheel_m_s[0]-slew+half, state.final_wheel_m_s[1]-slew-half)
    high = min(common, settings.forward_m_s, settings.wheel_speed_m_s-abs(half),
               state.final_wheel_m_s[0]+slew+half, state.final_wheel_m_s[1]+slew-half)
    if low > high + 1e-12 or (warmup and not low-1e-12 <= common <= high+1e-12):
        return stop("infeasible_projection")
    accepted_common = min(high, max(low, desired))
    final = (max(0., accepted_common-half), max(0., accepted_common+half))
    next_state = ProjectionState(baseline, final)
    nominal = (common, 2*half/settings.separation_m)
    final_body = (accepted_common, nominal[1])
    accepted_slowdown = min(settings.max_slowdown_m_s, max(0., common-accepted_common))
    return ProjectionResult(next_state, action, requested, accepted_slowdown, nominal, final_body,
                            "history_warmup" if warmup else "projected", not warmup)


@dataclass(frozen=True)
class MissionReference:
    route_length_m: float = 4.
    cruise_m_s: float = .2
    startup_acceleration_m_s2: float = .1
    approach_distance_m: float = .4
    deadline_s: float = 40.

    def __post_init__(self):
        _positive(self)
        if self.approach_distance_m > self.route_length_m:
            raise ValueError("Approach must fit inside route")

    def target(self, elapsed_s, route_progress_m):
        if not _number(elapsed_s) or elapsed_s < 0 or not _number(route_progress_m):
            raise ValueError("Invalid mission state")
        if elapsed_s >= self.deadline_s:
            return 0.
        approach = min(1., max(0., (self.route_length_m-route_progress_m)/self.approach_distance_m))
        return min(self.cruise_m_s*approach, self.startup_acceleration_m_s2*elapsed_s)


class EndReason(str, Enum):
    ONGOING = "ongoing"
    SUCCESS = "success"
    PHYSICAL_FAILURE = "physical_failure"
    INTRINSIC_DEADLINE = "intrinsic_deadline"
    EXTERNAL_SAMPLING = "external_sampling"
    CAMPAIGN_CUTOFF = "campaign_cutoff"
    INVALID_SOURCE = "invalid_source"


@dataclass(frozen=True)
class EndFlags:
    terminated: bool
    truncated: bool
    bootstrap: bool
    valid_transition: bool


def end_flags(reason):
    if not isinstance(reason, EndReason):
        raise ValueError("Unknown end reason")
    if reason is EndReason.INVALID_SOURCE:
        return EndFlags(False, False, False, False)
    terminal = reason in (EndReason.SUCCESS, EndReason.PHYSICAL_FAILURE, EndReason.INTRINSIC_DEADLINE)
    truncated = reason in (EndReason.EXTERNAL_SAMPLING, EndReason.CAMPAIGN_CUTOFF)
    return EndFlags(terminal, truncated, not terminal, True)


@dataclass(frozen=True)
class RewardSettings:
    route_length_m: float = 4.
    corridor_m: float = .1
    cross_scale_m: float = .05
    heading_scale_rad: float = .5
    speed_scale_m_s: float = .05
    progress_weight: float = 1.
    cross_weight: float = .1
    heading_weight: float = .1
    speed_weight: float = .1
    time_weight: float = .02
    action_weight: float = .01
    action_change_weight: float = .001
    stability_weight: float = .01
    success_bonus: float = 5.
    failure_penalty: float = 10.
    deadline_s: float = 40.

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if not _number(value) or value < 0:
                raise ValueError(f"Invalid reward field {field.name}")
        if min(self.route_length_m, self.corridor_m, self.cross_scale_m, self.heading_scale_rad, self.speed_scale_m_s, self.deadline_s) <= 0:
            raise ValueError("Reward scales and horizon must be positive")


@dataclass(frozen=True)
class RewardState:
    highest_credited_progress_m: float = 0.
    previous_elapsed_s: float = 0.
    previous_accepted_slowdown_fraction: float = 0.
    closed_reason: EndReason = EndReason.ONGOING
    highest_seen_progress_m: float = 0.

    def __post_init__(self):
        if not all(_number(x) and x >= 0 for x in (self.highest_credited_progress_m, self.previous_elapsed_s, self.highest_seen_progress_m)) or not _number(self.previous_accepted_slowdown_fraction) or not 0 <= self.previous_accepted_slowdown_fraction <= 1 or not isinstance(self.closed_reason, EndReason):
            raise ValueError("Invalid reward state")


@dataclass(frozen=True)
class RewardLabels:
    elapsed_s: float
    progress_m: float
    cross_error_m: float
    heading_error_rad: float
    speed_error_m_s: float
    accepted_slowdown_fraction: float
    stability_cost: float
    end_reason: EndReason = EndReason.ONGOING


@dataclass(frozen=True)
class RewardResult:
    next_state: RewardState
    total: float
    terms: Mapping[str, float]
    end: EndFlags
    end_reason: EndReason


def score_reward(settings, state, labels):
    """Corridor high-water credit is bounded objective shaping, not PBRS."""
    numeric = (labels.elapsed_s, labels.progress_m, labels.cross_error_m, labels.heading_error_rad,
               labels.speed_error_m_s, labels.accepted_slowdown_fraction, labels.stability_cost)
    if not all(_number(x) for x in numeric) or labels.elapsed_s <= state.previous_elapsed_s or not 0 <= labels.accepted_slowdown_fraction <= 1 or labels.stability_cost < 0:
        raise ValueError("Invalid or nonmonotonic reward labels")
    flags = end_flags(labels.end_reason)
    if not flags.valid_transition:
        raise ValueError("Invalid sources must not create a reward transition")
    if state.highest_credited_progress_m > settings.route_length_m or state.highest_seen_progress_m > settings.route_length_m or state.highest_credited_progress_m > state.highest_seen_progress_m:
        raise ValueError("Reward state belongs to another route")
    if state.closed_reason is not EndReason.ONGOING:
        raise ValueError("Episode already closed; reset before scoring another transition")
    reason = labels.end_reason
    if reason is EndReason.INTRINSIC_DEADLINE and labels.elapsed_s < settings.deadline_s:
        raise ValueError("Deadline terminal before deadline")
    if reason is EndReason.SUCCESS and labels.elapsed_s > settings.deadline_s:
        raise ValueError("Success after intrinsic task deadline")
    if labels.elapsed_s >= settings.deadline_s and reason in (EndReason.ONGOING, EndReason.EXTERNAL_SAMPLING, EndReason.CAMPAIGN_CUTOFF):
        reason = EndReason.INTRINSIC_DEADLINE
    flags = end_flags(reason)
    dt = labels.elapsed_s-state.previous_elapsed_s
    seen = max(state.highest_seen_progress_m, min(settings.route_length_m, max(0., labels.progress_m)))
    credit = state.highest_credited_progress_m
    if abs(labels.cross_error_m) <= settings.corridor_m:
        credit = min(seen, credit+(seen-state.highest_seen_progress_m))
    q = labels.accepted_slowdown_fraction
    terms = {
        "progress": settings.progress_weight*(credit-state.highest_credited_progress_m)/settings.route_length_m,
        "cross": -settings.cross_weight*_squared_ratio(labels.cross_error_m, settings.cross_scale_m)*dt,
        "heading": -settings.heading_weight*_squared_ratio(labels.heading_error_rad, settings.heading_scale_rad)*dt,
        "speed": -settings.speed_weight*_squared_ratio(labels.speed_error_m_s, settings.speed_scale_m_s)*dt,
        "time": -settings.time_weight*dt,
        "action": -settings.action_weight*q*q*dt,
        "action_change": -settings.action_change_weight*(q-state.previous_accepted_slowdown_fraction)**2/dt,
        "stability": -settings.stability_weight*labels.stability_cost*dt,
        "terminal": settings.success_bonus if reason is EndReason.SUCCESS else -settings.failure_penalty if flags.terminated else 0.,
    }
    total = sum(terms.values())
    if not all(math.isfinite(value) for value in (*terms.values(), total)):
        raise ValueError("Nonfinite reward result; no usable transition")
    next_state = RewardState(credit, labels.elapsed_s, q, reason, seen)
    return RewardResult(next_state, total, MappingProxyType(terms), flags, reason)


def _squared_ratio(value, scale):
    ratio = value / scale
    return ratio * ratio


def state_metadata(state, health, mission, reward_state, elapsed_s, route_progress_m):
    """Exact reducer/task metadata, not an implemented actor observation vector."""
    return dict(projection=state.to_dict(), history_real_frames=health.history_real_frames,
                mission_target_m_s=mission.target(elapsed_s, route_progress_m),
                remaining_time_fraction=max(0., (mission.deadline_s-elapsed_s)/mission.deadline_s),
                reward_state=asdict(reward_state))


@dataclass(frozen=True)
class V4Config:
    projection: SlowdownSettings
    mission: MissionReference
    reward: RewardSettings
    learning_rate: float


class _UniqueKeysLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node):
    pairs = loader.construct_pairs(node, deep=True)
    if any(not isinstance(key, str) for key, _ in pairs) or len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("Configuration keys must be unique strings")
    return dict(pairs)


_UniqueKeysLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_config(path):
    try:
        data = yaml.load(Path(path).read_text(), Loader=_UniqueKeysLoader)
    except yaml.YAMLError as error:
        raise ValueError("Malformed YAML configuration") from error
    _strict(data, ("schema_version", "contract_id", "release", "numeric_status", "projection", "mission", "reward", "algorithm", "curriculum"))
    expected = dict(schema_version=1, contract_id=CONTRACT_ID, release=RELEASE, numeric_status="experimental_proposals_not_operational_thresholds")
    if any(data[key] != value or type(data[key]) is not type(value) for key,value in expected.items()):
        raise ValueError("Unsupported contract metadata")
    parsed = []
    for name, cls in (("projection", SlowdownSettings), ("mission", MissionReference), ("reward", RewardSettings)):
        _strict(data[name], (f.name for f in fields(cls)))
        parsed.append(cls(**data[name]))
    _strict(data["algorithm"], ("name", "learning_rate"))
    _strict(data["curriculum"], ("maximum_stage",))
    rate = data["algorithm"]["learning_rate"]
    if data["algorithm"]["name"] != "TD3" or not _number(rate) or rate <= 0 or type(data["curriculum"]["maximum_stage"]) is not int or data["curriculum"]["maximum_stage"] != 0:
        raise ValueError("Only the locked software fixture configuration is supported")
    projection, mission, reward = parsed
    if mission.route_length_m != reward.route_length_m or mission.deadline_s != reward.deadline_s:
        raise ValueError("Mission and reward route/deadline must agree")
    if mission.cruise_m_s > projection.forward_m_s:
        raise ValueError("Mission exceeds forward reference envelope")
    return V4Config(projection, mission, reward, rate)


def identity(config):
    return dict(contract_id=CONTRACT_ID, release=RELEASE, config_sha256=_hash(asdict(config)),
                implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                action_sha256=_hash(dict(map="slowdown=(a+1)/2", neutral=-1, replay="requested_normalized_before_projection", max_m_s=config.projection.max_slowdown_m_s)),
                projection_sha256=_hash(dict(version="equal_delta_forward_latched_v1", settings=asdict(config.projection), state=[f.name for f in fields(ProjectionState)])),
                reward_sha256=_hash(dict(version="corridor_high_water_not_pbrs_v1", settings=asdict(config.reward))),
                observation_spec_sha256=_hash(dict(status="metadata_only_no_actor_adapter", fields=["baseline_wheels", "final_wheels", "baseline_latched", "final_latched", "history_real_frames", "mission_target", "remaining_time_fraction", "reward_state"])))


def require_identity(config, candidate):
    if candidate != identity(config):
        raise ValueError("Checkpoint/replay identity is incompatible, including all v3 contracts")


def require_release(config, operation):
    if operation != "software_contract":
        raise PermissionError("V4 has no Gazebo, optimizer, or hardware release")
    identity(config)
