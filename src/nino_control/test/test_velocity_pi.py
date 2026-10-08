from nino_control.velocity_pi import conditional_integral


def test_persistent_small_error_accumulates_under_a_slow_reference():
    integral = 0.
    for _ in range(1000):
        integral = conditional_integral(integral, .3, .002, .3, .1, 4., 4.)
    assert abs(integral - .6) < 1e-10


def test_saturated_pi_freezes_but_can_unwind_in_both_directions():
    for sign in (-1., 1.):
        integral = sign * 3.
        assert conditional_integral(integral, sign * 20., .1, .3, .1, 4., 2.) == integral
        unwound = conditional_integral(integral, -sign, .1, .3, .1, 4., 2.)
        assert abs(unwound) < abs(integral)


def test_integral_remains_bounded_with_persistent_load():
    integral = 0.
    for _ in range(10000):
        integral = conditional_integral(integral, 1., .002, .3, .1, 4., 4.)
    assert integral == 4.
