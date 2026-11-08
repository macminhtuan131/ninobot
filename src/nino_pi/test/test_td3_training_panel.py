"""Operator settings, job errors and interlocks; no physics or SSH."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import time
from PyQt5 import QtWidgets as Q,QtTest
from nino_pi.td3_training_panel import TD3TrainingPanel,TrainingRunner

def app():return Q.QApplication.instance() or Q.QApplication([])

def test_smoke_and_train_have_explicit_distinct_budgets(tmp_path):
    q=app();p=TD3TrainingPanel(root=tmp_path)
    p.engine.setCurrentIndex(p.engine.findData('legacy100_v1'))
    p.timesteps.setValue(12345);p.interval.setValue(50)
    assert p.request('train')['timesteps']==12345
    smoke=p.request('smoke');assert smoke['timesteps']==64 and smoke['resume'] is None
    assert smoke['profile']=='nino_td3_smoke_h5_v1' and p.auto_evaluate.isChecked()
    assert not p.busy and p.tb is None;p.close();q.processEvents()

def test_other_work_blocks_training_but_does_not_start_anything(tmp_path):
    q=app();p=TD3TrainingPanel(root=tmp_path,blocked=lambda:True)
    assert not p.train.isEnabled() and not p.smoke.isEnabled()
    p.start('train');assert not p.runner.busy
    assert not list(tmp_path.glob('requests/*'));p.close();q.processEvents()


def test_scientific_recommendation_does_not_launch_or_globally_ban_training(tmp_path):
    q=app();p=TD3TrainingPanel(root=tmp_path,observe_external=False)
    assert '30,000' in p.assessment_note.text() and 'CLASSICAL' in p.assessment_note.text()
    assert not p.busy and p.current_directory is None and p.last_result is None
    assert p.train.isEnabled() and not list(tmp_path.iterdir())
    p.close();q.processEvents()

def test_finished_error_is_visible_and_partial_result_not_called_success(tmp_path):
    q=app();p=TD3TrainingPanel(root=tmp_path)
    d=tmp_path/'bad';d.mkdir();(d/'error.txt').write_text('specific fixture traceback')
    p.handle(dict(directory=str(d),closed=True,returncode=1,error='specific error'))
    assert 'exit 1' in p.status.text() and 'specific fixture traceback' in p.log.toPlainText()
    assert p.last_result is None and not p.busy;p.close();q.processEvents()

def test_training_panel_interlocks_existing_research_jobs(tmp_path):
    from nino_pi.research_panel import ResearchPanel
    q=app();p=ResearchPanel(root=tmp_path)
    assert 'TRAIN TD3' in p.sections.tabText(4) and not p.busy
    p.trainer.runner.process=object();p.refresh()
    assert p.busy and not any(b.isEnabled() for b in p.buttons.values())
    p.trainer.runner.process=None;p.close();q.processEvents()

def test_actual_qprocess_log_exit_and_qobject_event_dispatch(tmp_path,monkeypatch):
    from nino_pi import td3_training_panel as module
    from nino_rl.td3_studio_contract import SMOKE_PROFILE
    scripts=tmp_path/'src/nino_rl/scripts';scripts.mkdir(parents=True)
    (scripts/'common_training_studio.sh').write_text('#!/bin/bash\nprintf \'fixture stdout\\n\'\nexit 3\n')
    monkeypatch.setattr(module,'repository',lambda:tmp_path)
    q=app();runner=TrainingRunner();events=[];runner.update.connect(events.append)
    r=dict(schema_version=1,mode='smoke',scenario='clear_box',profile=SMOKE_PROFILE,timesteps=64,seed=7,checkpoint_every=0,wall_minutes=1,evaluate=False,resume=None)
    assert runner.start(tmp_path/'jobs',r)
    until=time.monotonic()+10
    while runner.busy and time.monotonic()<until:q.processEvents();QtTest.QTest.qWait(10)
    assert not runner.busy
    assert any(e.get('message')=='fixture stdout' for e in events)
    assert events[-1]['closed'] and events[-1]['returncode']==3
    assert callable(runner.event)  # QObject virtual, never shadowed by a signal
