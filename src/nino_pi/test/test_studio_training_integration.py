"""One Studio window/runner, cross-page interlocks and training-budget feedback.

Historical benchmark scans are mocked: these tests exercise GUI ownership and
process lifecycle, not artifact qualification, ROS, Gazebo or training quality.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PyQt5 import QtWidgets as Q,QtTest
from nino_pi.mode_gui import ModeWindow
from nino_pi.td3_training_panel import TD3TrainingPanel


@pytest.fixture
def window(tmp_path,monkeypatch):
    from nino_pi import research_panel
    from nino_pi.sim_benchmark_panel import SimBenchmarkPanel
    monkeypatch.setattr(SimBenchmarkPanel,'reload',lambda self:None)
    monkeypatch.setattr(research_panel,'workflow_state',lambda root:{
        action:dict(state='missing',label='fixture: no historical scan') for action in research_panel.JOBS})
    app=Q.QApplication.instance() or Q.QApplication([])
    w=ModeWindow(demo=True,training_root=tmp_path/'training');w.timer.stop()
    w.studio.runner.timer.stop();w.show();app.processEvents()
    yield w
    w.demo=True;w.close();app.processEvents()


def test_training_is_one_top_level_Studio_tab_without_duplicate(window):
    w=window
    assert w.tabs.count()==5 and w.tabs.tabText(w.training_tab)=='Train TD3 · Sim'
    assert w.training is w.research.trainer
    assert w.training_scroll.widget() is w.training
    assert len(w.findChildren(TD3TrainingPanel))==1
    assert not any('TRAIN TD3' in w.research.sections.tabText(i) for i in range(w.research.sections.count()))
    assert '100D/2D' in w.training.contract_note.text() and '103D/1D' in w.training.contract_note.text()
    assert w.process is None and not w.research.busy and not w.studio.runner.busy


def test_demo_does_not_launch_training_and_local_training_needs_no_Pi(window):
    w=window
    assert not w.training.train.isEnabled() and not w.training.smoke.isEnabled()
    w.training.start('smoke');assert not w.training.runner.busy
    w.demo=False;w.refresh()
    assert w.process is None and w.training.train.isEnabled() and w.training.smoke.isEnabled()


def test_training_and_real_recording_share_busy_interlock(window):
    w=window;w.demo=False;w.refresh()
    w.studio.runner.process=object()
    try:
        w.refresh();assert not w.training.train.isEnabled()
        w.training.start('smoke');assert not w.training.runner.busy
    finally:w.studio.runner.process=None
    w.training.runner.process=object()
    try:
        w.refresh()
        assert w.research.busy and w.studio.external_busy()
        assert not w.studio.primary.isEnabled()
    finally:w.training.runner.process=None


def test_parameter_button_navigates_inside_same_window(window):
    w=window
    w.training.engine.setCurrentIndex(w.training.engine.findData('legacy100_v1'))
    w.training.profile.setCurrentIndex(w.training.profile.findData('nino_td3_research_h5_v1'))
    w.training.parameters_button.click()
    assert w.tabs.currentWidget() is w.research_scroll
    assert w.research.sections.currentWidget() is w.research.parameter_tab
    assert w.research.parameters.choose.currentText()=='nino_td3_research_h5_v1'
    assert w.process is None and not w.research.busy


def test_training_startup_defers_historical_benchmark_scan(window,monkeypatch):
    w=window;calls=[]
    assert not w.research.benchmark_load_started and not w.research.benchmark.verified
    monkeypatch.setattr(w.research.benchmark,'reload',lambda:calls.append('read-only scan'))
    w.research.sections.setCurrentWidget(w.research.benchmark_tab)
    QtTest.QTest.qWait(5)
    assert calls==['read-only scan']
    w.research.sections.setCurrentWidget(w.research.parameter_tab)
    w.research.sections.setCurrentWidget(w.research.benchmark_tab)
    QtTest.QTest.qWait(5)
    assert calls==['read-only scan']


def test_Studio_close_waits_for_embedded_training_cleanup(window):
    from types import SimpleNamespace
    w=window
    w.training.runner.process=SimpleNamespace(processId=lambda:0)
    w.close()
    assert w.isVisible() and w.research.closing and w.training.closing
    w.training.runner.process=None;w.training.runner.closed.emit()
    QtTest.QTest.qWait(20)
    assert not w.isVisible()
    assert not w.timer.isActive() and not w.studio.runner.timer.isActive()


def test_old_training_shortcut_opens_Studio(monkeypatch,tmp_path):
    from nino_pi import mode_gui,td3_training_panel
    forwarded=[]
    monkeypatch.setattr(mode_gui,'main',lambda argv:forwarded.append(argv) or 17)
    assert td3_training_panel.main(['--output',str(tmp_path),'--demo'])==17
    assert forwarded==[['--train','--training-output',str(tmp_path),'--demo']]


def test_research_warmup_only_request_cannot_masquerade_as_learning(tmp_path,monkeypatch):
    from nino_rl import common_studio_contract
    monkeypatch.setattr(common_studio_contract,'require_disk',lambda *args:{})
    app=Q.QApplication.instance() or Q.QApplication([]);panel=TD3TrainingPanel(root=tmp_path)
    try:
        panel.profile.setCurrentIndex(panel.profile.findData('nino_td3_research_h5_v1'))
        panel.timesteps.setValue(10000)
        assert 'CHƯA CÓ BƯỚC HỌC' in panel.budget_note.text()
        assert not panel.train.isEnabled() and panel.smoke.isEnabled()
        with pytest.raises(ValueError,match='CHƯA CÓ BƯỚC HỌC'):panel.request('train')
        panel.timesteps.setValue(20000)
        assert panel.train.isEnabled() and panel.request('train')['timesteps']==20000
        assert '10,000 bước thêm' in panel.budget_note.text()
        assert not panel.runner.busy
    finally:panel.close();app.processEvents()


def test_resume_counts_previous_global_steps_toward_warmup(tmp_path):
    app=Q.QApplication.instance() or Q.QApplication([]);panel=TD3TrainingPanel(root=tmp_path)
    try:
        panel.profile.setCurrentIndex(panel.profile.findData('nino_td3_research_h5_v1'))
        panel.timesteps.setValue(100)
        panel.resume_info=dict(path=str(tmp_path/'checkpoint'),global_steps=10000)
        panel.checkpoint_path.setText(panel.resume_info['path']);panel.resume.setChecked(True)
        assert panel.training_budget()[0] is True and '100 bước thêm' in panel.budget_note.text()
        panel.checkpoint_path.setText(str(tmp_path/'other'))
        assert panel.training_budget()[0] is None  # must inspect the newly chosen checkpoint
    finally:panel.close();app.processEvents()


def test_refresh_does_not_reparse_profiles_and_start_detects_changed_catalog(tmp_path,monkeypatch):
    from copy import deepcopy
    from nino_rl import common_studio_contract as td3_studio_contract
    app=Q.QApplication.instance() or Q.QApplication([]);panel=TD3TrainingPanel(root=tmp_path)
    try:
        def no_io():pytest.fail('Periodic UI refresh must not read the YAML catalog')
        monkeypatch.setattr(td3_studio_contract,'profiles',no_io)
        panel.refresh();panel.show_parameters();panel.refresh()
        changed=deepcopy(panel.parameter_profiles)
        changed[panel.profile.currentData()]['algorithm']['exploration_noise']=.12
        monkeypatch.setattr(td3_studio_contract,'profiles',lambda:changed)
        with pytest.raises(ValueError,match='Catalog tham số đã thay đổi'):panel.request('train')
        assert not panel.runner.busy
    finally:panel.close();app.processEvents()
