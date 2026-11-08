"""Native TD3 training console. Jobs are isolated local processes, never SSH."""
import json
import os
from pathlib import Path
import re
import signal
import uuid
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as Q
from .research_jobs import repository


class TrainingRunner(C.QObject):
    update=C.pyqtSignal(dict)
    closed=C.pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent);self.process=None;self.buffer=b'';self.last={};self.cancelling=False;self.log_path=None
    @property
    def busy(self):return self.process is not None
    def start(self,root,request):
        from nino_rl.training_studio_api import validate_request
        if self.busy:return False
        request=validate_request(request);root=Path(root).expanduser().resolve()
        (root/'requests').mkdir(parents=True,exist_ok=True);token=uuid.uuid4().hex
        path=root/'requests'/(token+'.json');path.write_text(json.dumps(request,indent=2)+'\n')
        (root/'ui_logs').mkdir(exist_ok=True);self.log_path=root/'ui_logs'/(token+'.log')
        self.last={};self.buffer=b'';self.cancelling=False
        p=C.QProcess(self);self.process=p;p.setProcessChannelMode(C.QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self.read);p.finished.connect(self.finish);p.errorOccurred.connect(self.error)
        p.start('/usr/bin/setsid',['/bin/bash',str(repository()/'src/nino_rl/scripts/common_training_studio.sh'),
            '--request',str(path),'--output',str(root)])
        return True
    def read(self):
        if not self.process:return
        data=bytes(self.process.readAllStandardOutput())
        if data and self.log_path:
            with self.log_path.open('ab') as stream:stream.write(data)
        self.buffer+=data
        while b'\n' in self.buffer:
            raw,self.buffer=self.buffer.split(b'\n',1);line=raw.decode('utf8','replace')
            if line.startswith('@@NINO_RESEARCH@@'):
                try:
                    value=json.loads(line[len('@@NINO_RESEARCH@@'):]);self.last=value;self.update.emit(value);continue
                except ValueError:pass
            self.update.emit(dict(message=line))
    def finish(self,code=1,status=None):
        if not self.process:return
        self.read();p=self.process;self.process=None
        if self.buffer:self.update.emit(dict(message=self.buffer.decode('utf8','replace')));self.buffer=b''
        self.update.emit(dict(self.last,closed=True,returncode=code,cancelled=self.cancelling))
        p.deleteLater();self.closed.emit()
    def error(self,error):
        if not self.process:return
        self.update.emit(dict(message='Lỗi process: '+self.process.errorString()))
        if self.process.state()==C.QProcess.NotRunning:self.finish()
    def cancel(self):
        if self.process and self.process.processId() and not self.cancelling:
            self.cancelling=True
            try:os.kill(int(self.process.processId()),signal.SIGINT)
            except ProcessLookupError:pass
            self.update.emit(dict(message='Đang dừng ở ranh giới transition; chờ lưu checkpoint và đóng Gazebo.'))


