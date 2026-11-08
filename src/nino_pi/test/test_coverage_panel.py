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
    p=ResearchPanel(root=tmp_path/'sim_coverage_study_v1')
    assert p.sim_version.currentIndex()==16
    assert p.active_sim_actions()==('sim-coverage-preflight','sim-coverage-study')
    assert p.sim_buttons['sim-coverage-preflight'].isEnabled()
    assert not p.sim_buttons['sim-coverage-study'].isEnabled()
    assert p.sim_table.rowCount()==6 and p.sim_progress.value()==0
    assert '0/1024'==p.sim_table.item(0,2).text()
    assert 'Bước1' in p.sim_next.text() and not p.runner.busy
    with pytest.raises(ValueError,match='chưa release'):p.runner.start('sim-coverage-study')
    assert not p.runner.busy and not (p.root/'state.json').exists()
    p.close();app.processEvents()


def test_preflight_does_not_consume_scientific_slot_but_run_and_corrupt_ledger_do(tmp_path):
    state=tmp_path/'state.json'
    state.write_text(json.dumps(dict(runs=[dict(action='sim-coverage-preflight',status='completed')])))
    assert not guided_td3_consumed(tmp_path,'sim-coverage-study')
    state.write_text(json.dumps(dict(runs=[dict(action='sim-coverage-study',status='failed')])))
    assert guided_td3_consumed(tmp_path,'sim-coverage-study')
    state.write_text('broken')
    assert guided_td3_consumed(tmp_path,'sim-coverage-study')


def test_hardware_busy_blocks_offline_button_too(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_coverage_study_v1',hardware_busy=lambda:True)
    assert not p.sim_buttons['sim-coverage-preflight'].isEnabled()
    p.run('sim-coverage-preflight');assert not p.runner.busy
    p.close();app.processEvents()


def test_unverified_closed_artifact_cannot_display_pass_or_metrics(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    root=tmp_path/'sim_coverage_study_v1';target=root/'unverified'/'A_gaussian_seed_11'
    target.mkdir(parents=True);(target/'training_result.json').write_text('tampered')
    (root/'state.json').write_text(json.dumps(dict(latest={},runs=[
        dict(action='sim-coverage-study',status='completed',path='unverified',error=None)])))
    p=ResearchPanel(root=root)
    assert 'CHƯA XÁC MINH ARTIFACT' in p.sim_next.text()
    assert p.sim_table.rowCount()==0 and not p.sim_buttons['sim-coverage-study'].isEnabled()
    p.close();app.processEvents()


def test_locked_refresh_does_not_hash_dependencies_during_collection(tmp_path,monkeypatch):
    from nino_pi import research_panel
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_coverage_study_v1',hardware_busy=lambda:True)
    p.states['sim-coverage-preflight']=dict(state='verified')
    monkeypatch.setattr(research_panel,'coverage_release_ready',lambda *a:pytest.fail('No dependency hash while locked'))
    p.refresh()
    assert not p.sim_buttons['sim-coverage-study'].isEnabled()
    p.close();app.processEvents()


def test_closed_root_is_not_labeled_unconsumed_budget(tmp_path,monkeypatch):
    from nino_pi import research_panel
    app=Q.QApplication.instance() or Q.QApplication([])
    p=ResearchPanel(root=tmp_path/'sim_coverage_study_v1')
    p.states['sim-coverage-preflight']=dict(state='verified',label='PREFLIGHT ĐẠT')
    p.states['sim-coverage-study']=dict(state='retained_failure',label='ĐÃ ĐÓNG DO LỖI')
    monkeypatch.setattr(research_panel,'guided_td3_consumed',lambda root,action:action=='sim-coverage-study')
    p.refresh()
    assert 'ĐÃ ĐÓNG DO LỖI' in p.sim_status['sim-coverage-study'].text()
    assert 'chưa tiêu thụ' not in p.sim_status['sim-coverage-study'].text()
    assert not p.sim_buttons['sim-coverage-study'].isEnabled()
    p.close();app.processEvents()
