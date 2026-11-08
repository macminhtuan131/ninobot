"""Coverage profile cannot acquire physics authority through GUI selection."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
import pytest
from PyQt5 import QtWidgets as Q
from nino_pi.research_panel import ResearchPanel
from nino_pi.research_jobs import ResearchRunner,guided_td3_consumed


def test_new_profile_shows_planned_learners_and_only_offline_button(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_coverage_study_v2')
    assert p.sim_version.currentIndex()==17
    assert p.active_sim_actions()==('sim-coverage-v2-preflight','sim-coverage-v2-study')
    assert p.sim_buttons['sim-coverage-v2-preflight'].isEnabled()
    assert not p.sim_buttons['sim-coverage-v2-study'].isEnabled()
    assert p.sim_table.rowCount()==6 and p.sim_progress.value()==0
    assert '0/1024'==p.sim_table.item(0,2).text()
    assert 'Bước1' in p.sim_next.text() and not p.runner.busy
    with pytest.raises(ValueError,match='chưa release'):p.runner.start('sim-coverage-v2-study')
    assert not p.runner.busy and not (p.root/'state.json').exists()
    p.close();app.processEvents()


def test_preflight_does_not_consume_scientific_slot_but_run_and_corrupt_ledger_do(tmp_path):
    state=tmp_path/'state.json'
    state.write_text(json.dumps(dict(runs=[dict(action='sim-coverage-v2-preflight',status='completed')])))
    assert not guided_td3_consumed(tmp_path,'sim-coverage-v2-study')
    state.write_text(json.dumps(dict(runs=[dict(action='sim-coverage-v2-study',status='failed')])))
    assert guided_td3_consumed(tmp_path,'sim-coverage-v2-study')
    state.write_text('broken')
    assert guided_td3_consumed(tmp_path,'sim-coverage-v2-study')


def test_hardware_busy_blocks_offline_button_too(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_coverage_study_v2',hardware_busy=lambda:True)
    assert not p.sim_buttons['sim-coverage-v2-preflight'].isEnabled()
    p.run('sim-coverage-v2-preflight');assert not p.runner.busy
    p.close();app.processEvents()


def test_unverified_closed_artifact_cannot_display_pass_or_metrics(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    root=tmp_path/'sim_coverage_study_v2';target=root/'unverified'/'A_gaussian_seed_11'
    target.mkdir(parents=True);(target/'training_result.json').write_text('tampered')
    (root/'state.json').write_text(json.dumps(dict(latest={},runs=[
        dict(action='sim-coverage-v2-study',status='completed',path='unverified',error=None)])))
    p=ResearchPanel(root=root)
    assert 'CHƯA XÁC MINH ARTIFACT' in p.sim_next.text()
    assert p.sim_table.rowCount()==0 and not p.sim_buttons['sim-coverage-v2-study'].isEnabled()
    p.close();app.processEvents()


def test_locked_refresh_does_not_hash_dependencies_during_collection(tmp_path,monkeypatch):
    from nino_pi import research_panel
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_coverage_study_v2',hardware_busy=lambda:True)
    p.states['sim-coverage-v2-preflight']=dict(state='verified')
    monkeypatch.setattr(research_panel,'coverage_release_ready',lambda *a:pytest.fail('No dependency hash while locked'))
    p.refresh()
    assert not p.sim_buttons['sim-coverage-v2-study'].isEnabled()
    p.close();app.processEvents()


def test_closed_root_is_not_labeled_unconsumed_budget(tmp_path,monkeypatch):
    from nino_pi import research_panel
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_coverage_study_v2')
    p.states['sim-coverage-v2-preflight']=dict(state='verified',label='PREFLIGHT ĐẠT')
    p.states['sim-coverage-v2-study']=dict(state='retained_failure',label='ĐÃ ĐÓNG DO LỖI')
    monkeypatch.setattr(research_panel,'guided_td3_consumed',lambda root,action:action=='sim-coverage-v2-study')
    p.refresh()
    assert 'ĐÃ ĐÓNG DO LỖI' in p.sim_status['sim-coverage-v2-study'].text()
    assert 'chưa tiêu thụ' not in p.sim_status['sim-coverage-v2-study'].text()
    assert not p.sim_buttons['sim-coverage-v2-study'].isEnabled()
    p.close();app.processEvents()


def test_partial_row_uses_own_counts_after_an_earlier_learner_completed(tmp_path,monkeypatch):
    """Rendering fixture; injected trust state is NOT artifact validation."""
    import hashlib
    from nino_pi import research_panel
    from nino_pi.research_jobs import JOBS
    app=Q.QApplication.instance() or Q.QApplication([])
    root=tmp_path/'sim_coverage_study_v2';out=root/'synthetic_failed'
    first=out/'A_gaussian_seed_11';first.mkdir(parents=True)
    second=out/'C_stratified_probes_seed_11';second.mkdir()
    (first/'training_result.json').write_text(json.dumps(dict(training_transitions=1024,
        critic_updates=960,actor_updates=480,coverage=dict(bin_counts=[1,2,3,4]))))
    (second/'learning_progress.jsonl').write_text(json.dumps(dict(transitions=128,critic_updates=63,actor_updates=31))+'\n')
    (root/'state.json').write_text(json.dumps(dict(latest={},runs=[dict(
        action='sim-coverage-v2-study',status='failed',path=out.name,error='synthetic failure')])) )
    manifest=out/'manifest.json';manifest.write_text('{}')
    (out/'job.json').write_text(json.dumps(dict(status='failed',error='synthetic failure')))
    (root/'review.json').write_text(json.dumps(dict(artifact=str(out),
        artifact_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        control_attempts=1153,replay_rows=1152,learners=[dict(arm='C_stratified_probes',seed=11,
            control_attempts=129,replay_rows=128,critic_updates=64,actor_updates=32)])))
    states={a:dict(state='pending',label='fixture',path=None) for a in JOBS}
    states['sim-coverage-v2-study']=dict(state='retained_failure',label='fixture failure',path=str(out))
    monkeypatch.setattr(research_panel,'workflow_state',lambda root:states)
    panel=ResearchPanel(root=root)
    assert panel.sim_table.item(0,2).text()=='1024/1024'
    assert panel.sim_table.item(1,2).text()=='129 raw / 128 replay'
    assert panel.sim_table.item(1,3).text()=='64'
    assert panel.sim_progress.value()==1153
    panel.show_sim_result('sim-coverage-v2-study')
    assert 'Derived audit bound to manifest' in panel.sim_log.toPlainText()
    assert '129' in panel.sim_log.toPlainText()
    panel.close();app.processEvents()
