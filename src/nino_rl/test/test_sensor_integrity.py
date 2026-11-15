import math

import pytest

from nino_rl.control_v2 import ImuWindow
from nino_rl.sensor_integrity import require_imu_support, scan_valid


def test_empty_imu_does_not_become_a_measured_zero_impact_window():
    result = ImuWindow().estimate(1., 1.1)
    assert result['duration'] == 0.
    assert result['coverage_fraction'] == 0.
    assert result['diagnostic_estimate'] is None
    with pytest.raises(RuntimeError):
        require_imu_support(result, 1., 1.1)


def test_future_sample_cannot_explain_an_earlier_interval():
    window = ImuWindow()
    window.add(2., 20.)
    result = window.estimate(1., 1.1)
    assert result['duration'] == result['square_integral'] == 0.
    assert result['diagnostic_estimate'] is None


def test_partial_support_is_not_scaled_into_full_measurement():
    window = ImuWindow()
    window.add(0., 2.)
    window.add(.02, 4.)
    result = window.estimate(0., .1)
    assert result['duration'] == pytest.approx(.02)
    assert result['square_integral'] == pytest.approx(.08)
    assert result['coverage_fraction'] == pytest.approx(.2)
    assert result['diagnostic_estimate']['duration'] == pytest.approx(.1)


def test_delayed_and_duplicate_samples_do_not_erase_an_observed_peak():
    window = ImuWindow()
    for t, az in [(0., 0.), (.02, 0.), (.04, 10.), (.06, 0.), (.1, 0.)]:
        window.add(t, az)
    before = window.measure(0., .1)
    assert window.add(.02, 0.) is False
    assert window.add(.1, 99.) is False
    assert window.measure(0., .1) == before
    assert before['peak'] == 10.
    window.reset()
    assert window.measure(0., .1)['duration'] == 0.


def test_large_source_gaps_do_not_earn_observed_coverage():
    window = ImuWindow()
    window.add(0., 10.)
    window.add(.2, 0.)
    assert window.measure(0., .2)['duration'] == 0.


def test_configured_source_gap_distinguishes_jitter_from_unobserved_span():
    window = ImuWindow(max_gap_s=.04)
    for t in (0., .019, .041, .061, .081, .1):
        window.add(t, 2.)
    assert window.measure(0., .1)['coverage_fraction'] == pytest.approx(1.)
    window.reset()
    window.add(0., 2.)
    window.add(.06, 2.)
    assert window.measure(0., .1)['duration'] == 0.


@pytest.mark.parametrize('ranges, maximum, expected', [
    ([], 10., False), ([math.nan]*5, 10., False),
    ([math.inf]*5, 10., True), ([10.]*5, 10., True),
    ([1., math.nan], 10., False), ([-math.inf], 10., False),
    ([-1.], 10., False), ([2.], 0., False),
])
def test_invalid_scan_and_valid_no_return_are_distinct(ranges, maximum, expected):
    assert scan_valid(ranges, maximum) is expected


@pytest.mark.parametrize('angle', [0., math.pi/2, math.pi, -math.pi/2, .7])
def test_clearance_is_direction_invariant_and_backout_does_not_succeed(angle):
    from nino_rl.control_v2 import ChallengeRegion, ChallengeTracker
    import numpy as np
    axis = np.array([math.cos(angle), math.sin(angle)])
    region = ChallengeRegion('test', 'cable', 0., 0., .01, .5, angle+math.pi/2)
    tracker = ChallengeTracker([region], contact_margin=.1, clearance_margin=.2)
    assert tracker.update(-.5*axis, -.05*axis) == (1, 0)
    assert tracker.update(-.05*axis, -.5*axis) == (0, 0)
    assert tracker.update(-.5*axis, .5*axis) == (0, 1)
    assert tracker.update(-.5*axis, .5*axis) == (0, 0)


@pytest.mark.parametrize('angle', [0., math.pi/2, math.pi, -math.pi/2])
def test_curved_local_crossing_preserves_entry_side_and_one_shot_reward(angle):
    from nino_rl.control_v2 import ChallengeRegion, ChallengeTracker
    import numpy as np
    rotation = np.array([[math.cos(angle), -math.sin(angle)],
                         [math.sin(angle), math.cos(angle)]])
    center = rotation @ np.array([1.,0.])
    tracker = ChallengeTracker([ChallengeRegion('curve', 'bump', *center, .05)],
                               contact_margin=.1, clearance_margin=.2)
    points = [rotation@np.array(p) for p in ((.5,0.), (.9,.05), (1.03,.08), (1.35,.05))]
    results = [tracker.update(a,b) for a,b in zip(points,points[1:])]
    assert sum(r[0] for r in results) == sum(r[1] for r in results) == 1
