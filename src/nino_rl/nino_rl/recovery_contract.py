"""Opt-in simulation contract. Historical Goal100 checkpoints are incompatible."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

from nino_control.residual_velocity import ResidualReference, wheels_to_body
from .unknown_step_runtime import SensorOnlyCommonAdapter, UnknownTaskData

CONTRACT_ID = 'nino_recovery_history100_accepted_common_v2'


def implementation_sources():
    root = Path(__file__).parents[3]
    paths = list(Path(__file__).parent.glob('*.py'))
    paths += list((root/'src/nino_control/nino_control').glob('*.py'))
    for folder in ('src/nino_rl/config', 'src/nino_control/config'):
        for extension in ('*.yaml', '*.json'):
            paths += list((root/folder).glob(extension))
    paths += [root/'src/nino_rl/launch/training_sim.launch.py',
              root/'src/nino_description/launch/sim.launch.py']
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


@dataclass(frozen=True)
class StartBudget:
    physical_goal_m: float
    estimated_stop_m: float
    odometry_uncertainty_m: float
    stopping_uncertainty_m: float
    maximum_initial_error_m: float
    maximum_initial_heading_rad: float

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError('Positive finite proposed start budget required')
        if self.maximum_initial_error_m > self.margin_m:
            raise ValueError('Initial pose budget cannot fit physical goal/estimated stop margin')

    @property
    def margin_m(self):
        return (self.physical_goal_m - self.estimated_stop_m
                - self.odometry_uncertainty_m - self.stopping_uncertainty_m)

    def check(self, geometry, declared_progress_m=0., declared_cross_m=0.,
              declared_heading_rad=0., remaining_path_m=0.):
        position = math.hypot(geometry['progress_m']-declared_progress_m,
                              geometry['cross_track_m']-declared_cross_m)
        angle = geometry['heading_error_rad']-declared_heading_rad
        angle = abs(math.atan2(math.sin(angle), math.cos(angle)))
        endpoint_bound = position + 2*remaining_path_m*math.sin(angle/2.)
        if (endpoint_bound > self.maximum_initial_error_m
                or angle > self.maximum_initial_heading_rad):
            raise UnknownTaskData('Initial physical pose exceeds declared start budget; no motion')
        return dict(position_error_m=position, heading_error_rad=angle,
                    endpoint_error_bound_m=endpoint_bound,
                    declared_pose_used_by_estimator=True, truth_used_for_guidance=False)


class AcceptedCommonReference(ResidualReference):
    """Shape baseline, then intersect a single common delta with feasible bounds."""
    def compose(self, baseline, action, dt, authority=0., **health):
        old = self.previous
        trace = super().compose(baseline, (0., 0.), dt, authority, **health)
        if self.latched:
            return trace
        try:
            common, differential = action
            if not math.isfinite(common) or not -1 <= common <= 1 or differential != 0.:
                raise ValueError('Accepted-common contract requires scalar common only')
        except (TypeError, ValueError):
            self.previous, self.latched = (0., 0.), True
            trace.update(body_reference=(0., 0.), accepted_reference_wheel_m_s=(0., 0.),
                         reason='invalid_common_action')
            return trace
        limits = self.limits
        base = trace['shaped_baseline_wheel_m_s']
        gain = limits.residual_wheel_m_s * authority if health['history_ready'] else 0.
        requested = gain * common if tuple(baseline) != (0., 0.) else 0.
        step = limits.wheel_acceleration_m_s2 * dt
        lower, upper = -gain, gain
        for previous, shaped in zip(old, base):
            lower = max(lower, -limits.wheel_speed_m_s-shaped, previous-step-shaped)
            upper = min(upper, limits.wheel_speed_m_s-shaped, previous+step-shaped)
        speed = sum(base) / 2.
        lower, upper = max(lower, -limits.forward_m_s-speed), min(upper, limits.forward_m_s-speed)
        if lower > upper + 1e-9:
            raise RuntimeError('Shaped baseline has no feasible common correction')
        delta = max(lower, min(upper, requested))
        accepted = tuple(v + delta for v in base)
        self.previous = accepted
        trace.update(proposal=(common, 0.), proposed_residual_wheel_m_s=(requested, requested),
                     accepted_reference_wheel_m_s=accepted,
                     body_reference=wheels_to_body(*accepted, limits.separation_m),
                     accepted_policy_delta_wheel_m_s=(delta, delta),
                     feasible_common_interval_m_s=(lower, upper),
                     implementation_revision=CONTRACT_ID,
                     reference_modified=abs(requested-delta) > 1e-9)
        return trace


class RecoveryAdapter(SensorOnlyCommonAdapter):
    def __init__(self, config):
        super().__init__(config)
        self.pipeline.reference = AcceptedCommonReference(self.pipeline.reference.limits)
        payload = dict(inherited=self.identity, contract_id=CONTRACT_ID,
                       projection='baseline_first_feasible_accepted_common', hardware_authorized=False,
                       sources={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                           Path(__file__),
                           Path(__file__).parents[2]/'nino_control/nino_control/residual_pipeline.py',
                           Path(__file__).parents[2]/'nino_control/nino_control/residual_velocity.py')})
        self.identity = dict(payload, abi_sha256=hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()).hexdigest())

    def project(self, requested):
        result = super().project(requested)
        result['task_contract_id'] = CONTRACT_ID
        return result
