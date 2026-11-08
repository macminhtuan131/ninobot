"""Common-only scheduled controller ABI, separate from every frozen V3 source.

Both controller systems get the same causal100D sensor history +2current
plan features +previous requested scalar. Shared projection is in the environment.
No ROS, Torch, Gazebo, actor loading or collection is performed on import.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from nino_control.residual_velocity import ReferenceLimits, ResidualReference
from . import residual_stop_transfer as parent
from . import residual_guided_td3 as guided
from . import residual_guided_baseline as baseline
from .core import load_config
from .residual_factory_workflow import repo

CONTRACT_ID = 'nino_equal_information_common_103x1_v1'


def protocol():
    p = load_config(repo() / 'src/nino_rl/config/residual_equal_information_v1.yaml')
    if parent.fingerprint() != p['parent_fingerprint']:
        raise ValueError('Frozen stop-transfer prerequisite changed')
    if (p['scope'], p['scenario'], p['development_source_stops_s'], p['control_interval_s'],
            p['warmup_s'], p['horizon_s'], p['withdraw_lead_s'], p['common_bound_m_s'],
            p['inherited_residual_scale_m_s'], p['nominal_steady_m_s']) != (
            'offline_qualification_only', 'clear_box', [6., 8.], .1, .5, 14., .5, .005, .04, .2):
        raise ValueError('New conditions/authority require a versioned equal-information contract')
    if (p['training_transitions'], p['optimizer_updates'], p['physics_steps'], p['hardware_actions'],
            p['offline_fixture_maximum_transitions'], p['offline_fixture_steps_per_run']) != (0, 0, 0, 0, 840, 140):
        raise ValueError('Offline contract releases no optimizer, physics or hardware budget')
    expected = ['source_stop_remaining_over_horizon', 'common_window_open', 'previous_requested_scalar']
    if (p['observation']['current_features'] != expected or p['observation']['size'] != 103
            or p['observation']['inherited_history_size'] != 100 or p['observation']['history_frames'] != 5
            or p['action'] != dict(size=1, bounds=[-1., 1.], semantic='requested_common_before_shared_window_and_projection')):
        raise ValueError('Equal-information observation/action ABI changed')
    if p['training_release']['allowed'] or p['training_release']['timesteps_per_seed'] is not None:
        raise ValueError('New scientific training release needs its own protocol')
    return p


def fingerprint():
    paths = [Path(__file__), repo() / 'src/nino_rl/nino_rl/residual_equal_information.py',
             repo() / 'src/nino_rl/config/residual_equal_information_v1.yaml',
             repo() / 'src/nino_rl/scripts/residual_equal_information.sh']
    return hashlib.sha256(json.dumps(dict(parent=parent.fingerprint(), files={
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}), sort_keys=True).encode()).hexdigest()


def configuration(source_stop_s):
    p = protocol()
    if type(source_stop_s) not in (float, int) or source_stop_s not in p['development_source_stops_s']:
        raise ValueError('Only declared development stops6/8s; not an unseen test bank')
    c, g, task, condition = guided.configuration('clear_box')
    c['purpose'] = p['protocol_id']
    c['backend'].update(scenario_id='clear_box_equal_information_common_v1',
                        command_until_s=float(source_stop_s), horizon_s=p['horizon_s'])
    c['task'].update(command_until_s=float(source_stop_s), horizon_s=p['horizon_s'])
    task.update(protocol_id=p['protocol_id'], command_until_s=float(source_stop_s),
                horizon_s=p['horizon_s'], warmup_s=p['warmup_s'])
    return c, g, task, condition


def identity():
    p = protocol()
    c, g, task, _ = configuration(6.)
    contract = dict(id=CONTRACT_ID, fingerprint=fingerprint(),
        inherited_abi_sha256=guided.experiment_contract(c)['abi_sha256'],
        observation=p['observation'], action=p['action'], reward=p['reward'],
        mapping=dict(common_bound_m_s=p['common_bound_m_s'], inherited_scale_m_s=p['inherited_residual_scale_m_s'],
                     differential=0., shared_window='nominal steady, source forward, valid history/owner/sensors, before planned withdrawal'),
        source_plan=dict(stops=p['development_source_stops_s'], warmup_s=p['warmup_s'], horizon_s=p['horizon_s'],
                         withdraw_lead_s=p['withdraw_lead_s'], clock='episode decision ticks, not wall/GT/contact time'),
        guidance=g, estimator=task['estimator'], functional_proposals=task['functional_proposals'],
        reference_limits=c['reference_limits'], nominal_geometry=c['nominal_geometry'],
        replay_action='requested scalar, before shared gate and inherited 2D reference projection',
        training_released=False, hardware_authorized=False)
    contract['abi_sha256'] = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    return contract


def require_identity(actual, expected=None):
    if actual != (identity() if expected is None else expected):
        raise ValueError('Equal-information103D/1D identity mismatch; V3/Studio checkpoints cannot resume here')


class PlannedCommonAdapter:
    """A decision is prepared once, then consumed once. No privileged fields read."""
    def __init__(self, config, source_stop_s):
        self.p = protocol()
        if source_stop_s not in self.p['development_source_stops_s']:
            raise ValueError('Unsupported development stop')
        self.stop = float(source_stop_s)
        self.withdraw = self.stop - self.p['withdraw_lead_s']
        self.config = deepcopy(config)
        if config['control_interval_s'] != self.p['control_interval_s'] or config['reference_limits']['residual_wheel_m_s'] != self.p['inherited_residual_scale_m_s']:
            raise ValueError('Inherited scale/control interval changed')
        self.reset()

    def reset(self):
        self.nominal = ResidualReference(ReferenceLimits(**self.config['reference_limits']))
        self.next_tick = 0
        self.pending = None
        self.previous_request = 0.

    def prepare(self, observation, view, history_ready, *, done=False, latched=False):
        if self.pending is not None:
            raise RuntimeError('Consume the pending decision before advancing the nominal shaper')
        base = np.asarray(observation, dtype=np.float32)
        if base.shape != (100,) or not np.all(np.isfinite(base)) or np.max(np.abs(base)) > 5.:
            raise ValueError('Finite bounded causal100D inherited history required')
        if any(type(view[k]) is not bool for k in ('permission', 'sensors_fresh', 'fault', 'emergency_stop')):
            raise ValueError('Explicit valid permission/sensor/fault flags required')
        t = self.next_tick * self.p['control_interval_s']
        if t > self.p['horizon_s'] + 1e-8:
            raise ValueError('Decision clock beyond task horizon')
        source = view['baseline']
        nominal = self.nominal.compose(source, (0., 0.), self.p['control_interval_s'],
            permission=True, sensors_fresh=True, history_ready=True, command_age_s=0.)['body_reference']
        age = view['command_age_s']
        healthy = (view['permission'] and view['sensors_fresh'] and not view['fault'] and not view['emergency_stop']
                   and history_ready and not done and not latched and math.isfinite(age)
                   and 0 <= age <= self.nominal.limits.max_age_s)
        if not healthy:
            reason = 'invalid_history_source_or_permission'
        elif t >= self.withdraw - 1e-8:
            reason = 'planned_withdrawal'
        elif t < self.p['warmup_s'] - 1e-8 or source[0] <= 0:
            reason = 'source_not_forward'
        elif abs(nominal[0] - self.p['nominal_steady_m_s']) > 1e-8:
            reason = 'nominal_not_steady'
        else:
            reason = 'common_window_open'
        # Withdrawal countdown is derived from stop countdown and the shared
        # fixed lead; use the third scalar for known previous request so action
        # change cost never depends on a hidden gated-away command.
        features = np.array([(self.stop - t) / self.p['horizon_s'],
                             float(reason == 'common_window_open'), self.previous_request], np.float32)
        audit = dict(decision_tick=self.next_tick, decision_task_s=t, planned_source_stop_s=self.stop,
                     withdraw_at_task_s=self.withdraw, current_features=features.tolist(), window_open=reason == 'common_window_open',
                     reason=reason, nominal_shaped_body=nominal, truth_input=False,
                     clock='episode decision ticks; reference generator plan, not obstacle preview')
        self.pending = audit
        return np.concatenate((base, features)), deepcopy(audit)

    def project(self, requested):
        if self.pending is None:
            raise RuntimeError('Prepare the causal observation before requesting an action')
        a = np.asarray(requested, dtype=np.float32)
        if a.shape != (1,) or not np.all(np.isfinite(a)) or np.max(np.abs(a)) > 1.:
            raise ValueError('Finite normalized scalar action required; no clipping or V3 conversion')
        audit = self.pending
        common = float(a[0]) * self.p['common_bound_m_s'] if audit['window_open'] else 0.
        mapped = np.array([common / self.p['inherited_residual_scale_m_s'], 0.], np.float32)
        audit = dict(audit, requested_scalar=a.tolist(), requested_common_m_s=float(a[0]) * self.p['common_bound_m_s'],
                     windowed_common_m_s=common, inherited_controller_proposal=mapped.tolist(),
                     replay_action=a.tolist(), mapping='scalar common request -> shared window -> 2D inherited projection; yaw follower retained')
        self.pending = None
        self.previous_request = float(a[0])
        self.next_tick += 1
        return mapped, audit


def classical_request(observation):
    obs = np.asarray(observation, dtype=np.float32)
    if obs.shape != (103,) or not np.all(np.isfinite(obs)):
        raise ValueError('Classical controller consumes the same103D packet')
    return np.array([1. if obs[101] == 1. else 0.], np.float32)


class CommonScore(baseline.BaselineScore):
    """Independent nominal task + scalar request costs, including gated requests."""
    def __init__(self, c, task, condition):
        super().__init__(c, task, condition)
        p = protocol()
        self.reward_config = p['reward']
        self.common_bound = p['common_bound_m_s']
        self.previous = 0.

    def update_request(self, info, request, elapsed, physical_failure):
        _, task = super().update(info, elapsed, physical_failure)
        r = self.reward_config
        # Preserve the inherited physical penalty scale when action dimensionality
        # and range change: a full scalar request is0.005/0.04, not1 in V3 units.
        a = float(request[0]) * self.common_bound / r['request_cost_scale_m_s']
        w = r['weights']
        dt = self.c['control_interval_s']
        terms = dict(velocity_tracking=-w['velocity'] * (task['velocity_error_m_s'] / r['velocity_scale_m_s']) ** 2 * dt,
                     yaw_tracking=-w['yaw'] * (task['yaw_rate_error_rad_s'] / r['yaw_rate_scale_rad_s']) ** 2 * dt,
                     action_size=-w['action'] * a * a * dt,
                     action_change=-w['action_change'] * (a - self.previous) ** 2 / dt)
        self.previous = a
        if physical_failure:
            terms['physical_failure'] = -r['penalties']['physical_failure']
        if task['task_deadline']:
            if not task['marker_reached']:
                terms['missing_marker'] = -r['penalties']['missing_marker']
            if not task['stop_completed']:
                terms['not_stopped'] = -r['penalties']['not_stopped']
        task.update(reward_terms=terms, reward_id=r['id'])
        return sum(terms.values()), task


def environment(config, backend, task, condition):
    """Wrap the unchanged2D sensor/projection path with the new103D/1D ABI."""
    import gymnasium as gym
    from .residual_experiment import make_environment
    inner = make_environment(config, backend)

    class EqualInformationEnv(gym.Wrapper):
        def __init__(self):
            super().__init__(inner)
            self.backend = backend
            self.observation_space = gym.spaces.Box(-5., 5., (103,), dtype=np.float32)
            self.action_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)
            self.contract = identity()
            self.adapter = PlannedCommonAdapter(config, task['command_until_s'])
            self.done = True
            self.current_observation = None

        def prepare(self, base, *, done=False):
            return self.adapter.prepare(base, self.env.pipeline.last_view, self.env.pipeline.history.ready,
                                        done=done, latched=self.env.pipeline.reference.latched)

        def reset(self, **kwargs):
            self.adapter.reset()
            self.score = CommonScore(config, task, condition)
            self.steps = 0
            base, info = self.env.reset(**kwargs)
            self.current_observation, audit = self.prepare(base)
            self.done = False
            return self.current_observation.copy(), dict(info,
                inherited_experiment_contract=info.get('experiment_contract'),
                experiment_contract=self.contract['abi_sha256'], abi_sha256=self.contract['abi_sha256'],
                equal_information_identity=deepcopy(self.contract), plan_preview=audit)

        def step(self, requested):
            if self.done:
                raise RuntimeError('Reset required after terminal/truncation')
            before = self.current_observation.copy()
            mapped, audit = self.adapter.project(requested)
            base, _, term, trunc, info = self.env.step(mapped)
            self.steps += 1
            reward, task_result = self.score.update_request(info, audit['requested_scalar'], self.steps * config['control_interval_s'], term)
            np.testing.assert_allclose(audit['nominal_shaped_body'], task_result['nominal_shaped_body'], atol=1e-10, rtol=0)
            if task_result['task_deadline'] and not term:
                term, trunc = True, False
                info['termination_reason'] = 'task_success' if task_result['task_success'] else 'task_deadline_failure'
            self.done = bool(term or trunc)
            # An external timeout is bootstrapped from the continuing MDP state;
            # do not fabricate a closed window in its next observation. The
            # caller still must reset before collecting another transition.
            self.current_observation, next_preview = self.prepare(base, done=bool(term))
            return self.current_observation.copy(), reward, bool(term), bool(trunc), dict(info,
                task=task_result, reward_terms=task_result['reward_terms'], equal_information_identity=CONTRACT_ID,
                inherited_abi_sha256=info['abi_sha256'], inherited_experiment_contract=info['experiment_contract'],
                inherited_policy_proposal=info['policy_proposal'], policy_proposal=audit['requested_scalar'],
                abi_sha256=self.contract['abi_sha256'], experiment_contract=self.contract['abi_sha256'],
                equal_observation=before, equal_next_observation=self.current_observation.copy(),
                requested_scalar_action=audit['requested_scalar'], controller_proposal=mapped.tolist(),
                plan_projection=audit, next_plan_preview=next_preview,
                replay_semantics='103D observation + requested1D action before shared window/projection')

    return EqualInformationEnv()


def audit_replay(buffer, rows):
    if buffer.size() != len(rows):
        raise ValueError('Fixture replay/trace length mismatch')
    for i, r in enumerate(rows):
        for actual, expected in [(buffer.actions[i, 0], r['requested_scalar_action']),
                (buffer.observations[i, 0], r['equal_observation']),
                (buffer.next_observations[i, 0], r['equal_next_observation']),
                ([buffer.rewards[i, 0]], [r['reward']])]:
            np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0)
        if bool(buffer.dones[i, 0]) != r['done'] or bool(buffer.timeouts[i, 0]) != r['TimeLimit.truncated']:
            raise ValueError('Requested replay terminal/truncation mismatch')
    return dict(rows_checked=len(rows), requested_action_preserved=True,
                scope='Synthetic software fixture only; not training data or real/Gazebo evaluation')
