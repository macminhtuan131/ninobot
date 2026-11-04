"""Operator-first real-data workflow; fixed buttons, explicit motion, visible closure."""
from datetime import datetime,timezone
import json
import time
from pathlib import Path
from PyQt5 import QtCore as C, QtWidgets as Q
from .collection_runner import CollectionRunner
from .data_quality import quality_text
from .collection_wizard import CollectionWizard

STEPS=(('deploy','1 · Chuẩn bị bộ thu trên Pi'),('connect-sensors','2a · Kết nối Agent / cảm biến'),('inventory','2b · Kiểm thiết bị / kết nối'),
       ('start-stack','3 · Chạy đường lệnh ZERO'),('record-diagnostic','4 · Bắt đầu thu 60 s'),
       ('run-trial','5 · Tiến 0,05 m/s trong 2 s'),('review','6 · Kiểm dữ liệu đã đóng'),
       ('observation','7 · Lưu quan sát người vận hành'),('fetch','8 · Tải dữ liệu về laptop'))
LABELS={'SENSORS_AVAILABLE':'Đã launch / giữ sensor; cần kiểm dữ liệu','RUNNING':'Đang xử lý','STARTING':'Đang khởi động','DEPLOYED':'Đã chuẩn bị',
        'INVENTORY_READY':'Đã có báo cáo thiết bị','STACK_READY':'Stack ZERO sẵn sàng',
        'WAITING_DATA':'Chờ samples','RECORDING_READY':'Có mẫu; đang ghi',
        'FORWARD':'Đang phát lệnh tiến','ZERO_DISABLED':'Đã yêu cầu zero/disable',
        'FINISHED':'Recorder đã đóng','REVIEW_READY':'Đã kiểm raw','OBSERVATION_SAVED':'Đã lưu quan sát',
        'FETCHED':'Đã tải về','FAILED':'Lỗi; giữ dữ liệu','CANCELLING':'Đang đóng process',
        'FORCED_UNKNOWN':'Đóng cưỡng bức / unknown','DEMO':'Demo; không có dữ liệu thật'}


