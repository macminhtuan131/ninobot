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
        assert set(p.sim_buttons)=={'sim-baselines','sim-train','sim-evaluate','sim-v2-baselines','sim-v2-train','sim-v2-evaluate','sim-bias-clear','sim-guidance-contract','sim-v3-baselines'}
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
