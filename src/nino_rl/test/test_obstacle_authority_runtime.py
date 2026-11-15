"""E2 neutral parity, causal snapshot and post-manifold-only execution fixtures."""
from copy import deepcopy
import json
import threading
from types import SimpleNamespace
import numpy as np
import pytest
from nino_rl import obstacle_authority_runtime as runtime
from nino_rl import obstacle_authority_draft as draft
from nino_rl.obstacle_authority_metrics import grids


def packet(stamp=3.2, receipt=103.3):
    return dict(channel="contact_caster_left_wheel", stamp_s=stamp, receipt_monotonic_s=receipt,
                values=[dict(collision1="nino::caster", collision2="cable_bumps::cables::C1_collision", points=1)])


def test_neutral_reference_history_reward_and_deadline_match_parent():
    result = runtime.neutral_parity()
    assert sum(r["paired_decisions"] for r in result) == 280
    assert all(r["exact_parity"] and r["trigger_observed"] for r in result)


@pytest.mark.parametrize("level", [-1, 0, 1])
def test_reference_is_identical_before_trigger_and_zero_after_withdrawal(level):
    c, _, task, condition = runtime.configuration(6.0)
    c["backend"].update(wheel_gain=[1.0, 1.0], imu_noise_std=0.0)
    backend = runtime.fixture_backend(c, 6.0)
    env = runtime.environment(c, backend, task, condition, level)
    try:
        obs, reset = env.reset(seed=701)
        assert obs.shape == (100,) and env.observation_space.shape == (100,)
        assert reset["e2_identity"]["parent_checkpoint_compatible"] is False
        rows = []
        for tick in range(140):
            obs, reward, term, trunc, row = env.step(np.array([level], np.float32))
            a = row["oracle_decision"]; rows.append(row)
            if tick < 33 or tick >= 55:
                assert row["controller_proposal"] == [0.0, 0.0]
            assert set(row["reference_trace"]["source_samples"]) == {"imu", "wheel", "baseline", "final", "status"}
            assert a["oracle_in_observation"] is False
        assert rows[35]["oracle_decision"]["requested_common_m_s"] == pytest.approx(level * .005)
        assert term and not trunc
        with pytest.raises(RuntimeError, match="reset"): env.step([level])
    finally: env.close()


def test_no_contact_never_opens_window_or_fabricates_trigger():
    c, _, task, condition = runtime.configuration(8.0)
    env = runtime.environment(c, runtime.fixture_backend(c, 8.0, contact=False), task, condition, 1)
    try:
        env.reset(seed=701)
        with pytest.raises(ValueError, match="declared"): env.step([0])
        for _ in range(140):
            _, _, _, _, info = env.step([1])
            assert info["controller_proposal"] == [0.0, 0.0]
            assert info["oracle_decision"]["trigger"] is None
    finally: env.close()


def test_mailbox_snapshot_copy_receipt_cutoff_capacity_and_cursor():
    box = runtime.ContactMailbox(maximum=1)
    floor = packet(); floor["values"][0]["collision2"] = "floor_collision"
    box.push(floor); assert box.rows == []
    box.push(packet())
    with pytest.raises(ValueError, match="cutoff"): box.snapshot(0, 3.3, 103.2)
    snapshot = box.snapshot(0, 3.3, 103.3)
    snapshot["contacts"][0]["values"].clear()
    assert box.rows[0]["values"]
    assert box.snapshot(1, 3.4, 103.4)["contacts"] == []
    with pytest.raises(RuntimeError, match="full"): box.push(packet())
    with pytest.raises(ValueError, match="cursor"): box.snapshot(2, 3.4, 103.4)


def test_backend_store_capture_does_not_modify_view_and_uses_raw_receipt():
    fake = SimpleNamespace(lock=threading.RLock(), oracle_mailbox=runtime.ContactMailbox(),
                           messages={}, counts={}, raw=[])
    # Execute the actual superclass _store through a minimal uninitialized backend.
    backend = object.__new__(runtime.OraclePiBackend)
    backend.__dict__.update(fake.__dict__)
    row = packet()
    backend._store(row["channel"], row["stamp_s"], row["values"])
    assert backend.raw == backend.oracle_mailbox.rows
    assert backend.raw[0]["receipt_monotonic_s"] == backend.messages[row["channel"]]["receipt_monotonic_s"]
    backend._store("wheel", 3.3, [1.0, 1.0])
    assert len(backend.oracle_mailbox.rows) == 1


