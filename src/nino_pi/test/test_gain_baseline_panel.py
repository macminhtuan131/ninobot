"""The gain baseline profile cannot launch training or reopen consumed slots."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5 import QtWidgets as Q
from nino_pi.research_panel import ResearchPanel
from nino_pi.research_jobs import guided_td3_consumed


def test_profile_is_separate_bounded_and_does_not_autostart(tmp_path):
    app = Q.QApplication.instance() or Q.QApplication([])
    panel = ResearchPanel(root=tmp_path/'sim_gain_baselines_v1')
    assert panel.sim_version.currentIndex() == 20
    assert panel.active_sim_actions() == ('sim-gain-baselines',)
    assert not panel.runner.busy and not panel.sim_buttons['sim-gain-baselines'].isEnabled()
    assert 'không actor/train' in panel.sim_buttons['sim-gain-baselines'].text()
    assert panel.sim_table.rowCount() == 0
    panel.close()
    app.processEvents()


def test_corrupt_ledger_cannot_reopen_gain_profile(tmp_path):
    assert not guided_td3_consumed(tmp_path, 'sim-gain-baselines')
    (tmp_path/'state.json').write_text('corrupt')
    assert guided_td3_consumed(tmp_path, 'sim-gain-baselines')


def test_hardware_busy_blocks_gain_job(tmp_path, monkeypatch):
    import pytest
    from nino_pi import research_panel
    app = Q.QApplication.instance() or Q.QApplication([])
    monkeypatch.setattr(research_panel, 'gain_baseline_release_ready', lambda *a: pytest.fail('Locked release IO'))
    panel = ResearchPanel(root=tmp_path/'sim_gain_baselines_v1', hardware_busy=lambda: True)
    assert not panel.runner.busy and not panel.sim_buttons['sim-gain-baselines'].isEnabled()
    panel.close()
    app.processEvents()
