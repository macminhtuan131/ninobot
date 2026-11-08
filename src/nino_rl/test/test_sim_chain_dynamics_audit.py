"""Diagnostic algebra, source clocks and model ambiguity; no physics outcomes."""
from copy import deepcopy
from pathlib import Path
import json,subprocess
import numpy as np
import pytest
from nino_rl import sim_chain_dynamics_audit as m


def native_row(t=4.):
    gap=-.01*np.exp(-(t-3.)/3.);target=.2;enc=target+gap;body=enc+.0001
    d=dict(sim_time_s=1+t,left_target_rad_s=target/.0625,right_target_rad_s=target/.0625,
        left_actual_rad_s=enc/.0625,right_actual_rad_s=enc/.0625,
        left_pi_nm=.3*(-gap/.0625)+.1*t*.01,right_pi_nm=.3*(-gap/.0625)+.1*t*.01)
    return dict(step=round(t*10)-1,drive_diagnostics=d,task=dict(nominal_shaped_body=[.2,0.],
        velocity_error_m_s=body-.2,elapsed_s=t),final_ros_reference=[.2,0.],effective_drive_reference=[.2,0.],
        body_speed_m_s=body,sensor_clock_s=1+t,source_lags_s=dict(truth=0.),
        plan_projection=dict(window_open=2.5<=t<7.5))


def raw(t):
    row=native_row(t);d=row['drive_diagnostics']
    return [dict(channel=n,stamp_s=1+t,values=v) for n,v in [
        ('drive',d),('gain_map',dict(common_gain=1.)),
        ('wheel',[d['left_actual_rad_s'],d['right_actual_rad_s']]),
        ('truth',dict(speed=row['body_speed_m_s'],pose=[.2*t,0.,0.,0.]))]]


