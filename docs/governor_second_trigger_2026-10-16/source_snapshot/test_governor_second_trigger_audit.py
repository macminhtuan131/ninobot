from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"src/nino_rl/scripts"))
from audit_governor_second_trigger import asof,replay_quiet_armed


def test_sensor_lookup_never_uses_future_or_stale_sample():
    series=[(1.,"old"),(1.02,"future")]
    assert asof(series,1.01,.02)["value"]=="old"
    assert asof(series,1.1,.02) is None
    assert asof(series,.99,.02) is None
    assert asof([],1.,.02) is None


def row(t,ratio,disturbed,armed,quiet,events,phase="HOLD"):
    return dict(governor_input_time_s=str(t),governor_trigger_ratio=str(ratio),
        governor_disturbed=str(disturbed),governor_armed=str(armed),
        governor_quiet_seconds=str(quiet),governor_events=str(events),governor_phase=phase)


def test_rearm_during_hold_survives_vertical_only_disturbance_then_wheel_trigger():
    controls=[row(.1,2.,True,False,0.,1),
        row(.2,.3,False,False,.1,1),row(.3,.4,False,False,.2,1),
        row(.4,.5,False,True,.30000000000000004,1),
        row(.5,3.,False,True,0.,1),  # Vertical-only cannot trigger, breaks quiet.
        row(.6,6.,True,False,0.,2,"DELAY")]
    result=replay_quiet_armed(controls,dict(release_ratio=.6,quiet_seconds=.3,confirmation_seconds=.04),.1)
    assert result[3]["rearmed"] and result[3]["phase_before"]=="HOLD"
    assert result[4]["armed_after"] and not result[4]["event"]
    assert result[5]["event"] and result[5]["confirmed_seconds"]==.1


def test_replay_rejects_inconsistent_timer_instead_of_silently_relabeling():
    with pytest.raises(ValueError,match="Quiet timer mismatch"):
        replay_quiet_armed([row(.1,.3,False,True,.2,0)],
            dict(release_ratio=.6,quiet_seconds=.3,confirmation_seconds=.04),.1)
