"""Research oracle must preserve the approach, ramp and physical failsafes."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src/nino_control"), str(ROOT / "src/nino_rl")]
from nino_control.governor_core import GovernorFrame
from nino_rl.research_contact_oracle import ContactGate, OracleIntervention


def frame(vertical=0.):
    return GovernorFrame(vertical, 0., 6.4, 6.4, 6.4, 6.4, .4)


def contact(t=1.):
    return dict(contact_time_s=t, component="caster_bracket_left")


def test_oracle_ignores_floor_and_reset_contacts():
    gate = ContactGate()
    gate.observe(1., "left", ["cable_bumps::C1"], 1., 0.)
    assert gate.snapshot() is None
    gate.reset(2.)
    gate.observe(1., "left", ["cable_bumps::C1"], 2., 0.)
    gate.observe(3., "left", ["terrain_collision"], 3., 0.)
    assert gate.snapshot() is None
    gate.observe(3., "left", ["cable_bumps::C1"], 3.1, 0.)
    assert gate.snapshot()["contact_time_s"] == 3.


@pytest.mark.parametrize("profile", ["full", "moderate", "pulse"])
def test_matching_approach_despite_large_sensor_disturbance(profile):
    governor = OracleIntervention(dict(profile=profile, pulse_seconds=1.))
    for _ in range(50):
        decision = governor.update(frame(100.), .1, .4)
        assert decision["scale"] == 1. and decision["events"] == 0
    governor.accept(contact(6.), 5.)
    assert governor.oracle_contact is None


@pytest.mark.parametrize("profile,target", [("moderate", .85), ("pulse", .70)])
def test_postcontact_ramp_release_recovery_and_no_retrigger(profile, target):
    governor = OracleIntervention(dict(profile=profile, pulse_seconds=1.))
    governor.accept(contact(), 1.1)
    scales = [governor.update(frame(), .1, .4)["scale"] for _ in range(30)]
    assert scales[0] == pytest.approx(.96)
    assert min(scales) == pytest.approx(target)
    assert scales[-1] == pytest.approx(1.)
    assert all(abs(b-a) <= .040001 for a, b in zip([1.]+scales, scales))
    governor.accept(contact(4.), 4.1)
    for _ in range(10):
        assert governor.update(frame(100.), .1, .4)["scale"] == 1.
    assert governor.events == 1
    assert governor.oracle_contact["contact_time_s"] == 1.
    governor.reset()
    assert governor.oracle_contact is None and governor.events == 0


def test_oracle_cannot_override_feedback_failsafe_or_stop():
    governor = OracleIntervention(dict(profile="pulse", pulse_seconds=1.))
    governor.accept(contact(), 1.1)
    assert governor.update(frame(), .1, .4, fresh=False)["phase"] == "FAILSAFE"
    governor.accept(contact(2.), 2.1)
    assert governor.update(frame(), .1, .4)["scale"] == 0.
    governor.reset()
    governor.accept(contact(), 1.1)
    assert governor.update(frame(), .1, 0.)["scale"] == 1.
    assert governor.phase == "CRUISE"


def test_normal_evaluator_cannot_silently_mislabel_oracle_config():
    from nino_rl.evaluation import validate_environment_factory_contract
    config=dict(research_experiment=dict(oracle_contact_input=True))
    with pytest.raises(ValueError, match="explicit simulation-only"):
        validate_environment_factory_contract(config, True, None, None)
    validate_environment_factory_contract(config, True, object(), dict(qualification="oracle"))
