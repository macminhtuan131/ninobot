from PyQt5 import QtWidgets as Q

from nino_rl import goal_studio_contract as goal
from nino_pi.td3_training_panel import TD3TrainingPanel


def test_goal_task_selected_in_studio_has_384_smoke_and_research_budget_without_starting(tmp_path,monkeypatch):
    monkeypatch.setattr(goal,'require_qualification',lambda:tmp_path)
    monkeypatch.setattr(goal,'require_disk',lambda *args:{})
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=TD3TrainingPanel(root=tmp_path,observe_external=False)
    try:
        panel.engine.setCurrentIndex(panel.engine.findData(goal.ENGINE))
        assert '100D' in panel.contract_note.text() and 'stop6/8' in panel.contract_note.text()
        smoke=panel.request('smoke')
        assert smoke['engine']==goal.ENGINE and smoke['timesteps']==384
        assert smoke['profile']==goal.SMOKE_PROFILE
        panel.timesteps.setValue(20000);panel.profile.setCurrentIndex(panel.profile.findData('nino_td3_research_h5_v1'))
        request=panel.request('train')
        assert request['timesteps']==20000 and request['resume'] is None
        assert not panel.runner.busy
        panel.prepare_goal_research()
        assert panel.timesteps.value()==20000 and panel.seed.value()==11 and not panel.runner.busy
    finally:
        panel.close();app.processEvents()
