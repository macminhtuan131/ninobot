import pytest
from nino_rl.authority_sampling_audit import contributions, native_equation
from nino_rl.causal_source_support import SourceSeries


def test_phase_split_preserves_spike_and_endpoint_overhang():
    bins = contributions([.05, .15], [1., 10.], [.1, .1], [0., .2, .25])
    assert sum(b['ise_m2_s'] for b in bins) == pytest.approx(10.1)
    assert bins[-1]['ise_m2_s'] == pytest.approx(5.)
    assert sum(b['observed_weight_s'] for b in bins) == pytest.approx(.2)


def test_attribution_rejects_missing_or_uncovered_samples():
    with pytest.raises(ValueError):
        contributions([0.], [None], [.1], [0., .1])
    with pytest.raises(ValueError):
        contributions([.05], [1.], [.1], [0., .1])


def row():
    return dict(step=1, sensor_clock_s=1.1, source_lags_s={'truth': .02},
                body_speed_m_s=.15, task={'nominal_shaped_body': [.2], 'velocity_error_m_s': -.05},
                oracle_decision={'nominal_shaped_body': [.2]})


def test_equation_uses_recorded_truth_source_not_future_sample():
    truth = SourceSeries([(1.08, .15), (1.1, .19)])
    assert native_equation([row()], truth)['pass_equation_and_source']
    r = row(); r['task']['velocity_error_m_s'] = .01
    assert native_equation([r], truth)['failed_steps'] == [1]


def test_missing_or_ambiguous_source_cannot_pass_equation_audit():
    for truth in (SourceSeries([(1.0, .15)]), SourceSeries([(1.08, .15), (1.08, .16)])):
        assert not native_equation([row()], truth)['pass_equation_and_source']
