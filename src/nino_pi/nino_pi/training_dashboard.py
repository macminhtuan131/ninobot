"""Read-only map, native episode/checkpoint statistics and optional Laya advice."""
import json
from pathlib import Path
from PyQt5 import QtCore as C,QtWidgets as Q
from .training_dashboard_data import DashboardReader,laya_summary
from .training_world_map import WorldMap

_retired=[]


class Scan(C.QThread):
    snapshot=C.pyqtSignal(dict)
    failed=C.pyqtSignal(str)
    def __init__(self,reader,parent=None):super().__init__(parent);self.reader=reader
    def run(self):
        try:
            result=self.reader.poll(self.isInterruptionRequested)
            if result is not None and not self.isInterruptionRequested():self.snapshot.emit(result)
        except Exception as exc:self.failed.emit(type(exc).__name__+': '+str(exc))


def text(value,digits=3):return '—' if value is None else f'{value:.{digits}f}' if isinstance(value,float) else str(value)
def table(headers):
    w=Q.QTableWidget(0,len(headers));w.setHorizontalHeaderLabels(headers)
    w.setEditTriggers(Q.QAbstractItemView.NoEditTriggers);w.setSelectionBehavior(Q.QAbstractItemView.SelectRows)
    w.horizontalHeader().setSectionResizeMode(Q.QHeaderView.ResizeToContents)
    w.horizontalHeader().setStretchLastSection(True);w.setAlternatingRowColors(True)
    w.setStyleSheet('QTableWidget {background:#111d2c;alternate-background-color:#1d2b3e;color:#e5efff;gridline-color:#35465c;} QHeaderView::section {background:#243347;color:#e5efff;padding:5px;}')
    return w


