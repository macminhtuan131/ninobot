import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import time
from PyQt5 import QtCore as C,QtTest,QtWidgets as Q
from nino_pi import body_reference as b
from nino_pi.body_reference_panel import BodyReferenceDialog


def prepare_dialog(tmp_path,monkeypatch):
    app=Q.QApplication.instance() or Q.QApplication([])
    session=tmp_path/'session';(session/'bag').mkdir(parents=True)
    (session/'manifest.json').write_text('{}')
    video=tmp_path/'video.mp4';video.write_bytes(b'not validated media')
    monkeypatch.setattr(b.shutil,'which',lambda *a:None)
    dialog=BodyReferenceDialog(session=session)
    dialog.destination.setText(str(tmp_path/'derived'))
    return app,dialog,video


def wait(app,predicate):
    until=time.monotonic()+5
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        QtTest.QTest.qWait(10)
    raise AssertionError('Worker did not finish')


def test_registered_video_stays_candidate_and_does_not_run_acquisition(tmp_path,monkeypatch):
    app,d,video=prepare_dialog(tmp_path,monkeypatch)
    assert not d.save.isEnabled() and d.last_saved is None
    d.videos.addItem(str(video));d.attest.setChecked(True)
    assert d.save.isEnabled()
    d.labels['body_translation'].setCurrentIndex(d.labels['body_translation'].findData('observed'))
    d.save.click();assert d.worker and not d.save.isEnabled()
    wait(app,lambda:d.worker is None)
    value=json.loads(open(d.last_saved).read())
    assert value['observations']['body_translation']=='observed'
    assert value['qc']['physical_motion_verdict']=='unknown' and value['motion_released'] is False
    assert 'chưa được dùng' in d.status.text()
    d.close();app.processEvents()


def test_close_cancels_reader_and_waits_before_destroying_thread(tmp_path,monkeypatch):
    from nino_pi import body_reference_panel as p
    app,d,video=prepare_dialog(tmp_path,monkeypatch)
    def slow(path,cancelled):
        for i in range(200):
            if cancelled():raise InterruptedError('cancelled')
            C.QThread.msleep(5)
        raise AssertionError('Expected cancellation')
    monkeypatch.setattr(p,'inspect_media',slow)
    d.videos.addItem(str(video));d.attest.setChecked(True);d.show();d.save.click()
    d.close();assert d.closing
    wait(app,lambda:d.worker is None)
    assert not d.isVisible() and d.last_saved is None and not (tmp_path/'derived').exists()


def test_studio_reference_button_opens_dialog_without_remote_action(tmp_path,monkeypatch):
    from nino_pi.studio_panel import StudioPanel
    from nino_pi import body_reference_panel as p
    app=Q.QApplication.instance() or Q.QApplication([]);calls=[]
    monkeypatch.setattr(p.BodyReferenceDialog,'exec_',lambda self:calls.append('local dialog'))
    studio=StudioPanel(lambda:dict(host='unused',key='unused',domain=0),demo=True)
    studio.reference_button.click();app.processEvents()
    assert calls==['local dialog'] and not studio.runner.busy
    assert not studio.ready and not studio.installed
    studio.close();app.processEvents()
