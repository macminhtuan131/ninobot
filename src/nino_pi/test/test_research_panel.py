"""Artifact-backed progress and a real bounded local validation job; no Pi."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import json
import hashlib
import pytest
import tempfile
import time
from PyQt5 import QtWidgets as Q,QtTest
from nino_pi.research_panel import ResearchPanel
from nino_pi.research_jobs import workflow_state
from nino_rl.residual_workflow import latest
from nino_rl.residual_experiment import source_fingerprint


def wait(app,predicate,seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        QtTest.QTest.qWait(20)
    raise AssertionError('Local job did not close')


def test_real_local_validate_job_updates_manifest_progress_and_tamper_invalidates():
    app=Q.QApplication.instance() or Q.QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        p=ResearchPanel(root=folder);p.show();app.processEvents()
        assert not p.buttons['train-td3'].isEnabled()
        p.run('validate');assert p.runner.busy
        wait(app,lambda:not p.runner.busy)
        assert workflow_state(folder)['validate']['state']=='verified',p.log.toPlainText()
        assert p.buttons['train-td3'].isEnabled()
        p.show_result(0,0);assert 'software_integration_reduced_order_only' in p.results.toPlainText()
        target=Path(workflow_state(folder)['validate']['path'])/'validation.json'
        target.write_text('{}')
        p.reload();assert not p.buttons['train-td3'].isEnabled()
        assert workflow_state(folder)['validate']['state']=='pending'
        p.close()


def test_hardware_work_blocks_local_jobs_and_sysid_requires_registration():
    app=Q.QApplication.instance() or Q.QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        p=ResearchPanel(root=folder,hardware_busy=lambda:True)
        assert not any(b.isEnabled() for b in p.buttons.values())
        p.run('validate');assert not p.runner.busy
        p.hardware_busy=lambda:False;p.refresh()
        assert p.buttons['validate'].isEnabled() and not p.buttons['sysid'].isEnabled()
        p.close();app.processEvents()


def test_latest_failure_cannot_fall_back_to_previous_success():
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder)/'state.json').write_text(json.dumps(dict(latest={'validate':'old_success'},runs=[
            dict(action='validate',path='old_success',status='completed'),
            dict(action='validate',path='new_failure',status='failed')])))
        with pytest.raises(ValueError,match='Latest validate attempt failed'):
            latest(folder,'validate',check_runtime=False)


def test_operational_outline_is_default_and_does_not_execute_jobs_or_motion():
    app=Q.QApplication.instance() or Q.QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        p=ResearchPanel(root=folder);events=[];p.collectionRequested.connect(events.append)
        assert p.sections.currentIndex()==3 and p.roadmap.list.count()==8
        assert set(p.sim_buttons)=={'sim-baselines','sim-train','sim-evaluate','sim-v2-baselines','sim-v2-train','sim-v2-evaluate','sim-bias-clear','sim-guidance-contract','sim-v3-baselines','sim-guided-contact','sim-v3-contract','sim-v3-train','sim-v3-evaluate','sim-axis-ablation','sim-classical-common','sim-stop-transfer','sim-equal-contract','sim-equal-gazebo','sim-common-td3','sim-joint-boundary','sim-joint-reliability-fixture','sim-joint-reliability-gazebo','sim-reliable-td3','sim-reliable-eval-only','sim-coverage-preflight','sim-coverage-study','sim-coverage-v2-preflight','sim-coverage-v2-study','sim-drive-readiness','sim-ready-eval-only','sim-gain-baselines'}
        assert p.active_sim_actions()[0]=='sim-v2-baselines'
        assert p.sim_buttons['sim-v2-baselines'].isEnabled() and not p.sim_buttons['sim-v2-train'].isEnabled()
        assert 'Không đợi real dataset' in p.roadmap.detail.toPlainText()
        assert not p.runner.busy
        assert not p.roadmap.open_collection.isEnabled()
        assert events==[]
        p.roadmap.list.setCurrentRow(5)
        assert not p.roadmap.open_collection.isEnabled()
        assert 'simulator' in p.roadmap.detail.toPlainText()
        assert not p.runner.busy
        p.roadmap.list.setCurrentRow(7)
        assert 'CHƯA MỞ TRIỂN KHAI' in p.roadmap.detail.toPlainText()
        p.close();app.processEvents()


def test_benchmark_decision_opens_document_without_starting_job(tmp_path, monkeypatch):
    from nino_pi import research_jobs
    from nino_pi.next_steps_panel import NextStepsPanel
    from PyQt5 import QtGui as G
    app=Q.QApplication.instance() or Q.QApplication([])
    doc=tmp_path/'docs/NINO_TD3_OFFLINE_PHASE_REVIEW_2026-11-07.md'
    doc.parent.mkdir();doc.write_text('draft')
    monkeypatch.setattr(research_jobs,'repository',lambda:tmp_path)
    opened=[]
    monkeypatch.setattr(G.QDesktopServices,'openUrl',lambda url:opened.append(url.toLocalFile()))
    panel=NextStepsPanel(workstream='hardware')
    assert 'BASELINE TRƯỚC LEARNER' in panel.detail.toPlainText()
    assert 'shadow trên trace cũ không phải outcome mới' in panel.detail.toPlainText()
    panel.open_protocol.click();app.processEvents()
    assert opened==[str(doc)]
    plan=json.loads(Path(research_jobs.__file__).with_name('research_plan.json').read_text())
    assert plan['sim_critic_coverage_draft']['training_released'] is False
    assert plan['sim_critic_coverage_draft']['runner_implemented'] is True
    assert plan['training_allowed'] is False
    panel.close();app.processEvents()


def test_clear_bias_workflow_starts_with_read_only_diagnostic_not_training(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_clear_bias_v1')
    assert p.sim_version.currentIndex()==2
    assert p.active_sim_actions()==('sim-bias-clear','sim-guidance-contract')
    assert p.sim_buttons['sim-bias-clear'].isEnabled()
    assert not p.sim_buttons['sim-guidance-contract'].isEnabled()
    assert 'zero optimizer' in p.sim_note.text()
    assert not p.runner.busy
    p.close();app.processEvents()


def test_v3_baseline_screen_is_finite_and_does_not_launch_on_open(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_guided_baseline_v3')
    assert p.sim_version.currentIndex()==3 and p.active_sim_actions()==('sim-v3-baselines',)
    assert p.sim_buttons['sim-v3-baselines'].isEnabled()
    assert '8 lượt' in p.sim_note.text() and 'không actor' in p.sim_note.text()
    assert not p.runner.busy
    p.close();app.processEvents()


def test_sim_progress_invalidates_downstream_after_new_baseline(tmp_path):
    from nino_rl.residual_sim_pilot import fingerprint
    def artifact(name,action,extras=None):
        path=tmp_path/name;path.mkdir()
        for file,value in (extras or {}).items():(path/file).write_text(json.dumps(value))
        manifest=dict(action=action,status='completed',source_fingerprint=source_fingerprint(),pilot_fingerprint=fingerprint(),files={})
        (path/'manifest.json').write_text(json.dumps(manifest));return path
    baseline=artifact('baseline_0','sim-baselines')
    trained=artifact('trained_0','sim-train',{'dependencies.json':dict(baseline=str(baseline),manifest_sha256=hashlib.sha256((baseline/'manifest.json').read_bytes()).hexdigest())})
    evaluation=artifact('eval_0','sim-evaluate',{'evaluation_result.json':dict(checkpoint=str(trained))})
    state=dict(latest={'sim-baselines':baseline.name,'sim-train':trained.name,'sim-evaluate':evaluation.name},runs=[])
    (tmp_path/'state.json').write_text(json.dumps(state))
    assert all(workflow_state(tmp_path)[a]['state']=='verified' for a in state['latest'])
    newer=artifact('baseline_1','sim-baselines');state['latest']['sim-baselines']=newer.name
    (tmp_path/'state.json').write_text(json.dumps(state))
    result=workflow_state(tmp_path)
    assert result['sim-baselines']['state']=='verified'
    assert result['sim-train']['state']=='pending' and result['sim-evaluate']['state']=='pending'


def test_v2_progress_checks_task_and_recursive_dependencies(tmp_path,monkeypatch):
    from nino_rl import residual_sim_task as task
    monkeypatch.setattr(task,'fingerprint',lambda:'v2-source')
    def artifact(name,action,extras=None):
        path=tmp_path/name;path.mkdir()
        for file,value in (extras or {}).items():(path/file).write_text(json.dumps(value))
        (path/'manifest.json').write_text(json.dumps(dict(action=action,status='completed',
            source_fingerprint=source_fingerprint(),task_fingerprint='v2-source',files={})))
        return path
    base=artifact('base','sim-v2-baselines')
    trained=artifact('train','sim-v2-train',{'dependencies.json':task.dependency_record(base)})
    evaluation=artifact('eval','sim-v2-evaluate',{'dependencies.json':task.dependency_record(trained)})
    state=dict(latest={'sim-v2-baselines':base.name,'sim-v2-train':trained.name,'sim-v2-evaluate':evaluation.name},runs=[])
    (tmp_path/'state.json').write_text(json.dumps(state))
    assert all(workflow_state(tmp_path)[a]['state']=='verified' for a in state['latest'])
    from nino_pi.research_jobs import ResearchRunner
    with pytest.raises(ValueError,match='hoàn tất'):
        ResearchRunner(tmp_path).start('sim-v2-baselines')
    newer=artifact('base2','sim-v2-baselines');state['latest']['sim-v2-baselines']=newer.name
    (tmp_path/'state.json').write_text(json.dumps(state))
    result=workflow_state(tmp_path)
    assert result['sim-v2-train']['state']=='pending' and result['sim-v2-evaluate']['state']=='pending'
    state['latest']['sim-v2-baselines']=base.name;(tmp_path/'state.json').write_text(json.dumps(state))
    monkeypatch.setattr(task,'fingerprint',lambda:'different-objective')
    assert workflow_state(tmp_path)['sim-v2-baselines']['state']=='pending'


def test_td3_audit_cannot_remain_verified_after_checkpoint_or_auditor_change(tmp_path):
    from nino_rl import residual_td3_audit
    def manifest(path,action,**extra):
        path.mkdir(exist_ok=True)
        value=dict(action=action,status='completed',source_fingerprint=source_fingerprint(),files={},**extra)
        (path/'manifest.json').write_text(json.dumps(value));return value
    train=tmp_path/'train';manifest(train,'train-td3')
    audit=tmp_path/'audit';value=manifest(audit,'audit-td3',input_artifact=str(train),
        input_manifest_sha256=hashlib.sha256((train/'manifest.json').read_bytes()).hexdigest(),
        auditor_sha256=hashlib.sha256(Path(residual_td3_audit.__file__).read_bytes()).hexdigest())
    state=dict(latest={'train-td3':'train','audit-td3':'audit'},runs=[])
    (tmp_path/'state.json').write_text(json.dumps(state))
    assert workflow_state(tmp_path)['audit-td3']['state']=='verified'
    broken=dict(value,auditor_sha256='stale');(audit/'manifest.json').write_text(json.dumps(broken))
    assert workflow_state(tmp_path)['audit-td3']['state']=='pending'
    (audit/'manifest.json').write_text(json.dumps(value))
    manifest(tmp_path/'new_train','train-td3');state['latest']['train-td3']='new_train'
    (tmp_path/'state.json').write_text(json.dumps(state))
    assert workflow_state(tmp_path)['audit-td3']['state']=='pending'


def test_factory_smoke_pass_does_not_claim_task_benefit_and_source_change_invalidates(tmp_path,monkeypatch):
    from nino_rl import residual_factory_workflow
    monkeypatch.setattr(residual_factory_workflow,'factory_fingerprint',lambda:'factory-source-v1')
    out=tmp_path/'factory';out.mkdir()
    result=out/'factory_result.json';result.write_text(json.dumps(dict(transitions=128,physical_benefit_verified=False)))
    (out/'manifest.json').write_text(json.dumps(dict(action='factory-td3',status='completed',
        source_fingerprint=source_fingerprint(),factory_fingerprint='factory-source-v1',
        files={'factory_result.json':hashlib.sha256(result.read_bytes()).hexdigest()})))
    (tmp_path/'state.json').write_text(json.dumps(dict(latest={'factory-td3':'factory'},runs=[])))
    app=Q.QApplication.instance() or Q.QApplication([]);p=ResearchPanel(root=tmp_path)
    assert p.states['factory-td3']['state']=='verified'
    assert 'TASK CHƯA XÁC NHẬN' in p.states['factory-td3']['label']
    p.show_result(list(p.buttons).index('factory-td3'),0)
    assert 'learned benefit chưa được xác nhận' in p.results.toPlainText()
    monkeypatch.setattr(residual_factory_workflow,'factory_fingerprint',lambda:'factory-source-v2')
    p.reload();assert p.states['factory-td3']['state']=='pending'
    p.close();app.processEvents()


def test_contact_screen_has_separate_root_and_no_job_on_open(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_guided_contact_v1')
    assert p.sim_version.currentIndex()==4
    assert p.active_sim_actions()==('sim-guided-contact',)
    assert '560 transition' in p.sim_note.text() and 'Gate fail' in p.sim_note.text()
    assert not p.runner.busy
    p.close();app.processEvents()


def test_v3_learning_ui_no_auto_training_and_failed_stage_cannot_retry(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_guided_td3_v3')
    assert p.sim_version.currentIndex()==5
    assert p.active_sim_actions()==('sim-v3-contract','sim-v3-train','sim-v3-evaluate')
    assert p.sim_buttons['sim-v3-contract'].isEnabled()
    assert not p.sim_buttons['sim-v3-train'].isEnabled() and not p.runner.busy
    p.root.mkdir();(p.root/'state.json').write_text(json.dumps(dict(latest={},runs=[dict(action='sim-v3-contract',status='failed',path='failed')])) )
    p.reload();assert not p.sim_buttons['sim-v3-contract'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-v3-contract')
    p.close();app.processEvents()


def test_contact_result_cannot_overwrite_other_job_states(tmp_path,monkeypatch):
    from nino_pi.research_jobs import JOBS
    from nino_rl import residual_workflow,residual_guided_contact
    def lookup(root,action,**kwargs):
        if action!='sim-guided-contact':raise ValueError('No artifact')
        return tmp_path
    monkeypatch.setattr(residual_workflow,'latest',lookup)
    monkeypatch.setattr(residual_guided_contact,'validated_latest',lambda *args,**kwargs:tmp_path)
    (tmp_path/'evaluation_result.json').write_text(json.dumps({'baseline_functional_candidate':True}))
    states=workflow_state(tmp_path)
    assert set(states)==set(JOBS) and states['sim-guided-contact']['state']=='verified'
    assert states['validate']['state']=='pending' and states['sysid']['state']=='pending'


def test_axis_ablation_separate_root_no_auto_job_and_closed_failure_blocks_retry(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_axis_ablation_v1')
    assert p.sim_version.currentIndex()==6 and p.active_sim_actions()==('sim-axis-ablation',)
    assert '840 transition' in p.sim_note.text() and not p.runner.busy
    p.root.mkdir();(p.root/'state.json').write_text(json.dumps(dict(latest={},runs=[dict(action='sim-axis-ablation',status='failed',path='failed')])) )
    p.reload();assert not p.sim_buttons['sim-axis-ablation'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-axis-ablation')
    p.close();app.processEvents()


def test_classical_common_has_single_closed_budget_and_no_auto_job(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_classical_common_v1')
    assert p.sim_version.currentIndex()==7 and p.active_sim_actions()==('sim-classical-common',)
    assert '840 tick' in p.sim_note.text() and not p.busy
    p.root.mkdir();(p.root/'state.json').write_text(json.dumps(dict(latest={},runs=[dict(action='sim-classical-common',status='running',path='running')])) )
    p.reload();assert not p.sim_buttons['sim-classical-common'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-classical-common')
    p.close();app.processEvents()


def test_stop_transfer_separate_root_and_closed_budget(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_stop_transfer_v1')
    assert p.sim_version.currentIndex()==8 and p.active_sim_actions()==('sim-stop-transfer',)
    assert '840 ticks' in p.sim_note.text() and not p.busy
    p.root.mkdir();(p.root/'state.json').write_text('{}')
    p.reload();assert not p.sim_buttons['sim-stop-transfer'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-stop-transfer')
    p.close();app.processEvents()


def test_equal_contract_profile_is_offline_and_consumed_budget_cannot_retry(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_equal_information_v1')
    assert p.sim_version.currentIndex()==9 and p.active_sim_actions()==('sim-equal-contract',)
    assert 'không physics' in p.sim_note.text() and not p.busy
    p.root.mkdir();(p.root/'state.json').write_text('{}')
    p.reload();assert not p.sim_buttons['sim-equal-contract'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-equal-contract')
    p.close();app.processEvents()


@pytest.mark.parametrize('action,filename',[('sim-reliable-eval-only','evaluation_result.json'),('sim-reliable-td3','pilot_result.json'),('sim-stop-transfer','evaluation_result.json'),('sim-equal-contract','qualification.json'),('sim-equal-gazebo','qualification_result.json'),('sim-common-td3','pilot_result.json'),('sim-joint-boundary','diagnostic_result.json'),('sim-joint-reliability-fixture','fixture_result.json'),('sim-joint-reliability-gazebo','qualification_result.json')])
def test_new_result_buttons_read_the_right_artifact_without_job(tmp_path,action,filename):
    from nino_pi.research_jobs import JOBS
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path);marker='result_button_fixture_'+action
    (tmp_path/filename).write_text(json.dumps(dict(marker=marker)))
    p.states[action]=dict(state='verified',path=str(tmp_path),label='fixture')
    p.show_sim_result(action)
    assert marker in p.sim_log.toPlainText()
    p.show_result(list(JOBS).index(action),0)
    assert marker in p.results.toPlainText() and not p.busy
    p.close();app.processEvents()


def test_reliable_td3_profile_has_separate_root_and_consumed_budget_lock(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_reliable_td3_v1')
    assert p.sim_version.currentIndex()==14 and p.active_sim_actions()==('sim-reliable-td3',)
    assert '3.072 train' in p.sim_note.text() and not p.busy
    assert p.sim_table.columnCount()==10
    p.root.mkdir();(p.root/'state.json').write_text('corrupt ledger')
    p.reload();assert not p.sim_buttons['sim-reliable-td3'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-reliable-td3')
    p.close();app.processEvents()


def test_eval_only_profile_separate_root_no_auto_job_and_corrupt_budget_lock(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_reliable_eval_only_v1')
    assert p.sim_version.currentIndex()==15 and p.active_sim_actions()==('sim-reliable-eval-only',)
    assert '1.400' in p.sim_note.text() and 'không optimizer' in p.sim_note.text() and not p.busy
    p.root.mkdir();(p.root/'state.json').write_text('corrupt')
    p.reload();assert not p.sim_buttons['sim-reliable-eval-only'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-reliable-eval-only')
    p.close();app.processEvents()


@pytest.mark.parametrize('failed',[False,True])
def test_eval_only_table_shows_valid_runs_and_keeps_failed_partial(tmp_path,failed):
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_reliable_eval_only_v1');out=tmp_path/'artifact';out.mkdir()
    m=dict(evaluation_condition=dict(arm='TD3',seed=11,source_stop_s=6.),steps=140,nominal_velocity_rmse_m_s=.005,
        timestamp_diagnostic=dict(header_grid={'0.0':dict(rmse_m_s=.006),'0.01':dict(rmse_m_s=.0061)}),
        cross_track_rmse_m=.0001,task_success=True,stop_completed=True,maximum_native_boundary_support_age_s=.02,
        actor_before=dict(critic_updates=960),actor_after=dict(critic_updates=960))
    filename='evaluation_progress.json' if failed else 'evaluation_result.json'
    (out/filename).write_text(json.dumps(dict(runs=[m])))
    state=dict(state='retained_failure' if failed else 'verified',path=str(out),error='auxiliary observer timeout' if failed else None)
    p.show_eval_only_table(state)
    assert p.sim_table.rowCount()==1 and p.sim_table.columnCount()==10
    assert p.sim_table.item(0,3).text()=='0.0050000' and p.sim_table.item(0,9).text()=='Đạt'
    assert p.sim_progress.value()==140 and 'optimizer 0' in p.sim_progress.format()
    if failed:assert 'auxiliary observer timeout' in p.sim_next.text() and 'không retry' in p.sim_next.text()
    else:assert 'Chưa mở train dài' in p.sim_next.text()
    assert not p.busy;p.close();app.processEvents()


def test_eval_only_quality_and_recommendation_require_matching_manifest(tmp_path):
    import hashlib
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_reliable_eval_only_v1');p.root.mkdir()
    out=p.root/'artifact';out.mkdir();(out/'manifest.json').write_text('{}')
    (out/'evaluation_result.json').write_text('{"runs":[]}')
    review=dict(artifact=str(out),artifact_manifest_sha256=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest(),
        files_verified=323,feedback_checks=4260,maximum_primary_joint_age_ms=1.,maximum_independent_joint_age_ms=1.,
        payload_mismatches=0,one_sided_stamps_by_phase={'independent_before_task':69},descriptive_all_grid_wins=0)
    (p.root/'review.json').write_text(json.dumps(review));state=dict(state='verified',path=str(out))
    p.show_eval_only_table(state)
    assert '323' in p.sim_guidance_status.text() and '0/6' in p.sim_next.text() and 'Giữ baseline' in p.sim_next.text()
    review['artifact_manifest_sha256']='bad';(p.root/'review.json').write_text(json.dumps(review))
    p.show_eval_only_table(state)
    assert 'QC audit:' not in p.sim_guidance_status.text() and '0/6' not in p.sim_next.text()
    p.close();app.processEvents()


def test_long_static_result_keeps_first_and_last_lines_and_live_limit_returns(tmp_path,monkeypatch):
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path);action='sim-reliable-eval-only'
    data='FIRST_RESULT_FIELD\n'+'detail\n'*600+'LAST_RESULT_FIELD'
    (tmp_path/'evaluation_result.json').write_text(data)
    p.states[action]=dict(state='verified',path=str(tmp_path),label='fixture')
    p.show_sim_result(action)
    assert 'FIRST_RESULT_FIELD' in p.sim_log.toPlainText() and 'LAST_RESULT_FIELD' in p.sim_log.toPlainText()
    assert p.sim_log.document().maximumBlockCount()==0 and not p.busy
    monkeypatch.setattr(p.runner,'start',lambda action:False)
    p.run(action)
    assert p.sim_log.document().maximumBlockCount()==300 and not p.busy
    p.close();app.processEvents()


def test_reliable_partial_is_retained_and_hash_tamper_never_unlocks_retry(tmp_path):
    import hashlib
    from nino_pi.research_jobs import retained_reliable_failure
    from nino_rl.residual_reliable_td3 import fingerprint
    app=Q.QApplication.instance() or Q.QApplication([])
    root=tmp_path/'sim_reliable_td3_v1';out=root/'failed';out.mkdir(parents=True)
    (out/'job.json').write_text('{"status":"failed","error":"other channel stale"}')
    (out/'manifest.json').write_text(json.dumps(dict(status='failed',reliable_td3_fingerprint=fingerprint(),
        files={'job.json':hashlib.sha256((out/'job.json').read_bytes()).hexdigest()})))
    (root/'state.json').write_text(json.dumps(dict(latest={},runs=[dict(action='sim-reliable-td3',path='failed',status='failed',error='other channel stale')])))
    p=ResearchPanel(root=root)
    assert p.states['sim-reliable-td3']['state']=='retained_failure'
    assert 'other channel stale' in p.sim_next.text()
    assert not p.sim_buttons['sim-reliable-td3'].isEnabled() and not p.busy
    p.show_sim_result('sim-reliable-td3');assert 'other channel stale' in p.sim_log.toPlainText()
    (out/'job.json').write_text('tampered')
    assert retained_reliable_failure(root) is None
    p.reload();assert not p.sim_buttons['sim-reliable-td3'].isEnabled()
    p.close();app.processEvents()


def test_equal_gazebo_has_four_launch_budget_and_no_automatic_job(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_equal_gazebo_v1')
    assert p.sim_version.currentIndex()==10 and p.active_sim_actions()==('sim-equal-gazebo',)
    assert '560ticks' in p.sim_note.text() and not p.busy
    p.root.mkdir();(p.root/'state.json').write_text('{}')
    p.reload();assert not p.sim_buttons['sim-equal-gazebo'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-equal-gazebo')
    p.close();app.processEvents()


def test_common_td3_profile_budget_and_no_automatic_job(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_common_td3_v1')
    assert p.sim_version.currentIndex()==11 and p.active_sim_actions()==('sim-common-td3',)
    assert '4472controlticks/34launches' in p.sim_note.text() and not p.busy
    p.root.mkdir();(p.root/'state.json').write_text('{}')
    p.reload();assert not p.sim_buttons['sim-common-td3'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-common-td3')
    p.close();app.processEvents()


def test_failed_common_batch_is_visible_but_not_verified_or_retryable(tmp_path):
    import hashlib
    from nino_rl.residual_common_td3 import fingerprint
    from nino_pi.research_jobs import retained_common_failure
    app=Q.QApplication.instance() or Q.QApplication([])
    root=tmp_path/'sim_common_td3_v1';out=root/'failed';out.mkdir(parents=True)
    (out/'job.json').write_text('{"status":"failed"}')
    (out/'manifest.json').write_text(json.dumps(dict(status='failed',common_td3_fingerprint=fingerprint(),
        files={'job.json':hashlib.sha256((out/'job.json').read_bytes()).hexdigest()})))
    (root/'state.json').write_text(json.dumps(dict(latest={},runs=[dict(action='sim-common-td3',path='failed',status='failed',error='stale joint')])) )
    review=dict(artifact=str(out),artifact_manifest_sha256=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest(),
        training_transitions=700,critic_updates=636,actor_optimizer_updates=318,episodes=[])
    (root/'review.json').write_text(json.dumps(review))
    p=ResearchPanel(root=root)
    assert p.states['sim-common-td3']['state']=='retained_failure'
    assert '700/3072' in p.sim_next.text() and 'Eval0/10' in p.sim_next.text()
    assert p.sim_progress.value()==700 and 'ĐÃ ĐÓNG' in p.sim_progress.format()
    assert not p.sim_buttons['sim-common-td3'].isEnabled() and not p.busy
    p.show_sim_result('sim-common-td3');assert '636' in p.sim_log.toPlainText()
    (out/'job.json').write_text('tampered')
    assert retained_common_failure(root) is None
    p.reload();assert p.states['sim-common-td3']['state']=='pending'
    assert not p.sim_buttons['sim-common-td3'].isEnabled()
    p.close();app.processEvents()


def test_joint_boundary_profile_two_launch_budget_no_auto_job(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_joint_boundary_v1')
    assert p.sim_version.currentIndex()==12 and p.active_sim_actions()==('sim-joint-boundary',)
    assert '200native ticks' in p.sim_note.text() and not p.busy
    p.root.mkdir();(p.root/'state.json').write_text('{}')
    p.reload();assert not p.sim_buttons['sim-joint-boundary'].isEnabled()
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-joint-boundary')
    p.close();app.processEvents()


def test_joint_diagnostic_quality_review_is_bound_to_artifact_and_keeps_unknown(tmp_path):
    import hashlib
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_joint_boundary_v1')
    p.root.mkdir();artifact=p.root/'result';artifact.mkdir();(artifact/'manifest.json').write_text('{}')
    p.states['sim-joint-boundary']=dict(state='verified',path=str(artifact),label='fixture')
    data=dict(runs=[dict(launch=0,complete_zero_ticks=100,feedback_checks=306,all_support_pass=True,error=None,cleanup_error=None)],
        complete_zero_control_ticks=100,launches=1,outcome='not_reproduced_unknown',root_cause='unknown')
    review=dict(artifact=str(artifact),manifest_sha256=hashlib.sha256((artifact/'manifest.json').read_bytes()).hexdigest(),
        quality=[dict(launch=0,max_supported_endpoint_age_ms=dict(primary=1.,independent=2.),semantic_hash_mismatches=0)])
    (p.root/'review.json').write_text(json.dumps(review))
    p.show_joint_boundary_table(data)
    assert p.sim_table.columnCount()==8 and p.sim_table.item(0,3).text()=='1.0'
    assert p.sim_table.item(0,5).text()=='0' and 'CHƯA RÕ' in p.sim_next.text()
    assert 'không training' in p.sim_progress.format() and not p.busy
    review['manifest_sha256']='invalid';(p.root/'review.json').write_text(json.dumps(review))
    p.show_joint_boundary_table(data)
    assert p.sim_table.item(0,3).text()=='Chưa audit'
    p.close();app.processEvents()


def test_joint_reliability_has_gated_stages_and_no_automatic_job(tmp_path):
    from nino_pi.research_jobs import ResearchRunner
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_joint_reliability_v1')
    assert p.sim_version.currentIndex()==13
    assert p.active_sim_actions()==('sim-joint-reliability-fixture','sim-joint-reliability-gazebo')
    assert p.sim_buttons['sim-joint-reliability-fixture'].isEnabled() and not p.sim_buttons['sim-joint-reliability-gazebo'].isEnabled()
    p.root.mkdir();(p.root/'state.json').write_text('{"runs":[{"action":"sim-joint-reliability-fixture","status":"failed"}],"latest":{}}')
    p.reload();assert not p.sim_buttons['sim-joint-reliability-fixture'].isEnabled()
    assert not p.sim_buttons['sim-joint-reliability-gazebo'].isEnabled() and not p.busy
    with pytest.raises(ValueError,match='đã tiêu thụ'):ResearchRunner(p.root).start('sim-joint-reliability-fixture')
    p.close();app.processEvents()


def test_joint_reliability_no_go_stays_locked_even_with_verified_fixture_state(tmp_path,monkeypatch):
    import nino_pi.research_panel as panel
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_joint_reliability_v1');p.root.mkdir()
    artifact=p.root/'fixture';artifact.mkdir();(artifact/'fixture_result.json').write_text('{"candidate_compatible":false,"readers":{}}')
    p.states['sim-joint-reliability-fixture']=dict(state='verified',path=str(artifact),label='no-go')
    monkeypatch.setattr(panel,'joint_reliability_fixture_ready',lambda root:False)
    p.refresh();p.show_joint_reliability_table()
    assert not p.sim_buttons['sim-joint-reliability-gazebo'].isEnabled() and 'no-go/unknown' in p.sim_next.text()
    assert not p.busy;p.close();app.processEvents()


def test_reliable_qualification_payload_review_requires_matching_manifest(tmp_path):
    import hashlib
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_joint_reliability_v1');p.root.mkdir()
    artifact=p.root/'qual';artifact.mkdir();(artifact/'manifest.json').write_text('{}')
    result=dict(qualification_pass=True,runs=[dict(source_stop_s=6.,complete_steps=140,replay_rows_checked=140,
        all_joint_paths_supported=True,maximum_primary_joint_age_ms=1.,maximum_independent_joint_age_ms=1.,
        nominal_velocity_rmse_m_s=.005,cross_track_rmse_m=.0001,task_success=True,stop_completed=True,qualification_pass=True,error=None)])
    (artifact/'qualification_result.json').write_text(json.dumps(result))
    p.states['sim-joint-reliability-gazebo']=dict(state='verified',path=str(artifact),label='fixture')
    review=dict(artifacts={'sim-joint-reliability-gazebo':dict(path=str(artifact),manifest_sha256=hashlib.sha256((artifact/'manifest.json').read_bytes()).hexdigest())},
        qualification_quality=[dict(source_stop_s=6.,payload_mismatches=0)])
    (p.root/'review.json').write_text(json.dumps(review));p.show_joint_reliability_table()
    assert p.sim_table.columnCount()==10 and p.sim_table.item(0,4).text()=='0'
    assert p.sim_table.item(0,6).text()=='0.0050000'
    review['artifacts']['sim-joint-reliability-gazebo']['manifest_sha256']='bad';(p.root/'review.json').write_text(json.dumps(review))
    p.show_joint_reliability_table();assert p.sim_table.item(0,4).text()=='Chưa audit'
    p.close();app.processEvents()