class TrainingDashboard(Q.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.reader=None;self.thread=None;self.closed=False;self.snapshot=None
        self.laya=None;self.laya_buffer=b'';self.laya_busy=False;self.pending=[];self.sent=None;self.seen=set()
        self.advisories={};self.targets={};self.last_ep=None;self.last_checkpoint=None
        layout=Q.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.title=Q.QLabel('BẢN ĐỒ + EPISODE / CHECKPOINT · chỉ đọc artifact mô phỏng')
        self.title.setStyleSheet('font-size:17px;font-weight:600');layout.addWidget(self.title)
        self.tabs=Q.QTabWidget();layout.addWidget(self.tabs)
        self.map=WorldMap();self.map.setMinimumHeight(430);self.tabs.addTab(self.map,'Robot / world live')
        self.episodes=table(['EP','Trạng thái','Bước / global cuối','Stop nguồn s','Return','v RMSE mm/s','Path RMSE mm','Task / stop','Termination','Laya advisory'])
        self.tabs.addTab(self.episodes,'Sau mỗi episode')
        self.checkpoints=table(['Global','Critic','Replay','Loại','EP trong window','v RMSE mm/s','Path RMSE mm','Laya advisory','Bundle'])
        self.tabs.addTab(self.checkpoints,'Sau mỗi checkpoint')
        self.evaluation=table(['Arm','Stop nguồn s','v RMSE mm/s','Path RMSE mm','Task / stop'])
        self.tabs.addTab(self.evaluation,'Evaluation riêng')
        self.summary=Q.QLabel('Đang chờ chọn phiên');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        row=Q.QHBoxLayout();self.auto_laya=Q.QCheckBox('Laya tự nhận xét sau episode/checkpoint (CPU 1 luồng)')
        self.auto_laya.setChecked(True);self.auto_laya.toggled.connect(self.toggle_laya)
        self.retry=Q.QPushButton('Thử Laya lại');self.retry.clicked.connect(self.retry_laya)
        row.addWidget(self.auto_laya);row.addStretch();row.addWidget(self.retry);layout.addLayout(row)
        self.laya_note=Q.QLabel('Laya chỉ gợi ý từ thống kê, confidence chưa hiệu chuẩn cho Nino; không tự đổi policy/gain hoặc promote. Chỉ dùng model đã cache, không tải trong lúc train.')
        self.laya_note.setWordWrap(True);layout.addWidget(self.laya_note)
        self.timer=C.QTimer(self);self.timer.setInterval(2000);self.timer.timeout.connect(self.poll);self.timer.start()
    def set_job(self,directory):
        if self.closed:return
        if directory is None:
            self.reader=None;return
        directory=Path(directory)
        if self.reader and self.reader.directory==directory:return
        self.reader=DashboardReader(directory);self.snapshot=None;self.pending=[];self.seen=set()
        self.last_ep=None;self.last_checkpoint=None;self.advisories={};self.targets={}
        self.title.setText('BẢN ĐỒ + THỐNG KÊ · '+directory.name)
        self.poll()
    def poll(self):
        if self.closed or not self.reader or self.thread:return
        worker=Scan(self.reader,self);self.thread=worker
        worker.snapshot.connect(self.render);worker.failed.connect(lambda error:self.summary.setText('Chưa đọc được dashboard: '+error))
        worker.finished.connect(lambda:self.scanned(worker));worker.start()
    def scanned(self,worker):
        if self.thread is worker:self.thread=None
        worker.deleteLater()
    def render(self,s):
        if self.closed or not self.reader or s['directory']!=str(self.reader.directory):return
        self.snapshot=s;self.map.update_snapshot(s);self.render_tables(s)
        w=s['window'];self.summary.setText(
            f"Đã đọc {s['trace_rows']:,} transition · {w['episodes']} EP cuối hoàn chỉnh: task {w['successes']}/{w['episodes']} · "
            f"mean v RMS {text(None if w['velocity_rmse_m_s'] is None else 1000*w['velocity_rmse_m_s'])} mm/s. "
            +('Đang đọc backlog %.1f MiB. '%(s['backlog_bytes']/1024**2) if s['backlog_bytes'] else '')
            +'Metric native trace; EP đang chạy/cắt giữa chừng không tính là success. Checkpoint dùng tối đa 20 EP hoàn chỉnh trước bước lưu, chưa phải đánh giá policy frozen. '
            +' / '.join(s['warnings']))
        if not s['backlog_bytes']:self.queue_laya(s)
    def fill(self,w,rows):
        w.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):
                item=Q.QTableWidgetItem(text(value));item.setToolTip(text(value));w.setItem(i,j,item)
    def render_tables(self,s):
        rows=[]
        for e in reversed(s['episodes']):
            m=e['metrics'];v=m.get('velocity_error_m_s');p=m.get('cross_track_m')
            label=self.advisories.get('ep:'+str(e['episode']),'chưa có nhận xét')
            rows.append([e['episode'],e['status'],f"{e['rows']} / {e['end_step']}",e['source_stop_s'],e['reward'],
                None if v is None else v*1000,None if p is None else p*1000,
                f"{e['task_success']} / {e['stop_completed']}" if e['status']=='completed' else '—',e['termination'],label])
        self.fill(self.episodes,rows);rows=[]
        for c in reversed(s['checkpoints']):
            w=c['window'];v=w['velocity_rmse_m_s'];p=w['path_rmse_m']
            rows.append([c['global_steps'],c['critic_updates'],c['replay_size'],c['reason'],
                w['episodes'] if c['trace_caught_up'] else 'đang đọc trace',
                None if v is None else v*1000,None if p is None else p*1000,
                self.advisories.get('cp:'+c['path'],'chưa có nhận xét'),c['path']])
        self.fill(self.checkpoints,rows)
        self.fill(self.evaluation,[[e.get('arm'),e.get('source_stop_s'),
            None if e.get('nominal_velocity_rmse_m_s') is None else 1000*e['nominal_velocity_rmse_m_s'],
            None if e.get('cross_track_rmse_m') is None else 1000*e['cross_track_rmse_m'],
            f"{e.get('task_success')} / {e.get('stop_completed')}"] for e in s.get('evaluation',[])])
    def queue_laya(self,s):
        if not self.auto_laya.isChecked():return
        completed=[e for e in s['episodes'] if e['status']=='completed']
        if not completed:return
        latest=completed[-1]['episode']
        # Backfill numeric history immediately, classify only its latest window.
        # Subsequent episodes each get a distinct advisory request.
        new=[completed[-1]] if self.last_ep is None else [e for e in completed if e['episode']>self.last_ep]
        events=[('ep:'+str(e['episode']),[v for v in completed if v['episode']<=e['episode']]) for e in new]
        for cp in s['checkpoints']:
            if cp['trace_caught_up']:
                events.append(('cp:'+cp['path'],[e for e in completed if e['end_step'] is not None and e['end_step']<=cp['global_steps']]))
        for target,episodes in events:
            key=json.dumps([s['directory'],target])
            if key in self.seen or not episodes:continue
            self.seen.add(key);self.targets[key]=[target]
            self.pending.append(dict(key=key,rows=laya_summary(dict(episodes=episodes))[-40:]))
        self.last_ep=latest
        self.send_laya()
    def send_laya(self):
        if self.closed or self.laya_busy or not self.pending or not self.auto_laya.isChecked():return
        if self.laya is None:
            from .research_jobs import repository
            try:repo=repository()
            except (OSError,ValueError) as exc:self.laya_error(str(exc));return
            p=C.QProcess(self);self.laya=p
            env=C.QProcessEnvironment.systemEnvironment()
            env.insert('HF_HUB_OFFLINE','1');env.insert('TRANSFORMERS_OFFLINE','1');env.insert('OMP_NUM_THREADS','1')
            env.insert('PYTHONPATH',str(repo/'src/nino_pi')+':'+env.value('PYTHONPATH'))
            p.setProcessEnvironment(env);p.setProcessChannelMode(C.QProcess.MergedChannels)
            p.readyReadStandardOutput.connect(self.read_laya);p.finished.connect(lambda *args:self.laya_finished(p))
            p.errorOccurred.connect(lambda error:self.process_error(p))
            p.started.connect(self.send_laya)
            p.start('/usr/bin/nice',['-n','10',str(repo/'.venv/bin/python'),'-u','-m','nino_pi.training_laya_worker',str(repo/'src/nino_rl/scripts/laya_training_monitor.py')])
            self.laya_note.setText('Đang mở Laya CPU từ cache local; bảng số liệu vẫn cập nhật độc lập.');return
        if self.laya.state()!=C.QProcess.Running:return
        payload=self.pending.pop(0);self.sent=payload['key'];self.laya_busy=True
        self.laya.write((json.dumps(payload)+'\n').encode())
        key=self.sent;C.QTimer.singleShot(90000,lambda:self.laya_timeout(key))
    def read_laya(self):
        if not self.laya:return
        self.laya_buffer+=bytes(self.laya.readAllStandardOutput())
        while b'\n' in self.laya_buffer:
            line,self.laya_buffer=self.laya_buffer.split(b'\n',1)
            if not line.startswith(b'@@NINO_LAYA@@'):continue
            try:reply=json.loads(line[len(b'@@NINO_LAYA@@'):])
            except ValueError:continue
            if reply.get('error'):self.laya_error(reply['error']);continue
            self.laya_busy=False;key=reply.get('key');a=reply.get('advisory',{})
            if key not in self.targets:
                self.send_laya();continue
            label=str(a.get('suggested_issue','unknown'))+' · confidence '+text(a.get('answer_confidence'))
            if a.get('matches_most_common_failure_group') is False:
                label+=' · KHÁC counts ('+str(reply.get('numeric_issue','no_clear_issue'))+')'
            for target in self.targets.pop(key,[]):self.advisories[target]=label
            self.laya_note.setText('Laya: '+label+' · chỉ gợi ý chưa hiệu chuẩn; khi khác counts phải xem số liệu. Thiếu endpoint metric nên chưa xác nhận goal_accuracy. Không là so sánh với baseline.')
            if self.snapshot:self.render_tables(self.snapshot)
            self.send_laya()
    def laya_timeout(self,key):
        if self.laya_busy and self.sent==key:self.laya_error('Laya quá 90 s; giữ bảng thống kê, dừng advisory worker.')
    def laya_error(self,message):
        self.laya_note.setText('Laya chưa sẵn sàng: '+message[:500]+' · bảng số liệu vẫn hoạt động.')
        self.laya_note.setToolTip(message);self.auto_laya.setChecked(False);self.laya_busy=False
    def process_error(self,p):
        self.laya_error(p.errorString())
        if self.laya is p and p.state()==C.QProcess.NotRunning:
            self.laya=None;p.deleteLater()
    def laya_finished(self,p):
        if self.laya is p:
            self.read_laya();self.laya=None;self.laya_busy=False;p.deleteLater()
    def toggle_laya(self,enabled):
        if not enabled:
            if self.laya:self.laya.terminate()
        elif self.snapshot:self.queue_laya(self.snapshot)
    def retry_laya(self):
        self.sent=None;self.last_ep=None;self.seen=set();self.pending=[];self.auto_laya.setChecked(True)
        if self.snapshot:self.queue_laya(self.snapshot)
    def shutdown(self):
        if self.closed:return
        self.closed=True;self.timer.stop()
        if self.thread:
            worker=self.thread;worker.requestInterruption()
            if not worker.wait(1500):
                worker.setParent(None);_retired.append(worker)
                worker.finished.connect(lambda:_retired.remove(worker) if worker in _retired else None)
            self.thread=None
        if self.laya:
            process=self.laya;process.terminate()
            if not process.waitForFinished(500):process.kill();process.waitForFinished(300)
    def closeEvent(self,event):self.shutdown();super().closeEvent(event)
