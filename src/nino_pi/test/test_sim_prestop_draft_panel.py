"""Selecting the Sim planning branch never allocates or launches a run."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PyQt5 import QtWidgets as Q,QtGui as G
from nino_pi.next_steps_panel import NextStepsPanel


def test_default_sim_outline_and_branch_switch_preserve_hardware_and_authority():
    app=Q.QApplication.instance() or Q.QApplication([]);p=NextStepsPanel();events=[]
    p.collectionRequested.connect(events.append)
    assert p.branch.currentData()=='sim_offline_preparation' and len(p.steps)==4
    assert p.draft['release']['allocated_attempts']==0 and not p.draft['release']['physics_allowed']
    p.list.setCurrentRow(1)
    assert '280' in p.detail.toPlainText() and 'INTEGRATION ĐẠT' in p.detail.toPlainText()
    assert 'prestop vẫn unknown' in p.current.text()
    p.branch.setCurrentIndex(p.branch.findData('hardware'));app.processEvents()
    p.list.setCurrentRow(1)
    assert 'OFFLINE ĐÃ XONG' in p.detail.toPlainText() and p.draft is None
    p.branch.setCurrentIndex(p.branch.findData('sim_offline_preparation'));app.processEvents()
    assert p.draft and events==[] and p.open_collection.isEnabled()  # Navigation only.
    p.close();app.processEvents()


def test_draft_document_opens_without_starting_any_job(tmp_path,monkeypatch):
    from nino_pi import research_jobs
    from nino_pi.sim_review import load
    doc=tmp_path/load()['document']
    doc.parent.mkdir();doc.write_text('draft only')
    monkeypatch.setattr(research_jobs,'repository',lambda:tmp_path)
    opened=[];monkeypatch.setattr(G.QDesktopServices,'openUrl',lambda u:opened.append(u.toLocalFile()))
    app=Q.QApplication.instance() or Q.QApplication([]);p=NextStepsPanel()
    p.open_protocol.click();app.processEvents()
    assert opened==[str(doc)] and p.draft['release']['training_transitions']==0
    p.close();app.processEvents()


def test_changed_draft_does_not_leave_old_verified_outline(monkeypatch):
    from nino_rl import prestop_authority_draft
    app=Q.QApplication.instance() or Q.QApplication([]);p=NextStepsPanel();assert p.draft
    def fail(*a):raise ValueError('draft source changed')
    monkeypatch.setattr(prestop_authority_draft,'load',fail);p.reload()
    assert p.draft is None and p.steps==[] and p.list.count()==0 and 'CHƯA XÁC MINH' in p.current.text()
    assert not p.open_collection.isEnabled()
    p.close();app.processEvents()


def test_project_direction_uses_sim_stages_without_claiming_hardware_evidence():
    from nino_pi.project_panel import ProjectPanel
    app=Q.QApplication.instance() or Q.QApplication([]);p=ProjectPanel()
    assert p.stage_table.item(0,0).text()=='SIM-R1'
    assert 'REVIEW SIM' in p.banner.text()
    assert '2 episode train hoàn chỉnh' in p.direction_text.text()
    rows={r['id']:r for r in p.catalog['data']}
    assert 'Chưa đủ' in rows['D14']['status'] and 'Chưa đủ' in rows['D18']['status']
    p.close();app.processEvents()
