"""Goal-driven Gazebo adapter; frozen planned-stop backends remain unchanged."""
from copy import deepcopy

from .causal_planar_estimator import CausalPlanarEstimator
from .factory_velocity_backend import FactoryVelocityBackend, simulation_seconds
from .residual_guidance import PoseSample, apply_guidance
from .residual_factory_workflow import repo
from .residual_workflow import save
from .studio_startup_repair import StudioStartupBackend
from .unknown_step_geometry import collision_envelope
from .unknown_step_runtime import EstimatedGoalReference, PhysicalSample


class UnknownStepBackend(StudioStartupBackend):
    def __init__(self, *args, expected_envelope, **kwargs):
        self.goal_reference = None
        self.expected_envelope = deepcopy(expected_envelope)
        super().__init__(*args, **kwargs)

    def reset(self, seed=None):
        self.goal_reference = None
        view, info = super().reset(seed=seed)
        actual = collision_envelope(self.episode_dir/'robot.urdf', repo()/'src/nino_description')
        if actual != self.expected_envelope:
            raise ValueError('Loaded robot collision envelope/kinematics differs from frozen bank')
        save(self.episode_dir/'verified_collision_envelope.json', actual)
        physical = self._physical(view, motion_requested=False)
        return view, dict(info, physical_sample=physical, truth_used_for_guidance=False,
                          goal_source='causal_wheel_IMU_estimator_not_sim_truth',
                          planned_stop_schedule=False)

    def view(self):
        # Explicitly bypass GuidedBackend.view's stop6/8 timer. Retain the same
        # raw sensor assembler and inherited causal estimator callbacks/reset.
        view = FactoryVelocityBackend.view(self)
        if not self.active:
            return view
        now = simulation_seconds(self.time)
        if self.cached_view is not None and self.cached_view['stamp_s'] == now:
            return deepcopy(self.cached_view)
        with self.lock:
            records = self.estimator.advance(now)
            estimate = self.estimator.estimate()
        for record in records:
            self._store('estimator_update', record['stamp_s'], record)
        if self.goal_reference is None:
            self.goal_reference = EstimatedGoalReference(self.gconf, epoch=self.estimator.epoch)
            self.guidance = self.goal_reference.guidance
        self.goal_reference.update_pose(PoseSample(*estimate['pose'], estimate['stamp_s'], now,
            self.gconf['pose_frame_id'], self.gconf['pose_source'], self.gconf['clock_id'], estimate['epoch']))
        reference = self.goal_reference.command(now, permission=bool(view['permission']))
        reference['follower_requested_reference'] = list(reference['reference'])
        if now-self.start_time < self.protocol['warmup_s']-1e-8:
            reference['reference'] = [0., 0.]
            reference['profile_phase'] = 'zero_warmup'
        else:
            reference['profile_phase'] = 'goal_stop' if self.goal_reference.stopped else 'path_following'
        view['clock_id'] = self.gconf['clock_id']
        view = apply_guidance(view, reference)
        view['estimator_audit'] = estimate
        self._store('guidance_reference', now, reference)
        self.cached_view = deepcopy(view)
        return view

    def _physical(self, view, *, motion_requested):
        with self.lock:
            truth = deepcopy(self.messages['truth'])
            drive = deepcopy(self.messages['drive'])
            wheel = deepcopy(self.messages['wheel'])
        values, d = truth['values'], drive['values']
        p = values['pose']
        # These are the acknowledged requested body references, NOT a fabricated
        # wheel-target telemetry channel or claimed hardware motor execution.
        v, w = d['requested_linear_m_s'], d['requested_yaw_rad_s']
        separation = self.config['nominal_geometry']['separation']
        physical = PhysicalSample(stamp_s=truth['stamp_s'], decision_stamp_s=view['stamp_s'],
            pose_m_rad=(p[0], p[1], p[2], values['roll'], values['pitch'], p[3]),
            body_speed_norm_m_s=values['speed_norm'], body_yaw_rad_s=values['yaw_rate'],
            wheel_rad_s=tuple(wheel['values']),
            accepted_reference_m_s=(v-separation*w/2, v+separation*w/2),
            motion_requested=bool(motion_requested), owner_intervention=not view['permission'] or view['emergency_stop'],
            drive_fault=view['fault'])
        physical.validate()
        self._store('physical_boundary', truth['stamp_s'], dict(
            decision_stamp_s=view['stamp_s'], truth_stamp_s=truth['stamp_s'],
            wheel_stamp_s=wheel['stamp_s'], drive_stamp_s=drive['stamp_s'],
            accepted_reference_evidence='post_projection_reference_matched_to_effort_drive_request_ACK',
            truth_used_for_guidance=False))
        return physical

    def advance_reference(self, v, w, dt):
        previous = deepcopy(self.cached_view)
        motion = previous is not None and any(abs(x) > 1e-8 for x in previous['baseline'])
        view, labels, term, trunc, info = super().advance_reference(v, w, dt)
        physical = self._physical(view, motion_requested=motion)
        self.flush_raw()
        return view, labels, term, trunc, dict(info, physical_sample=physical,
            truth_used_for_guidance=False, planned_stop_schedule=False,
            baseline_source='causal_estimator_goal_follower')
