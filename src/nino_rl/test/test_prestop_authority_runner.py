"""Unit tests for isolated pre-stop tail authority runtime adapter and 12-slot runner."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pytest

from nino_rl import prestop_authority_runner as runner
from nino_rl import residual_equal_information as offline_fixture


def _synthetic_cell_result(attempt: dict, *, kind: str = 'no_go') -> dict:
    stop = float(attempt['stop_s'])
    sign = int(attempt['tail_scalar'])
    block = int(attempt['block'])

    base_ise = 1.0e-3
    ise = base_ise
    gt_ise = base_ise
    full_vrmse = 0.010
    quiet_onset = 1.2
    approach_offset = 0.0
    body_delta = 0.002 * sign if sign != 0 else 0.0

    if sign == -1:
        if kind == 'go_minus':
            ise = 0.90 * base_ise
            gt_ise = 0.91 * base_ise
        elif kind == 'grid_flip':
            ise = 0.90 * base_ise
            gt_ise = 1.04 * base_ise
        elif kind == 'block_flip':
            ise = (0.90 if block == 0 else 1.08) * base_ise
            gt_ise = ise
        elif kind == 'caliper_fail' and block == 0:
            ise = 0.90 * base_ise
            gt_ise = 0.90 * base_ise
            approach_offset = 0.003
        elif kind == 'quiet_fail':
            ise = 0.90 * base_ise
            gt_ise = 0.90 * base_ise
            quiet_onset = 1.45

    return dict(
        steps=140,
        attempt=deepcopy(attempt),
        functional_proposal_pass=True,
        nominal_velocity_rmse_m_s=full_vrmse,
        timestamp_diagnostic=dict(
            valid=True,
            header_grid={'0.0': dict(rmse_m_s=0.01), '0.01': dict(rmse_m_s=0.01)},
        ),
        window_metrics=dict(
            valid=True,
            window_start_s=stop - 0.5,
            window_end_s=stop + 2.5,
            native_samples=30,
            native_ise_m2_s=ise,
            native_window_rmse_m_s=float(np.sqrt(ise / 3.0)),
            gt_grids={
                '0.0': dict(samples=150, unique_truth_samples=150, ise_m2_s=gt_ise, rmse_m_s=0.01, maximum_support_age_s=0.01),
                '0.01': dict(samples=150, unique_truth_samples=150, ise_m2_s=gt_ise, rmse_m_s=0.01, maximum_support_age_s=0.01),
            },
            quiet_onset_interval_s=quiet_onset,
            signed_velocity_error_mean_m_s=0.0,
            window_signed_velocity_error_mean_m_s=0.0,
            target_saturation_ticks=0,
            pre_tail_commands=[dict(tick=i, requested=1.0 if i >= 5 else 0.0, windowed_common_m_s=0.005 if i >= 5 else 0.0, accepted_v_m_s=0.2) for i in range(int(round((stop - 0.5) * 10)))],
            approach_body_speeds_m_s=[0.2 + approach_offset] * 10,
            window_body_speeds_m_s=[0.1 + body_delta] * 30,
            window_accepted_v_m_s=[0.1 + (0.005 * sign if sign != 0 else 0.0)] * 30,
            window_executed_v_m_s=[0.1 + (0.005 * sign if sign != 0 else 0.0)] * 30,
            window_wheel_mean_rad_s=[2.0 + (0.1 * sign if sign != 0 else 0.0)] * 30,
        ),
    )


def test_neutral_arm_exact_parity_with_frozen_classical():
    records = runner.verify_neutral_parity()
    assert len(records) == 2
    assert all(r['classical_parity_exact'] and r['paired_decisions'] == 140 for r in records)


@pytest.mark.parametrize('stop', [6.0, 8.0])
def test_tail_arms_preserve_prefix_equality_and_zero_poststop_authority(stop):
    traces = {}
    for sign in (-1, 0, 1):
        c, _, task, bc = runner.configuration(stop)
        c['backend'].update(wheel_gain=[1.0, 1.0], motor_lag_s=[0.16, 0.16], imu_noise_std=0.0)
        env = runner.environment(c, offline_fixture.fixture_backend(c, stop), task, bc, tail_scalar=sign)
        rows = []
        try:
            env.reset(seed=701)
            for step in range(140):
                req = env.scheduled_action()
                _, reward, term, trunc, info = env.step(req)
                rows.append(dict(step=step, reward=reward, terminated=term, truncated=trunc, **info))
        finally:
            env.close()
        traces[sign] = rows

    ctrl = traces[0]
    for sign in (-1, 1):
        cand = traces[sign]
        for r_cand, r_ctrl in zip(cand, ctrl):
            t_dec = r_cand['plan_projection']['decision_task_s']
            if t_dec < stop - 0.5 - 1e-8:
                assert r_cand['requested_scalar_action'] == r_ctrl['requested_scalar_action']
                assert r_cand['controller_proposal'] == r_ctrl['controller_proposal']
                assert r_cand['reference_trace']['body_reference'] == r_ctrl['reference_trace']['body_reference']
            elif t_dec < stop - 1e-8:
                assert r_cand['requested_scalar_action'] == [float(sign)]
                assert r_cand['plan_projection']['windowed_common_m_s'] == pytest.approx(0.005 * sign)
            else:
                assert r_cand['requested_scalar_action'] == [0.0]
                assert r_cand['controller_proposal'] == [0.0, 0.0]


@pytest.mark.parametrize(
    'kind,expected',
    [
        ('go_minus', 'go_classical_tail_minus_confirmation_required'),
        ('no_go', 'no_go_retain_historical_classical_clear_box'),
        ('grid_flip', 'unknown_grid_or_block_inconsistent'),
        ('block_flip', 'unknown_grid_or_block_inconsistent'),
        ('caliper_fail', 'unknown_preintervention_approach_caliper_exceeded'),
        ('quiet_fail', 'no_go_retain_historical_classical_clear_box'),
    ],
)
def test_compare_decision_rules_across_12_slot_matrix(kind, expected):
    plan = runner.draft_plan(verify_inputs=False)
    runs = [_synthetic_cell_result(a, kind=kind) for a in plan['proposed_attempts']]
    verdict = runner.compare(runs)
    assert verdict['decision'] == expected
    assert not verdict['training_released'] and not verdict['hardware_authorized']


def test_window_metrics_on_synthetic_raw_samples(tmp_path):
    stop = 6.0
    c, _, task, bc = runner.configuration(stop)
    c['backend'].update(wheel_gain=[1.0, 1.0], motor_lag_s=[0.16, 0.16], imu_noise_std=0.0)
    env = runner.environment(c, offline_fixture.fixture_backend(c, stop), task, bc, tail_scalar=0)
    rows = []
    try:
        env.reset(seed=701)
        for step in range(140):
            _, reward, term, trunc, info = env.step(env.scheduled_action())
            rows.append(dict(step=step, reward=reward, terminated=term, truncated=trunc, **info))
    finally:
        env.close()

    epoch = rows[0]['sensor_clock_s'] - rows[0]['task']['elapsed_s']
    raw_dir = tmp_path / 'backend'
    raw_dir.mkdir(parents=True)
    with (raw_dir / 'raw_samples.jsonl').open('w') as handle:
        for t in np.arange(0.0, 14.02, 0.01):
            rec = dict(channel='truth', stamp_s=float(epoch + t), values=dict(speed=0.2 if 0.5 <= t < 6.0 else 0.0))
            handle.write(json.dumps(rec) + '\n')

    wm = runner.window_metrics(tmp_path, rows, stop)
    assert wm['valid']
    assert wm['native_samples'] == 30
    assert wm['gt_grids']['0.0']['samples'] == 150
    assert wm['gt_grids']['0.01']['samples'] == 150
    assert wm['quiet_onset_interval_s'] is not None


def test_first_fault_closes_remaining_slots_and_blocks_reentry(tmp_path, monkeypatch):
    plan = runner.draft_plan(verify_inputs=False)
    monkeypatch.setattr(runner, 'draft_plan', lambda verify_inputs=True: deepcopy(plan))
    monkeypatch.setattr(runner, 'prepare_worlds', lambda out: dict(clear_box='synthetic_world'))
    monkeypatch.setattr(runner, 'verify_neutral_parity', lambda: [dict(stop_s=6.0, classical_parity_exact=True)])

    calls = []

    def fake_eval(out, attempt, world):
        calls.append(attempt['id'])
        if len(calls) == 2:
            raise RuntimeError('synthetic P02 failure')
        return _synthetic_cell_result(attempt)

    monkeypatch.setattr(runner, 'evaluate_attempt', fake_eval)
    with pytest.raises(RuntimeError, match='P02'):
        runner.execute(tmp_path)
    progress = json.loads((tmp_path / 'evaluation_progress.json').read_text())
    assert calls == ['P01', 'P02']
    assert progress['remaining_slots_closed'] and progress['unused_slots_closed'] == 10

