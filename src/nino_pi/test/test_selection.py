import pytest
from nino_pi.selection import CommandSelection


def test_disabled_and_source_switch_cannot_replay_old_motion():
    gate = CommandSelection()
    gate.receive("manual",.2,.1,1.)
    assert gate.output(1.) == (0.,0.)
    gate.enable(True)
    assert gate.output(1.) == (0.,0.)
    gate.receive("manual",.2,.1,1.)
    gate.receive("navigation",.15,-.1,1.)
    assert gate.output(1.1) == (.2,.1)
    gate.mode(True)
    assert gate.output(1.1) == (0.,0.)
    gate.receive("navigation",.15,-.1,1.1)
    assert gate.output(1.2) == (.15,-.1)
    gate.mode(False)
    assert gate.output(1.2) == (0.,0.)


def test_stale_invalid_and_overspeed_commands():
    gate = CommandSelection()
    gate.enable(True)
    gate.receive("manual",100.,-100.,1.)
    assert gate.output(1.1) == (.2,-.6)
    assert gate.output(1.301) == (0.,0.)
    assert gate.output(.9) == (0.,0.)
    assert not gate.receive("manual",float("nan"),.1,1.1)
    assert gate.output(1.2) == (0.,0.)
    gate.receive("manual",-100.,100.,1.2)
    assert gate.output(1.21) == (-.1,.6)


def test_stop_latches_and_reset_requires_fresh_enable_and_command():
    gate = CommandSelection()
    gate.enable(True)
    gate.receive("manual",.2,0.,1.)
    gate.stop()
    assert gate.output(1.1) == (0.,0.)
    assert not gate.enable(True)
    assert gate.reset_stop()
    assert gate.output(1.1) == (0.,0.)
    gate.enable(True)
    assert not gate.reset_stop()
    assert gate.output(1.2) == (0.,0.)
    gate.receive("manual",.1,0.,1.2)
    assert gate.output(1.21) == (.1,0.)


@pytest.mark.parametrize("values",[dict(timeout=0),dict(max_forward=float("inf")),dict(max_yaw=-1)])
def test_invalid_limits_rejected(values):
    with pytest.raises(ValueError):
        CommandSelection(**values)
