"""Causality and closed budgets of the offline E2 oracle; no ROS/physics."""
from copy import deepcopy
import json
import pytest
from nino_rl import obstacle_authority_draft as draft


def packet(stamp=3.2, receipt=103.3, name="cable_bumps::cables::C1_collision"):
    return dict(channel="contact_caster_left_wheel", stamp_s=stamp,
                receipt_monotonic_s=receipt,
                values=[dict(collision1="nino::caster", collision2=name, points=1)])


def decide(planner, stamp, receipt=None, **kwargs):
    return planner.decide(stamp, 100 + stamp if receipt is None else receipt,
                          **dict(dict(healthy=True, source_forward=True, nominal_v=0.2), **kwargs))


def test_budget_has_twelve_unique_cells_zero_authority_and_no_ki_confounds():
    plan = draft.load()
    assert plan["release"] == draft.NO_RELEASE
    assert plan["fixed"]["pi_ki"] == 0.10
    assert len(plan["proposed_attempts"]) == 12
    assert plan["proposed_budget"]["task_ticks_max"] == 1680
    assert plan["decision_rules"]["accepted"] is False


@pytest.mark.parametrize("mutation", ["release", "gain", "duplicate", "gate", "bound"])
def test_draft_rejects_budget_factor_and_gate_mutations(tmp_path, mutation):
    plan = draft.load()
    if mutation == "release": plan["release"]["physics_allowed"] = True
    elif mutation == "gain": plan["fixed"]["pi_ki"] = 0.15
    elif mutation == "duplicate": plan["proposed_attempts"][0] = deepcopy(plan["proposed_attempts"][1])
    elif mutation == "gate": plan["decision_rules"]["minimum_primary_relative_reduction"] = 0.001
    else: plan["intervention"]["common_bound_m_s"] = 0.02
    path = tmp_path / "bad.json"; path.write_text(json.dumps(plan))
    with pytest.raises(ValueError): draft.load(path, verify_inputs=False)


def test_source_stamp_is_not_receipt_and_late_events_never_backdate_trigger():
    planner = draft.PostManifoldPlan(draft.load(), 6.0, 1, epoch_s=0.0)
    planner.observe(packet())
    assert decide(planner, 3.2)["requested_common_m_s"] == 0
    result = decide(planner, 3.3)
    assert result["requested_common_m_s"] == 0.005
    assert result["trigger"]["decision_task_s"] == 3.3
    planner.observe(packet(3.1, 103.4))
    assert decide(planner, 3.4)["trigger"] == result["trigger"]
    assert result["loaded_contact_verified"] is False


def test_future_source_cannot_trigger_even_when_receipt_has_arrived():
    planner = draft.PostManifoldPlan(draft.load(), 6.0, -1, epoch_s=0.0)
    planner.observe(packet(3.5, 103.0))
    assert decide(planner, 3.3)["trigger"] is None
    assert decide(planner, 3.5)["requested_common_m_s"] == -0.005


@pytest.mark.parametrize("bad_name", ["floor_collision", "C1_collision_other", "other_model::cables::C1_collision"])
def test_floor_and_wrong_c1_names_are_not_triggers(bad_name):
    planner = draft.PostManifoldPlan(draft.load(), 8.0, 1, epoch_s=0.0)
    planner.observe(packet(name=bad_name))
    assert decide(planner, 3.4)["trigger"] is None


def test_old_epoch_zero_arm_withdrawal_no_trigger_and_health_latch():
    plan = draft.load()
    old = draft.PostManifoldPlan(plan, 6.0, 1, epoch_s=3.3)
    old.observe(packet())
    assert old.decide(3.4, 103.4, healthy=True, source_forward=True, nominal_v=0.2)["trigger"] is None
    zero = draft.PostManifoldPlan(plan, 6.0, 0, epoch_s=0.0)
    zero.observe(packet())
    assert decide(zero, 3.3)["trigger"] is not None
    assert decide(zero, 3.4)["requested_common_m_s"] == 0
    planner = draft.PostManifoldPlan(plan, 6.0, 1, epoch_s=0.0)
    planner.observe(packet())
    assert decide(planner, 3.3)["active"]
    assert not decide(planner, 3.4, healthy=False)["active"]
    assert decide(planner, 3.5)["latched"]
    assert not decide(planner, 5.5)["active"]
    late = draft.PostManifoldPlan(plan, 6.0, 1, epoch_s=0.0)
    late.observe(packet(receipt=105.6))
    assert decide(late, 5.6)["trigger"] is None


def test_invalid_flags_levels_and_reversed_clocks_are_errors():
    plan = draft.load()
    for stop, level in ((7.0, 1), (6.0, True), (6.0, 2)):
        with pytest.raises(ValueError): draft.PostManifoldPlan(plan, stop, level, epoch_s=0.0)
    planner = draft.PostManifoldPlan(plan, 6.0, 1, epoch_s=0.0)
    with pytest.raises(ValueError): decide(planner, float("nan"))
    with pytest.raises(ValueError): decide(planner, 3.3, healthy=1)
    malformed = packet(); malformed.pop("receipt_monotonic_s")
    with pytest.raises(ValueError): planner.observe(malformed)
    decide(planner, 3.3)
    with pytest.raises(ValueError): decide(planner, 3.3)


def test_stateful_reference_preview_zero_precontact_and_stop_priorities():
    from nino_rl.equal_information_v2 import configuration
    config, _, _, _ = configuration(6.0, "box_c1_6mm")
    preview = draft.reference_preview(draft.load(), config["reference_limits"])
    for stop in (6.0, 8.0):
        arms = {r["level"]: r["rows"] for r in preview if r["stop_s"] == stop}
        assert len(arms[0]) == 140
        for rows in arms.values():
            assert all(r["requested_common_m_s"] == 0 for r in rows if r["decision_task_s"] < 3.3)
            assert all(r["requested_common_m_s"] == 0 for r in rows if r["decision_task_s"] >= stop - 0.5)
            assert all(r["accepted_reference"] == [0.0, 0.0] for r in rows if r["decision_task_s"] >= stop + 2.5)
        for tick in range(33):
            assert arms[-1][tick]["accepted_reference"] == arms[0][tick]["accepted_reference"] == arms[1][tick]["accepted_reference"]
        assert arms[-1][35]["accepted_reference"][0] == pytest.approx(0.195)
        assert arms[1][35]["accepted_reference"][0] == pytest.approx(0.205)