class TD3TrainingPanel(Q.QWidget):
    changed=C.pyqtSignal()
    all_closed=C.pyqtSignal()
    parametersRequested=C.pyqtSignal()
    def __init__(self,parent=None,blocked=None,root=None,observe_external=True):
        super().__init__(parent);self.blocked=blocked or (lambda:False);self.closing=False
        self.live_reader=None;self.live_snapshot=None;self.external_running=False
        self.follow_live=True;self.observe_external=observe_external;self.watch_all_roots=root is None
        self.watch_closed=False;self.live_catalog=None
        self.runner=TrainingRunner(self);self.runner.update.connect(self.handle);self.runner.closed.connect(self.job_closed)
        self.tb=None;self.tb_url=None;self.tb_buffer='';self.current_directory=None;self.last_result=None
        self.resume_info=None
        from nino_rl.training_studio_api import ENGINES,module
        self.engine_modules={name:module(name) for name in ENGINES}
        self.engine_profiles={name:m.profiles() for name,m in self.engine_modules.items()}
        self.parameter_profiles=self.engine_profiles['common103_v1']
        layout=Q.QVBoxLayout(self)
        title=Q.QLabel('TRAIN TD3 · smoke → train / resume → kết quả');title.setStyleSheet('font-size:22px;font-weight:700');layout.addWidget(title)
        note=Q.QLabel('Gazebo Nino local · không cần Pi/agent · baseline frozen + residual · history 5 mẫu / 10 Hz.\n'
            '1 Chọn map/profile và số bước → 2 Smoke hoặc Train → 3 Xem kết quả / TensorBoard → 4 Chọn checkpoint để học tiếp. '
            'Các map dưới đây là fixture sàn sạch/gờ của factory, chưa phải toàn map mixed.');note.setWordWrap(True);layout.addWidget(note)
        self.contract_note=Q.QLabel()
        self.contract_note.setWordWrap(True);layout.addWidget(self.contract_note)
        self.assessment_note=Q.QLabel();self.assessment_note.setWordWrap(True)
        self.assessment_note.setStyleSheet('background:#183044;color:#e7edf7;padding:10px;');layout.addWidget(self.assessment_note)
        self.assessment=None
        try:
            from .studio_training_evidence import scientific_assessment
            plan=json.loads(Path(__file__).with_name('research_plan.json').read_text())
            self.assessment=scientific_assessment(plan)
            if self.assessment:self.assessment_note.setText(self.assessment['summary'])
            else:self.assessment_note.hide()
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.assessment_note.setText('Kết luận khoa học chưa xác minh: '+str(exc))
        # Keep live state above the parameter form, visible without scrolling.
        self.progress=Q.QProgressBar();layout.addWidget(self.progress)
        self.status=Q.QLabel('Chưa chạy. Smoke dùng model mới/profile smoke; Train dùng số bước bạn nhập.');self.status.setWordWrap(True);layout.addWidget(self.status)
        live_row=Q.QHBoxLayout();self.find_live_button=Q.QPushButton('Theo dõi lượt train đang chạy')
        self.find_live_button.clicked.connect(self.find_live);live_row.addWidget(self.find_live_button)
        self.live_note=Q.QLabel('Tự tìm worker local; có thể mở lại Studio trong khi job đang chạy.')
        self.live_note.setWordWrap(True);live_row.addWidget(self.live_note,1);layout.addLayout(live_row)
        self.live_metrics=Q.QLabel();self.live_metrics.setWordWrap(True)
        self.live_metrics.setStyleSheet('font-size:16px;font-weight:600');layout.addWidget(self.live_metrics)
        from .training_dashboard import TrainingDashboard
        self.dashboard=TrainingDashboard(self);layout.addWidget(self.dashboard)
        self.location=Q.QLineEdit(str(root or C.QSettings('Nino','ControlModes').value('td3_training_root',str(Path.home()/'nino_research/td3_studio'))))
        self.choose_root=Q.QPushButton('Chọn thư mục lưu');self.choose_root.clicked.connect(self.pick_root)
        row=Q.QHBoxLayout();row.addWidget(self.location,1);row.addWidget(self.choose_root);layout.addLayout(row)
        form=Q.QFormLayout();layout.addLayout(form)
        self.engine=Q.QComboBox()
        for name,label in ENGINES.items():self.engine.addItem(label,name)
        form.addRow('Contract / trainer',self.engine)
        self.scenario=Q.QComboBox()
        for value,label in self.engine_modules['common103_v1'].SCENARIOS.items():self.scenario.addItem(label,value)
        self.profile=Q.QComboBox()
        for name in self.parameter_profiles:self.profile.addItem(name,name)
        self.profile.setCurrentIndex(self.profile.findData('nino_td3_research_h5_v1'))
        self.timesteps=Q.QSpinBox();self.timesteps.setRange(1,1_000_000_000);self.timesteps.setValue(20000);self.timesteps.setGroupSeparatorShown(True)
        self.seed=Q.QSpinBox();self.seed.setRange(0,2_147_483_647);self.seed.setValue(7)
        self.interval=Q.QSpinBox();self.interval.setRange(0,1_000_000_000);self.interval.setValue(5000);self.interval.setSpecialValueText('Chỉ checkpoint cuối / khi dừng')
        self.wall=Q.QSpinBox();self.wall.setRange(1,10080);self.wall.setValue(180);self.wall.setSuffix(' phút')
        form.addRow('Map mô phỏng',self.scenario);form.addRow('Profile TD3',self.profile)
        form.addRow('Timesteps học thêm',self.timesteps);form.addRow('Seed (khóa khi resume)',self.seed)
        form.addRow('Checkpoint mỗi N bước thêm',self.interval);form.addRow('Wall-time tối đa',self.wall)
        self.parameter_note=Q.QLabel();self.parameter_note.setWordWrap(True);layout.addWidget(self.parameter_note)
        self.profile.currentIndexChanged.connect(self.show_parameters);self.show_parameters()
        self.parameters_button=Q.QPushButton('Xem tham số / lưu draft để tune trong Studio')
        self.parameters_button.clicked.connect(self.open_parameters);layout.addWidget(self.parameters_button)
        self.budget_note=Q.QLabel();self.budget_note.setWordWrap(True);layout.addWidget(self.budget_note)
        self.resume=Q.QCheckBox('Tiếp tục từ checkpoint · giữ model / target / optimizer / replay');layout.addWidget(self.resume)
        checkpoint_row=Q.QHBoxLayout();self.checkpoint_path=Q.QLineEdit();self.checkpoint_path.setPlaceholderText('Chọn model.zip hoặc thư mục checkpoint hoàn chỉnh')
        self.browse_checkpoint=Q.QPushButton('Chọn checkpoint…');self.browse_checkpoint.clicked.connect(self.pick_checkpoint)
        checkpoint_row.addWidget(self.checkpoint_path,1);checkpoint_row.addWidget(self.browse_checkpoint);layout.addLayout(checkpoint_row)
        self.checkpoint_note=Q.QLabel('Resume tạo episode sim mới; không khôi phục chính xác trạng thái Gazebo hoặc RNG.');self.checkpoint_note.setWordWrap(True);layout.addWidget(self.checkpoint_note)
        self.resume.toggled.connect(self.refresh)
        self.auto_evaluate=Q.QCheckBox();self.auto_evaluate.setChecked(True);layout.addWidget(self.auto_evaluate)
        actions=Q.QHBoxLayout();self.smoke=Q.QPushButton('1 · Smoke test · 64 bước mới');self.train=Q.QPushButton('2 · Train TD3');self.train.setObjectName('primary')
        self.stop=Q.QPushButton('Dừng + giữ checkpoint');self.stop.setObjectName('danger')
        for button in (self.smoke,self.train,self.stop):actions.addWidget(button)
        self.smoke.clicked.connect(lambda:self.start('smoke'));self.train.clicked.connect(lambda:self.start('train'));self.stop.clicked.connect(self.runner.cancel);layout.addLayout(actions)
        bar=Q.QHBoxLayout();self.open_tb=Q.QPushButton('Mở TensorBoard');self.stop_tb=Q.QPushButton('Tắt TensorBoard');self.open_folder=Q.QPushButton('Mở kết quả')
        self.open_tb.clicked.connect(self.start_tensorboard);self.stop_tb.clicked.connect(self.stop_tensorboard)
        self.open_folder.clicked.connect(lambda:G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(self.current_directory or self.root()))))
        for b in (self.open_tb,self.stop_tb,self.open_folder):bar.addWidget(b)
        layout.addLayout(bar);self.tb_status=Q.QLabel('TensorBoard chưa mở · chỉ bind 127.0.0.1');self.tb_status.setWordWrap(True);self.tb_status.setOpenExternalLinks(True);layout.addWidget(self.tb_status)
        self.output=Q.QTabWidget();layout.addWidget(self.output,1)
        self.log=Q.QPlainTextEdit();self.log.setReadOnly(True);self.log.document().setMaximumBlockCount(700);self.output.addTab(self.log,'Quá trình / lỗi')
        self.results=Q.QPlainTextEdit();self.results.setReadOnly(True);self.output.addTab(self.results,'Kết quả / metric')
        saved=Q.QWidget();saved_layout=Q.QVBoxLayout(saved)
        self.saved=Q.QComboBox();self.reload_button=Q.QPushButton('Đọc lại phiên / checkpoint');self.reload_button.clicked.connect(self.reload_sessions)
        self.use_checkpoint=Q.QPushButton('Dùng checkpoint đã chọn để train tiếp');self.use_checkpoint.clicked.connect(self.use_saved_checkpoint)
        saved_layout.addWidget(self.reload_button);saved_layout.addWidget(self.saved);saved_layout.addWidget(self.use_checkpoint)
        self.session_table=Q.QTableWidget(0,5);self.session_table.setHorizontalHeaderLabels(['Phiên','Trạng thái','Bước thêm','Global steps','Lỗi / kết quả'])
        self.session_table.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Stretch);self.session_table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.session_table.cellClicked.connect(self.select_session);saved_layout.addWidget(self.session_table)
        self.output.addTab(saved,'Phiên đã chạy / checkpoints')
        self.timesteps.valueChanged.connect(self.refresh)
        self.checkpoint_path.textChanged.connect(self.refresh)
        self.engine.currentIndexChanged.connect(self.engine_changed)
        self.sessions=[];self.reload_sessions();self.engine_changed()
        self.live_timer=C.QTimer(self);self.live_timer.setInterval(2000);self.live_timer.timeout.connect(self.poll_live)
        self.live_timer.start();C.QTimer.singleShot(0,self.poll_live)
        if root is None and observe_external:C.QTimer.singleShot(0,self.restore_assessed_session)

    def restore_assessed_session(self):
        """Display a reviewed result without starting or resuming a learner."""
        if not self.assessment or self.busy or self.live_reader or self.closing:return
        directory=Path(self.assessment['training_artifact'])
        if directory.parent!=self.root():return
        for row,(path,job,result) in enumerate(self.sessions):
            if path==directory:
                self.select_session(row,0);self.progress.setValue(100)
                completed=self.assessment['completed']
                self.status.setText('Đã hoàn tất và review · đang xem kết quả lưu; không có job mới.')
                self.live_metrics.setText(f"Global {completed['training_transitions']:,} · thêm {completed['job_transitions']:,} · "
                    f"critic {completed['critic_updates']:,} · actor {completed['actor_updates']:,} · cùng seed {completed['seed']}")
                break
    @property
    def busy(self):return self.runner.busy or self.external_running
    @property
    def active(self):return self.runner.busy or self.tb is not None
    def root(self):return Path(self.location.text()).expanduser().resolve()
    def pick_root(self):
        path=Q.QFileDialog.getExistingDirectory(self,'Thư mục lưu các job TD3',str(self.root()))
        if path:self.location.setText(path);C.QSettings('Nino','ControlModes').setValue('td3_training_root',path);self.reload_sessions()
    def show_parameters(self):
        if self.profile.currentData() not in self.parameter_profiles:return
        p=self.parameter_profiles[self.profile.currentData()]['algorithm'];common=self.engine.currentData()=='common103_v1'
        memory=p['buffer_size']*((103 if common else 100)*2+(1 if common else 2)+4)*4/1024**2
        self.parameter_note.setText(f"MLP {p['network_arch']} · LR {p['actor_lr']} · warmup {p['learning_starts']} · batch {p['batch_size']} · replay {p['buffer_size']:,} (arrays khoảng {memory:.1f} MiB). Smoke luôn dùng profile smoke h5; profile smoke chỉ kiểm pipeline. Research profile là cấu hình khởi đầu, chưa tune cho Nino. Không đổi profile checkpoint khi resume.")
        if hasattr(self,'train'):self.refresh()

    def engine_changed(self):
        name=self.engine.currentData();module=self.engine_modules[name]
        selected=self.profile.currentData();self.parameter_profiles=self.engine_profiles[name]
        self.profile.blockSignals(True);self.profile.clear()
        for profile in self.parameter_profiles:self.profile.addItem(profile,profile)
        self.profile.setCurrentIndex(max(0,self.profile.findData(selected)));self.profile.blockSignals(False)
        self.scenario.clear()
        for value,label in module.SCENARIOS.items():self.scenario.addItem(label,value)
        common=name=='common103_v1'
        self.timesteps.setMaximum(20000 if common else 1_000_000_000)
        self.contract_note.setText('Hiện tại: common103D/1D, history100D + source-plan3D, Ki0.10 frozen; ±0,005 m/s common, differential=0. '
            'Legacy100D/2D là nhánh khác. A/C đã đóng; không resume chúng trong pilot mới.' if common else
            'Legacy100D/2D; khác common103D/1D. Không chuyển đổi checkpoint chéo ABI.')
        self.auto_evaluate.setText('Đánh giá sau train: B0 / classical scheduled / TD3 × source stop 6/8 s; 6 lượt × 14 s' if common else
            'Đánh giá sau train: B0 + TD3, một lượt 14 s/arm trên map đã chọn')
        self.parameters_button.setText('Xem effective profile · common103D/1D' if common else
            'Xem tham số / lưu draft để tune trong Studio')
        self.show_parameters()

    def open_parameters(self):
        if self.engine.currentData()!='common103_v1':
            self.parametersRequested.emit();return
        dialog=Q.QDialog(self);dialog.setWindowTitle('Effective profile · common103D/1D · chưa tune');dialog.resize(700,650)
        layout=Q.QVBoxLayout(dialog)
        label=Q.QLabel('Profile common có replay tối đa 32.768, tách với catalog legacy. Muốn tune phải tạo phiên bản profile mới; không đổi profile khi resume.');label.setWordWrap(True);layout.addWidget(label)
        text=Q.QPlainTextEdit();text.setReadOnly(True)
        text.setPlainText(json.dumps(self.parameter_profiles[self.profile.currentData()],indent=2,ensure_ascii=False));layout.addWidget(text)
        close=Q.QPushButton('Đóng');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec_()

    def training_budget(self):
        warmup=self.parameter_profiles[self.profile.currentData()]['algorithm']['learning_starts']
        start=0
        if self.resume.isChecked():
            if not self.resume_info or self.checkpoint_path.text()!=self.resume_info['path']:
                return None,'Chọn/kiểm checkpoint để tính warmup còn lại; worker sẽ xác minh bundle trước khi load.'
            start=self.resume_info['global_steps']
        eligible=max(0,start+self.timesteps.value()-max(start,warmup))
        if eligible==0:
            return False,f'CHƯA CÓ BƯỚC HỌC: warmup {warmup:,}, global bắt đầu {start:,}, học thêm {self.timesteps.value():,}. Tăng số bước để vượt warmup; Smoke vẫn dùng64bước/profile smoke.'
        return True,f'Warmup {warmup:,} · global bắt đầu {start:,} · tối đa {eligible:,} bước thêm sau warmup có thể cập nhật. Số update thực xem ở kết quả; không phải bảo đảm hội tụ.'
    def pick_checkpoint(self):
        path,_=Q.QFileDialog.getOpenFileName(self,'Chọn model.zip trong bundle có replay + manifest',str(self.root()),'Model (model.zip)')
        if path:self.load_checkpoint(path)
    def load_checkpoint(self,path):
        from nino_rl.training_studio_api import inspect_checkpoint
        try:
            info=inspect_checkpoint(path,verify_files=False)
            self.engine.setCurrentIndex(self.engine.findData(info['engine']))
            self.resume_info=info
            self.checkpoint_path.setText(info['path']);self.scenario.setCurrentIndex(self.scenario.findData(info['scenario']))
            self.profile.setCurrentIndex(self.profile.findData(info['profile']));self.seed.setValue(info['seed']);self.resume.setChecked(True)
            self.checkpoint_note.setText(f"Global {info['global_steps']} · updates {info['optimizer_updates']} · replay {info['replay_size']}. Đã đọc metadata; worker sẽ kiểm toàn bộ hash/runtime trước khi load. Timesteps là số bước thêm; simulator bắt đầu episode mới.")
            self.refresh();return True
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.checkpoint_note.setText('Không load được checkpoint: '+str(exc));return False
    def request(self,mode):
        from nino_rl.training_studio_api import validate_request
        module=self.engine_modules[self.engine.currentData()];SMOKE_PROFILE=module.SMOKE_PROFILE
        if mode=='train' and self.resume.isChecked():
            if not self.checkpoint_path.text().strip() or not self.load_checkpoint(self.checkpoint_path.text()):raise ValueError('Chọn checkpoint hợp lệ để tiếp tục')
        if mode=='train':
            ready,message=self.training_budget()
            if ready is False:raise ValueError(message)
        selected=SMOKE_PROFILE if mode=='smoke' else self.profile.currentData()
        if module.profiles()[selected]!=self.parameter_profiles[selected]:
            raise ValueError('Catalog tham số đã thay đổi; mở lại Studio để xem đúng cấu hình trước khi chạy.')
        request=validate_request(dict(schema_version=2,engine=self.engine.currentData(),mode=mode,scenario=self.scenario.currentData(),profile=SMOKE_PROFILE if mode=='smoke' else self.profile.currentData(),
            timesteps=64 if mode=='smoke' else self.timesteps.value(),seed=self.seed.value(),checkpoint_every=self.interval.value(),wall_minutes=self.wall.value(),
            evaluate=self.auto_evaluate.isChecked(),resume=self.checkpoint_path.text() if mode=='train' and self.resume.isChecked() else None))
        if self.engine.currentData()=='common103_v1':
            from nino_rl.training_studio_api import split
            module.require_disk(self.root(),split(request)[1])
        return request
    def start(self,mode):
        self.poll_live()
        if self.blocked() or self.closing or self.busy:return
        try:
            request=self.request(mode)
            if self.runner.start(self.root(),request):
                self.live_reader=None;self.live_snapshot=None;self.live_metrics.clear()
                self.dashboard.set_job(None)
                self.log.clear();self.results.clear();self.last_result=None;self.current_directory=None;self.output.setCurrentIndex(0)
                self.progress.setRange(0,100);self.progress.setValue(0);self.status.setText('Khởi động '+mode+' · '+str(request['timesteps'])+' bước thêm; chưa có kết quả.');self.refresh();self.changed.emit()
        except (OSError,ValueError,KeyError,TypeError) as exc:self.status.setText('Chưa chạy: '+str(exc))
    def handle(self,event):
        if event.get('directory'):
            self.current_directory=Path(event['directory']);self.dashboard.set_job(self.current_directory)
        if event.get('checkpoint'):self.checkpoint_note.setText('Checkpoint đã lưu: '+event['checkpoint'])
        if event.get('message'):self.log.appendPlainText(event['message']);self.status.setText(event['message'])
        if event.get('progress') is not None:
            self.progress.setRange(0,100);self.progress.setValue(round(event['progress']*100))
        elif event.get('phase') in ('prepare','load','evaluate'):self.progress.setRange(0,0)
        if event.get('result'):self.display_result(event['result'])
        if event.get('error'):self.log.appendPlainText('LỖI: '+event['error'])
        if event.get('closed'):
            self.progress.setRange(0,100)
            if event['returncode']==0:
                self.progress.setValue(100);self.status.setText('Đã hoàn tất · xem Kết quả / TensorBoard / checkpoint để học tiếp.')
            else:
                self.status.setText(f"Job đã dừng/lỗi · exit {event['returncode']}. Giữ log/checkpoint hoàn chỉnh; không tự chạy lại.")
                if self.current_directory:
                    partial=self.current_directory/'training_result.json'
                    if partial.is_file():self.display_result(json.loads(partial.read_text()))
                    if (self.current_directory/'error.txt').is_file():self.log.appendPlainText((self.current_directory/'error.txt').read_text())
                self.output.setCurrentIndex(0)
            self.reload_sessions()
        self.refresh()
    def display_result(self,result):
        self.last_result=result
        intro=f"THÊM {result['transitions']} bước · global {result['starting_global_steps']} → {result['global_steps']} · optimizer +{result['optimizer_updates_this_job']}\n"
        if 'actor_updates_this_job' in result:intro+=f"Critic +{result['optimizer_updates_this_job']} · actor +{result['actor_updates_this_job']} · engine {result.get('engine')}\n"
        intro+='Checkpoint: '+result['checkpoint']+'\n'
        if result.get('evaluation'):
            for m in result['evaluation']:
                intro+=f"{m['arm']}: path RMSE {m['cross_track_rmse_m']*1000:.3f} mm · v RMSE {m['nominal_velocity_rmse_m_s']:.6f} m/s · marker/stop {m['task_success']}/{m['stop_completed']}\n"
        else:intro+='Chưa đánh giá B0/TD3; reward hoặc checkpoint không chứng minh lợi ích.\n'
        if result['final_segment_right_censored']:intro+='Đoạn train cuối dừng giữa episode: chưa có outcome hoàn chỉnh cho đoạn đó.\n'
        self.results.setPlainText(intro+'\n'+json.dumps(result,ensure_ascii=False,indent=2));self.output.setCurrentIndex(1)
    def reload_sessions(self):
        self.saved.clear();self.sessions=[]
        for path in sorted(self.root().glob('*/job.json'),reverse=True):
            try:
                job=json.loads(path.read_text());directory=path.parent;result_path=directory/'training_result.json'
                result=json.loads(result_path.read_text()) if result_path.is_file() else {}
                self.sessions.append((directory,job,result))
            except (OSError,ValueError):continue
        self.session_table.setRowCount(len(self.sessions))
        for row,(directory,job,result) in enumerate(self.sessions):
            for col,value in enumerate((directory.name,job['status'],str(result.get('transitions','—')),str(result.get('global_steps','—')),job.get('error') or ('Kết quả có sẵn' if result else 'Chưa có kết quả'))):
                self.session_table.setItem(row,col,Q.QTableWidgetItem(value))
            for p in sorted((directory/'checkpoints').glob('*/checkpoint.json'),reverse=True):
                if not p.parent.name.startswith('.') and (p.parent/'manifest.json').is_file():self.saved.addItem(directory.name+' / '+p.parent.name,str(p.parent))
        legacy=Path.home()/'nino_research/sim_guided_td3_v3/state.json'
        try:
            name=json.loads(legacy.read_text())['latest']['sim-v3-train'];self.saved.addItem('V3 lịch sử · 512 bước',str(legacy.parent/name))
        except (OSError,ValueError,KeyError):pass
        self.use_checkpoint.setEnabled(self.saved.count()>0 and not self.busy and not self.closing)
    def select_session(self,row,column):
        directory,job,result=self.sessions[row];self.current_directory=directory
        self.dashboard.set_job(directory)
        if self.live_reader and directory==self.live_reader.directory:
            self.follow_live=True;self.poll_live();return
        self.follow_live=False
        self.status.setText('Đang xem phiên đã lưu · '+job['status']+' · '+directory.name+'; không có job mới từ thao tác này.')
        final=directory/'result.json'
        if final.is_file():self.display_result(json.loads(final.read_text()))
        elif result:self.display_result(result)
        if job.get('error'):self.log.setPlainText((directory/'error.txt').read_text() if (directory/'error.txt').is_file() else job['error']);self.output.setCurrentIndex(0)
    def use_saved_checkpoint(self):
        if self.saved.currentData():self.load_checkpoint(self.saved.currentData())
    def find_live(self):
        self.observe_external=True;self.watch_all_roots=True;self.follow_live=True
        if not self.external_running:self.live_reader=None
        self.poll_live()
    def show_live_request(self):
        """Show the observed job's config, never submit it or load its model."""
        worker=self.live_reader.worker;request=worker['request']
        index=self.engine.findData(worker['engine'])
        if index>=0:self.engine.setCurrentIndex(index)
        for widget,key in ((self.profile,'profile'),(self.scenario,'scenario')):
            index=widget.findData(request.get(key))
            if index>=0:widget.setCurrentIndex(index)
        for widget,key in ((self.timesteps,'timesteps'),(self.seed,'seed'),(self.interval,'checkpoint_every'),(self.wall,'wall_minutes')):
            if type(request.get(key)) is int:widget.setValue(request[key])
        self.auto_evaluate.setChecked(bool(request.get('evaluate')))
        path=request.get('resume') or ''
        self.resume_info=dict(path=path,global_steps=self.live_reader.start) if path else None
        self.checkpoint_path.setText(path);self.resume.setChecked(bool(path))
        if path:self.checkpoint_note.setText('Job đang theo dõi resume từ: '+path+' · chỉ đọc metadata; chưa QC cuối.')
    def poll_live(self):
        if self.closing or self.watch_closed or not self.observe_external:return
        if self.runner.busy:
            self.live_note.setText('GUI đang sở hữu worker này; tiến độ lấy từ process trực tiếp.');return
        from .training_live import discover,LiveJob
        was_busy=self.external_running
        if self.live_reader is None:
            workers=discover(None if self.watch_all_roots else [self.root()])
            if not workers:
                self.live_note.setText('Chưa tìm thấy worker local đang chạy. Nút này chỉ đọc, không khởi động train.');return
            self.live_reader=LiveJob(workers[0]);self.follow_live=True
            self.location.setText(workers[0]['root']);self.log.clear();self.live_catalog=None
            self.show_live_request()
        try:snapshot=self.live_reader.poll()
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.live_note.setText('Chưa đọc được tiến độ: '+str(exc));return
        self.live_snapshot=snapshot;self.external_running=snapshot['status'] in ('running','worker_missing')
        worker=snapshot['worker'];age=snapshot['log_age_s']
        self.live_note.setText(f"Theo dõi PID{worker['pid']} · đóng GUI không dừng worker · log "+
            (f'cập nhật {age:.0f}s trước' if age is not None else 'chưa đọc được'))
        critic=snapshot['critic_updates'];actor=snapshot['actor_updates']
        self.live_metrics.setText(
            f"GLOBAL {snapshot['global_steps']:,} · lượt này {snapshot['additional_steps']:,}/{snapshot['total_steps']:,} "
            f"· bắt đầu {snapshot['starting_global_steps']:,} · critic {critic if critic is not None else '—'}"
            +(' (log, có thể trễ)' if snapshot['critic_count_is_logged'] else '')
            +f" · actor {actor if actor is not None else 'chưa có counter checkpoint cuối'}")
        if self.follow_live:
            self.current_directory=self.live_reader.directory
            self.dashboard.set_job(self.current_directory)
            for line in snapshot['log_lines']:self.log.appendPlainText(line)
            self.progress.setRange(0,100);self.progress.setValue(round(snapshot['progress']*100))
            self.progress.setFormat('%p% · bước của lượt hiện tại')
            status=snapshot['status']
            if status=='running':
                phase=(f"evaluation {snapshot['evaluation_runs']}/6" if snapshot['phase']=='evaluate' else 'training')
                self.status.setText('ĐANG CHẠY · '+phase+' · '+self.live_reader.directory.name+' · chỉ theo dõi; chưa QC cuối.')
            elif status=='worker_missing':
                self.status.setText('KHÔNG THẤY WORKER nhưng job chưa đóng; giữ tiến độ cuối và xem log, không tự retry.')
            else:
                self.status.setText('WORKER ĐÃ ĐÓNG · '+status+' · xem kết quả/error và QC; không tự chạy tiếp.')
            if snapshot['checkpoints']:self.checkpoint_note.setText('Checkpoint hoàn chỉnh mới nhất: '+snapshot['checkpoints'][-1])
            if status in ('completed','failed','cancelled') and snapshot['result'] and self.last_result!=snapshot['result']:
                self.display_result(snapshot['result'])
            if snapshot['error'] and not self.log.toPlainText().endswith(snapshot['error']):
                self.log.appendPlainText('LỖI: '+snapshot['error'])
        elif snapshot['log_lines']:
            self.live_note.setText(self.live_note.text()+' · đang xem lịch sử; bấm Theo dõi để trở lại job live')
        catalog=(snapshot['status'],tuple(snapshot['checkpoints']))
        if catalog!=self.live_catalog:
            self.live_catalog=catalog;self.reload_sessions()
        for row,(directory,job,result) in enumerate(self.sessions):
            if directory==self.live_reader.directory:
                for column,value in ((1,snapshot['status']),(2,str(snapshot['additional_steps'])),(3,str(snapshot['global_steps']))):
                    self.session_table.setItem(row,column,Q.QTableWidgetItem(value))
        self.refresh()
        if was_busy!=self.external_running:self.changed.emit()
    def closeEvent(self,event):
        if not self.active:
            self.watch_closed=True;self.live_timer.stop()
            self.dashboard.shutdown()
        super().closeEvent(event)
    def refresh(self):
        locked=self.busy or self.blocked() or self.closing
        for w in (self.location,self.choose_root,self.timesteps,self.interval,self.wall,self.resume,self.browse_checkpoint,self.checkpoint_path,self.auto_evaluate):w.setEnabled(not locked)
        for w in (self.engine,self.scenario,self.profile,self.seed):w.setEnabled(not locked and not self.resume.isChecked())
        budget_ready,budget_message=self.training_budget()
        self.budget_note.setText(budget_message)
        self.budget_note.setStyleSheet('color:#ffb36c' if budget_ready is False else '')
        self.smoke.setEnabled(not locked);self.train.setEnabled(not locked and budget_ready is not False)
        self.train.setText('2 · Tiếp tục TD3 · học thêm' if self.resume.isChecked() else '2 · Train TD3 mới')
        self.stop.setEnabled(self.runner.busy and not self.runner.cancelling);self.use_checkpoint.setEnabled(not locked and self.saved.count()>0)
        self.stop.setToolTip('Chỉ dừng worker do cửa sổ này tạo; worker đang theo dõi không thuộc GUI.' if self.external_running else '')
        self.stop_tb.setEnabled(self.tb is not None);self.open_tb.setEnabled(not self.closing)
    def start_tensorboard(self):
        if self.closing:return
        if self.tb:
            if self.tb_url:G.QDesktopServices.openUrl(C.QUrl(self.tb_url))
            return
        logdir=(self.current_directory/'tensorboard' if self.current_directory and (self.current_directory/'tensorboard').is_dir() else self.root())
        logdir.mkdir(parents=True,exist_ok=True)
        p=C.QProcess(self);self.tb=p;self.tb_url=None;self.tb_buffer='';p.setProcessChannelMode(C.QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self.read_tensorboard);p.finished.connect(self.tensorboard_closed)
        p.errorOccurred.connect(lambda e:self.tensorboard_error(p))
        p.start('/usr/bin/setsid',[str(repository()/'.venv/bin/python'),'-m','tensorboard.main','--logdir',str(logdir),
            '--host','127.0.0.1','--port','0','--load_fast','false'])
        self.tb_status.setText('Đang mở TensorBoard local…');self.refresh()
        C.QTimer.singleShot(45000,lambda:self.tensorboard_timeout(p))
    def read_tensorboard(self):
        if not self.tb:return
        self.tb_buffer+=bytes(self.tb.readAllStandardOutput()).decode('utf8','replace')
        found=re.search(r'http://127\.0\.0\.1:\d+',self.tb_buffer)
        if found and not self.tb_url:
            self.tb_url=found.group();self.tb_status.setText(f'TensorBoard: <a href="{self.tb_url}">{self.tb_url}</a> · localhost')
            G.QDesktopServices.openUrl(C.QUrl(self.tb_url))
    def tensorboard_timeout(self,process):
        if self.tb is process and not self.tb_url:self.tb_status.setText('TensorBoard chưa sẵn sàng sau45s: '+self.tb_buffer[-1000:]);self.stop_tensorboard()
    def tensorboard_error(self,process):
        self.tb_status.setText('TensorBoard lỗi: '+process.errorString())
        if self.tb is process and process.state()==C.QProcess.NotRunning:
            self.tb=None;self.tb_url=None;process.deleteLater();self.refresh();self.maybe_closed()
    def stop_tensorboard(self):
        if self.tb and self.tb.processId():
            try:os.killpg(int(self.tb.processId()),signal.SIGTERM)
            except ProcessLookupError:pass
    def tensorboard_closed(self,code=0,status=None):
        if not self.tb:return
        self.read_tensorboard();p=self.tb;self.tb=None;self.tb_url=None;p.deleteLater()
        self.tb_status.setText('TensorBoard đã đóng.' if code in (0,15) or self.closing else f'TensorBoard dừng (exit {code}): '+self.tb_buffer[-1200:])
        self.refresh();self.maybe_closed()
    def job_closed(self):self.changed.emit();self.refresh();self.maybe_closed()
    def request_close(self):
        self.closing=True;self.watch_closed=True;self.live_timer.stop()
        self.dashboard.shutdown()
        self.runner.cancel();self.stop_tensorboard();self.refresh();self.maybe_closed()
    def maybe_closed(self):
        if self.closing and not self.active:self.all_closed.emit()


def main(argv=None):
    import argparse
    from .mode_gui import main as studio_main
    parser=argparse.ArgumentParser(description='Open the training tab in Nino Studio')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--demo',action='store_true')
    args=parser.parse_args(argv);forward=['--train']
    if args.output:forward+=['--training-output',str(args.output)]
    if args.demo:forward.append('--demo')
    return studio_main(forward)

if __name__=='__main__':raise SystemExit(main())
