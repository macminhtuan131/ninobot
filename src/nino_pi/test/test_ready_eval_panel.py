"""Eval-only GUI is a distinct bounded stage; selecting it cannot train."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PyQt5 import QtWidgets as Q
from nino_pi.research_panel import ResearchPanel
from nino_pi.research_jobs import guided_td3_consumed


def test_profile_has_only_eval_action_and_no_automatic_execution(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=ResearchPanel(root=tmp_path/'sim_ready_eval_only_v1')
    assert panel.sim_version.currentIndex()==19
    assert panel.active_sim_actions()==('sim-ready-eval-only',)
    assert not panel.sim_buttons['sim-ready-eval-only'].isEnabled()
    assert not panel.runner.busy and panel.sim_table.rowCount()==0
    assert 'không train' in panel.sim_buttons['sim-ready-eval-only'].text()
    panel.sim_benchmark_link.click();app.processEvents()
    assert panel.sections.currentWidget() is panel.benchmark_tab
    assert not panel.runner.busy
    panel.close();app.processEvents()


def test_existing_ledger_always_closes_eval_budget(tmp_path):
    assert not guided_td3_consumed(tmp_path,'sim-ready-eval-only')
    (tmp_path/'state.json').write_text('broken')
    assert guided_td3_consumed(tmp_path,'sim-ready-eval-only')


def test_hardware_busy_blocks_eval_without_hashing_release(tmp_path,monkeypatch):
    from nino_pi import research_panel
    app=Q.QApplication.instance() or Q.QApplication([])
    monkeypatch.setattr(research_panel,'ready_eval_release_ready',lambda *a:pytest.fail('No release IO while locked'))
    panel=ResearchPanel(root=tmp_path/'sim_ready_eval_only_v1',hardware_busy=lambda:True)
    assert not panel.sim_buttons['sim-ready-eval-only'].isEnabled()
    assert not panel.runner.busy
    panel.close();app.processEvents()
