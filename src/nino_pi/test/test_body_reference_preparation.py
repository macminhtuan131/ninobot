"""A prepared reference protocol must not become motion evidence or authority."""
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5 import QtWidgets as Q
from nino_pi.next_steps_panel import NextStepsPanel
from nino_pi.project_panel import ProjectPanel


def test_reviewed_gap_and_draft_are_visible_without_promoting_body_claims():
    app=Q.QApplication.instance() or Q.QApplication([])
    panel=ProjectPanel();events=[];panel.collectionRequested.connect(events.append)
    assert '30,000' in panel.direction_text.text()
    assert '95.459' in panel.banner.text() and '0 slot' in panel.banner.text()
    rows={r['id']:r for r in panel.catalog['data']}
    assert 'Chưa đủ' in rows['D14']['status'] and 'Chưa đủ' in rows['D18']['status']
    assert 'chưa thu' in rows['D14']['result'].lower()
    tasks={r['id']:r for r in panel.catalog['tasks']}
    assert 'chưa release' in tasks['T05']['status']
    for key in ('wheel_body_gap','body_reference_draft'):
        source=panel.catalog['sources'][key]
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()==source['sha256']
    table=panel.tables[3][2]
    table.selectRow(next(i for i,r in enumerate(panel.catalog['tasks']) if r['id']=='T05'))
    app.processEvents()
    assert panel.open_source.isEnabled() and events==[]
    panel.close();app.processEvents()


def test_roadmap_review_done_leads_to_unreleased_single_diagnostic():
    app=Q.QApplication.instance() or Q.QApplication([]);panel=NextStepsPanel(workstream='hardware');events=[]
    panel.collectionRequested.connect(events.append)
    panel.list.setCurrentRow(1)
    assert 'OFFLINE ĐÃ XONG' in panel.detail.toPlainText()
    panel.list.setCurrentRow(2);app.processEvents()
    text=panel.detail.toPlainText()
    assert '0 SLOT' in text and 'chưa mở ba repeats' in text
    assert not panel.open_collection.isEnabled() and events==[]
    panel.close();app.processEvents()


def test_reference_form_leaves_unmeasured_quantities_unknown():
    root=Path(__file__).resolve().parents[1]
    form=json.loads((root/'config/body_reference_observation.template.json').read_text())
    assert form['motion_released'] is False
    assert all(form['reference'][k] is None for k in
        ('body_displacement_m','body_speed_m_s','ros_to_body_latency_s','slip','sync_uncertainty_s'))
    assert form['qc']['physical_motion_verdict']=='unknown'
    assert form['qc']['eligible_for_slip'] is False and form['qc']['eligible_for_td3_replay'] is False