class GuidedCollection(Q.QWidget):
    all_closed=C.pyqtSignal()
    progress=C.pyqtSignal(dict)

    def __init__(self,connection,demo=False,parent=None):
        super().__init__(parent)
        self.connection,self.demo=connection,bool(demo)
        self.runner=CollectionRunner(self,demo=demo);self.runner.job_event.connect(self.handle)
        self.done={};self.results={};self.errors={};self.stopping=False;self.closing=False;self.external_busy=False
        self.diagnostic_used=False;self.record_ready=False;self.record_closed=False;self.remaining=None
        self.current_job='record-diagnostic';self.journal=None
        self.capture_started=False;self.ready_received=float('-inf')
        self.wizard=CollectionWizard(self,STEPS)
        self.refresh()

    def metadata(self):
        return dict({k:b.isChecked() for k,b in self.checks.items()},pose_caster_note=self.pose.text().strip(),
                    floor_load_note=self.floor.text().strip(),video_note=self.video.text().strip(),
                    outcome=self.outcome.currentData(),text=self.observation.text().strip(),
                    research_plan_id='nino_bounded_velocity_research_v1')

    def select_recipe(self,name):
        key='stationary' if name=='stationary' else 'future' if name in ('repeatability','body_reference','future','gui_authority') else 'diagnostic'
        if not self.capture_started and not any(j in self.runner.active_jobs for j in ('start-stack','record-diagnostic','stationary','run-trial')):
            self.mode.setCurrentIndex(self.mode.findData(key))

    def start(self,job):
        if not self.buttons[job].isEnabled():return
        actual='stationary' if job=='record-diagnostic' and self.mode.currentData()=='stationary' else job
        metadata=self.metadata()
        if job=='run-trial':metadata['confirm_motion']=True
        if actual in ('record-diagnostic','stationary'):
            self.current_job=actual;self.record_closed=False;self.record_ready=False
            for key in ('review','observation','fetch'):self.done.pop(key,None)
            self.quality.setPlainText('Đang chuẩn bị/thu: chưa có chất lượng cuối.');self.bar.setValue(0)
        self.errors.pop(actual,None)
        if self.runner.start(actual,self.connection(),metadata):
            if actual=='run-trial':self.diagnostic_used=True
            if actual in ('stationary','record-diagnostic'):
                self.capture_started=True;self.motion_confirm.setChecked(False)
        self.refresh()

    def handle(self,event):
        job=event['job'];kind=event['kind'];state=event.get('state','RUNNING');data=event.get('data') or {}
        if not self.demo:
          try:
            if self.journal is None:
                root=Path.home()/'.local/state/nino/collection_gui';root.mkdir(parents=True,exist_ok=True)
                self.journal=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.jsonl')
            with self.journal.open('a') as stream:stream.write(json.dumps(dict(event,local_utc=datetime.now(timezone.utc).isoformat()),ensure_ascii=False,allow_nan=False)+'\n')
          except (OSError, ValueError) as error:
            self.output.appendPlainText('Không ghi được journal local: '+str(error))
        display_job='record-diagnostic' if job=='stationary' else job
        if display_job in dict(STEPS):
            row=[j for j,_ in STEPS].index(display_job)
            self.table.item(row,1).setText(LABELS.get(state,state))
            self.table.item(row,1).setToolTip(LABELS.get(state,state))
            detail=event.get('message','')
            if data.get('counts'):
                detail+=' · '+', '.join(name+': '+str(data['counts'].get(name,0)) for name in ('/imu/data','/motor_fb','/scan_raw'))
            if data.get('directory'):detail+=' · '+data['directory']
            self.table.item(row,2).setText(detail)
            self.table.item(row,2).setToolTip(detail)
        if kind in ('progress','finished'):
            if kind=='finished' and data.get('recorder_closed') and job==self.current_job:
                self.record_closed=True;self.record_ready=False
            self.results[job]=data or self.results.get(job,{})
            if data.get('directory'):self.wizard.session_path.setText(data['directory'])
            if data.get('counts'):
                self.wizard.sample_counts.setText('Mẫu đã ghi: '+', '.join(name+': '+str(data['counts'].get(name,0)) for name in ('/imu/data','/motor_fb','/scan_raw')))
            if job=='fetch' and data.get('local_directory') and not self.demo:
                path=Path(data['local_directory'])
                if path.is_absolute():self.local_directory.setText(str(path))
            if state in ('DEPLOYED','SENSORS_AVAILABLE','INVENTORY_READY','STACK_READY','REVIEW_READY','FETCHED','OBSERVATION_SAVED'):
                self.done[job]=True
            if state=='INVENTORY_READY':self.diagnostic_used |= bool(data.get('diagnostic_used'))
            if job==self.current_job and state=='RECORDING_READY':
                self.record_ready=True;self.ready_received=time.monotonic();self.remaining=data.get('remaining_s')
            if kind=='finished' and state=='FINISHED' and job==self.current_job:
                self.record_closed=bool(data.get('recorder_closed') or self.demo)
                self.record_ready=False;self.done['record-diagnostic']=True
                self.bar.setValue(600);self.bar.setFormat('Recorder đã đóng · chưa kết luận outcome')
            if data.get('quality_report'):
                report=data['quality_report']
                if self.demo:self.quality.setPlainText('Q0 · DEMO · không có bag, số đo hoặc bằng chứng thật.')
                elif 'label' in report:self.quality.setPlainText(quality_text(report))
        if kind=='finished':
            if event.get('returncode')!=0 or event.get('cancelled'):
                self.errors[job]=event.get('message','Process lỗi')
                if job in ('start-stack','connect-sensors'):self.done.pop(job,None)
            if job==self.current_job:
                self.record_ready=False
                if 'run-trial' in self.runner.active_jobs:self.runner.stop('run-trial')
            if self.stopping:self.cancel_next()
        if kind=='error':self.errors[job]=event.get('message','Lỗi')
        if kind=='error' or (kind=='finished' and (event.get('returncode')!=0 or event.get('cancelled'))):
            self.wizard.details_toggle.setChecked(True)
        if kind in ('output','error') or (kind=='progress' and state not in ('RECORDING_READY','WAITING_DATA')):
            self.output.appendPlainText(job+' · '+event.get('message',''))
        if self.remaining is not None and self.record_ready:
            self.bar.setValue(int((60-self.remaining)*10));self.bar.setFormat(f'Còn khoảng {self.remaining:.1f} s · đang ghi')
        self.progress.emit(event);self.refresh()
        if self.closing and not self.runner.active_jobs:self.all_closed.emit()

    def refresh(self,*_):
        jobs=self.runner.active_jobs;recording=any(k in jobs for k in ('record-diagnostic','stationary'));motion='run-trial' in jobs
        busy=recording or motion;kind=self.mode.currentData()
        self.mode.setEnabled(not busy and not self.stopping and not self.capture_started and 'start-stack' not in jobs)
        for edit in (self.pose,self.floor,self.video):edit.setEnabled(not busy and not self.capture_started)
        for b in self.checks.values():b.setEnabled(not busy and not self.capture_started)
        for job,b in self.buttons.items():b.setEnabled(False)
        idle=not self.closing and not self.stopping and not self.external_busy
        self.buttons['deploy'].setEnabled(idle and not jobs)
        only_sensors=not any(k!='connect-sensors' for k in jobs)
        self.buttons['connect-sensors'].setEnabled(idle and self.done.get('deploy',False) and not jobs)
        self.buttons['inventory'].setEnabled(idle and self.done.get('deploy',False) and only_sensors)
        self.buttons['start-stack'].setEnabled(idle and kind=='diagnostic' and self.done.get('inventory',False) and only_sensors and not self.diagnostic_used)
        notes=bool(self.pose.text().strip() and self.floor.text().strip())
        conditions=notes and all(b.isChecked() for b in self.checks.values()) and bool(self.video.text().strip())
        can_record=idle and not busy and self.done.get('inventory',False) and not self.record_closed
        if kind=='diagnostic':can_record=can_record and self.done.get('start-stack',False) and conditions and not self.diagnostic_used
        elif kind=='stationary':can_record=can_record and notes and only_sensors
        else:can_record=False
        self.buttons['record-diagnostic'].setEnabled(bool(can_record))
        self.buttons['record-diagnostic'].setText('4 · Thu đứng yên 60 s' if kind=='stationary' else '4 · Bắt đầu thu 60 s')
        self.buttons['run-trial'].setEnabled(idle and kind=='diagnostic' and self.record_ready and (self.demo or time.monotonic()-self.ready_received<=2.) and self.motion_confirm.isChecked() and not self.diagnostic_used and not motion
                                             and 'record-diagnostic' in jobs and (self.remaining is None or self.remaining>=33))
        self.buttons['review'].setEnabled(idle and self.record_closed and not busy and 'review' not in jobs and not self.done.get('review'))
        self.buttons['observation'].setEnabled(idle and self.done.get('review',False) and not busy and 'observation' not in jobs
                                              and not self.done.get('observation') and bool(self.observation.text().strip()))
        self.buttons['fetch'].setEnabled(idle and self.record_closed and not busy and 'fetch' not in jobs)
        self.stop.setEnabled(bool(jobs) and not self.stopping)
        self.wizard.refresh()

    def cancel(self):
        self.stopping=True;self.cancel_next();self.refresh()

    def cancel_next(self):
        jobs=self.runner.active_jobs
        for job in ('run-trial','record-diagnostic','stationary','inventory','review','fetch','deploy','observation','start-stack','connect-sensors'):
            if job in jobs:
                self.runner.stop(job);return
        self.stopping=False
        if self.closing:self.all_closed.emit()

    def request_close(self):
        self.closing=True
        if self.runner.active_jobs:self.cancel()
        else:self.runner.dispose();self.all_closed.emit()
