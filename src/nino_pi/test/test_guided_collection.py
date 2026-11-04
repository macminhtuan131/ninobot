"""Fixed button flow, process cancellation and real local gateway fixtures. No SSH/ROS."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from PyQt5 import QtCore as C, QtWidgets as Q, QtTest
from nino_pi.collection_runner import CollectionRunner, job_command, validated_metadata
from nino_pi.guided_collection import GuidedCollection

RUNTIME=Path(__file__).parents[1]/'runtime'


class GuidedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=Q.QApplication.instance() or Q.QApplication([])
    def setUp(self):
        self.qt_errors=[];self.hook=sys.excepthook
        sys.excepthook=lambda *args:self.qt_errors.append(args)
        self.w=GuidedCollection(lambda:dict(host='d@192.168.0.109',key='/tmp/key'),demo=True)
    def tearDown(self):
        self.w.cancel();self.app.processEvents();self.w.runner.dispose();self.w.deleteLater()
        self.app.processEvents();sys.excepthook=self.hook
        self.assertEqual(self.qt_errors,[],'Qt slots/virtuals must not swallow errors')
    def wait(self,predicate,seconds=2):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            self.app.processEvents()
            if predicate():return
            QtTest.QTest.qWait(15)
        self.fail('GUI timed out: '+self.w.next.text())
    def test_fixed_noninteractive_argv_and_metadata_no_automatic_motion(self):
        r=self.w.runner
        self.assertEqual(r.active_jobs,{})
        # QObject.event must remain a callable virtual, not a pyqtSignal.
        self.assertTrue(callable(r.event));self.app.sendEvent(r,C.QEvent(C.QEvent.User))
        with self.assertRaises(ValueError):validated_metadata('run-trial',{})
        cmd=job_command('run-trial',dict(host='d@pi',key="/tmp/key with ' and $(literal)"),dict(confirm_motion=True,text='literal $(not_run)'))
        self.assertIn('-T',cmd);self.assertNotIn('-tt',cmd)
        payload=cmd[-1].split('--metadata-base64 ')[1]
        self.assertEqual(json.loads(base64.urlsafe_b64decode(payload))['text'],'literal $(not_run)')
    def test_separate_record_and_motion_click_and_demo_never_promotes(self):
        w=self.w
        for job in ('deploy','inventory'):
            w.buttons[job].click();self.wait(lambda j=job:w.done.get(j) and j not in w.runner.active_jobs)
        w.buttons['start-stack'].click();self.wait(lambda:w.done.get('start-stack'))
        w.pose.setText('same heading; caster unknown');w.floor.setText('same tile/load');w.video.setText('demo reference only')
        for box in w.checks.values():box.setChecked(True)
        self.assertTrue(w.buttons['record-diagnostic'].isEnabled())
        w.buttons['record-diagnostic'].click();self.wait(lambda:w.record_ready)
        self.assertNotIn('run-trial',w.runner.active_jobs)
        self.assertFalse(w.buttons['run-trial'].isEnabled())
        w.motion_confirm.setChecked(True)
        self.assertTrue(w.buttons['run-trial'].isEnabled())
        w.buttons['run-trial'].click();self.wait(lambda:'run-trial' not in w.runner.active_jobs)
        self.assertFalse(w.buttons['run-trial'].isEnabled())
        self.wait(lambda:w.record_closed,seconds=7)
        w.buttons['review'].click();self.wait(lambda:w.done.get('review'))
        self.assertIn('Q0',w.quality.toPlainText())
        w.observation.setText('DEMO only');w.buttons['observation'].click();self.wait(lambda:w.done.get('observation'))
        w.buttons['fetch'].click();self.wait(lambda:w.done.get('fetch'))
        self.assertIsNone(w.journal)
    def test_failed_capture_can_retain_closed_raw_for_qc_and_future_is_locked(self):
        self.w.handle(dict(job='record-diagnostic',kind='progress',state='FAILED',data=dict(recorder_closed=True)))
        self.assertFalse(self.w.record_closed)  # QProcess has not closed yet.
        self.w.handle(dict(job='record-diagnostic',kind='finished',state='FAILED',returncode=1,data=dict(recorder_closed=True)))
        self.assertTrue(self.w.buttons['review'].isEnabled());self.assertTrue(self.w.buttons['fetch'].isEnabled())
        self.w.mode.setCurrentIndex(self.w.mode.findData('future'))
        self.assertFalse(self.w.buttons['run-trial'].isEnabled())
        self.assertFalse(self.w.buttons['record-diagnostic'].isEnabled())

    def test_wizard_primary_action_full_flow_without_automatic_motion(self):
        w=self.w;wizard=w.wizard
        self.assertEqual(wizard.pages.currentIndex(),0)
        wizard.primary.click();self.assertEqual(wizard.pages.currentIndex(),1)
        for job in ('deploy','connect-sensors','inventory'):
            self.assertEqual(wizard.command,job);wizard.primary.click();self.wait(lambda j=job:w.done.get(j))
            self.wait(lambda j=job:j not in w.runner.active_jobs or j=='connect-sensors')
        self.assertEqual(wizard.pages.currentIndex(),2)
        self.assertFalse(wizard.primary.isEnabled());self.assertIn('Còn thiếu',wizard.conditions_hint.text())
        w.pose.setText('caster unknown');w.floor.setText('same floor/load');w.video.setText('demo only')
        for box in w.checks.values():box.setChecked(True)
        self.assertEqual(wizard.command,'start-stack');wizard.primary.click();self.wait(lambda:w.done.get('start-stack'))
        wizard.primary.click();self.assertEqual(wizard.pages.currentIndex(),3)
        self.assertEqual(wizard.command,'record-diagnostic');wizard.primary.click();self.wait(lambda:w.record_ready)
        self.assertFalse(wizard.primary.isEnabled());self.assertNotIn('run-trial',w.runner.active_jobs)
        self.assertFalse(w.mode.isEnabled());self.assertFalse(w.pose.isEnabled())
        # Looking back/forward must not trigger motion or change the frozen profile.
        wizard.navigation.setCurrentRow(0);w.select_recipe('stationary')
        self.assertEqual(w.mode.currentData(),'diagnostic')
        wizard.navigation.setCurrentRow(3);w.motion_confirm.setChecked(True)
        self.assertEqual(wizard.command,'run-trial');self.assertTrue(wizard.primary.isEnabled());wizard.primary.click()
        self.assertTrue(w.diagnostic_used);self.assertFalse(wizard.primary.isEnabled())
        self.wait(lambda:w.record_closed,seconds=7);self.assertEqual(wizard.pages.currentIndex(),4)
        wizard.primary.click();self.wait(lambda:w.done.get('review'))
        self.assertFalse(wizard.primary.isEnabled());w.observation.setText('DEMO; no robot')
        wizard.primary.click();self.wait(lambda:w.done.get('observation'))
        self.assertEqual(wizard.pages.currentIndex(),5);wizard.primary.click();self.wait(lambda:w.done.get('fetch'))
        self.assertFalse(w.local_directory.text());self.assertFalse(wizard.primary.isEnabled())
        self.assertIn('Q0',w.quality.toPlainText())

    def test_stationary_wizard_never_opens_motion_or_requires_rc(self):
        w=self.w;wizard=w.wizard;w.select_recipe('stationary');wizard.primary.click()
        for job in ('deploy','inventory'):
            w.buttons[job].click();self.wait(lambda j=job:w.done.get(j) and j not in w.runner.active_jobs)
        w.pose.setText('unknown');w.floor.setText('stationary')
        self.assertEqual(wizard.pages.currentIndex(),2);self.assertTrue(wizard.primary.isEnabled())
        wizard.primary.click();self.assertEqual(wizard.command,'record-diagnostic');wizard.primary.click()
        self.wait(lambda:w.record_ready);self.assertIn('stationary',w.runner.active_jobs)
        self.assertFalse(w.buttons['run-trial'].isEnabled());self.assertNotIn('start-stack',w.runner.active_jobs)
        self.assertFalse(w.diagnostic_used)
        w.cancel();self.wait(lambda:not w.runner.active_jobs)

    def test_stale_recorder_and_late_window_cannot_open_trial(self):
        w=self.w
        w.runner._jobs['record-diagnostic']=dict(state='RECORDING_READY',token=123)
        w.record_ready=True;w.remaining=59.;w.ready_received=time.monotonic()-3
        w.motion_confirm.setChecked(True);w.demo=False;w.refresh()
        self.assertFalse(w.buttons['run-trial'].isEnabled())
        w.ready_received=time.monotonic();w.remaining=32.;w.refresh()
        self.assertFalse(w.buttons['run-trial'].isEnabled())
        w.remaining=50.;w.refresh();self.assertTrue(w.buttons['run-trial'].isEnabled())
        w.runner._jobs.clear();w.demo=True

    def test_fetch_preserves_structured_local_directory_on_process_exit(self):
        runner=CollectionRunner(demo=False);events=[];runner.job_event.connect(events.append)
        script="print('@@NINO_EVENT@@'+"+repr(json.dumps(dict(job='fetch',kind='progress',state='FETCHED',data=dict(local_directory='/tmp/session_fixture'))))+",flush=True)"
        with patch('nino_pi.collection_runner.job_command',return_value=[sys.executable,'-u','-c',script]):
            self.assertTrue(runner.start('fetch',{}));self.wait(lambda:not runner.active_jobs)
        event=next(e for e in events if e['kind']=='finished')
        self.assertEqual(event['data']['local_directory'],'/tmp/session_fixture')
        runner.dispose()

    def test_sensor_button_reuses_reviewed_path_and_cancel_closes_owned_jobs(self):
        w=self.w
        w.buttons['deploy'].click();self.wait(lambda:w.done.get('deploy'))
        w.buttons['connect-sensors'].click();self.wait(lambda:w.done.get('connect-sensors'))
        self.assertTrue(w.buttons['inventory'].isEnabled())
        w.buttons['inventory'].click();self.wait(lambda:w.done.get('inventory'))
        w.cancel();self.wait(lambda:not w.runner.active_jobs)
        self.assertFalse(w.done.get('connect-sensors',False))

    def test_real_qprocess_parses_events_but_cannot_forge_process_closure(self):
        runner=CollectionRunner(demo=False);events=[];runner.job_event.connect(events.append)
        script='''import json,time
print('@@NINO_EVENT@@'+json.dumps(dict(job='inventory',kind='finished',state='FINISHED')),flush=True)
time.sleep(.1)
print('@@NINO_EVENT@@'+json.dumps(dict(job='inventory',kind='progress',state='INVENTORY_READY',data={'not_motion_readiness':True})),flush=True)
'''
        with patch('nino_pi.collection_runner.job_command',return_value=[sys.executable,'-u','-c',script]):
            self.assertTrue(runner.start('inventory',{}))
            self.assertIn('inventory',runner.active_jobs)
            self.wait(lambda:not runner.active_jobs)
        closed=[e for e in events if e['kind']=='finished']
        self.assertEqual(len(closed),1)
        self.assertEqual(closed[0]['returncode'],0)
        self.assertTrue(closed[0]['data']['not_motion_readiness'])
        runner.dispose()

    def test_demo_record_final_state_precedes_closure_even_with_late_timers(self):
        runner=CollectionRunner(demo=True);events=[];runner.job_event.connect(events.append)
        pending=[]
        with patch('nino_pi.collection_runner.C.QTimer.singleShot',side_effect=lambda ms,callback:pending.append((ms,callback))):
            self.assertTrue(runner.start('stationary',dict(host='d@pi',key='/tmp/key'),
                dict(pose_caster_note='unknown',floor_load_note='demo')))
        # Simulate delayed/coalesced delivery: final deadline fires first.
        pending[-1][1]();pending[0][1]()
        final=[row for row in events if row['kind']=='finished']
        self.assertEqual(len(final),1)
        self.assertEqual(final[0]['state'],'FINISHED')
        self.assertTrue(final[0]['demo']);self.assertFalse(runner.active_jobs)
        runner.dispose()


class GatewayTests(unittest.TestCase):
    def test_closed_ssh_output_cannot_prevent_owned_child_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'job_gateway.py').write_bytes((RUNTIME/'job_gateway.py').read_bytes())
            (root/'session_cli.py').write_text('''from pathlib import Path
import time
root=Path(__file__).parent
try:
 (root/'started').touch()
 time.sleep(10)
except KeyboardInterrupt:
 (root/'stopped').touch()
''')
            arg=base64.urlsafe_b64encode(b'{}').decode()
            p=subprocess.Popen([sys.executable,'-u',str(root/'job_gateway.py'),'status','--gui','--metadata-base64',arg],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+2
                while not (root/'started').exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue((root/'started').exists())
                p.stdout.close();p.stdin.close();p.wait(timeout=5)
                self.assertTrue((root/'stopped').exists())
            finally:
                if p.poll() is None:p.kill();p.wait()

    def test_heartbeat_loss_closes_owned_child_without_retry(self):
        # Real subprocess: fixed gateway supervises a harmless local sleep fixture.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'job_gateway.py').write_bytes((RUNTIME/'job_gateway.py').read_bytes())
            (root/'session_cli.py').write_text('import time\nprint("fixture started",flush=True)\ntime.sleep(10)\n')
            arg=base64.urlsafe_b64encode(b'{}').decode()
            p=subprocess.Popen([sys.executable,'-u',str(root/'job_gateway.py'),'status','--gui','--metadata-base64',arg],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            try:
                time.sleep(1.8)
                output,_=p.communicate(timeout=5)
                self.assertNotEqual(p.returncode,0)
                self.assertIn(b'heartbeat stale',output)
                self.assertEqual(len(list((root/'gui_jobs').glob('*.jsonl'))),1)
            finally:
                if p.poll() is None:p.kill();p.wait()
    def test_heartbeat_pulses_allow_completion_and_unknown_has_no_fake_readiness(self):
        spec=importlib.util.spec_from_file_location('gateway_test',RUNTIME/'job_gateway.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            mod.ROOT=Path(d)
            self.assertIsNone(mod.recorder_snapshot('record-diagnostic'))
            with self.assertRaises((OSError,RuntimeError)):mod.result_data('record-diagnostic',time.time())
            (mod.ROOT/'job_gateway.py').write_bytes((RUNTIME/'job_gateway.py').read_bytes())
            (mod.ROOT/'session_cli.py').write_text('import time\ntime.sleep(.4)\nprint("fixture complete",flush=True)\n')
            arg=base64.urlsafe_b64encode(b'{}').decode()
            p=subprocess.Popen([sys.executable,'-u',str(mod.ROOT/'job_gateway.py'),'status','--gui','--metadata-base64',arg],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            p.stdin.write(b'{"command":"pulse"}\n');p.stdin.flush()
            time.sleep(.5)
            output,_=p.communicate(timeout=5)
            self.assertEqual(p.returncode,0,output.decode());self.assertIn(b'STATUS_READY',output)
