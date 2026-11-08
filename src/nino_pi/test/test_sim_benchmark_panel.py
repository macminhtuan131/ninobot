"""Benchmark UI separates offline proof from unrun physics/training stages."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
import pytest
from PyQt5 import QtWidgets as Q,QtGui as G
from nino_pi.sim_benchmark_panel import SimBenchmarkPanel


@pytest.fixture
def decision_fixture(monkeypatch):
    from nino_pi import studio_training_evidence
    monkeypatch.setattr(studio_training_evidence,'scientific_assessment',lambda *a:None)
    monkeypatch.setattr(SimBenchmarkPanel,'latest_gain_record',lambda *a:None)
    monkeypatch.setattr(SimBenchmarkPanel,'latest_held_record',lambda *a:None)
    monkeypatch.setattr(SimBenchmarkPanel,'latest_dynamics_record',lambda *a:None)
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_record',lambda *a:None)
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_runner_record',lambda *a:None)
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_screen_record',lambda *a:None)
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_validation_record',lambda *a:None)
    monkeypatch.setattr(SimBenchmarkPanel,'latest_td3_training_record',lambda *a:None)
    from nino_rl import sim_benchmark_decision as decision
    report=dict(runs=[dict(condition=dict(arm=arm,source_stop_s=stop),open_ticks=30 if stop==6. else 50,
        closed_ticks=110 if stop==6. else 90,open_decision_first_s=2.5,
        open_decision_last_s=5.4 if stop==6. else 7.4,
        observed_open_cost_fraction=.4,observed_closed_cost_fraction=.6)
        for stop in (6.,8.) for arm in ('B0','A_gaussian','Classical_scheduled')])
    monkeypatch.setattr(decision,'verified_report',lambda *args:report)
    from nino_rl import gain_context_preflight
    monkeypatch.setattr(gain_context_preflight,'verified_report',lambda *args:dict(
        synthetic_driver_callbacks=4800,synthetic_wrapper_transitions=840))


def test_verified_panel_separates_offline_proof_from_unrun_physics(decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=SimBenchmarkPanel()
    assert panel.verified and panel.cost.rowCount()==6
    assert 'ĐÃ KIỂM OFFLINE' in panel.status.text()
    assert panel.gates.item(2,1).text()=='Offline đạt; Gazebo chưa chạy'
    assert panel.gates.item(3,1).text()=='Chưa mở'
    assert 'không phải counterfactual' in panel.limits.text()
    panel.close();app.processEvents()


def test_tamper_after_success_clears_all_previously_verified_rows(monkeypatch,decision_fixture):
    from nino_rl import sim_benchmark_decision as decision
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=SimBenchmarkPanel();assert panel.verified
    def fail(*args):raise ValueError('source changed')
    monkeypatch.setattr(decision,'verified_report',fail)
    panel.refresh.click();app.processEvents()
    assert not panel.verified and panel.cost.rowCount()==0
    assert 'CHƯA XÁC MINH' in panel.status.text()
    assert panel.gates.item(0,1).text()=='Chưa xác minh'
    panel.close();app.processEvents()


def test_benchmark_buttons_only_open_existing_documents(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    opened=[];monkeypatch.setattr(G.QDesktopServices,'openUrl',lambda url:opened.append(url.toLocalFile()))
    panel=SimBenchmarkPanel()
    panel.decision.click();panel.protocol.click();app.processEvents()
    assert [Path(p).name for p in opened]==['NINO_SIM_BENCHMARK_DECISION_2026-11-06.md',
        'NINO_SIM_GAIN_BASELINE_QUALIFICATION_DRAFT_2026-11-06.md']
    assert all(Path(p).is_file() for p in opened)
    panel.close();app.processEvents()


def test_roadmap_names_actual_next_step_without_releasing_learning():
    from nino_pi.next_steps_panel import NextStepsPanel
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=NextStepsPanel()
    assert '30,000' in panel.current.text() and 'CLASSICAL' in panel.current.text()
    assert 'BASELINE TRƯỚC LEARNER' in panel.steps[0]['status']
    assert not panel.open_collection.isEnabled()
    plan=json.loads(Path(__import__('nino_pi').__file__).with_name('research_plan.json').read_text())
    assert plan['training_allowed'] is False
    assert plan['sim_benchmark_decision']['new_gazebo_launches']==0
    assert not plan['sim_benchmark_decision']['qualification_released']
    panel.close();app.processEvents()


def test_reviewed_30k_view_and_tampered_evidence_clear_previous_success(monkeypatch):
    from nino_pi import studio_training_evidence as evidence
    app=Q.QApplication.instance() or Q.QApplication([]);panel=SimBenchmarkPanel()
    assert panel.verified and panel.assessment_metrics.rowCount()==2
    assert '30,000' in panel.status.text() and 'CLASSICAL' in panel.status.text()
    assert '25k' in panel.scope.text() and not panel.gates.isVisible()
    def fail(*a):raise ValueError('assessment changed')
    monkeypatch.setattr(evidence,'scientific_assessment',fail);panel.reload()
    assert not panel.verified and panel.assessment_metrics.rowCount()==0
    assert 'CHƯA XÁC MINH' in panel.status.text()
    panel.close();app.processEvents()


def test_stop6_validation_preparation_never_looks_like_physics_pass(monkeypatch,decision_fixture):
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_validation_record',lambda *a:dict(
        software_tests_passed=68,synthetic_cells=4,synthetic_decisions=560))
    app=Q.QApplication.instance() or Q.QApplication([]);panel=SimBenchmarkPanel()
    assert panel.verified and 'OFFLINE ĐẠT' in panel.pi_validation_status.text()
    assert '0slot' in panel.pi_validation_status.text() and 'synthetic' in panel.pi_validation_status.text()
    assert 'chưa cấp budget' in panel.status.text()
    opened=[];monkeypatch.setattr(G.QDesktopServices,'openUrl',lambda u:opened.append(u.toLocalFile()))
    panel.pi_validation_protocol.click()
    assert Path(opened[0]).name=='NINO_SIM_PI_STOP6_VALIDATION_PREPARATION_2026-11-07.md'
    panel.close();app.processEvents()


def test_stop6_artifact_change_clears_preparation_success(monkeypatch,decision_fixture):
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_validation_record',lambda *a:dict(
        software_tests_passed=68,synthetic_cells=4,synthetic_decisions=560))
    app=Q.QApplication.instance() or Q.QApplication([]);panel=SimBenchmarkPanel();assert panel.verified
    def fail(*a):raise ValueError('Stop6 source changed')
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_validation_record',fail);panel.reload()
    assert not panel.verified and 'chưa xác minh' in panel.pi_validation_status.text()
    assert 'OFFLINE ĐẠT' not in panel.pi_validation_status.text()
    panel.close();app.processEvents()


def test_short_TD3_training_is_not_an_algorithm_verdict(monkeypatch,decision_fixture):
    monkeypatch.setattr(SimBenchmarkPanel,'latest_td3_training_record',lambda *a:dict(
        seed=11,training_transitions=1024,critic_updates=960,actor_updates=480))
    app=Q.QApplication.instance() or Q.QApplication([]);panel=SimBenchmarkPanel()
    assert panel.verified and '1,024' in panel.td3_training_status.text()
    assert '960 critic / 480 actor' in panel.td3_training_status.text()
    assert 'chưa đủ' in panel.td3_training_status.text()
    assert 'Không yêu cầu TD3 thắng trước khi cho train' in panel.gates.item(3,2).text()
    assert 'thiết kế pilot TD3' in panel.status.text()
    panel.close();app.processEvents()


def test_TD3_training_counter_loader_checks_artifact_and_count(tmp_path):
    import hashlib
    path=tmp_path/'training_result.json'
    row=dict(seed=11,training_transitions=1024,critic_updates=960,actor_updates=480)
    path.write_text(json.dumps(row))
    record=dict(row,training_result=str(path),training_result_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    # No QWidget/ROS/Gazebo construction is needed to validate the counter source.
    assert SimBenchmarkPanel.latest_td3_training_record(None,dict(td3_training_evidence=record))==row
    record['training_transitions']=1025
    with pytest.raises(ValueError,match='counter mismatch'):
        SimBenchmarkPanel.latest_td3_training_record(None,dict(td3_training_evidence=record))
    path.write_text('{}')
    with pytest.raises(ValueError,match='artifact changed'):
        SimBenchmarkPanel.latest_td3_training_record(None,dict(td3_training_evidence=record))


def test_changed_context_preflight_cannot_leave_old_success_visible(monkeypatch,decision_fixture):
    from nino_rl import gain_context_preflight
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=SimBenchmarkPanel();assert panel.verified
    def fail(*args):raise ValueError('gain source changed')
    monkeypatch.setattr(gain_context_preflight,'verified_report',fail)
    panel.reload()
    assert not panel.verified and panel.cost.rowCount()==0
    assert panel.gates.item(2,1).text()=='Chưa xác minh'
    panel.close();app.processEvents()


def test_sealed_gazebo_result_replaces_unrun_stage_without_opening_learning(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    monkeypatch.setattr(SimBenchmarkPanel,'latest_gain_record',lambda *a:dict(
        status='completed',cells=9,ticks=1260,decision='unknown_grid_sensitive'))
    panel=SimBenchmarkPanel()
    assert panel.verified and panel.gates.item(2,1).text()=='Gazebo đã đóng9/9'
    assert panel.gates.item(3,1).text()=='Chưa mở'
    assert 'unknown_grid_sensitive' in panel.status.text()
    assert '1260' in panel.gates.item(2,2).text()
    panel.close();app.processEvents()


def test_held_software_proof_does_not_promote_physics_or_learning(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    monkeypatch.setattr(SimBenchmarkPanel,'latest_held_record',lambda *a:dict(
        synthetic_decisions=143,shadow_decisions=1260))
    panel=SimBenchmarkPanel()
    assert panel.verified and '143' in panel.held_status.text() and '1260' in panel.held_status.text()
    assert 'UNKNOWN' in panel.held_status.text() and 'shadow không là outcome' in panel.held_status.text()
    assert panel.gates.item(3,1).text()=='Chưa mở'
    panel.close();app.processEvents()


def test_held_report_tamper_clears_success(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=SimBenchmarkPanel();assert panel.verified
    def fail(*args):raise ValueError('held artifact changed')
    monkeypatch.setattr(SimBenchmarkPanel,'latest_held_record',fail)
    panel.reload()
    assert not panel.verified and panel.cost.rowCount()==0
    assert 'không giữ trạng thái pass cũ' in panel.held_status.text()
    panel.close();app.processEvents()


def test_dynamics_panel_keeps_raw_unknown_and_draft_unreleased(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    monkeypatch.setattr(SimBenchmarkPanel,'latest_dynamics_record',lambda *a:dict(
        native_rows_checked=1260,complete_raw_query_cells=8,unknown_raw_query_cells=1,raw_conflicting_stamps=4,
        runs=[dict(relaxation_models=dict(eligible=True),raw_target_encoder_rmse_m_s=.005,
            raw_encoder_body_rmse_m_s=.0001) for i in range(6)]))
    panel=SimBenchmarkPanel()
    assert panel.verified and '8/9 raw query đủ, 1 UNKNOWN' in panel.dynamics_status.text()
    assert '4 conflicting stamps' in panel.dynamics_status.text()
    assert 'chưa đổi gain/current' in panel.dynamics_status.text()
    assert panel.gates.item(3,1).text()=='Chưa mở'
    panel.close();app.processEvents()


def test_dynamics_tamper_clears_prior_success(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=SimBenchmarkPanel();assert panel.verified
    def fail(*args):raise ValueError('dynamics artifact changed')
    monkeypatch.setattr(SimBenchmarkPanel,'latest_dynamics_record',fail)
    panel.reload()
    assert not panel.verified and panel.cost.rowCount()==0
    assert 'không giữ trạng thái pass cũ' in panel.dynamics_status.text()
    panel.close();app.processEvents()


def test_pi_preflight_is_software_proof_and_never_starts_job(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_record',lambda *a:dict(
        synthetic_kernel_callbacks=3600,synthetic_wrapper_transitions=560))
    opened=[];monkeypatch.setattr(G.QDesktopServices,'openUrl',lambda url:opened.append(url.toLocalFile()))
    panel=SimBenchmarkPanel()
    assert panel.verified and '3,600 callbacks' in panel.pi_status.text()
    assert 'chưa chạy Gazebo' in panel.pi_status.text() and panel.gates.item(3,1).text()=='Chưa mở'
    panel.pi_draft.click();app.processEvents()
    assert [Path(p).name for p in opened]==['NINO_SIM_PI_SCREEN_OFFLINE_RESULT_2026-11-07.md']
    assert all(Path(p).is_file() for p in opened)
    panel.close();app.processEvents()


def test_pi_artifact_failure_clears_all_success(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=SimBenchmarkPanel();assert panel.verified
    def fail(*args):raise ValueError('PI source changed')
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_record',fail);panel.reload()
    assert not panel.verified and panel.cost.rowCount()==0
    assert 'không giữ trạng thái pass cũ' in panel.pi_status.text()
    panel.close();app.processEvents()


def test_runner_proof_does_not_release_physics_and_button_only_opens_protocol(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_runner_record',lambda *a:dict(
        synthetic_cells=4,synthetic_decisions=560))
    opened=[];monkeypatch.setattr(G.QDesktopServices,'openUrl',lambda url:opened.append(url.toLocalFile()))
    panel=SimBenchmarkPanel()
    assert panel.verified and '4 cell / 560 decisions synthetic' in panel.pi_runner_status.text()
    assert 'release=false' in panel.pi_runner_status.text()
    assert panel.gates.item(3,1).text()=='Chưa mở'
    panel.pi_runner_protocol.click();app.processEvents()
    assert [Path(p).name for p in opened]==['NINO_SIM_PI_SCREEN_RUNNER_PROTOCOL_2026-11-07.md']
    assert all(Path(p).is_file() for p in opened)
    panel.close();app.processEvents()


def test_runner_proof_tamper_clears_every_verified_label(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=SimBenchmarkPanel();assert panel.verified
    def fail(*a):raise ValueError('runner source changed')
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_runner_record',fail);panel.reload()
    assert not panel.verified and panel.cost.rowCount()==0
    assert 'không giữ trạng thái pass cũ' in panel.pi_runner_status.text()
    panel.close();app.processEvents()


def test_PI_screen_shows_native_GT_constraints_and_no_promotion(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_screen_record',lambda *a:dict(
        completed_cells=4,valid_ticks=560,
        comparison=dict(decision='descriptive_PI_candidate_separate_validation_required',
            pairs=[dict(relative_candidate_vs_baseline=[-.217,-.134,-.134]),dict(relative_candidate_vs_baseline=[-.195,-.102,-.102])]),
        source_ambiguity=dict(total_joint_conflicting_stamps=3),metrics=[dict(
            condition=dict(cell=i,ki=.1 if i in (0,3) else .15),native_vrmse_m_s=.005,
            GT20ms_vrmse_m_s=.007,GTshift10ms_vrmse_m_s=.0071,path_rmse_mm=.1,task_pass=True)
            for i in range(4)]))
    opened=[];monkeypatch.setattr(G.QDesktopServices,'openUrl',lambda url:opened.append(url.toLocalFile()))
    panel=SimBenchmarkPanel()
    assert panel.verified and panel.pi_metrics.rowCount()==4
    assert '21.7% / 19.5%' in panel.pi_screen_status.text()
    assert '3 conflicting joint stamps' in panel.pi_screen_status.text()
    assert panel.pi_metrics.item(0,1).text()=='5.000'
    assert panel.pi_metrics.item(0,2).text()=='7.000'
    assert panel.gates.item(3,1).text()=='Chưa mở'
    assert 'chưa promote' in panel.pi_screen_status.text()
    panel.pi_screen_result.click();app.processEvents()
    assert [Path(p).name for p in opened]==['NINO_SIM_PI_SCREEN_RESULT_2026-11-07.md']
    assert all(Path(p).is_file() for p in opened)
    panel.close();app.processEvents()


def test_PI_screen_tamper_clears_table_and_positive_status(monkeypatch,decision_fixture):
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=SimBenchmarkPanel();assert panel.verified
    def fail(*args):raise ValueError('PI screen changed')
    monkeypatch.setattr(SimBenchmarkPanel,'latest_pi_screen_record',fail);panel.reload()
    assert not panel.verified and panel.pi_metrics.rowCount()==0
    assert panel.gates.item(2,1).text()=='Chưa xác minh'
    assert 'không giữ trạng thái pass cũ' in panel.pi_screen_status.text()
    panel.close();app.processEvents()
