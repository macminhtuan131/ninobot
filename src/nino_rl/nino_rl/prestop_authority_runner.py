"""Isolated runtime adapter and 12-slot coordinator for pre-stop tail authority.

Executes protocol nino_prestop_tail_authority_draft_v1_2026_11_08 in an isolated
versioned contract without modifying any frozen v1 files, checkpoints, or draft
specifications. Zero actor loads, zero training steps, zero optimizer updates,
and zero hardware authority.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import shutil
import signal
import time
import traceback

import numpy as np
from nino_control.residual_velocity import ReferenceLimits, ResidualReference

from . import equal_information_contract as parent_contract
from . import prestop_authority_draft as draft
from . import residual_common_td3 as common_v1
from . import residual_drive_readiness as ready
from .coverage_reset_readiness import require_uninhibited_transition
from .drive_readiness_candidate import DriveReadinessBackend
from .reliable_episode import EpisodeLifecycle
from .residual_experiment import make_environment, source_fingerprint
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import emit, json_value, latest, runtime_versions, save

ACTION = 'sim-prestop-tail-authority'
PROTOCOL_ID = 'nino_prestop_tail_authority_runtime_v1_2026_11_08'
CONTRACT_ID = 'prestop_tail_authority_probe_v1'
ROOT_NAME = 'sim_prestop_tail_authority_v1'


def draft_path() -> Path:
    return repo() / 'src/nino_rl/config/prestop_tail_authority_draft_v1.json'


def release_path() -> Path:
    return repo() / 'src/nino_rl/config/prestop_tail_authority_release_v1.json'


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(Path(path).read_text())


def draft_plan(verify_inputs: bool = True) -> dict:
    return draft.load(draft_path(), verify_inputs=verify_inputs)


def fingerprint() -> str:
    base = repo() / 'src/nino_rl'
    names = [
        'nino_rl/prestop_authority_draft.py',
        'nino_rl/prestop_authority_runner.py',
        'config/prestop_tail_authority_draft_v1.json',
        'scripts/prestop_authority_runner.sh',
        'test/test_prestop_authority_runner.py',
    ]
    payload = dict(
        parent=parent_contract.fingerprint(),
        drive_ready=ready.fingerprint(),
        files={name: sha(base / name) for name in names},
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def configuration(source_stop_s: float):
    plan = draft_plan(verify_inputs=False)
    if float(source_stop_s) not in plan['intervention']['source_stops_s']:
        raise ValueError(f'Unsupported source stop: {source_stop_s}')
    c, g, task, condition = parent_contract.configuration(float(source_stop_s))
    c['purpose'] = PROTOCOL_ID
    c['training']['allowed'] = False
    c['hardware_authority'] = 0.0
    c['backend'].update(
        scenario_id='clear_box_prestop_tail_authority_v1',
        command_until_s=float(source_stop_s),
        horizon_s=float(plan['intervention']['horizon_s']),
        max_episodes=1,
    )
    c['task'].update(
        command_until_s=float(source_stop_s),
        horizon_s=float(plan['intervention']['horizon_s']),
    )
    task.update(
        protocol_id=PROTOCOL_ID,
        command_until_s=float(source_stop_s),
        horizon_s=float(plan['intervention']['horizon_s']),
        warmup_s=float(plan['unchanged']['task']['source_warmup_s']),
    )
    return c, g, task, condition


def identity() -> dict:
    plan = draft_plan(verify_inputs=False)
    inherited = parent_contract.identity()
    ident = dict(
        id=CONTRACT_ID,
        protocol_id=PROTOCOL_ID,
        draft_id=plan['draft_id'],
        fingerprint=fingerprint(),
        parent_abi_sha256=inherited['abi_sha256'],
        observation=inherited['observation'],
        action=inherited['action'],
        intervention=plan['intervention'],
        actor_checkpoint_loading_allowed=False,
        resume_allowed=False,
        training_released=False,
        hardware_authorized=False,
    )
    ident['abi_sha256'] = hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()
    return ident


class PrestopTailAdapter:
    """Isolated runtime adapter opening [stop-0.5, stop) solely for classical tail probe."""

    def __init__(self, config: dict, source_stop_s: float, tail_scalar: int, *, verify_inputs: bool = False):
        self.plan = draft_plan(verify_inputs=verify_inputs)
        p = self.plan['intervention']
        if float(source_stop_s) not in p['source_stops_s']:
            raise ValueError('Unsupported source stop')
        if type(tail_scalar) is not int or tail_scalar not in p['tail_scalar_levels']:
            raise ValueError('Unsupported tail scalar')
        self.stop = float(source_stop_s)
        self.tail_scalar = tail_scalar
        self.tail_start = self.stop - float(p['tail_seconds'])
        self.dt = float(p['control_interval_s'])
        self.horizon = float(p['horizon_s'])
        self.common_bound = float(p['common_bound_m_s'])
        self.residual_scale = float(config['reference_limits']['residual_wheel_m_s'])
        self.nominal_steady = float(p['nominal_source_m_s'])
        self.warmup = float(self.plan['unchanged']['task']['source_warmup_s'])
        if config['control_interval_s'] != self.dt or self.residual_scale != 0.04:
            raise ValueError('Control interval or inherited residual scale drifted')
        self.config = deepcopy(config)
        self.reset()

    def reset(self):
        self.nominal = ResidualReference(ReferenceLimits(**self.config['reference_limits']))
        self.next_tick = 0
        self.pending = None
        self.previous_request = 0.0

    def prepare(self, observation, view: dict, history_ready: bool, *, done: bool = False, latched: bool = False):
        if self.pending is not None:
            raise RuntimeError('Consume pending decision before advancing nominal shaper')
        base = np.asarray(observation, dtype=np.float32)
        if base.shape != (100,) or not np.all(np.isfinite(base)) or np.max(np.abs(base)) > 5.0:
            raise ValueError('Finite bounded causal 100D inherited history required')
        if any(type(view[k]) is not bool for k in ('permission', 'sensors_fresh', 'fault', 'emergency_stop')):
            raise ValueError('Explicit boolean health flags required')
        t = self.next_tick * self.dt
        if t > self.horizon + 1e-8:
            raise ValueError('Decision clock beyond task horizon')
        source = view['baseline']
        nominal = self.nominal.compose(
            source,
            (0.0, 0.0),
            self.dt,
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
        source_forward = bool(self.warmup - 1e-8 <= t < self.stop - 1e-8 and source[0] > 0.0)
        steady = abs(nominal[0] - self.nominal_steady) <= 1e-8
        if not healthy:
            reason = 'invalid_history_source_or_permission'
            window_open = False
        elif t >= self.stop - 1e-8:
            reason = 'at_or_after_source_stop'
            window_open = False
        elif not source_forward:
            reason = 'source_not_forward'
            window_open = False
        elif not steady:
            reason = 'nominal_not_steady'
            window_open = False
        elif t >= self.tail_start - 1e-8:
            reason = 'tail_window_open'
            window_open = True
        else:
            reason = 'pre_tail_common_window_open'
            window_open = True

        scheduled = (
            0.0
            if done or t >= self.horizon - 1e-8
            else draft.request_at(
                self.plan,
                t,
                self.stop,
                self.tail_scalar,
                healthy=healthy,
                nominal_v=float(nominal[0]),
                source_forward=source_forward,
            )
        )
        features = np.array(
            [(self.stop - t) / self.horizon, float(window_open), self.previous_request],
            dtype=np.float32,
        )
        audit = dict(
            decision_tick=self.next_tick,
            decision_task_s=t,
            planned_source_stop_s=self.stop,
            tail_start_task_s=self.tail_start,
            tail_scalar=self.tail_scalar,
            current_features=features.tolist(),
            window_open=window_open,
            in_tail_window=bool(reason == 'tail_window_open'),
            reason=reason,
            healthy=healthy,
            source_forward=source_forward,
            nominal_shaped_body=nominal,
            scheduled_scalar=float(scheduled),
            truth_input=False,
        )
        self.pending = audit
        return np.concatenate((base, features)), deepcopy(audit)

    def project(self, requested):
        if self.pending is None:
            raise RuntimeError('Prepare observation before projecting action')
        a = np.asarray(requested, dtype=np.float32)
        if a.shape != (1,) or not np.all(np.isfinite(a)) or np.max(np.abs(a)) > 1.0:
            raise ValueError('Finite normalized scalar action required')
        audit = self.pending
        if abs(float(a[0]) - audit['scheduled_scalar']) > 1e-9:
            raise ValueError('Runtime request diverged from declared classical/tail schedule')
        common = float(a[0]) * self.common_bound if audit['window_open'] else 0.0
        if audit['decision_task_s'] >= self.stop - 1e-8 and common != 0.0:
            raise ValueError('Post-stop residual authority is prohibited')
        mapped = np.array([common / self.residual_scale, 0.0], dtype=np.float32)
        audit = dict(
            audit,
            requested_scalar=a.tolist(),
            requested_common_m_s=float(a[0]) * self.common_bound,
            windowed_common_m_s=common,
            inherited_controller_proposal=mapped.tolist(),
            replay_action=a.tolist(),
        )
        self.pending = None
        self.previous_request = float(a[0])
        self.next_tick += 1
        return mapped, audit


def environment(config: dict, backend, task: dict, condition: dict, tail_scalar: int):
    import gymnasium as gym

    if config['training']['allowed'] or config['hardware_authority'] != 0.0:
        raise ValueError('Pre-stop authority probe forbids training and hardware authority')
    inner = make_environment(config, backend)
    contract_ident = identity()

    class PrestopProbeEnv(gym.Wrapper):
        def __init__(self):
            super().__init__(inner)
            self.backend = backend
            self.observation_space = gym.spaces.Box(-5.0, 5.0, (103,), dtype=np.float32)
            self.action_space = gym.spaces.Box(-1.0, 1.0, (1,), dtype=np.float32)
            self.contract = contract_ident
            self.adapter = PrestopTailAdapter(config, task['command_until_s'], tail_scalar)
            self.done = True
            self.current_observation = None
            self.last_preview = None

        def _prepare(self, base, *, done: bool = False):
            obs, preview = self.adapter.prepare(
                base,
                self.env.pipeline.last_view,
                self.env.pipeline.history.ready,
                done=done,
                latched=self.env.pipeline.reference.latched,
            )
            self.last_preview = preview
            return obs, preview

        def scheduled_action(self) -> np.ndarray:
            if self.last_preview is None:
                raise RuntimeError('Environment must be reset before querying scheduled action')
            return np.array([self.last_preview['scheduled_scalar']], dtype=np.float32)

        def reset(self, **kwargs):
            self.adapter.reset()
            self.score = parent_contract.CommonScore(config, task, condition)
            self.steps = 0
            base, info = self.env.reset(**kwargs)
            self.current_observation, preview = self._prepare(base)
            self.done = False
            return self.current_observation.copy(), dict(
                info,
                prestop_probe_identity=deepcopy(self.contract),
                abi_sha256=self.contract['abi_sha256'],
                experiment_contract=self.contract['abi_sha256'],
                plan_preview=preview,
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
            self.current_observation, next_preview = self._prepare(base, done=bool(term))
            return self.current_observation.copy(), reward, bool(term), bool(trunc), dict(
                info,
                task=task_result,
                reward_terms=task_result['reward_terms'],
                prestop_probe_identity=CONTRACT_ID,
                abi_sha256=self.contract['abi_sha256'],
                experiment_contract=self.contract['abi_sha256'],
                equal_observation=before,
                equal_next_observation=self.current_observation.copy(),
                requested_scalar_action=audit['requested_scalar'],
                controller_proposal=mapped.tolist(),
                plan_projection=audit,
                next_plan_preview=next_preview,
            )

    return PrestopProbeEnv()


def verify_neutral_parity() -> list[dict]:
    """Prove Tail0 matches frozen Classical_scheduled bit-for-bit on fixture plant."""
    from . import residual_equal_information as offline_fixture

    records = []
    for stop in (6.0, 8.0):
        c_old, _, task_old, bc_old = parent_contract.configuration(stop)
        c_new, _, task_new, bc_new = configuration(stop)
        for cfg in (c_old, c_new):
            cfg['backend'].update(wheel_gain=[1.0, 1.0], motor_lag_s=[0.16, 0.16], imu_noise_std=0.0)
        old_env = parent_contract.environment(c_old, offline_fixture.fixture_backend(c_old, stop), task_old, bc_old)
        new_env = environment(c_new, offline_fixture.fixture_backend(c_new, stop), task_new, bc_new, tail_scalar=0)
        try:
            obs_old, _ = old_env.reset(seed=701)
            obs_new, _ = new_env.reset(seed=701)
            for step in range(140):
                np.testing.assert_array_equal(obs_old[:100], obs_new[:100])
                req_old = parent_contract.classical_request(obs_old)
                req_new = new_env.scheduled_action()
                np.testing.assert_array_equal(req_old, req_new)
                obs_old, r_old, t_old, u_old, i_old = old_env.step(req_old)
                obs_new, r_new, t_new, u_new, i_new = new_env.step(req_new)
                if (r_old, t_old, u_old) != (r_new, t_new, u_new):
                    raise ValueError(f'Neutral parity reward/terminal drift at stop={stop} step={step}')
                for key in ('controller_proposal', 'reference_trace', 'applied_target_rad_s', 'final_ros_reference'):
                    if i_old[key] != i_new[key]:
                        raise ValueError(f'Neutral parity {key} drift at stop={stop} step={step}')
            if not t_new or u_new:
                raise ValueError('Neutral fixture did not reach clean terminal deadline')
        finally:
            old_env.close()
            new_env.close()
        records.append(
            dict(
                stop_s=stop,
                paired_decisions=140,
                neutral_tail_scalar=0,
                classical_parity_exact=True,
            )
        )
    return records


def verify_transition(row: dict, previous: dict | None, epoch: float, abi_sha256: str, attempt: dict):
    require_uninhibited_transition(row)
    a = row['plan_projection']
    obs, nxt = row['equal_observation'], row['equal_next_observation']
    if len(obs) != 103 or len(nxt) != 103 or row['abi_sha256'] != abi_sha256:
        raise ValueError('103D observation or probe ABI mismatch')
    np.testing.assert_allclose(obs[:100], row['reference_trace']['observation'], atol=2e-6, rtol=0)
    mapped = list(row['controller_proposal'])
    if mapped != list(row['reference_trace']['proposal']):
        raise ValueError('Controller proposal trace mismatch')
    if mapped[1] != 0.0 or max(map(abs, mapped)) > 0.125 + 1e-12:
        raise ValueError('Common-only physical residual range violated')
    if not a['window_open'] and any(mapped):
        raise ValueError('Closed window emitted nonzero residual')
    decision_s = row['step'] * 0.1
    if (
        a['decision_tick'] != row['step']
        or abs(a['decision_task_s'] - decision_s) > 1e-9
        or abs(row['reference_trace']['input_stamp_s'] - epoch - decision_s) > 1e-8
        or abs(row['sensor_clock_s'] - epoch - row['task']['elapsed_s']) > 1e-8
    ):
        raise ValueError('Decision clock or measurement epoch drift')
    stop = float(attempt['stop_s'])
    if decision_s >= stop - 1e-8 and (row['requested_scalar_action'] != [0.0] or any(mapped)):
        raise ValueError('Post-stop residual authority detected')
    if a['tail_scalar'] != attempt['tail_scalar'] or a['planned_source_stop_s'] != stop:
        raise ValueError('Attempt condition metadata mismatch')
    common_v1.feasibility(row, 0.04)


def quiet_onset_interval_s(rows: list[dict], stop_s: float) -> float | None:
    """Interval from source-zero to onset of sustained (>=2.0s) quiet condition."""
    post = [r for r in rows if r['task']['elapsed_s'] >= stop_s - 1e-8]
    streak_start = None
    streak_s = 0.0
    for r in post:
        if r['task']['quiet_now']:
            if streak_start is None:
                streak_start = float(r['task']['elapsed_s']) - 0.1
            streak_s += 0.1
            if streak_s >= 2.0 - 1e-8:
                return max(0.0, float(streak_start - stop_s))
        else:
            streak_start = None
            streak_s = 0.0
    return None


def window_metrics(target: Path, rows: list[dict], stop_s: float) -> dict:
    """Compute primary ISE_v on [stop-0.5, stop+2.5) across native and 2 GT grids."""
    w_start = float(stop_s) - 0.5
    w_end = float(stop_s) + 2.5
    native_window = [r for r in rows if w_start - 1e-8 <= r['task']['elapsed_s'] < w_end - 1e-8]
    approach_window = [r for r in rows if (w_start - 1.0) - 1e-8 <= r['task']['elapsed_s'] < w_start - 1e-8]
    pre_tail_decisions = [r for r in rows if r['plan_projection']['decision_task_s'] < w_start - 1e-8]

    if len(native_window) != 30 or len(approach_window) != 10:
        return dict(
            valid=False,
            reason=f'Unexpected native window counts: primary={len(native_window)}, approach={len(approach_window)}',
        )

    native_errors = np.array([float(r['task']['velocity_error_m_s']) for r in native_window], dtype=np.float64)
    native_ise = float(np.sum(native_errors ** 2) * 0.1)

    epoch = rows[0]['sensor_clock_s'] - rows[0]['task']['elapsed_s']
    end_clock = rows[-1]['sensor_clock_s']
    truth = {}
    for path in (target / 'backend').rglob('raw_samples.jsonl'):
        for line in path.open():
            rec = json.loads(line)
            if rec['channel'] == 'truth' and epoch <= rec['stamp_s'] <= end_clock:
                truth[rec['stamp_s']] = float(rec['values']['speed'])

    stamps = np.array(sorted(truth), dtype=np.float64)
    values = np.array([truth[t] for t in stamps], dtype=np.float64)
    max_support_age = 0.020000001
    if len(stamps) < 2 or float(np.max(np.diff(stamps))) > max_support_age:
        return dict(valid=False, reason='GT-header source gap in window diagnostic')

    ends = np.array([float(r['task']['elapsed_s']) for r in rows], dtype=np.float64)
    nominal = np.array([float(r['task']['nominal_shaped_body'][0]) for r in rows], dtype=np.float64)
    grids = {}
    for shift in (0.0, 0.01):
        grid = np.arange(w_start + shift, w_end - 1e-8, 0.02)
        if len(grid) != 150:
            return dict(valid=False, reason=f'Unexpected GT grid count {len(grid)} for shift {shift}')
        query = epoch + grid
        support = np.searchsorted(stamps, query + 1e-9, side='right') - 1
        if int(np.min(support)) < 0 or float(np.max(query - stamps[support])) > max_support_age:
            return dict(valid=False, reason='Insufficient causal GT support in primary window')
        indices = np.searchsorted(ends, stamps[support] - epoch - 1e-9, side='left')
        if int(np.max(indices)) >= len(rows):
            return dict(valid=False, reason='Nominal support missing for GT sample')
        err = values[support] - nominal[indices]
        grids[str(shift)] = dict(
            samples=int(len(grid)),
            unique_truth_samples=int(len(set(support.tolist()))),
            ise_m2_s=float(np.sum(err ** 2) * 0.02),
            rmse_m_s=float(np.sqrt(np.mean(err ** 2))),
            maximum_support_age_s=float(np.max(query - stamps[support])),
        )

    onset = quiet_onset_interval_s(rows, stop_s)
    if onset is None:
        return dict(valid=False, reason='Sustained quiet onset not reached')

    sat_ticks = sum(
        1 for r in rows if max(map(abs, r.get('applied_target_rad_s', [0.0, 0.0]))) >= 12.0 - 1e-6
    )
    return dict(
        valid=True,
        window_start_s=w_start,
        window_end_s=w_end,
        native_samples=len(native_window),
        native_ise_m2_s=native_ise,
        native_window_rmse_m_s=float(np.sqrt(np.mean(native_errors ** 2))),
        gt_grids=grids,
        quiet_onset_interval_s=onset,
        signed_velocity_error_mean_m_s=float(np.mean([r['task']['velocity_error_m_s'] for r in rows])),
        window_signed_velocity_error_mean_m_s=float(np.mean(native_errors)),
        target_saturation_ticks=int(sat_ticks),
        pre_tail_commands=[
            dict(
                tick=int(r['step']),
                requested=float(r['requested_scalar_action'][0]),
                windowed_common_m_s=float(r['plan_projection']['windowed_common_m_s']),
                accepted_v_m_s=float(r['reference_trace']['body_reference'][0]),
            )
            for r in pre_tail_decisions
        ],
        approach_body_speeds_m_s=[float(r['body_speed_m_s']) for r in approach_window],
        window_body_speeds_m_s=[float(r['body_speed_m_s']) for r in native_window],
        window_accepted_v_m_s=[float(r['reference_trace']['body_reference'][0]) for r in native_window],
        window_executed_v_m_s=[float(r['final_ros_reference'][0]) for r in native_window],
        window_wheel_mean_rad_s=[
            float(0.5 * (r['feedback_wheel_rad_s'][0] + r['feedback_wheel_rad_s'][1])) for r in native_window
        ],
    )


def max_consecutive_contrast(diff: np.ndarray, threshold: float) -> tuple[int, int]:
    """Return (max_pos_ticks, max_neg_ticks) where diff >= +threshold or <= -threshold."""
    pos_max = neg_max = pos_cur = neg_cur = 0
    for val in diff:
        if val >= threshold:
            pos_cur += 1
            pos_max = max(pos_max, pos_cur)
        else:
            pos_cur = 0
        if val <= -threshold:
            neg_cur += 1
            neg_max = max(neg_max, neg_cur)
        else:
            neg_cur = 0
    return pos_max, neg_max


def compare(runs: list[dict]) -> dict:
    plan = draft_plan(verify_inputs=False)
    expected_attempts = plan['proposed_attempts']
    if len(runs) != 12 or [r['attempt'] for r in runs] != expected_attempts:
        raise ValueError('Exact 12-slot proposed_attempts order required')

    rules = plan['proposed_decision_rules']
    caliper = float(rules['preintervention_body_rms_caliper_m_s'])
    useful_diff = float(rules['useful_body_difference_m_s'])
    min_persist_ticks = int(round(float(rules['body_difference_persistence_s']) / 0.1))
    min_reduction = float(rules['minimum_primary_relative_reduction'])
    max_full_reg = float(rules['maximum_full_route_rms_regression_fraction'])
    max_quiet_reg = float(rules['maximum_quiet_onset_regression_s'])

    by_cell = {(r['attempt']['block'], float(r['attempt']['stop_s']), int(r['attempt']['tail_scalar'])): r for r in runs}

    def ise_vec(run_row: dict) -> np.ndarray:
        wm = run_row['window_metrics']
        if (
            not run_row['functional_proposal_pass']
            or not run_row['timestamp_diagnostic']['valid']
            or not wm['valid']
        ):
            raise ValueError('Invalid task/timing/window result in compare')
        return np.array(
            [
                wm['native_ise_m2_s'],
                wm['gt_grids']['0.0']['ise_m2_s'],
                wm['gt_grids']['0.01']['ise_m2_s'],
            ],
            dtype=np.float64,
        )

    by_sign = {}
    any_approach_violation = False
    any_nonfinite_or_zero = False

    for sign in (-1, 1):
        sign_key = 'tail_minus' if sign == -1 else 'tail_plus'
        stop_summaries = {}
        pairs = []
        for stop in (6.0, 8.0):
            block_pairs = []
            for block in (0, 1):
                ctrl = by_cell[(block, stop, 0)]
                cand = by_cell[(block, stop, sign)]
                c_vec = ise_vec(ctrl)
                x_vec = ise_vec(cand)
                if not np.isfinite(np.concatenate((c_vec, x_vec))).all() or np.any(c_vec <= 0.0) or np.any(x_vec < 0.0):
                    any_nonfinite_or_zero = True
                    rel = [None, None, None]
                    grid_sensitive = False
                else:
                    rel_arr = (x_vec - c_vec) / c_vec
                    rel = rel_arr.tolist()
                    grid_sensitive = bool(np.any(rel_arr < 0.0) and np.any(rel_arr > 0.0))

                cand_cmds = cand['window_metrics']['pre_tail_commands']
                ctrl_cmds = ctrl['window_metrics']['pre_tail_commands']
                cmd_equal_before_tail = len(cand_cmds) == len(ctrl_cmds) and all(
                    a['tick'] == b['tick']
                    and a['requested'] == b['requested']
                    and a['windowed_common_m_s'] == b['windowed_common_m_s']
                    for a, b in zip(cand_cmds, ctrl_cmds)
                )
                if not cmd_equal_before_tail:
                    raise ValueError(f'Before-tail command equality violated at block={block} stop={stop} sign={sign}')
                pre_tail_accepted_diff = max(
                    (abs(float(a['accepted_v_m_s']) - float(b['accepted_v_m_s'])) for a, b in zip(cand_cmds, ctrl_cmds)),
                    default=0.0,
                )
                if pre_tail_accepted_diff > caliper:
                    any_approach_violation = True

                approach_diff = np.array(cand['window_metrics']['approach_body_speeds_m_s']) - np.array(
                    ctrl['window_metrics']['approach_body_speeds_m_s']
                )
                approach_rms = float(np.sqrt(np.mean(approach_diff ** 2)))
                if approach_rms > caliper:
                    any_approach_violation = True

                body_diff = np.array(cand['window_metrics']['window_body_speeds_m_s']) - np.array(
                    ctrl['window_metrics']['window_body_speeds_m_s']
                )
                ref_diff = np.array(cand['window_metrics']['window_accepted_v_m_s']) - np.array(
                    ctrl['window_metrics']['window_accepted_v_m_s']
                )
                exec_diff = np.array(cand['window_metrics']['window_executed_v_m_s']) - np.array(
                    ctrl['window_metrics']['window_executed_v_m_s']
                )
                wheel_diff = np.array(cand['window_metrics']['window_wheel_mean_rad_s']) - np.array(
                    ctrl['window_metrics']['window_wheel_mean_rad_s']
                )
                pos_ticks, neg_ticks = max_consecutive_contrast(body_diff, useful_diff)
                expected_contrast_ticks = pos_ticks if sign > 0 else neg_ticks

                full_rms_ctrl = float(ctrl['nominal_velocity_rmse_m_s'])
                full_rms_cand = float(cand['nominal_velocity_rmse_m_s'])
                full_rms_rel = (full_rms_cand - full_rms_ctrl) / full_rms_ctrl if full_rms_ctrl > 0 else float('nan')
                quiet_delta_s = float(
                    cand['window_metrics']['quiet_onset_interval_s'] - ctrl['window_metrics']['quiet_onset_interval_s']
                )

                pair = dict(
                    block=block,
                    stop_s=stop,
                    tail_scalar=sign,
                    control_id=ctrl['attempt']['id'],
                    candidate_id=cand['attempt']['id'],
                    control_ise_m2_s=c_vec.tolist(),
                    candidate_ise_m2_s=x_vec.tolist(),
                    delta_ise_m2_s=(x_vec - c_vec).tolist(),
                    relative_ise_vs_control=rel,
                    grid_sensitive=grid_sensitive,
                    before_tail_commands_equal=cmd_equal_before_tail,
                    max_pre_tail_accepted_v_abs_diff_m_s=pre_tail_accepted_diff,
                    approach_body_rms_diff_m_s=approach_rms,
                    approach_within_caliper=bool(approach_rms <= caliper),
                    max_ref_abs_diff_m_s=float(np.max(np.abs(ref_diff))),
                    max_driver_exec_abs_diff_m_s=float(np.max(np.abs(exec_diff))),
                    max_wheel_abs_diff_rad_s=float(np.max(np.abs(wheel_diff))),
                    max_body_abs_diff_m_s=float(np.max(np.abs(body_diff))),
                    positive_body_contrast_ticks=pos_ticks,
                    negative_body_contrast_ticks=neg_ticks,
                    useful_signed_body_contrast=bool(
                        expected_contrast_ticks >= min_persist_ticks
                        and float(np.max(np.abs(exec_diff))) > 0.0
                        and float(np.max(np.abs(wheel_diff))) > 0.0
                    ),
                    control_full_vrmse_m_s=full_rms_ctrl,
                    candidate_full_vrmse_m_s=full_rms_cand,
                    relative_full_vrmse_vs_control=full_rms_rel,
                    full_vrmse_constraint_pass=bool(full_rms_rel <= max_full_reg),
                    control_quiet_onset_s=float(ctrl['window_metrics']['quiet_onset_interval_s']),
                    candidate_quiet_onset_s=float(cand['window_metrics']['quiet_onset_interval_s']),
                    quiet_onset_delta_s=quiet_delta_s,
                    quiet_onset_constraint_pass=bool(quiet_delta_s <= max_quiet_reg + 1e-9),
                )
                block_pairs.append(pair)
                pairs.append(pair)

            if any_nonfinite_or_zero:
                mean_rel = [None, None, None]
            else:
                mean_rel = np.mean([bp['relative_ise_vs_control'] for bp in block_pairs], axis=0).tolist()
            stop_summaries[str(stop)] = dict(
                mean_relative_ise_vs_control=mean_rel,
                blocks=block_pairs,
            )

        if any_nonfinite_or_zero:
            sign_go = False
            sign_grid_or_block_inconsistent = True
        else:
            rels = np.array([p['relative_ise_vs_control'] for p in pairs], dtype=np.float64)
            all_primary_reduced = bool(np.all(rels <= -min_reduction))
            all_contrast = all(p['useful_signed_body_contrast'] for p in pairs)
            all_constraints = all(
                p['full_vrmse_constraint_pass'] and p['quiet_onset_constraint_pass'] for p in pairs
            )
            sign_go = bool(all_primary_reduced and all_contrast and all_constraints and not any_approach_violation)
            any_grid_sens = any(p['grid_sensitive'] for p in pairs)
            native_rels = rels[:, 0]
            block_sign_flip = bool(
                any(
                    pairs[i]['relative_ise_vs_control'][0] * pairs[i + 1]['relative_ise_vs_control'][0] < 0.0
                    and min(abs(pairs[i]['relative_ise_vs_control'][0]), abs(pairs[i + 1]['relative_ise_vs_control'][0])) >= min_reduction
                    for i in (0, 2)
                )
            )
            sign_grid_or_block_inconsistent = bool(any_grid_sens or block_sign_flip)
            _ = native_rels

        by_sign[sign_key] = dict(
            tail_scalar=sign,
            stops=stop_summaries,
            pairs=pairs,
            go_candidate=sign_go,
            grid_or_block_inconsistent=sign_grid_or_block_inconsistent,
        )

    if any_nonfinite_or_zero:
        decision = 'unknown_nonfinite_or_zero_denominator'
    elif any_approach_violation:
        decision = 'unknown_preintervention_approach_caliper_exceeded'
    elif any(v['go_candidate'] for v in by_sign.values()):
        winners = [k for k, v in by_sign.items() if v['go_candidate']]
        decision = (
            f'go_classical_{winners[0]}_confirmation_required'
            if len(winners) == 1
            else 'unknown_both_signs_claim_reduction'
        )
    elif any(v['grid_or_block_inconsistent'] for v in by_sign.values()):
        decision = 'unknown_grid_or_block_inconsistent'
    else:
        decision = 'no_go_retain_historical_classical_clear_box'

    return dict(
        decision=decision,
        by_sign=by_sign,
        any_approach_caliper_violation=any_approach_violation,
        training_released=False,
        hardware_authorized=False,
        benefit_verified=False,
        screening_only_no_holdout=True,
    )


def evaluate_attempt(out: Path, attempt: dict, world: str) -> dict:
    plan = draft_plan(verify_inputs=False)
    if attempt not in plan['proposed_attempts']:
        raise ValueError('Undeclared pre-stop attempt')
    out.mkdir()
    stop_s = float(attempt['stop_s'])
    tail_scalar = int(attempt['tail_scalar'])
    c, g, task, bc = configuration(stop_s)
    lp = ready.parent.lifecycle_protocol(True)
    lp['protocol_id'] = PROTOCOL_ID
    ident = identity()
    backend = EpisodeLifecycle(
        c,
        out / 'episodes',
        world,
        g,
        task,
        bc,
        lp,
        backend_factory=DriveReadinessBackend,
    )
    env = environment(c, backend, task, bc, tail_scalar=tail_scalar)
    rows, epoch, error = [], None, None
    save(out / 'config.json', dict(config=c, guidance=g, task=task, attempt=attempt, identity=ident))

    def attempt_timeout(*_args):
        raise TimeoutError(f"Attempt {attempt['id']} exceeded 180s wall deadline")

    prev_handler = signal.signal(signal.SIGALRM, attempt_timeout)
    signal.alarm(int(plan['proposed_budget']['wall_deadline_s_per_attempt_proposed']))
    try:
        obs, reset = env.reset(seed=int(attempt['requested_env_seed']))
        save(out / 'reset.json', reset)
        if not backend.namespace or backend.current is None:
            raise ValueError('Fresh Gazebo evaluation epoch required')
        initial = backend.view()
        save(out / 'initial_view.json', initial)
        ready.require_ready(initial)
        for step in range(140):
            ready.require_ready(backend.view())
            request = env.scheduled_action()
            common_v1.append(out / 'control_attempts.jsonl', dict(step=step, requested=request.tolist()))
            obs, reward, term, trunc, info = env.step(request)
            row = dict(
                step=step,
                reward=reward,
                terminated=term,
                truncated=trunc,
                done=bool(term or trunc),
                **info,
                qualification_condition=dict(
                    id=attempt['id'],
                    block=attempt['block'],
                    source_stop_s=stop_s,
                    tail_scalar=tail_scalar,
                ),
                episode_namespace=backend.namespace,
            )
            row['TimeLimit.truncated'] = bool(trunc and not term)
            common_v1.append(out / 'trace.jsonl', row)
            epoch = epoch if epoch is not None else row['sensor_clock_s'] - row['task']['elapsed_s']
            verify_transition(row, rows[-1] if rows else None, epoch, ident['abi_sha256'], attempt)
            rows.append(row)
            if term or trunc:
                break
    except BaseException as exc:
        error = exc
        save(out / 'failure.json', dict(error=repr(exc), traceback=traceback.format_exc(), valid_rows=len(rows)))
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev_handler)
        try:
            env.close()
        except BaseException as exc:
            save(out / 'cleanup_failure.json', dict(error=repr(exc), original=repr(error)))
            if error is None:
                raise

    target = backend.directory / backend.namespace
    summary = common_v1.baseline.summarize(rows, target)
    diag = common_v1.timing.timestamp_diagnostic(target, rows)
    w_metrics = window_metrics(target, rows, stop_s)
    summary.update(
        attempt=attempt,
        timestamp_diagnostic=diag,
        window_metrics=w_metrics,
        actor_loads=0,
        training_transitions=0,
        optimizer_updates_in_job=0,
        reset_backend='drive_ack_and_physical_quiet_v1',
    )
    save(out / 'summary.json', summary)
    if len(rows) != 140 or not summary['functional_proposal_pass'] or not diag['valid'] or not w_metrics['valid']:
        raise ValueError(f"Attempt {attempt['id']} task/measurement validation failed")
    return summary


def release_record() -> dict:
    return read_json(release_path())


def release_ready(root: Path) -> dict:
    plan = draft_plan(verify_inputs=True)
    r = release_record()
    if (
        r.get('released') is not True
        or r.get('protocol_id') != PROTOCOL_ID
        or r.get('draft_id') != plan['draft_id']
        or r.get('draft_sha256') != sha(draft_path())
        or r.get('fingerprint') != fingerprint()
        or r.get('allocated_attempts') != 12
        or r.get('training_authorized') is not False
        or r.get('hardware_authorized') is not False
        or Path(r.get('result_root', '')).resolve() != Path(root).resolve()
    ):
        raise ValueError('Pre-stop authority probe not released for these sources/root')
    if Path(root).resolve() != Path.home() / 'nino_research' / ROOT_NAME:
        raise ValueError('Noncanonical pre-stop authority result root')
    free_bytes = shutil.disk_usage(Path(root).parent if not Path(root).exists() else Path(root)).free
    required_bytes = int(plan['proposed_budget']['required_reserve_bytes_proposed']) + int(
        plan['proposed_budget']['estimated_raw_bytes']
    )
    if free_bytes < required_bytes:
        raise RuntimeError(f'Insufficient free disk ({free_bytes} < {required_bytes} bytes)')
    return r


def execute(out: Path) -> dict:
    plan = draft_plan(verify_inputs=True)
    parity = verify_neutral_parity()
    save(out / 'neutral_parity.json', parity)
    runs, attempted = [], []
    try:
        save(out / 'evaluation_progress.json', dict(runs=[], attempted=[], remaining_slots_closed=False))
        worlds = prepare_worlds(out)
        for i, attempt in enumerate(plan['proposed_attempts']):
            if shutil.disk_usage(out).free < int(plan['proposed_budget']['required_reserve_bytes_proposed']):
                raise RuntimeError('Disk reserve breached during pre-stop batch; closing remaining slots')
            attempted.append(attempt)
            save(out / 'evaluation_progress.json', dict(runs=runs, attempted=attempted, remaining_slots_closed=False))
            emit(ACTION, f"Pre-stop cell {i + 1}/12 ({attempt['id']}): stop={attempt['stop_s']}s tail={attempt['tail_scalar']}", i / 12.0)
            runs.append(evaluate_attempt(out / f"{attempt['id']}_eval_{i:02d}", attempt, worlds['clear_box']))
            if runs[-1]['attempt'] != attempt or runs[-1]['steps'] != 140:
                raise ValueError('Cell outcome or 140-step budget mismatch')
            save(out / 'evaluation_progress.json', dict(runs=runs, attempted=attempted, remaining_slots_closed=False))
    except BaseException as exc:
        save(
            out / 'evaluation_progress.json',
            dict(
                runs=runs,
                attempted=attempted,
                error=repr(exc),
                unused_slots_closed=12 - len(attempted),
                remaining_slots_closed=True,
            ),
        )
        raise
    save(
        out / 'evaluation_progress.json',
        dict(runs=runs, attempted=attempted, unused_slots_closed=0, remaining_slots_closed=True),
    )
    ticks = sum(r['steps'] for r in runs)
    if ticks != 1680:
        raise ValueError('Exact 1680-tick pre-stop budget mismatch')
    result = dict(
        protocol_id=PROTOCOL_ID,
        draft_id=plan['draft_id'],
        neutral_parity=parity,
        runs=runs,
        comparison=compare(runs),
        gazebo_launches=12,
        evaluation_transitions=ticks,
        training_transitions=0,
        optimizer_updates=0,
        actor_loads=0,
        hardware_actions=0,
        remaining_slots_closed=True,
    )
    save(out / 'evaluation_result.json', result)
    return result


def run(root: Path) -> Path:
    root = Path(root).expanduser().resolve()
    if (root / 'state.json').exists():
        raise ValueError('Pre-stop authority budget already consumed; no retry allowed')
    release = release_ready(root)
    root.mkdir(parents=True, exist_ok=True)
    shared = Path.home() / 'nino_research/.factory_sim.lock'
    shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root / '.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / 'state.json').exists():
            raise ValueError('Pre-stop authority budget already consumed; no retry allowed')
        release = release_ready(root)
        current = fingerprint()
        out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + ACTION)
        out.mkdir()
        row = dict(action=ACTION, path=out.name, status='running', error=None)
        state = dict(
            schema_version=1,
            protocol_id=PROTOCOL_ID,
            allocated_slots=12,
            maximum_eval_ticks=1680,
            retry_allowed=False,
            latest={},
            runs=[row],
        )
        save(root / 'state.json', state)
        save(out / 'draft.json', draft_plan(verify_inputs=True))
        save(out / 'release.json', release)
        status, error, result, started = 'running', None, None, time.monotonic()
        try:
            emit(ACTION, 'Starting 12-launch pre-stop tail authority probe (0 training steps)')
            result = execute(out)
            if fingerprint() != current:
                raise ValueError('Pre-stop runner sources changed during execution')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            save(out / 'failure.json', dict(error=repr(exc), traceback=traceback.format_exc()))
            raise
        finally:
            save(
                out / 'job.json',
                dict(action=ACTION, status=status, error=error, wall_s=time.monotonic() - started, hardware_actions=0),
            )
            save(
                out / 'manifest.json',
                dict(
                    action=ACTION,
                    status=status,
                    prestop_runner_fingerprint=current,
                    source_fingerprint=source_fingerprint(),
                    runtime=runtime_versions(),
                    hardware_actions=0,
                    files={
                        str(f.relative_to(out)): sha(f)
                        for f in out.rglob('*')
                        if f.is_file() and f.name != 'manifest.json'
                    },
                ),
            )
            progress = read_json(out / 'evaluation_progress.json') if (out / 'evaluation_progress.json').exists() else {}
            attempted = len(progress.get('attempted', []))
            row.update(
                status=status,
                error=error,
                attempted_slots=attempted,
                unattempted_slots_closed=12 - attempted,
                remaining_slots_closed=True,
            )
            if status == 'completed':
                state['latest'][ACTION] = out.name
            save(root / 'state.json', state)
            emit(
                ACTION,
                status,
                1.0 if status == 'completed' else None,
                directory=str(out),
                decision=result['comparison']['decision'] if result else None,
                error=error,
            )
    return out


def finalize_posthoc_comparison(root: Path) -> Path:
    """Offline-only evaluation of a completed 12-launch Gazebo batch whose post-processor raised before saving."""
    root = Path(root).expanduser().resolve()
    state = read_json(root / 'state.json')
    if not state.get('runs'):
        raise ValueError('No recorded pre-stop authority run in state.json')
    run_entry = state['runs'][-1]
    out = root / run_entry['path']
    manifest = read_json(out / 'manifest.json')
    for rel_path, expected_sha in manifest['files'].items():
        if sha(out / rel_path) != expected_sha:
            raise ValueError(f'Manifest hash mismatch in {rel_path}; raw Gazebo batch modified')
    progress = read_json(out / 'evaluation_progress.json')
    runs = progress['runs']
    ticks = sum(int(r['steps']) for r in runs)
    if len(runs) != 12 or ticks != 1680 or not progress.get('remaining_slots_closed'):
        raise ValueError('Expected 12 completed Gazebo attempts (1680 ticks) with closed slots')
    plan = draft_plan(verify_inputs=True)
    parity = read_json(out / 'neutral_parity.json')
    comparison = compare(runs)
    posthoc = dict(
        protocol_id=PROTOCOL_ID,
        draft_id=plan['draft_id'],
        artifact_dir=str(out),
        raw_manifest_sha256=sha(out / 'manifest.json'),
        original_runner_fingerprint=manifest['prestop_runner_fingerprint'],
        finalizer_runner_fingerprint=fingerprint(),
        original_postproc_status=run_entry['status'],
        original_postproc_error=run_entry['error'],
        postproc_correction_reason=(
            'compare() originally compared accepted_v_m_s (which includes v_source * cos(ekf_yaw_error) '
            'with <=3.65e-5 m/s closed-loop heading cosine variation at tick 24) using exact IEEE-754 == '
            'instead of comparing scheduled request + windowed_common_m_s equality and caliper-bounding accepted_v_m_s.'
        ),
        additional_gazebo_launches=0,
        additional_physics_ticks=0,
        training_transitions=0,
        optimizer_updates=0,
        hardware_actions=0,
        neutral_parity=parity,
        comparison=comparison,
    )
    target = root / 'posthoc_evaluation_result.json'
    save(target, posthoc)
    emit(ACTION, 'posthoc_completed', 1.0, file=str(target), decision=comparison['decision'])
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--finalize-posthoc', action='store_true')
    args = parser.parse_args()
    if args.finalize_posthoc:
        finalize_posthoc_comparison(args.output)
    else:
        run(args.output)


if __name__ == '__main__':
    main()
