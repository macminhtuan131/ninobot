"""Opt-in delay: timing, unchanged active sequence, and stop/fault priority."""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nino_control.governor_core import GovernorFrame,GovernorSettings,ReactiveGovernor

FRAME=GovernorFrame(0.,0.,6.4,6.4,6.4,6.4,.4)
DISTURBED=replace(FRAME,body_rate_rad_s=.5)


def make(delay):
    return ReactiveGovernor(GovernorSettings(target_scale=.9,maximum_hold_seconds=1.,
        startup_seconds=0.,trigger_to_brake_delay_seconds=delay))


def test_delay_is_two_intervals_and_hold_clock_starts_at_braking():
    immediate,delayed=make(0.),make(.2)
    reference=[]
    sequence=[]
    for index in range(25):
        reference.append(immediate.update(DISTURBED,.1,.4))
        sequence.append(delayed.update(DISTURBED,.1,.4))
    assert [r["phase"] for r in sequence[:3]]==["DELAY","DELAY","HOLD"]
    assert [r["hold_seconds"] for r in sequence[:3]]==pytest.approx([0.,0.,.1])
    assert [r["scale"] for r in sequence[:3]]==pytest.approx([1.,1.,.96])
    assert sequence[2]["brake_onset_elapsed_s"]-sequence[2]["trigger_elapsed_s"]==pytest.approx(.2)
    assert sequence[0]["delay_remaining_seconds"]==pytest.approx(.2)
    # Entire active HOLD/ramp/RECOVER sequence is a translation by two ticks.
    for old,new in zip(reference,sequence[2:]):
        for key in ("phase","scale","hold_seconds","events"):
            assert new[key]==old[key]
    assert delayed.events==1


@pytest.mark.parametrize("fault",["stale","invalid","stall","explicit"])
def test_faults_cancel_pending_immediately_and_latch(fault):
    governor=make(.2)
    governor.update(DISTURBED,.1,.4)
    assert governor.phase=="DELAY"
    if fault=="stale":result=governor.update(FRAME,.1,.4,fresh=False)
    elif fault=="invalid":result=governor.update(FRAME,.3,.4)
    elif fault=="explicit":result=governor.fail("watchdog")
    else:
        governor.stall_elapsed=governor.settings.wheel_stall_seconds
        result=governor.update(replace(FRAME,left_velocity_rad_s=0.,right_velocity_rad_s=0.),.1,.4)
    assert result["phase"]=="FAILSAFE" and result["scale"]==0.
    assert governor.pending_until is None
    assert governor.update(FRAME,.1,.4)["phase"]=="FAILSAFE"


def test_stop_and_reset_discard_pending_without_delayed_replay():
    governor=make(.2)
    governor.update(DISTURBED,.1,.4)
    stop=governor.update(FRAME,.1,0.)
    assert stop["phase"]=="CRUISE" and governor.pending_until is None
    assert 0.*stop["scale"]==0.
    for _ in range(5):
        assert governor.update(FRAME,.1,.4)["phase"]=="CRUISE"
    governor.reset()
    assert governor.trigger_elapsed_s is None and governor.brake_onset_elapsed_s is None
    assert governor.pending_until is None


def test_negative_delay_rejected():
    with pytest.raises(ValueError):GovernorSettings(trigger_to_brake_delay_seconds=-.1)


def test_external_disable_discards_pending_event_without_advancing_clock():
    governor=make(.2)
    governor.update(DISTURBED,.1,.4)
    now=governor.elapsed
    governor.cancel_pending_delay()
    assert governor.elapsed==now and governor.pending_until is None
    for _ in range(5):
        assert governor.update(FRAME,.1,.4)["phase"]=="CRUISE"