def fixture_cell(cell):
    cell.mkdir(parents=True)
    rows=[native_row((i+1)*.1) for i in range(140)]
    for i,row in enumerate(rows):row['step']=i
    (cell/'trace.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    m.save(cell/'config.json',dict(condition=dict(arm='B0',gain=1.,source_stop_s=8.),
        config=dict(nominal_geometry=dict(radius_l=.0625,radius_r=.0625))))
    m.save(cell/'summary.json',dict(nominal_velocity_rmse_m_s=m.rms([r['task']['velocity_error_m_s'] for r in rows])))
    folder=cell/'episodes/episode_0/backend/episode_0';folder.mkdir(parents=True)
    m.save(folder/'drive_parameters.json',dict(wheel_radius=.0625,velocity_kp=.3,velocity_ki=.1,
        pi_integrator_profile='conditional_v1',max_wheel_torque=4.))
    records=[r for i in range(1,751) for r in raw(i*.02)]
    (folder/'raw_samples.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    return cell


def test_additive_decomposition_reproduces_native_including_cancellation():
    r=native_row();r['final_ros_reference'][0]=.205;r['effective_drive_reference'][0]=.2009
    c=m.native_components(r,.0625)
    assert c['reference_minus_nominal']==pytest.approx(.005)
    assert c['gain_map']==pytest.approx(-.0041)
    assert sum(c[k] for k in ('reference_minus_nominal','gain_map','target_minus_effective',
        'encoder_minus_target','body_minus_encoder'))==pytest.approx(r['task']['velocity_error_m_s'])


@pytest.mark.parametrize('fault',['nonfinite','changed_metric'])
def test_native_invalid_or_changed_primary_is_rejected(fault):
    r=native_row()
    if fault=='nonfinite':r['body_speed_m_s']=float('nan')
    else:r['task']['velocity_error_m_s']=.5
    with pytest.raises(ValueError):m.native_components(r,.0625)


def test_source_header_join_uses_preceding_not_future_samples():
    a=raw(3.);b=raw(3.02)
    records=[r for r in a if r['channel']!='truth']+[r for r in b if r['channel']=='truth']
    aligned,_=m.align_raw(records,1.,3.,3.1)
    assert aligned[0]['source_ages_s']['wheel']==pytest.approx(.02)
    assert aligned[0]['source_ages_s']['drive']==pytest.approx(.02)
    assert aligned[0]['drive']['sim_time_s']==4.


@pytest.mark.parametrize('fault',['stale','future_only','missing_gain'])
def test_raw_missing_or_unsupported_samples_are_not_filled(fault):
    records=raw(3.)
    if fault=='stale':
        for r in records:
            if r['channel']=='truth':r['stamp_s']=4.05
    if fault=='future_only':
        for r in records:
            if r['channel']=='wheel':r['stamp_s']=4.01
    if fault=='missing_gain':records=[r for r in records if r['channel']!='gain_map']
    with pytest.raises(ValueError,match='support incomplete'):m.align_raw(records,1.,3.,3.1)


def test_identical_duplicates_count_but_conflicting_payload_fails():
    records=raw(3.);copy=deepcopy(records[0]);records.append(copy)
    _,duplicates=m.align_raw(records,1.,3.,3.1)
    assert duplicates['drive']==1
    copy['values']['left_actual_rad_s']=999.
    with pytest.raises(ValueError,match='Conflicting'):m.align_raw(records,1.,3.,3.1)


def test_relaxation_model_predicts_later_time_block_but_is_not_identification():
    t=np.arange(221)*.02+3.
    target=np.full(len(t),.2);y=target-.01*np.exp(-(t-3.)/2.5)
    fit=m.recovery_fit(t,target,y,m.specification())
    assert fit['eligible'] and fit['affine_gain_bias_design_rank']==1
    assert not fit['affine_gain_bias_identified'] and not fit['physical_deadtime_identified']
    assert fit['exponential_zero_asymptote']['later_block_rmse_m_s']<fit['static_gain_later_rmse_m_s']/10
    assert fit['exponential_zero_asymptote']['tau_best_s']==pytest.approx(2.5,rel=.1)
    assert not fit['exponential_free_asymptote']['profile_band_is_confidence_interval']


def test_constant_bias_has_flat_tau_profile_not_a_measured_time_constant():
    t=np.arange(221)*.02+3.;u=np.full(len(t),.2);y=u-.004
    fit=m.recovery_fit(t,u,y,m.specification())
    assert fit['affine_gain_bias_design_rank']==1
    assert fit['exponential_free_asymptote']['sse_profile_tau_band_s']==pytest.approx([.1,10.])
    assert not fit['rank_is_sufficient_for_physical_identification']


def test_varying_reference_is_not_forced_into_static_plateau_model():
    t=np.arange(221)*.02+3.;u=np.linspace(.2,.205,len(t))
    fit=m.recovery_fit(t,u,u*.98,m.specification())
    assert not fit['eligible']


@pytest.mark.parametrize('fault',['reordered','nonfinite','missing_block'])
def test_fit_requires_both_ordered_finite_time_blocks(fault):
    t=np.arange(221)*.02+3.;u=np.full(len(t),.2);y=u-.004
    if fault=='reordered':t[10]=t[9]
    if fault=='nonfinite':y[10]=float('nan')
    if fault=='missing_block':t=t[:30];u=u[:30];y=y[:30]
    with pytest.raises(ValueError):m.recovery_fit(t,u,y,m.specification())


def test_actual_cell_diagnosis_preserves_primary_and_recovers_algorithm_proxy(tmp_path):
    cell=fixture_cell(tmp_path/'cell');r,points=m.audit_cell(cell,m.specification())
    assert r['native_rows']==140 and r['raw_plateau_samples']==len(points)==221
    assert r['raw_encoder_body_rmse_m_s']==pytest.approx(.0001)
    assert r['pi_algorithm_state_proxy']['inferred_integral_delta_rad']==pytest.approx(.044)
    assert not r['apparent_slope_is_geometry_or_traction_calibration']


def inputs(tmp_path,monkeypatch):
    upstream=tmp_path/'upstream';upstream.mkdir();held=tmp_path/'held';held.mkdir()
    for i in range(9):fixture_cell(upstream/f'eval_{i:02d}')
    m.save(upstream/'manifest.json',{});m.save(held/'manifest.json',{})
    monkeypatch.setattr(m,'source',lambda:(upstream,held))
    monkeypatch.setattr(m,'SOURCE_SHA',m.sha(upstream/'manifest.json'));monkeypatch.setattr(m,'HELD_SHA',m.sha(held/'manifest.json'))
    from nino_rl import gain_context
    monkeypatch.setattr(gain_context,'identity',lambda:dict(synthetic_only=True))
    monkeypatch.setattr(gain_context,'verify_transition',lambda *a,**kw:None)
    return upstream,held


def test_actual_offline_coordinator_no_processes_and_no_input_mutation(tmp_path,monkeypatch):
    upstream,held=inputs(tmp_path,monkeypatch)
    before={str(p):m.sha(p) for p in upstream.rglob('*') if p.is_file()}
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:pytest.fail('No processes from read-only audit'))
    out=tmp_path/'report';r=m.run(out)
    assert r['native_rows_checked']==1260 and r['raw_plateau_samples']==9*221
    assert not any(r['release'].values()) and not r['parameter_identification_verified']
    assert not r['controller_parameters_changed'] and not r['primary_metric_changed']
    assert m.verified_report(out)==r
    assert before=={str(p):m.sha(p) for p in upstream.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='exists'):m.run(out)


@pytest.mark.parametrize('target',['report','raw','traversal'])
def test_report_and_source_tampering_invalidate_diagnostic(tmp_path,monkeypatch,target):
    upstream,_=inputs(tmp_path,monkeypatch);out=tmp_path/'report';m.run(out)
    if target=='report':(out/'diagnostic.json').write_text('{}')
    if target=='raw':(upstream/'eval_00/episodes/episode_0/backend/episode_0/raw_samples.jsonl').write_text('{}')
    if target=='traversal':
        mf=m.read(out/'manifest.json');mf['files']['../escape']='x';m.save(out/'manifest.json',mf)
    with pytest.raises(ValueError):m.verified_report(out)


def test_incomplete_cell_retains_failure_without_success_seal(tmp_path,monkeypatch):
    upstream,_=inputs(tmp_path,monkeypatch)
    (upstream/'eval_00/trace.jsonl').write_text('{}\n')
    out=tmp_path/'report'
    with pytest.raises(ValueError):m.run(out)
    assert m.read(out/'failure.json')['retain_no_retry'] and not (out/'manifest.json').exists()


def test_protected_input_root_cannot_be_used_for_derived_output(tmp_path,monkeypatch):
    upstream,_=inputs(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='outside'):m.run(upstream/'child')
    assert not (upstream/'child').exists()
