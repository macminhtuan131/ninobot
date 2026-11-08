"""Stop-time transfer contract, causal diagnostics and closed experiment budget."""
import json
from pathlib import Path
import numpy as np
import pytest
from nino_control.residual_velocity import ReferenceLimits, ResidualReference
from nino_rl import residual_stop_transfer as transfer


def test_backend_guidance_scorer_and_profile_share_stop_schedule():
    c, _, task, _, profile = transfer.configuration()
    assert c['backend']['command_until_s'] == c['task']['command_until_s'] == task['command_until_s'] == 6.
    assert c['backend']['horizon_s'] == c['task']['horizon_s'] == task['horizon_s'] == 14.
    assert profile['withdraw_at_task_s'] == 5.5
    assert task['functional_proposals']['local_progress_marker_m'] == .95
    assert c['actor']['history_frames'] == 5 and c['hardware_authority'] == 0


def view(**changes):
    return dict(dict(baseline=(.2, 0.), permission=True, sensors_fresh=True,
                     fault=False, emergency_stop=False, command_age_s=0.), **changes)


@pytest.mark.parametrize('changes,ready,extra', [
    ({'permission': False}, True, {}), ({'sensors_fresh': False}, True, {}),
    ({'fault': True}, True, {}), ({'emergency_stop': True}, True, {}),
    ({'command_age_s': .3}, True, {}), ({'command_age_s': -.1}, True, {}),
    ({}, False, {}), ({}, True, {'latched': True}), ({}, True, {'done': True}),
    ({'baseline': (0., 0.)}, True, {})])
def test_transfer_retains_zero_and_fault_gates(changes, ready, extra):
    c, _, _, _, p = transfer.configuration()
    profile = transfer.common.ClassicalCommonProfile(c, p)
    for i in range(30):
        profile.proposal(i * .1, view(), True)
    action, _ = profile.proposal(3., view(**changes), ready, **extra)
    assert not any(action)


def test_withdrawal_boundaries_nominal_parity_and_unchanged_ramp():
    c, _, _, _, p = transfer.configuration()
    profile = transfer.common.ClassicalCommonProfile(c, p)
    nominal = ResidualReference(ReferenceLimits(**c['reference_limits']))
    actual = ResidualReference(ReferenceLimits(**c['reference_limits']))
    active = []
    previous = np.zeros(2)
    for i in range(140):
        t = i * .1
        source = (.2 if .5 <= t < 6. else 0., 0.)
        action, audit = profile.proposal(t, view(baseline=source), i >= 4)
        target = nominal.compose(source, (0., 0.), .1, permission=True, sensors_fresh=True,
                                 history_ready=True, command_age_s=0.)['body_reference']
        np.testing.assert_allclose(audit['nominal_shaped_body'], target, atol=1e-10, rtol=0)
        if any(action):
            active.append(t)
            assert t < 5.5 and action.tolist() == [.125, 0.]
        if t in (5.4, 5.5, 6.):
            assert bool(any(action)) == (t == 5.4)
        trace = actual.compose(source, action, .1, 1., permission=True, sensors_fresh=True,
                               history_ready=i >= 4, command_age_s=0.)
        wheels = np.asarray(trace['accepted_reference_wheel_m_s'])
        assert np.max(np.abs(wheels - previous)) <= .01 + 1e-9
        previous = wheels
        if 5.5 <= t <= 6.:
            np.testing.assert_allclose(trace['accepted_policy_delta_wheel_m_s'], [0., 0.], atol=1e-9)
    assert active[-1] == 5.4 and not any(previous)


def synthetic_runs(classical=(.004, .0041, .0042), diagnostic=(.005, .0051, .0052)):
    runs = []
    for arm, values, ds in [('B0', (.006, .0061, .0062), (.007, .0071, .0072)),
                            ('Classical_scheduled', classical, diagnostic)]:
        for i, (v, d) in enumerate(zip(values, ds)):
            runs.append(dict(condition=dict(arm=arm, repeat=i), nominal_velocity_rmse_m_s=v,
                task_success=True, stop_completed=True, functional_proposal_pass=True,
                timestamp_diagnostic=dict(valid=True, header_grid={k: dict(rmse_m_s=d) for k in ('0.0', '0.01')})))
    return runs


def test_native_win_cannot_promote_or_hide_overlap_reversal_missing_or_constraint_failure():
    result = transfer.decision(synthetic_runs())
    assert result['descriptive_transfer_signal'] and not result['benefit_verified']
    assert not result['hardware_authorized'] and result['minimum_effect_accepted'] is None
    assert not transfer.decision(synthetic_runs(diagnostic=(.008, .0081, .0082)))['descriptive_transfer_signal']
    assert not transfer.decision(synthetic_runs(classical=(.004, .0041, .0061)))['descriptive_transfer_signal']
    rows = synthetic_runs();rows[-1]['timestamp_diagnostic']['valid'] = False
    assert not transfer.decision(rows)['descriptive_transfer_signal']
    rows = synthetic_runs();rows[-1]['functional_proposal_pass'] = False
    assert not transfer.decision(rows)['descriptive_transfer_signal']
    assert not transfer.decision(synthetic_runs()[:-1])['descriptive_transfer_signal']


def test_header_diagnostic_detects_source_gap_without_replacing_primary(tmp_path):
    backend = tmp_path / 'backend';backend.mkdir()
    raw = backend / 'raw_samples.jsonl'
    def write(stamps):
        raw.write_text(''.join(json.dumps(dict(channel='truth', stamp_s=float(t), values=dict(speed=.2)))+'\n' for t in stamps))
    rows = [dict(sensor_clock_s=(i+1)*.1, task=dict(elapsed_s=(i+1)*.1, nominal_shaped_body=[.2, 0.])) for i in range(140)]
    write(np.arange(0., 14.00001, .02))
    result = transfer.timestamp_diagnostic(tmp_path, rows)
    assert result['valid'] and not result['post_hoc'] and not result['body_interpolated']
    assert result['header_grid']['0.0']['rmse_m_s'] == 0
    write(np.arange(0., 14.00001, .04))
    assert not transfer.timestamp_diagnostic(tmp_path, rows)['valid']


def test_closed_ledger_cannot_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path / 'home'))
    (tmp_path / 'state.json').write_text('{}')
    with pytest.raises(ValueError, match='already consumed'):
        transfer.run(tmp_path)


def test_physical_failure_closes_remaining_slots_and_preserves_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(transfer, 'parent', lambda: tmp_path)
    monkeypatch.setattr(transfer.learner, 'dependency_record', lambda p: {})
    monkeypatch.setattr(transfer, 'prepare_worlds', lambda p: {'clear_box': 'world'})
    calls = []
    def fail(*args):
        calls.append(1)
        return dict(physical_failure=True, guidance_faults=0, steps=20)
    monkeypatch.setattr(transfer, 'rollout', fail)
    with pytest.raises(RuntimeError, match='no retry'):
        transfer.evaluate(tmp_path)
    assert len(calls) == 1 and (tmp_path / 'evaluation_progress.json').is_file()
    assert not (tmp_path / 'evaluation_result.json').exists()
