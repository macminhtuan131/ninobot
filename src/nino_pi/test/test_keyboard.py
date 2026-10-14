from nino_pi.keyboard import KeyboardState


def test_release_stops_even_with_periodic_publishing():
    state = KeyboardState()
    state.press("i",1.)
    assert state.output(1.5) == (.2,0.)
    assert state.output(1.601) == (0.,0.)
    state.press("i",1.61)
    assert state.output(1.8) == (.2,0.)
    state.press("k",1.81)
    assert state.output(1.82) == (0.,0.)


def test_reverse_turn_and_unknown_keys():
    state = KeyboardState()
    state.press("m",1.)
    assert state.output(1.1) == (-.1,-.6)
    state.press("q",1.11)
    assert state.output(1.12) == (0.,0.)