def test_adapter_declared_warmup_does_not_latch_but_late_missing_history_does():
    c, _, _, _ = runtime.configuration(6.0)
    backend = runtime.fixture_backend(c, 6.0)
    view, _ = backend.reset(seed=701)
    adapter = runtime.OracleAdapter(c, 6.0, 1, 0.0)
    snapshot = backend.oracle_snapshot(0)
    _, audit = adapter.decide(view, False, False, snapshot)
    assert not audit["latched"]
    for tick in range(1, 7):
        view = deepcopy(view); view["stamp_s"] = tick * .1
        snapshot.update(source_stamp_s=tick*.1, decision_receipt_monotonic_s=100+tick*.1)
        _, audit = adapter.decide(view, False, False, snapshot)
    assert audit["latched"]
    bad = deepcopy(snapshot); bad["source_stamp_s"] = 2.0
    with pytest.raises(ValueError, match="epoch"): adapter.decide(view, True, False, bad)


def test_primary_grids_are_causal_and_keep_shifted_uncovered_prefix():
    truth = [(i*.02, 0.2) for i in range(251)]
    nominal = [(i*.1, 0.1) for i in range(51)]
    out = grids(truth, nominal, 1.0, 4.0)
    assert out["0.0"]["ise_m2_s"] == pytest.approx(.03)
    assert out["0.01"]["ise_m2_s"] == pytest.approx(.0299)
    assert out["0.01"]["supported_duration_s"] == pytest.approx(2.99)
    with pytest.raises(ValueError, match="gap"): grids(truth[::4], nominal, 1., 4.)
    with pytest.raises(ValueError, match="boundaries"): grids(truth[60:], nominal, 1., 4.)
    with pytest.raises(ValueError, match="reversed"): grids(list(reversed(truth)), nominal, 1., 4.)


def test_full_transition_verifier_with_pi_fixture_and_bad_telemetry():
    from nino_rl.pi_screen_preflight import fixture_backend
    c, _, task, condition = runtime.configuration(8.0)
    c["backend"].update(wheel_gain=[1.0, 1.0], motor_lag_s=[.16, .16], imu_noise_std=0.0)
    backend = fixture_backend(c)
    backend.oracle_snapshot = lambda cursor: dict(source_stamp_s=backend.time,
        decision_receipt_monotonic_s=100+round(backend.time, 9), cursor=cursor, contacts=[])
    ident = runtime.identity()
    env = runtime.environment(c, backend, task, condition, 0, contract_identity=ident)
    rows = []
    try:
        env.reset(seed=701)
        for tick in range(140):
            _, reward, term, trunc, info = env.step([0])
            row = dict(step=tick, reward=reward, terminated=term, truncated=trunc,
                       **info, qualification_condition=dict(level=0))
            runtime.verify_transition(row, rows[-1] if rows else None, 0., ident)
            rows.append(row)
    finally: env.close()
    for mutation in ("nan", "future", "oracle_feature", "gain", "clock", "condition"):
        row = deepcopy(rows[0])
        if mutation == "nan": row["drive_diagnostics"]["left_applied_nm"] = float("nan")
        elif mutation == "future":
            row["oracle_decision"]["trigger"] = dict(source_s=1., decision_stamp_s=0.,
                receipt_monotonic_s=100., decision_receipt_monotonic_s=100.)
        elif mutation == "oracle_feature": row["reference_trace"]["source_samples"]["contact"] = {}
        elif mutation == "gain": row["gain_map_audit"]["common_gain"] = 1.02
        elif mutation == "condition": row["qualification_condition"]["level"] = 1
        else: row["oracle_decision"]["decision_source_stamp_s"] = .1
        with pytest.raises((ValueError, AssertionError)):
            runtime.verify_transition(row, None, 0., ident)


def test_contact_qc_retains_gt_reversal_and_never_infers_body_authority(tmp_path):
    from nino_rl.obstacle_authority_metrics import assess
    event=dict(source_s=3.2,receipt_monotonic_s=103.3,component="caster_left_wheel",
               decision_stamp_s=3.3,decision_task_s=3.3,decision_receipt_monotonic_s=103.3)
    rows=[dict(sensor_clock_s=(i+1)*.1,task=dict(elapsed_s=(i+1)*.1,task_success=True,
               stop_completed=True,velocity_error_m_s=0.),oracle_decision=dict(
               decision_source_stamp_s=i*.1,nominal_shaped_body=[.2,0],active=i>=33,
               trigger=event if i>=33 else None)) for i in range(140)]
    raw=[dict(channel="truth",stamp_s=i*.02,values=dict(speed=.2)) for i in range(701)]
    raw.append(packet());drive=packet(4.5,104.5);drive["channel"]="contact_left_wheel";raw.append(drive)
    path=tmp_path/"raw.jsonl"
    path.write_text("".join(json.dumps(r)+"\n" for r in raw))
    result=assess(rows,[path])
    assert result["status"]=="per_slot_measurement_pass_not_benefit"
    assert result["useful_body_authority_verified"] is False
    assert result["loaded_contact_verified"] is False
    raw[200],raw[201]=raw[201],raw[200]
    path.write_text("".join(json.dumps(r)+"\n" for r in raw))
    with pytest.raises(ValueError,match="source reversal"):assess(rows,[path])
