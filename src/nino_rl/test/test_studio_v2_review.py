"""Regression checks for metric units, campaign accounting, and failure handling."""
import json
import pytest

from nino_rl import common_studio_v2_contract as spec
from nino_rl import common_training_studio_v2 as studio
from nino_rl import training_studio_api_v2 as api
from nino_rl.studio_v2_metrics import physical_metrics


def request():
    return dict(schema_version=1, mode='train', scenario='box_c1_6mm_dr',
                profile='nino_td3_research_h5_v1', timesteps=12000, seed=11,
                checkpoint_every=1000, wall_minutes=30, evaluate=True, resume=None)


def rows():
    result = []
    for n in range(1, 41):
        t = n * .1
        result.append(dict(task=dict(elapsed_s=t, quiet_now=t >= 1.,
                           task_success=True, stop_completed=True, cross_track_m=.001,
                           velocity_error_m_s=.002, yaw_rate_error_rad_s=.003,
                           nominal_shaped_body=[0., 0.]),
                           body_speed_m_s=.002,
                           reference_trace=dict(body_reference=[.1 * t * t, 0.]),
                           applied_target_rad_s=[7. if n == 1 else 0., 0.]))
    return result


def test_reference_jerk_has_second_derivative_units_and_uses_real_speed_cap():
    config, _, _, _ = spec.controller.configuration(6., 'box_c1_6mm')
    metric = physical_metrics(rows(), .5, config)
    # v(t)=0.1*t^2 => d^2v/dt^2=0.2 m/s^3; acceleration is not constant.
    assert metric['action_jerk_rms'] == pytest.approx(.2)
    assert metric['reference_acceleration_rms_m_s2'] != pytest.approx(.2)
    assert metric['saturation_fraction'] == pytest.approx(1 / 40)
    assert metric['cross_track_rmse_m'] == pytest.approx(.001)


def test_failed_task_is_not_diluted_into_a_small_tick_rate():
    config, _, _, _ = spec.controller.configuration(6.)
    trace = rows()
    trace[-1]['task']['task_success'] = False
    assert physical_metrics(trace, .5, config)['safety_intervention_rate'] == 1.


def test_missing_target_and_unobserved_stop_remain_unknown():
    config, _, _, _ = spec.controller.configuration(6.)
    trace = rows()
    del trace[0]['applied_target_rad_s']
    with pytest.raises(KeyError):
        physical_metrics(trace, .5, config)
    trace = rows()
    for row in trace:
        row['task']['quiet_now'] = False
    with pytest.raises(ValueError, match='unknown'):
        physical_metrics(trace, .5, config)
    trace = rows()
    trace[4]['task']['elapsed_s'] += .02
    with pytest.raises(ValueError, match='clock'):
        physical_metrics(trace, .5, config)
    trace = rows()
    trace[0]['body_speed_m_s'] = float('nan')
    with pytest.raises(ValueError, match='Nonfinite'):
        physical_metrics(trace, .5, config)


def test_DR_world_builder_rejects_unbounded_geometry_before_writing(tmp_path):
    bad = dict(floor_mu=1., bump_x_m=.65, bump_radius_m=.1)
    with pytest.raises(ValueError, match='bounds'):
        spec.controller.build_dr_world_sdf(tmp_path / 'missing_source.sdf', tmp_path / 'output.sdf', bad)
    assert not (tmp_path / 'output.sdf').exists()


def test_campaign_disk_counts_all_retained_seeds_and_peak_raw():
    req = request()
    single = spec.budget(req)
    prune = spec.campaign_budget(req, [11, 22, 33], auto_prune_raw=True)
    keep = spec.campaign_budget(req, [11, 22, 33], auto_prune_raw=False)
    assert prune['training_transitions'] == 36000
    assert prune['evaluation_launches'] == 18
    assert prune['wall_minutes_max'] == 90
    assert prune['required_free_bytes'] == (3 * single['estimated_retained_bytes']
            + single['estimated_training_raw_bytes'] + single['reserve_bytes'])
    assert keep['required_free_bytes'] > prune['required_free_bytes'] > single['required_free_bytes']


@pytest.mark.parametrize('seeds', [[11, 11, 33], [True, 22, 33], [11, -1, 33], []])
def test_invalid_seed_campaign_cannot_start(seeds):
    with pytest.raises(ValueError, match='seeds'):
        spec.campaign_budget(request(), seeds)


def test_api_rejects_smoke_campaign_and_untyped_prune():
    raw = dict(request(), schema_version=2, engine=spec.ENGINE, multi_seeds=[11, 22, 33])
    raw.update(mode='smoke', timesteps=64, profile=spec.SMOKE_PROFILE)
    with pytest.raises(ValueError, match='train mode'):
        api.split(raw)
    raw = dict(request(), schema_version=2, engine=spec.ENGINE, auto_prune_raw='false')
    with pytest.raises(ValueError, match='boolean'):
        api.split(raw)


def test_campaign_retention_failure_closes_remaining_seeds(tmp_path, monkeypatch):
    from nino_pi import training_storage
    monkeypatch.setattr(spec, 'require_campaign_disk', lambda *a, **kw: dict(required_free_bytes=1))
    calls = []
    def fake_run(root, req):
        calls.append(req['seed'])
        directory = root / f"seed_{req['seed']}"
        directory.mkdir()
        (directory / 'result.json').write_text(json.dumps(dict(seed=req['seed'])))
        return directory, 'completed'
    monkeypatch.setattr(studio, 'run', fake_run)
    def failed_prune(directory, *, apply):
        assert apply is True
        raise ValueError('retention fault injection')
    monkeypatch.setattr(training_storage, 'prune_completed_job', failed_prune)
    directory, status = studio.run_multi_seed_campaign(tmp_path, request(), auto_prune_raw=True)
    assert calls == [11]
    assert status == 'failed'
    job = json.loads((directory / 'job.json').read_text())
    assert 'retention fault injection' in job['error']
    assert job['hardware_actions'] == 0


def test_smoke_stays_single_seed_even_if_campaign_checkbox_checked(tmp_path, monkeypatch):
    from PyQt5 import QtWidgets as Q
    from nino_pi.td3_training_panel import TD3TrainingPanel
    monkeypatch.setattr(spec, 'require_disk', lambda *a, **kw: {})
    app = Q.QApplication.instance() or Q.QApplication([])
    panel = TD3TrainingPanel(root=tmp_path, observe_external=False)
    try:
        panel.engine.setCurrentIndex(panel.engine.findData(spec.ENGINE))
        panel.multi_seed.setChecked(True)
        value = panel.request('smoke')
        assert value['mode'] == 'smoke' and value['timesteps'] == 64
        assert 'multi_seeds' not in value
        assert 'chưa' in panel.contract_note.text()
    finally:
        panel.close()
        app.processEvents()
