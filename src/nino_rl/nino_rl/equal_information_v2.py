"""Isolated common103_v2 controller/reward contract for long obstacle & DR training.

Preserves frozen equal_information_contract (v1) with explicit experimental changes:
1. Gates out action_size and action_change penalties when window_open == False so
   unapplied requests have zero cost. This changes the objective; improved Critic
   calibration or controller benefit has not been established.
2. Opens obstacle ('box_c1_6mm') and bounded Domain Randomization ('box_c1_6mm_dr')
   scenarios with +/-0.02 m/s common residual authority (within inherited 0.04 m/s scale).
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from nino_control.residual_velocity import ReferenceLimits, ResidualReference

from . import equal_information_contract as v1_contract
from . import residual_guided_baseline as baseline
from . import residual_guided_td3 as guided
from .coverage_reset_readiness import require_uninhibited_transition
from .residual_experiment import make_environment
from .residual_factory_workflow import prepare as prepare_factory, repo

CONTRACT_ID = 'nino_equal_information_common_103x1_v2'
REWARD_ID = 'common103_v2_gated_request_cost'

SCENARIO_SPECS = {
    'box_c1_6mm': dict(
        label='Gờ cáp 6 mm · common103_v2 (±0,02 m/s · sạch phạt đóng cổng)',
        base_world='box_c1_6mm',
        common_bound_m_s=0.02,
        domain_randomization=None,
    ),
    'box_c1_6mm_dr': dict(
        label='Gờ cáp 6 mm + Domain Randomization có biên · common103_v2',
        base_world='box_c1_6mm',
        common_bound_m_s=0.02,
        domain_randomization=dict(
            floor_mu_range=[0.85, 1.15],
            bump_x_m_range=[0.55, 0.75],
            bump_radius_m_range=[0.0025, 0.0035],
        ),
    ),
    'clear_box': dict(
        label='Sàn sạch đối chứng · common103_v2 (±0,005 m/s · sạch phạt đóng cổng)',
        base_world='clear_box',
        common_bound_m_s=0.005,
        domain_randomization=None,
    ),
}


def fingerprint() -> str:
    payload = dict(
        parent_v1=v1_contract.fingerprint(),
        file_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def scenario_spec(scenario: str) -> dict:
    if scenario not in SCENARIO_SPECS:
        raise ValueError(f'Unsupported common103_v2 scenario: {scenario}')
    return deepcopy(SCENARIO_SPECS[scenario])


def configuration(source_stop_s: float, scenario: str = 'box_c1_6mm'):
    p = v1_contract.protocol()
    if type(source_stop_s) not in (float, int) or float(source_stop_s) not in p['development_source_stops_s']:
        raise ValueError('Supported source stops are 6.0s and 8.0s')
    spec = scenario_spec(scenario)
    c, g, task, condition = guided.configuration(spec['base_world'])
    c['purpose'] = CONTRACT_ID
    c['training']['allowed'] = False
    c['hardware_authority'] = 0.0
    c['backend'].update(
        scenario_id=f'{scenario}_common103_v2',
        command_until_s=float(source_stop_s),
        horizon_s=float(p['horizon_s']),
    )
    c['task'].update(command_until_s=float(source_stop_s), horizon_s=float(p['horizon_s']))
    task.update(
        protocol_id=CONTRACT_ID,
        command_until_s=float(source_stop_s),
        horizon_s=float(p['horizon_s']),
        warmup_s=float(p['warmup_s']),
    )
    condition['scenario'] = scenario
    return c, g, task, condition


def identity(scenario: str = 'box_c1_6mm') -> dict:
    p = v1_contract.protocol()
    spec = scenario_spec(scenario)
    c, g, task, _ = configuration(6.0, scenario=scenario)
    reward_cfg = deepcopy(p['reward'])
    reward_cfg['id'] = REWARD_ID
    reward_cfg['closed_window_request_penalty'] = 'gated_zero'
    contract = dict(
        id=CONTRACT_ID,
        fingerprint=fingerprint(),
        scenario=scenario,
        scenario_spec=spec,
        inherited_abi_sha256=guided.experiment_contract(c)['abi_sha256'],
        observation=dict(
            size=103,
            inherited_history_size=100,
            history_frames=5,
            current_features=[
                'source_stop_remaining_over_horizon',
                'common_window_open',
                'previous_effective_scalar',
            ],
        ),
        action=p['action'],
        reward=reward_cfg,
        mapping=dict(
            common_bound_m_s=spec['common_bound_m_s'],
            inherited_scale_m_s=p['inherited_residual_scale_m_s'],
            differential=0.0,
            shared_window='nominal steady, source forward, valid history/owner/sensors, before planned withdrawal',
        ),
        source_plan=dict(
            stops=p['development_source_stops_s'],
            warmup_s=p['warmup_s'],
            horizon_s=p['horizon_s'],
            withdraw_lead_s=p['withdraw_lead_s'],
            clock='episode decision ticks',
        ),
        guidance=g,
        estimator=task['estimator'],
        functional_proposals=task['functional_proposals'],
        reference_limits=c['reference_limits'],
        nominal_geometry=c['nominal_geometry'],
        hardware_authorized=False,
    )
    contract['abi_sha256'] = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    return contract


def sample_dr_params(rng: np.random.Generator, scenario: str = 'box_c1_6mm_dr') -> dict:
    spec = scenario_spec(scenario)
    dr = spec['domain_randomization']
    if dr is None:
        return dict(floor_mu=1.0, bump_x_m=0.65, bump_radius_m=0.003, randomized=False)
    return dict(
        floor_mu=float(rng.uniform(*dr['floor_mu_range'])),
        bump_x_m=float(rng.uniform(*dr['bump_x_m_range'])),
        bump_radius_m=float(rng.uniform(*dr['bump_radius_m_range'])),
        randomized=True,
    )


def build_dr_world_sdf(source_sdf: Path, out_path: Path, dr_params: dict) -> Path:
    """Create a standalone bounded-DR obstacle SDF without altering factory assets."""
    bounds = scenario_spec('box_c1_6mm_dr')['domain_randomization']
    for key, field in (('floor_mu', 'floor_mu_range'), ('bump_x_m', 'bump_x_m_range'),
                       ('bump_radius_m', 'bump_radius_m_range')):
        value = dr_params.get(key)
        if (isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)
                or not bounds[field][0] <= value <= bounds[field][1]):
            raise ValueError('DR parameter outside declared bounds: ' + key)
    source_tree = ET.parse(source_sdf)
    tree = deepcopy(source_tree)
    world = tree.getroot().find('world')
    for model in list(world.findall('model')):
        if model.get('name') != 'enclosed_hall':
            world.remove(model)

    mu = f"{float(dr_params['floor_mu']):.5f}"
    ground = ET.SubElement(world, 'model', name='controlled_box_floor')
    ET.SubElement(ground, 'static').text = 'true'
    link = ET.SubElement(ground, 'link', name='ground')
    for tag in ('collision', 'visual'):
        node = ET.SubElement(link, tag, name='floor_' + tag)
        ET.SubElement(node, 'pose').text = '3 0 -0.05 0 0 0'
        geom = ET.SubElement(node, 'geometry')
        box = ET.SubElement(geom, 'box')
        ET.SubElement(box, 'size').text = '10 7 0.1'
        if tag == 'collision':
            surface = ET.SubElement(node, 'surface')
            friction = ET.SubElement(surface, 'friction')
            ode = ET.SubElement(friction, 'ode')
            ET.SubElement(ode, 'mu').text = mu
            ET.SubElement(ode, 'mu2').text = mu

    bump_x = float(dr_params['bump_x_m'])
    bump_r = float(dr_params['bump_radius_m'])
    model = ET.SubElement(world, 'model', name='cable_bumps')
    ET.SubElement(model, 'static').text = 'true'
    cables = ET.SubElement(model, 'link', name='cables')
    for tag in ('collision', 'visual'):
        node = deepcopy(source_tree.find('.//' + tag + "[@name='C1_" + tag + "']"))
        node.find('pose').text = f'{bump_x:.5f} 0 {bump_r:.5f} 1.57079632679 0 0'
        node.find('geometry/cylinder/radius').text = f'{bump_r:.5f}'
        cables.append(node)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding='utf-8', xml_declaration=True)
    return out_path


class PlannedCommonAdapterV2:
    """103D/1D causal adapter tracking previous effective scalar for clean Critic signal."""

    def __init__(self, config: dict, source_stop_s: float, scenario: str = 'box_c1_6mm'):
        self.p = v1_contract.protocol()
        if float(source_stop_s) not in self.p['development_source_stops_s']:
            raise ValueError('Unsupported source stop')
        self.spec = scenario_spec(scenario)
        self.scenario = scenario
        self.common_bound = float(self.spec['common_bound_m_s'])
        self.stop = float(source_stop_s)
        self.withdraw = self.stop - float(self.p['withdraw_lead_s'])
        self.config = deepcopy(config)
        if (
            config['control_interval_s'] != self.p['control_interval_s']
            or config['reference_limits']['residual_wheel_m_s'] != self.p['inherited_residual_scale_m_s']
        ):
            raise ValueError('Inherited scale or control interval changed')
        self.reset()

    def reset(self):
        self.nominal = ResidualReference(ReferenceLimits(**self.config['reference_limits']))
        self.next_tick = 0
        self.pending = None
        self.previous_effective_scalar = 0.0

    def prepare(self, observation, view: dict, history_ready: bool, *, done: bool = False, latched: bool = False):
        if self.pending is not None:
            raise RuntimeError('Consume pending decision before advancing nominal shaper')
        base = np.asarray(observation, dtype=np.float32)
        if base.shape != (100,) or not np.all(np.isfinite(base)) or np.max(np.abs(base)) > 5.0:
            raise ValueError('Finite bounded causal 100D inherited history required')
        if any(type(view[k]) is not bool for k in ('permission', 'sensors_fresh', 'fault', 'emergency_stop')):
            raise ValueError('Explicit boolean health flags required')
        t = self.next_tick * self.p['control_interval_s']
        if t > self.p['horizon_s'] + 1e-8:
            raise ValueError('Decision clock beyond task horizon')
        source = view['baseline']
        nominal = self.nominal.compose(
            source,
            (0.0, 0.0),
            self.p['control_interval_s'],
            permission=True,
            sensors_fresh=True,
            history_ready=True,
            command_age_s=0.0,
        )['body_reference']
        age = view['command_age_s']
        healthy = bool(
            view['permission']
            and view['sensors_fresh']
            and not view['fault']
            and not view['emergency_stop']
            and history_ready
            and not done
            and not latched
            and math.isfinite(age)
            and 0.0 <= age <= self.nominal.limits.max_age_s
        )
        if not healthy:
            reason = 'invalid_history_source_or_permission'
        elif t >= self.withdraw - 1e-8:
            reason = 'planned_withdrawal'
        elif t < self.p['warmup_s'] - 1e-8 or source[0] <= 0.0:
            reason = 'source_not_forward'
        elif abs(nominal[0] - self.p['nominal_steady_m_s']) > 1e-8:
            reason = 'nominal_not_steady'
        else:
            reason = 'common_window_open'

        window_open = reason == 'common_window_open'
        features = np.array(
            [
                (self.stop - t) / self.p['horizon_s'],
                float(window_open),
                self.previous_effective_scalar,
            ],
            dtype=np.float32,
        )
        audit = dict(
            decision_tick=self.next_tick,
            decision_task_s=t,
            planned_source_stop_s=self.stop,
            withdraw_at_task_s=self.withdraw,
            scenario=self.scenario,
            common_bound_m_s=self.common_bound,
            current_features=features.tolist(),
            window_open=window_open,
            reason=reason,
            nominal_shaped_body=nominal,
            truth_input=False,
        )
        self.pending = audit
        return np.concatenate((base, features)), deepcopy(audit)

    def project(self, requested):
        if self.pending is None:
            raise RuntimeError('Prepare causal observation before requesting action')
        a = np.asarray(requested, dtype=np.float32)
        if a.shape != (1,) or not np.all(np.isfinite(a)) or np.max(np.abs(a)) > 1.0:
            raise ValueError('Finite normalized scalar action in [-1, 1] required')
        audit = self.pending
        effective_scalar = float(a[0]) if audit['window_open'] else 0.0
        common = effective_scalar * self.common_bound
        mapped = np.array([common / self.p['inherited_residual_scale_m_s'], 0.0], dtype=np.float32)
        audit = dict(
            audit,
            requested_scalar=a.tolist(),
            effective_scalar=effective_scalar,
            unapplied_closed_gate_request=float(a[0]) if not audit['window_open'] else 0.0,
            requested_common_m_s=float(a[0]) * self.common_bound,
            windowed_common_m_s=common,
            inherited_controller_proposal=mapped.tolist(),
            replay_action=a.tolist(),
        )
        self.pending = None
        self.previous_effective_scalar = effective_scalar
        self.next_tick += 1
        return mapped, audit


def classical_request(observation, scenario: str = 'box_c1_6mm') -> np.ndarray:
    """Emit exact physical +0.005 m/s steady compensation regardless of scenario bound."""
    obs = np.asarray(observation, dtype=np.float32)
    if obs.shape != (103,) or not np.all(np.isfinite(obs)):
        raise ValueError('Classical controller requires finite 103D observation')
    bound = float(scenario_spec(scenario)['common_bound_m_s'])
    scalar = 0.005 / bound if obs[101] == 1.0 else 0.0
    return np.array([scalar], dtype=np.float32)


class CommonScoreV2(baseline.BaselineScore):
    """Gates out action_size and action_change penalties when window_open == False."""

    def __init__(self, c: dict, task: dict, condition: dict, scenario: str = 'box_c1_6mm'):
        super().__init__(c, task, condition)
        p = v1_contract.protocol()
        self.reward_config = p['reward']
        self.common_bound = float(scenario_spec(scenario)['common_bound_m_s'])
        self.previous_applied = 0.0

    def update_request(self, info: dict, request, window_open: bool, elapsed: float, physical_failure: bool):
        _, task = super().update(info, elapsed, physical_failure)
        r = self.reward_config
        w = r['weights']
        dt = self.c['control_interval_s']
        if window_open:
            applied = float(request[0]) * self.common_bound / r['request_cost_scale_m_s']
            action_size_term = -w['action'] * applied * applied * dt
            action_change_term = -w['action_change'] * (applied - self.previous_applied) ** 2 / dt
            self.previous_applied = applied
        else:
            action_size_term = 0.0
            action_change_term = 0.0
            self.previous_applied = 0.0

        terms = dict(
            velocity_tracking=-w['velocity'] * (task['velocity_error_m_s'] / r['velocity_scale_m_s']) ** 2 * dt,
            yaw_tracking=-w['yaw'] * (task['yaw_rate_error_rad_s'] / r['yaw_rate_scale_rad_s']) ** 2 * dt,
            action_size=action_size_term,
            action_change=action_change_term,
        )
        if physical_failure:
            terms['physical_failure'] = -r['penalties']['physical_failure']
        if task['task_deadline']:
            if not task['marker_reached']:
                terms['missing_marker'] = -r['penalties']['missing_marker']
            if not task['stop_completed']:
                terms['not_stopped'] = -r['penalties']['not_stopped']
        task.update(reward_terms=terms, reward_id=REWARD_ID, window_open=bool(window_open))
        return sum(terms.values()), task


def verify_transition_v2(row: dict, previous: dict | None, epoch: float, abi: str, scenario: str, *, strict_task: bool = False):
    """Enforce hard causality/transport/safety invariants; enforce task gates in eval."""
    require_uninhibited_transition(row)
    a = row['plan_projection']
    obs, nxt = row['equal_observation'], row['equal_next_observation']
    if len(obs) != 103 or len(nxt) != 103 or row['abi_sha256'] != abi:
        raise ValueError('103D observation or common103_v2 ABI mismatch')
    np.testing.assert_allclose(obs[:100], row['reference_trace']['observation'], atol=2e-6, rtol=0)
    if row['policy_proposal'] != row['requested_scalar_action'] or len(row['policy_proposal']) != 1:
        raise ValueError('Replay must preserve scalar requested action')
    mapped = list(row['controller_proposal'])
    max_mapped = float(scenario_spec(scenario)['common_bound_m_s']) / 0.04
    if mapped != list(row['inherited_policy_proposal']) or mapped != list(row['reference_trace']['proposal']):
        raise ValueError('Controller proposal projection trace mismatch')
    if mapped[1] != 0.0 or max(map(abs, mapped)) > max_mapped + 1e-9:
        raise ValueError('Common-only physical residual range violated')
    if not a['window_open']:
        if any(mapped):
            raise ValueError('Closed shared window emitted nonzero residual')
        if row['reward_terms']['action_size'] != 0.0 or row['reward_terms']['action_change'] != 0.0:
            raise ValueError('Closed shared window charged unapplied action penalty')
    expected_prev = previous['plan_projection']['effective_scalar'] if previous else 0.0
    if obs[101] != float(a['window_open']) or abs(obs[102] - expected_prev) > 1e-7:
        raise ValueError('Window or previous effective scalar not causal')
    if previous is not None:
        np.testing.assert_array_equal(obs, previous['equal_next_observation'])
    if not row.get('fixture_only'):
        if 'truth_used_for_guidance' not in row or 'guidance_audit' not in row or 'source_lags_s' not in row:
            raise ValueError('Gazebo transition missing guidance/source_lags audit fields')
    if a['truth_input'] or bool(row.get('truth_used_for_guidance', False)):
        raise ValueError('Privileged controller input detected')
    decision = row['step'] * 0.1
    if (
        a['decision_tick'] != row['step']
        or abs(a['decision_task_s'] - decision) > 1e-9
        or abs(row['reference_trace']['input_stamp_s'] - epoch - decision) > 1e-8
        or abs(row['sensor_clock_s'] - epoch - row['task']['elapsed_s']) > 1e-8
    ):
        raise ValueError('Decision clock or measurement epoch mismatch')
    if abs(sum(row['reward_terms'].values()) - row['reward']) > 1e-9:
        raise ValueError('Scalar reward trace mismatch')

    task = row['task']
    finite_vals = [
        row['reward'],
        *obs,
        *nxt,
        task['cross_track_m'],
        task['estimator_position_error_m'],
        task['estimator_yaw_error_rad'],
    ]
    if not all(math.isfinite(float(v)) for v in finite_vals):
        raise ValueError('Nonfinite transition value')
    guidance_fault = bool(row.get('guidance_audit', {}).get('fault', False))
    max_lag = max(row['source_lags_s'].values()) if row.get('source_lags_s') else 0.0
    if row.get('intervention') or guidance_fault or max_lag > 0.04 + 1e-9:
        raise ValueError('Safety intervention, guidance fault, or stale sensor boundary')
    if strict_task:
        if (
            abs(task['cross_track_m']) > 0.04
            or task['estimator_position_error_m'] > 0.08
            or abs(task['estimator_yaw_error_rad']) > 0.06
            or row['truncated']
            or (row['terminated'] and not task['task_success'])
        ):
            raise ValueError('Held-out evaluation task/feasibility gate failed')


def environment(config: dict, backend, task: dict, condition: dict, scenario: str = 'box_c1_6mm'):
    import gymnasium as gym

    inner = make_environment(config, backend)
    contract_ident = identity(scenario=scenario)

    class EqualInformationV2Env(gym.Wrapper):
        def __init__(self):
            super().__init__(inner)
            self.backend = backend
            self.observation_space = gym.spaces.Box(-5.0, 5.0, (103,), dtype=np.float32)
            self.action_space = gym.spaces.Box(-1.0, 1.0, (1,), dtype=np.float32)
            self.contract = contract_ident
            self.adapter = PlannedCommonAdapterV2(config, task['command_until_s'], scenario=scenario)
            self.done = True
            self.current_observation = None

        def prepare(self, base, *, done: bool = False):
            return self.adapter.prepare(
                base,
                self.env.pipeline.last_view,
                self.env.pipeline.history.ready,
                done=done,
                latched=self.env.pipeline.reference.latched,
            )

        def reset(self, **kwargs):
            self.adapter.reset()
            self.score = CommonScoreV2(config, task, condition, scenario=scenario)
            self.steps = 0
            base, info = self.env.reset(**kwargs)
            self.current_observation, audit = self.prepare(base)
            self.done = False
            return self.current_observation.copy(), dict(
                info,
                inherited_experiment_contract=info.get('experiment_contract'),
                experiment_contract=self.contract['abi_sha256'],
                abi_sha256=self.contract['abi_sha256'],
                equal_information_identity=deepcopy(self.contract),
                plan_preview=audit,
            )

        def step(self, requested):
            if self.done:
                raise RuntimeError('Reset required after terminal/truncation')
            before = self.current_observation.copy()
            mapped, audit = self.adapter.project(requested)
            base, _, term, trunc, info = self.env.step(mapped)
            self.steps += 1
            reward, task_result = self.score.update_request(
                info,
                audit['requested_scalar'],
                audit['window_open'],
                self.steps * config['control_interval_s'],
                term,
            )
            np.testing.assert_allclose(
                audit['nominal_shaped_body'],
                task_result['nominal_shaped_body'],
                atol=1e-10,
                rtol=0,
            )
            if task_result['task_deadline'] and not term:
                term, trunc = True, False
                info['termination_reason'] = (
                    'task_success' if task_result['task_success'] else 'task_deadline_failure'
                )
            self.done = bool(term or trunc)
            self.current_observation, next_preview = self.prepare(base, done=bool(term))
            return self.current_observation.copy(), reward, bool(term), bool(trunc), dict(
                info,
                task=task_result,
                reward_terms=task_result['reward_terms'],
                equal_information_identity=CONTRACT_ID,
                inherited_abi_sha256=info['abi_sha256'],
                inherited_experiment_contract=info['experiment_contract'],
                inherited_policy_proposal=info['policy_proposal'],
                policy_proposal=audit['requested_scalar'],
                abi_sha256=self.contract['abi_sha256'],
                experiment_contract=self.contract['abi_sha256'],
                equal_observation=before,
                equal_next_observation=self.current_observation.copy(),
                requested_scalar_action=audit['requested_scalar'],
                controller_proposal=mapped.tolist(),
                plan_projection=audit,
                next_plan_preview=next_preview,
                replay_semantics='103D observation + requested 1D action; closed-gate penalties gated zero',
            )

    return EqualInformationV2Env()
