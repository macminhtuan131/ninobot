"""Zero-only readiness profile is separate from all consumed TD3 budgets."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5 import QtWidgets as Q
from nino_pi.research_panel import ResearchPanel
from nino_pi.research_jobs import guided_td3_consumed


def test_new_profile_is_zero_only_and_selection_never_launches(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=ResearchPanel(root=tmp_path/'sim_drive_readiness_v1')
    assert panel.sim_version.currentIndex()==18
    assert panel.active_sim_actions()==('sim-drive-readiness',)
    assert not panel.sim_buttons['sim-drive-readiness'].isEnabled()
    assert not panel.runner.busy and panel.sim_table.rowCount()==0
    assert 'không actor' in panel.sim_buttons['sim-drive-readiness'].text()
    panel.close();app.processEvents()


def test_any_existing_qualification_ledger_closes_budget_even_if_corrupt(tmp_path):
    assert not guided_td3_consumed(tmp_path,'sim-drive-readiness')
    (tmp_path/'state.json').write_text('broken')
    assert guided_td3_consumed(tmp_path,'sim-drive-readiness')
