"""Native Qt build/progress panel with actual artifact-backed job controls."""
import json
import hashlib
from pathlib import Path
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as Q
from .research_jobs import JOBS,ResearchRunner,repository,workflow_state,guided_td3_consumed,joint_reliability_fixture_ready,coverage_release_ready,drive_readiness_release_ready,ready_eval_release_ready,gain_baseline_release_ready
from .next_steps_panel import NextStepsPanel
from .td3_parameter_panel import TD3ParameterPanel
from .td3_training_panel import TD3TrainingPanel
from .sim_benchmark_panel import SimBenchmarkPanel


class ResearchPanel(Q.QWidget):
    collectionRequested=C.pyqtSignal(str)
    all_closed=C.pyqtSignal()
    def __init__(self,parent=None,root=None,hardware_busy=None,embed_training=True,training_root=None,training_blocked=None,observe_training=True):
        super().__init__(parent);self.hardware_busy=hardware_busy or (lambda:False);self.closing=False;self.external_busy=False
        setting=C.QSettings('Nino','ControlModes')
        self.root=Path(root or setting.value('research_root_gain_baselines',str(Path.home()/'nino_research/sim_gain_baselines_v1')))
        self.runner=ResearchRunner(self.root,self);self.runner.update.connect(self.handle)
        self.runner.closed.connect(self.job_closed)
        root_layout=Q.QVBoxLayout(self)
        self.sections=Q.QTabWidget();root_layout.addWidget(self.sections)
        def section(widget,title):
            scroll=Q.QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(Q.QFrame.NoFrame)
            scroll.setWidget(widget);self.sections.addTab(scroll,title)
            return scroll
        self.roadmap=NextStepsPanel();self.roadmap.collectionRequested.connect(self.collectionRequested.emit)
        section(self.roadmap,'Việc cần làm · robot / dữ liệu / nghiên cứu')
        software=Q.QWidget();section(software,'Công cụ kiểm phần mềm · History / TD3 / PPO')
        self.parameters=TD3ParameterPanel();self.parameter_tab=section(self.parameters,'TD3 · tham số có phiên bản')
        sim=Q.QWidget();section(sim,'NHÁNH SIM · không chờ dữ liệu thật')
        sim_layout=Q.QVBoxLayout(sim)
        sim_title=Q.QLabel('SIM · tracking → dừng → đánh giá');sim_title.setStyleSheet('font-size:21px;font-weight:700');sim_layout.addWidget(sim_title)
        self.sim_version=Q.QComboBox();self.sim_version.addItems(['V2 · task/reward/stop · 512 bước','V1 · lịch sử progress · 256 bước','Kiểm bias sàn sạch + reference offline','V3 · estimator + follower trong Gazebo · residual zero','Tiếp xúc · guided clear/gờ 6 mm · residual zero','TD3 V3 · guided baseline + zero-init · pilot 512','Ablation · frozen full / common-only / B0 · clear','Common cổ điển · planned stop / B0 / frozen common','Chuyển lịch dừng · stop6s / withdraw5,5s / B0','Contract cùng preview · TD3/cổ điển · chỉ offline','Qualification103D/1D · Gazebo · 4 lượt','TD3 common103D/1D · 3seed ×1024 +10eval','Joint boundary · hai observer · 2lượt zero-only','Joint RELIABLE · fixture rồi B0 qualification','TD3 RELIABLE · fresh learner / epoch riêng','Eval-only · ba checkpoint TD3 đã có / B0 / cổ điển','Critic/coverage V1 · đã đóng do lỗi metadata','Coverage V2 · metadata correction / preflight / study riêng','Reset drive readiness · ACK + quiet · zero-only','Eval-only A seed11 · B0/cổ điển · reset ACK chung','Gain baseline · B0/fixed/causal · 9lượt · không train'])
        self.sim_version.setCurrentIndex(20 if self.root.name=='sim_gain_baselines_v1' else 19 if self.root.name=='sim_ready_eval_only_v1' else 18 if self.root.name=='sim_drive_readiness_v1' else 17 if self.root.name=='sim_coverage_study_v2' else 16 if self.root.name=='sim_coverage_study_v1' else 15 if self.root.name=='sim_reliable_eval_only_v1' else 14 if self.root.name=='sim_reliable_td3_v1' else 13 if self.root.name=='sim_joint_reliability_v1' else 12 if self.root.name=='sim_joint_boundary_v1' else 11 if self.root.name=='sim_common_td3_v1' else 10 if self.root.name=='sim_equal_gazebo_v1' else 9 if self.root.name=='sim_equal_information_v1' else 8 if self.root.name=='sim_stop_transfer_v1' else 7 if self.root.name=='sim_classical_common_v1' else 6 if self.root.name=='sim_axis_ablation_v1' else 5 if self.root.name=='sim_guided_td3_v3' else 4 if self.root.name=='sim_guided_contact_v1' else 3 if self.root.name=='sim_guided_baseline_v3' else 2 if self.root.name=='sim_clear_bias_v1' else 1 if self.root.name=='sim_branch_pilot_v1' else 0)
        self.sim_version.currentIndexChanged.connect(self.change_sim_version);sim_layout.addWidget(self.sim_version)
        self.sim_note=Q.QLabel();self.sim_note.setWordWrap(True);sim_layout.addWidget(self.sim_note)
        self.sim_buttons={};self.sim_status={};self.sim_rows={}
        sim_titles={'sim-baselines':'1 · Kiểm B0 trên ba môi trường','sim-train':'2 · Train TD3 h5 · tối đa 256 bước','sim-evaluate':'3 · So B0 / B1 yaw / TD3 h5'}
        sim_titles.update({'sim-v2-baselines':'1 · B0 đi + dừng · 2 lượt/môi trường','sim-v2-train':'2 · Train TD3 h5 · tối đa 512 bước','sim-v2-evaluate':'3 · So tracking / dừng · 2 lượt/arm'})
        sim_titles.update({'sim-bias-clear':'1 · Kiểm B0 / checkpoint V2 đóng băng · sàn sạch','sim-guidance-contract':'2 · Kiểm reference follower → residual · chỉ offline'})
        sim_titles.update({'sim-v3-baselines':'V3 · Chạy 8 lượt baseline clear floor · không actor/optimizer'})
        sim_titles.update({'sim-guided-contact':'Guided clear/gờ 6 mm · tối đa 4 lượt · residual zero'})
        sim_titles.update({'sim-v3-contract':'1 · Kiểm contract / actor zero-init offline','sim-v3-train':'2 · Train TD3 V3 h5 · tối đa 512 transition','sim-v3-evaluate':'3 · So guided B0 / TD3 V3 · 8 lượt clear/gờ'})
        sim_titles.update({'sim-axis-ablation':'Ablation B0 / TD3 full / common-only · tối đa 6 lượt clear'})
        sim_titles.update({'sim-classical-common':'B0 / common cổ điển / TD3 common-only · tối đa 6 lượt clear'})
        sim_titles.update({'sim-stop-transfer':'B0 / common cổ điển · source stop6s · tối đa 6 lượt mới'})
        sim_titles.update({'sim-equal-contract':'Kiểm contract103D/1D · fixture/replay/save-load · không train'})
        sim_titles.update({'sim-equal-gazebo':'Kiểm wrapper103D/1D trong Gazebo · tối đa4 lượt/560ticks'})
        sim_titles.update({'sim-gain-baselines':'Gain baseline · 9fresh launches/1260ticks · không actor/train'})
        sim_titles.update({'sim-ready-eval-only':'Đánh giá A seed11 / B0 / cổ điển · 6lượt /840ticks · không train'})
        sim_titles.update({'sim-drive-readiness':'Kiểm reset drive ACK + quiet · 2launch /20zero ticks · không actor'})
        sim_titles.update({'sim-coverage-v2-preflight':'1 · V2 kiểm đường train / terminal / reset6–8 / replay offline','sim-coverage-v2-study':'2 · V2 study 2 arm × 3 seed +16 eval · cần release riêng'})
        sim_titles.update({'sim-coverage-preflight':'1 · Kiểm coverage offline · sampler / replay / checkpoint','sim-coverage-study':'2 · Study 2 arm × 3 seed + 16 eval · cần release riêng'})
        sim_titles.update({'sim-reliable-eval-only':'Đánh giá B0 / cổ điển / 3 TD3 · tối đa 10 lượt · không train'})
        sim_titles.update({'sim-reliable-td3':'Train TD3 RELIABLE · 3 seed × 1024 rồi 10 eval · một budget'})
        sim_titles.update({'sim-common-td3':'Train TD3 common103D/1D · 3seed ×1024 rồi10eval · một budget'})
        sim_titles.update({'sim-joint-boundary':'Chẩn đoán joint primary/independent · tối đa2lượt zero-only'})
        sim_titles.update({'sim-joint-reliability-fixture':'1 · So ROS RELIABLE/BEST_EFFORT · 1000messages +pause100ms','sim-joint-reliability-gazebo':'2 · Candidate RELIABLE · B0 stop6/8 · tối đa2launches'})
        for action in sim_titles:
            container=Q.QWidget();column=Q.QVBoxLayout(container);column.setContentsMargins(0,0,0,0)
            row=Q.QHBoxLayout();button=Q.QPushButton(sim_titles[action]);button.setObjectName('primary')
            button.clicked.connect(lambda checked=False,a=action:self.run(a));row.addWidget(button,1);self.sim_buttons[action]=button
            view=Q.QPushButton('Xem kết quả');view.clicked.connect(lambda checked=False,a=action:self.show_sim_result(a));row.addWidget(view)
            column.addLayout(row)
            status=Q.QLabel();status.setWordWrap(True);column.addWidget(status);self.sim_status[action]=status
            sim_layout.addWidget(container);self.sim_rows[action]=container
        self.sim_progress=Q.QProgressBar();sim_layout.addWidget(self.sim_progress)
        self.sim_stop=Q.QPushButton('Hủy job sim local · giữ artifact');self.sim_stop.clicked.connect(self.runner.cancel);sim_layout.addWidget(self.sim_stop)
        self.sim_location=Q.QLabel();self.sim_location.setWordWrap(True);sim_layout.addWidget(self.sim_location)
        self.sim_next=Q.QLabel('Điểm dừng: baseline không có body response → sửa backend; gờ 6 mm chưa vượt được → chỉ train sàn sạch.\n'
            'Mixed 22 mm là diagnostic, không mặc định thuộc envelope vượt. Dữ liệu real phục vụ calibration/sim-to-real ở nhánh song song.')
        self.sim_next.setWordWrap(True);sim_layout.addWidget(self.sim_next)
        self.sim_benchmark_link=Q.QPushButton('Bước kế tiếp · Xem quyết định benchmark và các gate')
        self.sim_benchmark_link.clicked.connect(lambda:self.sections.setCurrentWidget(self.benchmark_tab))
        sim_layout.addWidget(self.sim_benchmark_link)
        self.sim_table=Q.QTableWidget(0,5);self.sim_table.setHorizontalHeaderLabels(['Arm','Body x cuối (m)','RMSE ngang (mm)','v cuối (m/s)','Mốc 0,95 m (s)'])
        self.sim_table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.sim_table.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Stretch);self.sim_table.setMaximumHeight(145)
        sim_layout.addWidget(self.sim_table)
        self.sim_guidance_status=Q.QLabel();self.sim_guidance_status.setWordWrap(True);sim_layout.addWidget(self.sim_guidance_status)
        self.sim_log=Q.QPlainTextEdit();self.sim_log.setReadOnly(True);self.sim_log.document().setMaximumBlockCount(300)
        sim_layout.addWidget(self.sim_log,1)
        self.sections.setCurrentIndex(3)
        layout=Q.QVBoxLayout(software)
        title=Q.QLabel('XÂY DỰNG PROJECT · bằng chứng theo từng gate');title.setStyleSheet('font-size:21px;font-weight:700');layout.addWidget(title)
        note=Q.QLabel('Các nút chạy trên laptop, không nối Pi. TD3/PPO fixture giảm bậc và TD3 FACTORY là các job riêng.\nFACTORY dùng factory_floor_mixed + mô hình Nino + wheel PI: 48 bước kiểm, 128 bước học; chưa chứng minh hiệu quả trên robot.');note.setWordWrap(True);layout.addWidget(note)
        row=Q.QHBoxLayout();self.location=Q.QLineEdit(str(self.root));self.location.setReadOnly(True);row.addWidget(self.location,1)
        choose=Q.QPushButton('Thư mục kết quả');choose.clicked.connect(self.choose_root);row.addWidget(choose)
        self.reload_button=Q.QPushButton('Đọc lại bằng chứng');self.reload_button.clicked.connect(self.reload);row.addWidget(self.reload_button);layout.addLayout(row)
        self.scene=Q.QGraphicsScene(self);self.diagram=Q.QGraphicsView(self.scene);self.diagram.setMinimumHeight(255);self.diagram.setMaximumHeight(310)
        self.diagram.setRenderHint(G.QPainter.Antialiasing);layout.addWidget(self.diagram)
        self.buttons={};grid=Q.QGridLayout()
        for i,(action,(label,deps)) in enumerate(JOBS.items()):
            b=Q.QPushButton(label);b.setToolTip('Phụ thuộc: '+(', '.join(deps) or 'không')+' · lưu toàn bộ lần lỗi/hủy');b.clicked.connect(lambda checked=False,a=action:self.run(a));grid.addWidget(b,i//2,i%2);self.buttons[action]=b
            if action=='factory-td3':
                b.setObjectName('primary');b.setToolTip('Gazebo factory mixed + Nino/caster + wheel PI. 48 bước kiểm rồi 128 bước học mới. Nạp mesh có thể lâu; xem log. Chỉ localhost, không nối Pi.')
        register=Q.QPushButton('Đăng ký dữ liệu SysID · CSV + metadata');register.clicked.connect(self.register);grid.addWidget(register,(len(JOBS)+1)//2,0,1,2);self.register_button=register
        layout.addLayout(grid)
        controls=Q.QHBoxLayout();self.stop=Q.QPushButton('Hủy job local');self.stop.clicked.connect(self.runner.cancel);controls.addWidget(self.stop)
        open_result=Q.QPushButton('Mở thư mục artifact');open_result.clicked.connect(lambda:G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(self.root))));controls.addWidget(open_result)
        real=Q.QPushButton('Bước dữ liệu thật → phiên diagnostic');real.clicked.connect(lambda:self.collectionRequested.emit('diagnostic'));controls.addWidget(real);layout.addLayout(controls)
        self.progress=Q.QProgressBar();layout.addWidget(self.progress)
        self.next=Q.QLabel();self.next.setWordWrap(True);self.next.setStyleSheet('color:#72ded0;font-weight:600');layout.addWidget(self.next)
        output=Q.QTabWidget()
        self.job_table=Q.QTableWidget(len(JOBS),3);self.job_table.setHorizontalHeaderLabels(['Bước','Bằng chứng','Artifact'])
        self.job_table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers);self.job_table.setSelectionBehavior(Q.QAbstractItemView.SelectRows)
        self.job_table.horizontalHeader().setSectionResizeMode(0,Q.QHeaderView.ResizeToContents)
        self.job_table.horizontalHeader().setSectionResizeMode(1,Q.QHeaderView.ResizeToContents)
        self.job_table.horizontalHeader().setSectionResizeMode(2,Q.QHeaderView.Stretch)
        self.job_table.cellClicked.connect(self.show_result)
        output.addTab(self.job_table,'Kết quả / to-do')
        self.results=Q.QPlainTextEdit();self.results.setReadOnly(True);output.addTab(self.results,'Thông số / kết quả chi tiết')
        self.log=Q.QPlainTextEdit();self.log.setReadOnly(True);self.log.document().setMaximumBlockCount(300);output.addTab(self.log,'Quá trình chạy')
        output.setMinimumHeight(170);layout.addWidget(output,1);self.output_tabs=output
        self.reload()
        self.trainer=TD3TrainingPanel(self,root=training_root,observe_external=observe_training and (training_root is not None or root is None),
            blocked=lambda:self.runner.busy or self.hardware_busy() or self.external_busy or self.closing or bool(training_blocked and training_blocked()))
        self.trainer.changed.connect(self.refresh);self.trainer.all_closed.connect(self.job_closed)
        if embed_training:section(self.trainer,'TRAIN TD3 · Smoke / timesteps / checkpoint / TensorBoard')
        self.benchmark=SimBenchmarkPanel(load_on_init=False)
        section(self.benchmark,'SIM · Quyết định benchmark / gate kế tiếp')
        self.benchmark_tab=self.sections.widget(self.sections.count()-1)
        self.benchmark_load_started=False
        self.sections.currentChanged.connect(self.open_benchmark)
    def open_benchmark(self,index):
        if self.sections.widget(index) is self.benchmark_tab and not self.benchmark_load_started:
            self.benchmark_load_started=True
            self.benchmark.status.setText('Đang kiểm hồ sơ benchmark; chưa xác minh kết quả trong lần mở này.')
            C.QTimer.singleShot(0,self.benchmark.reload)
    @property
    def busy(self):return self.runner.busy or (hasattr(self,'trainer') and self.trainer.busy)
    @property
    def active(self):return self.runner.busy or (hasattr(self,'trainer') and self.trainer.active)
    def active_sim_actions(self):
        if self.sim_version.currentIndex()==20:return ('sim-gain-baselines',)
        if self.sim_version.currentIndex()==19:return ('sim-ready-eval-only',)
        if self.sim_version.currentIndex()==18:return ('sim-drive-readiness',)
        if self.sim_version.currentIndex()==17:return ('sim-coverage-v2-preflight','sim-coverage-v2-study')
        if self.sim_version.currentIndex()==16:return ('sim-coverage-preflight','sim-coverage-study')
        if self.sim_version.currentIndex()==15:return ('sim-reliable-eval-only',)
        if self.sim_version.currentIndex()==14:return ('sim-reliable-td3',)
        if self.sim_version.currentIndex()==13:return ('sim-joint-reliability-fixture','sim-joint-reliability-gazebo')
        if self.sim_version.currentIndex()==12:return ('sim-joint-boundary',)
        if self.sim_version.currentIndex()==11:return ('sim-common-td3',)
        if self.sim_version.currentIndex()==10:return ('sim-equal-gazebo',)
        if self.sim_version.currentIndex()==9:return ('sim-equal-contract',)
        if self.sim_version.currentIndex()==8:return ('sim-stop-transfer',)
        if self.sim_version.currentIndex()==7:return ('sim-classical-common',)
        if self.sim_version.currentIndex()==6:return ('sim-axis-ablation',)
        if self.sim_version.currentIndex()==5:return ('sim-v3-contract','sim-v3-train','sim-v3-evaluate')
        if self.sim_version.currentIndex()==4:return ('sim-guided-contact',)
        if self.sim_version.currentIndex()==3:return ('sim-v3-baselines',)
        if self.sim_version.currentIndex()==2:return ('sim-bias-clear','sim-guidance-contract')
        return ('sim-v2-baselines','sim-v2-train','sim-v2-evaluate') if self.sim_version.currentIndex()==0 else ('sim-baselines','sim-train','sim-evaluate')
    def change_sim_version(self,index):
        if self.runner.busy:return
        settings=C.QSettings('Nino','ControlModes')
        key={0:'research_root_v2',1:'research_root',2:'research_root_bias',3:'research_root_v3',4:'research_root_contact',5:'research_root_td3_v3',6:'research_root_axis',7:'research_root_classical',8:'research_root_transfer',9:'research_root_equal',10:'research_root_equal_gazebo',11:'research_root_common_td3',12:'research_root_joint_boundary',13:'research_root_joint_reliability',14:'research_root_reliable_td3',15:'research_root_reliable_eval',16:'research_root_coverage',17:'research_root_coverage_v2',18:'research_root_drive_readiness',19:'research_root_ready_eval',20:'research_root_gain_baselines'}[index]
        fallback=Path.home()/'nino_research'/{0:'sim_task_v2',1:'sim_branch_pilot_v1',2:'sim_clear_bias_v1',3:'sim_guided_baseline_v3',4:'sim_guided_contact_v1',5:'sim_guided_td3_v3',6:'sim_axis_ablation_v1',7:'sim_classical_common_v1',8:'sim_stop_transfer_v1',9:'sim_equal_information_v1',10:'sim_equal_gazebo_v1',11:'sim_common_td3_v1',12:'sim_joint_boundary_v1',13:'sim_joint_reliability_v1',14:'sim_reliable_td3_v1',15:'sim_reliable_eval_only_v1',16:'sim_coverage_study_v1',17:'sim_coverage_study_v2',18:'sim_drive_readiness_v1',19:'sim_ready_eval_only_v1',20:'sim_gain_baselines_v1'}[index]
        self.root=Path(settings.value(key,str(fallback)));self.runner.root=self.root
        self.location.setText(str(self.root));self.reload()
    def choose_root(self):
        if self.runner.busy:return
        path=Q.QFileDialog.getExistingDirectory(self,'Chọn thư mục workflow',str(self.root))
        if path:
            self.root=Path(path);self.runner.root=self.root;self.location.setText(path)
            key={0:'research_root_v2',1:'research_root',2:'research_root_bias',3:'research_root_v3',4:'research_root_contact',5:'research_root_td3_v3',6:'research_root_axis',7:'research_root_classical',8:'research_root_transfer',9:'research_root_equal',10:'research_root_equal_gazebo',11:'research_root_common_td3',12:'research_root_joint_boundary',13:'research_root_joint_reliability',14:'research_root_reliable_td3',15:'research_root_reliable_eval',16:'research_root_coverage',17:'research_root_coverage_v2',18:'research_root_drive_readiness',19:'research_root_ready_eval',20:'research_root_gain_baselines'}[self.sim_version.currentIndex()]
            C.QSettings('Nino','ControlModes').setValue(key,path);self.reload()
    def reload(self):
        self.roadmap.reload()
        try:self.states=workflow_state(self.root);self.error=None
        except (ImportError,OSError,ValueError) as exc:self.states={};self.error=str(exc)
        self.draw_diagram();self.refresh()
        for i,action in enumerate(JOBS):
            state=self.states.get(action,{})
            for col,value in enumerate((JOBS[action][0],state.get('label','CHƯA KIỂM'),state.get('path') or state.get('error','Chưa có dữ liệu'))):
                item=Q.QTableWidgetItem(value);item.setToolTip(value);self.job_table.setItem(i,col,item)
        if self.error:self.next.setText('Chưa đọc được research toolchain: '+self.error);return
        actions=self.active_sim_actions()
        todo=next((a for a in actions if self.states[a]['state']!='verified'),None)
        if not self.runner.busy:
            self.sim_progress.setRange(0,100);self.sim_progress.setFormat('%p%')
            self.sim_progress.setValue(round(100*sum(self.states[a]['state']=='verified' for a in actions)/len(actions)))
        self.next.setText('Nhánh sim: bấm '+JOBS[todo][0] if todo else 'Pilot sim đã có artifact. Review bảng baseline/TD3 trước khi mở train dài; dữ liệu real phục vụ calibration song song.')
        self.sim_next.setText('Bước tiếp: '+JOBS[todo][0]+' → đợi manifest và xem kết quả trước bước kế.' if todo else 'Đã có artifact ba stage; review task/tracking/dừng. Chưa mở train dài hoặc hardware.')
        self.sim_table.setRowCount(0)
        self.sim_guidance_status.clear()
        current=self.states.get('sim-bias-clear' if actions[0]=='sim-bias-clear' else actions[-1],{})
        if actions[0]=='sim-gain-baselines':
            self.show_gain_baseline_table(current)
            return
        if actions[0]=='sim-ready-eval-only':
            self.show_ready_eval_table(current)
            return
        if actions[0]=='sim-drive-readiness':
            self.show_drive_readiness_table(current)
            return
        if actions[0] in ('sim-coverage-preflight','sim-coverage-v2-preflight'):
            self.show_coverage_table()
            return
        if actions[0]=='sim-reliable-eval-only':
            self.show_eval_only_table(current)
            return
        if actions[0]=='sim-reliable-td3':
            self.show_reliable_td3_table(current)
            return
        if actions[0]=='sim-joint-reliability-fixture':
            self.show_joint_reliability_table()
            return
        if actions[0]=='sim-joint-boundary':
            if current.get('state')=='verified':
                try:self.show_joint_boundary_table(json.loads((Path(current['path'])/'diagnostic_result.json').read_text()))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được joint diagnostic: '+str(exc))
            else:self.sim_next.setText('Budget diagnostic đã tiêu thụ; giữ artifact, không retry.' if guided_td3_consumed(self.root,actions[0]) else 'Hai observer ROS độc lập, endpoint gate40ms; tối đa2fresh launches ×100ticks zero. Không actor/train/hardware, một lỗi đóng slot còn lại.')
            return
        if actions[0]=='sim-common-td3':
            if current.get('state')=='verified':
                try:self.show_common_td3_table(json.loads((Path(current['path'])/'pilot_result.json').read_text()))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được common TD3: '+str(exc))
            elif current.get('state')=='retained_failure':
                try:self.show_common_td3_failure(json.loads((self.root/'review.json').read_text()))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được partial review: '+str(exc))
            else:self.sim_next.setText('Budget đã tiêu thụ; đọc artifact/lỗi, không retry.' if guided_td3_consumed(self.root,actions[0]) else 'Bấm Train: fresh103D/1D · 3seed11/22/33 ×1024, rồi10eval B0/cổ điển/TD3. Giữ terminal partial, không resume V3/Studio.')
            return
        if actions[0]=='sim-equal-gazebo':
            if current.get('state')=='verified':
                try:self.show_equal_gazebo_table(json.loads((Path(current['path'])/'qualification_result.json').read_text()))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được qualification Gazebo: '+str(exc))
            else:self.sim_next.setText('Đợt đã tiêu thụ; giữ artifact và đóng slot chưa chạy.' if guided_td3_consumed(self.root,actions[0]) else 'B0/cổ điển/probe stop6s và probe stop8s · tối đa4launches/560ticks; không actor/optimizer.')
            return
        if actions[0]=='sim-equal-contract':
            if current.get('state')=='verified':
                try:self.show_equal_information_table(json.loads((Path(current['path'])/'qualification.json').read_text()))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được contract: '+str(exc))
            else:self.sim_next.setText('Đợt offline đã tiêu thụ; xem artifact, không retry.' if guided_td3_consumed(self.root,actions[0]) else 'Chỉ kiểm103D/1D, shared preview/window, replay và model chưa train. Optimizer/physics/hardware0.')
            return
        if actions[0]=='sim-stop-transfer':
            if current.get('state')=='verified':
                try:self.show_stop_transfer_table(json.loads((Path(current['path'])/'evaluation_result.json').read_text()))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được transfer: '+str(exc))
            else:self.sim_next.setText('Đợt đã tiêu thụ; giữ artifact và đóng slot còn lại.' if guided_td3_consumed(self.root,actions[0]) else 'Tối đa6 lượt mới: stop6s / withdraw5,5s; native100ms + GT-header20ms/+10ms. Không train.')
            return
        if actions[0]=='sim-classical-common':
            if current.get('state')=='verified':
                try:self.show_classical_common_table(json.loads((Path(current['path'])/'evaluation_result.json').read_text()))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được common cổ điển: '+str(exc))
            else:self.sim_next.setText('Ledger đã giữ/đóng budget; xem trạng thái và artifact, không chạy lại.' if guided_td3_consumed(self.root,actions[0]) else 'Tối đa6 lượt clear: B0 / common +0,005 m/s rút7,5s / frozen TD3 common; optimizer0.')
            return
        if actions[0]=='sim-axis-ablation':
            if current.get('state')=='verified':
                try:self.show_axis_ablation_table(json.loads((Path(current['path'])/'evaluation_result.json').read_text()),Path(current['path']))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được ablation: '+str(exc))
            else:self.sim_next.setText('Đợt đã tiêu thụ hoặc lỗi: giữ artifact, không tự chạy lại.' if guided_td3_consumed(self.root,actions[0]) else 'Kiểm checkpoint frozen rồi chạy đúng 6 lượt clear; không optimizer, giữ raw/masked proposal riêng.')
            return
        if actions[0]=='sim-v3-contract':
            self.show_guided_learning_status()
            return
        if actions[0] in ('sim-v3-baselines','sim-guided-contact'):
            if current.get('state')=='verified':
                try:self.show_guided_baseline_table(json.loads((Path(current['path'])/'evaluation_result.json').read_text()),contact=actions[0]=='sim-guided-contact')
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được V3: '+str(exc))
            else:self.sim_next.setText('Guided clear/gờ 6 mm: tối đa 4 lượt; gate fail đóng slot còn lại. Không actor/optimizer.' if actions[0]=='sim-guided-contact' else 'V3: kiểm B0 constant / guided, path bearing ±5°, 2 lượt/điều kiện. Không train; giữ các batch cũ.')
            return
        if current.get('state')=='verified':
            try:
                evaluation=json.loads((Path(current['path'])/'evaluation_result.json').read_text())
                v2=actions[-1].startswith('sim-v2-') or actions[0]=='sim-bias-clear'
                metrics=[(arm+'/'+str(i+1),m) for arm,runs in evaluation['arms'].items() for i,m in enumerate(runs)] if v2 else list(evaluation['arms'].items())
                self.sim_table.setColumnCount(8 if v2 else 5)
                self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','x cuối (m)','RMSE ngang (mm)','v cuối (m/s)','Mốc (s)']+(['RMSE chuẩn (m/s)','Dừng 2 s','Task'] if v2 else []))
                if actions[0]=='sim-bias-clear':self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','RMSE v (m/s)','RMSE ngang (mm)','ω ref TB (rad/s)','ω GT TB (rad/s)','y cuối (m)','Dừng 2 s','Task'])
                self.sim_table.setRowCount(len(metrics));self.sim_table.setMinimumHeight(240 if v2 else 140);self.sim_table.setMaximumHeight(280 if v2 else 180)
                for row,(arm,metric) in enumerate(metrics):
                    marker=metric['local_marker_time_s']
                    values=[arm,f"{metric['final_x_m']:.4f}",f"{metric['lateral_rmse_m']*1000:.3f}",
                            f"{metric['final_body_speed_m_s']:.5f}",'chưa tới' if marker is None else f'{marker:.2f}']
                    if v2:values += [f"{metric['nominal_shaped_tracking_rmse_m_s']:.5f}",'ĐẠT' if metric['stop_completed'] else 'CHƯA ĐẠT','ĐẠT' if metric['task_success'] else 'KHÔNG ĐẠT']
                    if actions[0]=='sim-bias-clear':values=[arm,f"{metric['nominal_shaped_tracking_rmse_m_s']:.5f}",f"{metric['lateral_rmse_m']*1000:.3f}",
                        f"{metric['mean_accepted_yaw_rad_s']:.5f}",f"{metric['mean_gt_yaw_rate_rad_s']:.5f}",f"{metric['final_y_m']:.4f}",
                        'ĐẠT' if metric['stop_completed'] else 'CHƯA ĐẠT','ĐẠT' if metric['task_success'] else 'KHÔNG ĐẠT']
                    for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
                self.sim_next.setText(('V2 · hai fresh launches/arm; một learner seed. Dừng đạt và task đạt là hai điều kiện riêng.\n' if v2 else 'PILOT ĐÃ CHẠY · mỗi arm một fresh launch, một learner seed. Return/progress cao hơn chưa là benefit.\n')+
                    'Xem cả lệch ngang và vận tốc cuối: dừng nguồn không đồng nghĩa thân đã dừng tại horizon. Chưa promote checkpoint.')
                if v2:
                    b0=evaluation['arms']['B0'];td3=evaluation['arms']['TD3_h5']
                    worse=all(min(r[key] for r in td3)>max(r[key] for r in b0) for key in ('nominal_shaped_tracking_rmse_m_s','lateral_rmse_m'))
                    self.sim_next.setText('V2 · '+('Hai lượt TD3 đều có RMSE vận tốc và lệch ngang lớn hơn từng lượt B0. Chưa tăng ngân sách train.' if worse else 'Review từng lượt: pilot nhỏ chưa đủ xác nhận benefit.')+
                        '\nTask/dừng đạt chỉ là feasibility, chưa là chất lượng tốt. Một learner seed; chưa promote. Bước tiếp: baseline/follower và phân tích bias residual trước tiếp xúc.')
                if actions[0]=='sim-bias-clear':
                    bias=evaluation.get('clear_floor_reference_bias_observed')
                    self.sim_next.setText(('SÀN SẠCH · bias yaw vẫn xuất hiện ở cả hai lượt TD3. Gờ không giải thích toàn bộ lệch hướng.' if bias else 'SÀN SẠCH · chưa thấy bias nhất quán; review từng lượt.')+
                        '\nCheckpoint không sửa, không train thêm. Reference follower mới chỉ đạt offline, chưa nối Gazebo/robot.'+
                        ('\nBước tiếp: protocol V3 cho baseline có guidance và velocity-tracking objective.' if self.states.get('sim-guidance-contract',{}).get('state')=='verified' else '\nBước tiếp: bấm 2 để kiểm adapter reference offline.'))
                    guide=self.states.get('sim-guidance-contract',{})
                    if guide.get('state')=='verified':
                        data=json.loads((Path(guide['path'])/'guidance_result.json').read_text())
                        self.sim_guidance_status.setText(f"REFERENCE OFFLINE · {data['fixture_count']}/{data['fixture_count']} fixture đạt · observation {data['observation_size']}D, thêm 0 pose feature. Chưa nối guidance vào Gazebo/robot; localization chưa được xác minh.")
            except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được bảng pilot: '+str(exc))
    def show_guided_baseline_table(self,evaluation,contact=False):
        runs=evaluation['runs'];self.sim_table.setColumnCount(9)
        self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','Tuyến (°)','RMSE path (mm)','Max path (mm)','Max est pos (mm)','Max est yaw (rad)','Dừng 2 s','Marker + stop','Gate đề xuất'])
        self.sim_table.setRowCount(len(runs));self.sim_table.setMinimumHeight(310);self.sim_table.setMaximumHeight(360)
        if contact:self.sim_table.setHorizontalHeaderLabels(['World/lượt','Tuyến (°)','RMSE path (mm)','Max path (mm)','Max est pos (mm)','Max est yaw (rad)','Dừng 2 s','Marker + stop','Gate đề xuất'])
        for row,metric in enumerate(runs):
            c=metric['condition'];values=[c['arm']+'/'+str(c['repeat']+1),f"{c['path_bearing_deg']:+.0f}",
                f"{metric['cross_track_rmse_m']*1000:.2f}",f"{metric['maximum_cross_track_m']*1000:.2f}",
                f"{metric['maximum_estimator_position_error_m']*1000:.2f}",f"{metric['maximum_estimator_yaw_error_rad']:.5f}",
                'ĐẠT' if metric['stop_completed'] else 'CHƯA','ĐẠT' if metric['task_success'] else 'CHƯA',
                'CANDIDATE' if metric['functional_proposal_pass'] else 'CHƯA ĐẠT']
            for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
            if contact:self.sim_table.setItem(row,0,Q.QTableWidgetItem(('clear' if c['scenario']=='clear_box' else 'gờ 6 mm')+'/'+str(c['repeat']+1)))
        passed=evaluation['baseline_functional_candidate']
        self.sim_next.setText(('V3 baseline đạt gate đề xuất trong batch này; chưa là chứng nhận chất lượng nhà máy.' if passed else 'V3 chưa qua gate đề xuất; review drift/reference/stop trước learning.')+
            '\n8 lượt này: residual zero, không actor/optimizer. Marker 0,95 m không là arrival goal 3 m. Bước tiếp: kiểm baseline guided trên gờ 6 mm, rồi contract reward/zero-init TD3 V3; không resume V2 chỉ vì cùng ABI.')
        self.sim_guidance_status.setText('ĐÃ NỐI GAZEBO · wheel + gyro-Z → estimate → follower → residual zero → projection → wheel PI. GT chỉ reset/evaluator; chưa calibration hoặc triển khai robot thật.')
        if contact:
            initial_x=max(abs(r['initial_truth_pose'][0]) for r in runs)
            self.sim_next.setText(f"ĐỢT ĐÃ ĐÓNG · {evaluation['completed_runs']}/{evaluation['planned_runs']} lượt; {evaluation['closed_unused_slots']} slot đóng chưa dùng. "+
                ('Baseline guided qua gate đề xuất ở clear/gờ 6 mm.' if passed else 'Baseline chưa qua gate; review drift/tracking/stop trước learning.')+
                '\nResidual zero, không actor/optimizer. Marker không là full navigation; chưa có learned benefit. Bước tiếp: contract TD3 V3 reward/zero-init hoặc giải thích baseline failure.'+
                f'\nPose thật tick đầu có |x| tới {initial_x*1000:.2f} mm so estimate khởi tạo 0. Max estimate error gồm offset/tuổi dữ liệu; không tự căn chỉnh GT.')
    def show_guided_learning_status(self):
        details=[]
        for action,file in [('sim-v3-contract','contract_result.json'),('sim-v3-train','training_result.json')]:
            state=self.states.get(action,{})
            if state.get('state')!='verified':continue
            data=json.loads((Path(state['path'])/file).read_text())
            if action=='sim-v3-contract':details.append('CONTRACT OFFLINE ĐẠT · actor/target zero trước optimizer; critic giữ nguyên; save/load + identity đã kiểm.')
            else:details.append(f"ĐÃ TRAIN V3 · {data['transitions']} transition / {data['optimizer_updates']} critic updates / seed 7; replay {data['replay']['rows_checked']} rows + optimizer/target/save-load đã kiểm.")
        self.sim_guidance_status.setText('\n'.join(details)+'\nWheel+IMU estimate → follower → bounded residual → projection → PI. GT chỉ reset/reward/evaluator; hardware authority 0.')
        state=self.states.get('sim-v3-evaluate',{})
        if state.get('state')!='verified':
            next_action=next((a for a in self.active_sim_actions() if self.states[a]['state']!='verified'),None)
            if next_action and guided_td3_consumed(self.root,next_action):self.sim_next.setText('Stage lỗi/hủy đã đóng; đọc artifact và nguyên nhân. Không retry hoặc mở lại ngân sách cũ.')
            else:self.sim_next.setText('Bước tiếp: '+(JOBS[next_action][0] if next_action else 'review kết quả')+'. Train 512 + evaluate 8 lượt là pilot tích hợp, chưa chứng minh hội tụ hoặc benefit.')
            return
        data=json.loads((Path(state['path'])/'evaluation_result.json').read_text());runs=data['runs']
        self.sim_table.setColumnCount(10)
        self.sim_table.setHorizontalHeaderLabels(['Arm/world/lượt','RMSE v (m/s)','RMSE yaw (rad/s)','RMSE path (mm)','Max path (mm)','Max est pos (mm)','ω ref motion TB','Dừng 2 s','Marker + stop','Gate đề xuất'])
        self.sim_table.setRowCount(len(runs));self.sim_table.setMinimumHeight(310);self.sim_table.setMaximumHeight(360)
        for row,m in enumerate(runs):
            c=m['condition'];label=c['arm']+'/'+('clear' if c['scenario']=='clear_box' else '6 mm')+'/'+str(c['repeat']+1)
            values=[label,f"{m['nominal_velocity_rmse_m_s']:.5f}",f"{m['nominal_yaw_rate_rmse_rad_s']:.5f}",f"{m['cross_track_rmse_m']*1000:.2f}",f"{m['maximum_cross_track_m']*1000:.2f}",f"{m['maximum_estimator_position_error_m']*1000:.2f}",f"{m['motion_mean_accepted_yaw_rad_s']:.5f}",'ĐẠT' if m['stop_completed'] else 'CHƯA','ĐẠT' if m['task_success'] else 'CHƯA','CANDIDATE' if m['functional_proposal_pass'] else 'CHƯA ĐẠT']
            for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
        passed=sum(m['task_success'] and m['stop_completed'] for m in runs)
        worse=[]
        for scene in ('clear_box','box_c1_6mm'):
            b0=[m for m in runs if m['condition']['arm']=='B0' and m['condition']['scenario']==scene]
            td3=[m for m in runs if m['condition']['arm']=='TD3_h5' and m['condition']['scenario']==scene]
            if all(min(m[k] for m in td3)>max(m[k] for m in b0) for k in ('nominal_velocity_rmse_m_s','cross_track_rmse_m')):worse.append('clear' if scene=='clear_box' else 'gờ 6 mm')
        self.sim_next.setText(f"V3 ĐÃ TRAIN + ĐÁNH GIÁ · {len(runs)} lượt, {passed}/{len(runs)} marker + stop. "+
            ('TD3 có RMSE v/path cao hơn toàn bộ B0 ở '+', '.join(worse)+'. Giữ B0 ở các điều kiện này, phân tích bias trước train khác.' if worse else 'Review từng điều kiện với guided B0; chưa có minimum effect được chấp nhận hoặc benefit promotion.')+
            '\nMột training seed; hai fresh launches mỗi arm/world, không exact-state pair hoặc unseen bank. Không bấm lại batch đã đóng; hardware authority vẫn 0.')
        misses=[m for m in runs if m['condition']['arm']=='B0' and not m['functional_proposal_pass']]
        if misses:self.sim_next.setText(self.sim_next.text()+f'\nB0 có {len(misses)} lượt vượt gate chất lượng: giữ failure, hiệu ứng contact chưa kết luận. Không dùng riêng lượt B0 xấu để promote TD3.')
    def show_axis_ablation_table(self,data,directory):
        runs=data['runs'];self.sim_table.setColumnCount(10)
        self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','RMSE path (mm)','RMSE v (m/s)','Max path (mm)','Actor common TB','Actor diff TB','Diff sau mask TB','Δω policy TB (rad/s)','Marker + stop','Gate đề xuất'])
        self.sim_table.setRowCount(len(runs));self.sim_table.setMinimumHeight(255);self.sim_table.setMaximumHeight(310)
        for row,m in enumerate(runs):
            c=m['condition'];raw=m['actor_raw_motion_mean']
            values=[c['arm']+'/'+str(c['repeat']+1),f"{m['cross_track_rmse_m']*1000:.3f}",f"{m['nominal_velocity_rmse_m_s']:.5f}",
                f"{m['maximum_cross_track_m']*1000:.3f}",'—' if raw is None else f'{raw[0]:.5f}','—' if raw is None else f'{raw[1]:.5f}',
                f"{m['controller_motion_mean'][1]:.5f}",f"{m['policy_yaw_delta_motion_mean_rad_s']:.6f}",
                'ĐẠT' if m['task_success'] and m['stop_completed'] else 'CHƯA','CANDIDATE' if m['functional_proposal_pass'] else 'CHƯA ĐẠT']
            for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
        b0=[m for m in runs if m['condition']['arm']=='B0'];common=[m for m in runs if m['condition']['arm']=='TD3_common_only']
        slower_fit=min(m['nominal_velocity_rmse_m_s'] for m in common)>max(m['nominal_velocity_rmse_m_s'] for m in b0)
        passed=sum(m['task_success'] and m['stop_completed'] for m in runs)
        self.sim_next.setText(f"ABLATION ĐÃ ĐÓNG · {len(runs)} lượt / {data['evaluation_transitions']} transition / optimizer 0; {passed}/{len(runs)} marker + stop. "+
            ('Common-only giảm RMSE path so full ở cả hai lượt; đây là kết quả mô tả.' if data['descriptive_path_separation_common_vs_full'] else 'Chưa có phân tách RMSE path nhất quán; xem từng lượt.')+
            ('\nRMSE vận tốc common-only vẫn cao hơn cả hai B0. Giữ guided B0 trên clear; chưa có lý do promote actor hoặc train dài.' if slower_fit else '\nSo cả chi phí vận tốc với B0; chưa có minimum effect được chấp nhận hoặc benefit promotion.')+
            '\nBước tiếp: đối chứng bù common cổ điển có rút trước lịch dừng đã biết, theo protocol mới; không tăng ngân sách train. Contact vẫn unknown.')
        self.sim_guidance_status.setText('CHECKPOINT V3 ĐÓNG BĂNG · actor raw / proposal sau mask / reference sau projection được ghi riêng. Chỉ mask residual vi sai; yaw follower vẫn hoạt động. History và common output thay đổi theo feedback: không exact-state counterfactual. Không train common-only mới, không hardware.')
        phases={arm:{phase:[] for phase in ('steady','deceleration')} for arm in ('B0','TD3_common_only')}
        for m in b0+common:
            c=m['condition'];path=directory/(c['arm']+'_'+str(c['repeat']))/'trace.jsonl'
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            for phase in ('steady','deceleration'):
                if phase=='steady':selected=[r for r in rows if r['reference_trace']['original_baseline_body'][0]>0 and abs(r['task']['nominal_shaped_body'][0]-.2)<1e-9]
                else:selected=[r for r in rows if r['reference_trace']['original_baseline_body'][0]==0 and r['task']['nominal_shaped_body'][0]>1e-9]
                if selected:phases[c['arm']][phase].append((sum((r['body_speed_m_s']-r['task']['nominal_shaped_body'][0])**2 for r in selected)/len(selected))**.5)
        def interval(arm,phase):
            values=phases[arm][phase]
            return 'unknown' if not values else f'{min(values):.5f}–{max(values):.5f}'
        self.sim_guidance_status.setText(self.sim_guidance_status.text()+'\nDIAGNOSTIC SAU KẾT QUẢ · RMSE v chạy đều: B0 '+interval('B0','steady')+'; common-only '+interval('TD3_common_only','steady')+' m/s. Pha hạ: B0 '+interval('B0','deceleration')+'; common-only '+interval('TD3_common_only','deceleration')+' m/s. Không thay metric primary toàn 14 s bằng cửa sổ thuận lợi.')
    def show_classical_common_table(self,data):
        runs=data['runs'];self.sim_table.setColumnCount(10)
        self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','RMSE v (m/s)','RMSE path (mm)','Max path (mm)','Steady RMSE v','Hạ tốc RMSE v','Tick bật bù','Decision bù cuối(s)','Marker + stop','Gate đề xuất'])
        self.sim_table.setRowCount(len(runs));self.sim_table.setMinimumHeight(255);self.sim_table.setMaximumHeight(310)
        for row,m in enumerate(runs):
            c=m['condition'];end=m['compensation_last_decision_s'];phases=m['phases']
            values=[c['arm']+'/'+str(c['repeat']+1),f"{m['nominal_velocity_rmse_m_s']:.6f}",f"{m['cross_track_rmse_m']*1000:.3f}",f"{m['maximum_cross_track_m']*1000:.3f}",
                'unknown' if phases['steady'] is None else f"{phases['steady']['velocity_rmse_m_s']:.6f}",
                'unknown' if phases['deceleration'] is None else f"{phases['deceleration']['velocity_rmse_m_s']:.6f}",
                str(m['compensation_active_ticks']),'—' if end is None else f'{end:.1f}',
                'ĐẠT' if m['task_success'] and m['stop_completed'] else 'CHƯA','CANDIDATE' if m['functional_proposal_pass'] else 'CHƯA ĐẠT']
            for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
        passed=sum(m['task_success'] and m['stop_completed'] for m in runs)
        self.sim_next.setText(f"ĐỢT ĐÃ ĐÓNG · {len(runs)} lượt/{data['evaluation_transitions']} tick, {passed}/{len(runs)} marker + stop; optimizer0. "+
            ('Common cổ điển có RMSE v toàn14s thấp hơn cả B0 và frozen common ở cả hai lượt; tín hiệu mô tả.' if data['descriptive_velocity_separation'] else 'Common cổ điển chưa tách tốt hơn hai đối chứng về RMSE v toàn14s; giữ B0, xem từng lượt.')+
            '\nXem path/stop, estimate và độ nhạy timestamp riêng; chưa có minimum effect ứng dụng. Không promote TD3 hoặc suy contact benefit từ sàn sạch.'+
            ('\nBước tiếp đã có profile riêng: Chuyển lịch dừng · stop6s / withdraw5,5s / B0. Xem ledger của profile đó; không bấm lại batch này.' if data['descriptive_velocity_separation'] else '\nGiữ B0; khoanh phase/ramp trước protocol khác. Không tăng train để che failure.'))
        self.sim_guidance_status.setText('COMMON CỔ ĐIỂN · +0,005m/s chỉ ở steady; đặt proposal về0 từ decision7,5s, source stop8s. Qua projection/ramp/PI cũ. Đây là preview lịch dừng đã biết, không preview gờ chưa biết. Actor h5 không có preview tương ứng: so cấu hình hệ thống, chưa ranking thuật toán cùng thông tin. Nominal không đọc GT; raw actor / controller proposal / accepted reference riêng; không xuất masked replay.')
    def show_stop_transfer_table(self,data):
        runs=data['runs'];self.sim_table.setColumnCount(10)
        self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','Native v(m/s)','GT20ms v(m/s)','GT+10ms v(m/s)','RMSE path(mm)','Hạ tốc RMSE v','Bù cuối(s)','Marker + stop','Gate đề xuất','Diagnostic'])
        self.sim_table.setRowCount(len(runs));self.sim_table.setMinimumHeight(255);self.sim_table.setMaximumHeight(310)
        for row,m in enumerate(runs):
            d=m['timestamp_diagnostic'];grid=d.get('header_grid',{});end=m['compensation_last_decision_s'];phase=m['phases']['deceleration'];c=m['condition']
            values=[('Cổ điển' if c['arm']=='Classical_scheduled' else c['arm'])+'/'+str(c['repeat']+1),f"{m['nominal_velocity_rmse_m_s']:.6f}"]
            values += [f"{grid[k]['rmse_m_s']:.6f}" if k in grid else 'UNKNOWN' for k in ('0.0','0.01')]
            values += [f"{m['cross_track_rmse_m']*1000:.3f}",'unknown' if phase is None else f"{phase['velocity_rmse_m_s']:.6f}",'—' if end is None else f'{end:.1f}',
                'ĐẠT' if m['task_success'] and m['stop_completed'] else 'CHƯA','CANDIDATE' if m['functional_proposal_pass'] else 'CHƯA ĐẠT','ĐỦ SUPPORT' if d['valid'] else 'UNKNOWN']
            for col,value in enumerate(values):
                item=Q.QTableWidgetItem(value);item.setToolTip(c['arm'] if col==0 else value);self.sim_table.setItem(row,col,item)
        self.sim_next.setText(f"ĐỢT TRANSFER ĐÃ ĐÓNG · {len(runs)}/6 lượt, {data['evaluation_transitions']}/840 ticks; optimizer/actor0. "+
            ('Có separation mô tả ở native và cả hai grids; chưa promote vì minimum worthwhile effect chưa chốt.' if data['descriptive_transfer_signal'] else 'UNKNOWN / FAILED · không đủ separation hoặc constraints/support; giữ B0, dừng tăng budget compensation.')+
            '\nContract cùng preview đã có profile offline riêng. Tiếp kiểm wrapper103D/1D trong Gazebo theo protocol mới; chưa optimizer hoặc contact/real claim.')
        self.sim_guidance_status.setText('KNOWN STOP TRANSFER · +0,005m/s sau nominal steady; withdraw=stop−0,5s=5,5s, source stop6s. Backend / guidance / scorer đồng bộ. Primary toàn14s native100ms; diagnostic GT-header20ms/+10ms giữ riêng, không nội suy body. Ba fresh launches/arm là pilot mô tả, không exact-state pairing hoặc generalization. B0 đối chứng; không actor/optimizer/hardware.')
    def show_eval_only_table(self, state):
        self.sim_table.setColumnCount(10)
        self.sim_table.setHorizontalHeaderLabels(['Arm / seed','Stop (s)','Ticks','Native vRMSE','GT 20 ms','GT +10 ms','Path RMSE (mm)','Task / stop','Support','Actor giữ nguyên'])
        self.sim_table.setMinimumHeight(300);self.sim_table.setMaximumHeight(420)
        self.sim_guidance_status.setText('Cùng observation 103D / action 1D, history 5, preview lịch dừng và limiter. Checkpoint cuối của cả ba seed được khóa hash; inference deterministic, optimizer 0. Chưa holdout hoặc minimum worthwhile effect. Không suy lợi ích contact/hardware từ sàn sạch.')
        if not state.get('path'):
            self.sim_next.setText('Bấm Đánh giá để chạy một budget: B0 / cổ điển / ba TD3 tại stop 6/8 s. Chờ từng lượt và manifest cuối; không train lại.' if not guided_td3_consumed(self.root,'sim-reliable-eval-only') else 'Budget eval đã tiêu thụ; chờ job đóng hoặc xem lỗi. Không bấm chạy lại.')
            return
        try:
            out=Path(state['path']);completed=state.get('state')=='verified'
            path=out/('evaluation_result.json' if completed else 'evaluation_progress.json')
            data=json.loads(path.read_text());runs=data.get('runs',[])
            self.sim_table.setRowCount(len(runs))
            for row,m in enumerate(runs):
                c=m['evaluation_condition'];g=m['timestamp_diagnostic'].get('header_grid',{})
                values=[c['arm']+('/'+str(c['seed']) if 'seed' in c else ''),str(c['source_stop_s']),str(m['steps']),f"{m['nominal_velocity_rmse_m_s']:.7f}",
                    *[f"{g[k]['rmse_m_s']:.7f}" if k in g else 'unknown' for k in ('0.0','0.01')],f"{m['cross_track_rmse_m']*1000:.4f}",
                    str(m['task_success'])+'/'+str(m['stop_completed']),f"{m['maximum_native_boundary_support_age_s']*1000:.1f} ms",
                    ('Đạt' if m.get('actor_before')==m.get('actor_after') else 'FAIL') if c['arm']=='TD3' else 'Không actor']
                for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
            ticks=sum(m['steps'] for m in runs)
            self.sim_progress.setRange(0,1400);self.sim_progress.setValue(ticks)
            self.sim_progress.setFormat(f'ĐÃ ĐÓNG · {len(runs)}/10 lượt / {ticks}/1.400 ticks · optimizer 0')
            if completed:
                self.sim_next.setText('Đã đủ 10 lượt. So TD3 từng seed/stop với cả B0 và cổ điển; kiểm ranking native/GT20ms/+10ms, tracking và dừng. Chưa mở train dài, promote hoặc hardware.')
            else:self.sim_next.setText('EVAL ĐÃ ĐÓNG DO LỖI · '+str(state.get('error'))+'. Giữ partial, các slot còn lại đóng; không retry hoặc train lại.')
            review_path=self.root/'review.json'
            if review_path.exists():
                review=json.loads(review_path.read_text())
                if review.get('artifact')==str(out) and review.get('artifact_manifest_sha256')==hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest():
                    self.sim_guidance_status.setText(self.sim_guidance_status.text()+f"\nQC audit: {review['files_verified']} file hashes; {review['feedback_checks']} support checks; joint age P/I {review['maximum_primary_joint_age_ms']}/{review['maximum_independent_joint_age_ms']} ms; payload mismatch {review['payload_mismatches']}. Reader-only stamps: {review['one_sided_stamps_by_phase']}; không gọi loss-free.")
                    if completed:
                        wins=review['descriptive_all_grid_wins']
                        self.sim_next.setText(f'ĐÃ ĐÓNG 10/10 · {wins}/6 điều kiện TD3 thấp hơn cả B0 và cổ điển trên native + hai grids. '+('Giữ baseline; chưa có ưu thế TD3 nhất quán. Review phase/critic/coverage đã có; chỉ thiết kế study có giới hạn, chưa train dài hoặc đổi gain/reward mặc định.' if wins<6 else 'Có tín hiệu mô tả; cần holdout và mức cải thiện ứng dụng trước khi mở rộng.')+' Chưa promote/hardware.')
        except (OSError,ValueError,KeyError,TypeError) as exc:self.sim_next.setText('Chưa đọc được eval-only artifact: '+str(exc))

    def show_gain_baseline_table(self,state):
        self.sim_table.setColumnCount(9)
        self.sim_table.setHorizontalHeaderLabels(['Arm','Gain','Ticks','Native m/s','GT20 m/s','GT+10 m/s','Path mm','Task/stop','Trạng thái'])
        self.sim_table.setMinimumHeight(340);self.sim_table.setMaximumHeight(380)
        self.sim_table.horizontalHeader().setSectionResizeMode(0,Q.QHeaderView.ResizeToContents)
        self.sim_guidance_status.setText('Cùng103D/1D/history5/10Hz/preview/reset ACK. Gain cố định là stress giả lập, không calibration Nino. Một run/cell; không exact-state branching hoặc bằng chứng cần TD3.')
        out=Path(state['path']) if state.get('path') else None
        if out is None and self.runner.busy and self.runner.action=='sim-gain-baselines':
            try:
                record=json.loads((self.root/'state.json').read_text())['runs'][-1]
                candidate=(self.root/record['path']).resolve()
                if record['action']=='sim-gain-baselines' and candidate.parent==self.root.resolve():out=candidate
            except (OSError,ValueError,KeyError,TypeError,IndexError):pass
        rows=[];ticks=0
        if out:
            for file in sorted(out.glob('eval_*/summary.json')):
                r=json.loads(file.read_text());c=r['evaluation_condition'];g=r['timestamp_diagnostic']['header_grid'];ticks+=r['steps']
                rows.append([c['arm'],str(c['gain']),str(r['steps']),f"{r['nominal_velocity_rmse_m_s']:.6f}",
                    f"{g['0.0']['rmse_m_s']:.6f}",f"{g['0.01']['rmse_m_s']:.6f}",
                    f"{1000*r['cross_track_rmse_m']:.3f}",str(r['functional_proposal_pass']),
                    'Đã seal' if state.get('state')=='verified' else 'Partial/chờ seal'])
        self.sim_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):self.sim_table.setItem(i,j,Q.QTableWidgetItem(value))
        self.sim_progress.setRange(0,1260);self.sim_progress.setValue(ticks)
        self.sim_progress.setFormat(f'{ticks}/1260 valid ticks · 0 actor/optimizer')
        if state.get('state')=='verified':
            result=json.loads((out/'evaluation_result.json').read_text())
            labels={'unknown_small_or_gain_dependent_effect':'Hiệu ứng nhỏ hoặc phụ thuộc gain; chưa có phương án thắng toàn dải.',
                'unknown_grid_sensitive':'UNKNOWN: kết luận đổi dấu giữa native/header grids.',
                'retain_fixed_classical_no_learning_justified':'Giữ fixed classical trong screen này; chưa có lý do mở learner.',
                'descriptive_causal_candidate_separate_validation_required':'Causal là ứng viên mô tả; cần validation riêng.',
                'unknown_nonfinite_or_zero_denominator':'UNKNOWN: metric không hữu hạn hoặc baseline bằng zero.'}
            self.sim_next.setText('Đã đóng9/9: '+labels.get(result['comparison']['decision'],result['comparison']['decision'])+
                ' So B0 cần xem riêng cả native/header; không gộp effect qua gain. Xem kết quả và gate mới nhất ở tab Quyết định benchmark; chưa mở learner/holdout/hardware.')
        elif state.get('state')=='retained_failure':
            self.sim_next.setText('Đã đóng do lỗi: '+state.get('error','unknown')+' · giữ raw và slot còn lại đóng; không chạy bù.')
        else:self.sim_next.setText('Đợi release đúng source/tests/root; các cell gain1 là integration trong1260ticks. Chọn profile không tự chạy.' if not self.runner.busy else 'Đang chạy từng baseline; lỗi đóng toàn bộ phần còn lại.')

    def show_ready_eval_table(self,state):
        self.sim_table.setColumnCount(9)
        self.sim_table.setHorizontalHeaderLabels(['Arm','Stop s','Ticks','Native (m/s)','GT20 (m/s)','GT+10 (m/s)','Path mm','Task/stop','Trạng thái'])
        self.sim_table.setMinimumHeight(240);self.sim_table.setMaximumHeight(280)
        self.sim_table.setRowCount(0)
        self.sim_guidance_status.setText('Một checkpoint A seed11 đóng băng; deterministic, không probe/optimizer. B0/cổ điển cùng preview/window/reset ACK. Một seed và một run/condition chỉ screening; không exact-state branching hoặc generalization.')
        out=Path(state['path']) if state.get('path') else None
        if out is None and self.runner.busy and self.runner.action=='sim-ready-eval-only':
            try:
                row=json.loads((self.root/'state.json').read_text())['runs'][-1]
                if row['action']=='sim-ready-eval-only' and row['status']=='running':
                    candidate=(self.root/row['path']).resolve()
                    if candidate.parent==self.root.resolve():out=candidate
            except (OSError,ValueError,KeyError,TypeError,IndexError):pass
        ticks=0;rows=[]
        if out:
            for file in sorted(out.glob('eval_*/summary.json')):
                r=json.loads(file.read_text());condition=r['evaluation_condition'];g=r['timestamp_diagnostic']['header_grid']
                ticks+=r['steps']
                rows.append([condition['arm'],str(condition['source_stop_s']),str(r['steps']),
                    f"{r['nominal_velocity_rmse_m_s']:.6f}",f"{g['0.0']['rmse_m_s']:.6f}",f"{g['0.01']['rmse_m_s']:.6f}",
                    f"{1000*r['cross_track_rmse_m']:.3f}",str(r['functional_proposal_pass']),
                    'Đã seal' if state.get('state')=='verified' else 'Partial/chờ manifest'])
        self.sim_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):self.sim_table.setItem(i,j,Q.QTableWidgetItem(value))
        self.sim_progress.setRange(0,840);self.sim_progress.setValue(ticks)
        self.sim_progress.setFormat(f'{ticks}/840 eval ticks · 0 optimizer updates')
        if state.get('state')=='verified':
            result=json.loads((out/'evaluation_result.json').read_text())
            decision=result['comparison']['decision']
            labels={
                'no_go_expand_this_checkpoint_clear_known_stop':'A không tốt hơn cổ điển ở cả hai lịch dừng và ba grids. Giữ cổ điển; chưa mở train dài cho bài thử này.',
                'descriptive_candidate_requires_separate_holdout':'A là ứng viên mô tả; cần protocol holdout riêng trước khi kết luận lợi ích.',
                'unknown_grid_sensitive':'UNKNOWN: kết luận đổi dấu theo grid; chưa tăng mẫu hoặc đổi metric.',
                'unknown_small_or_condition_dependent_effect':'UNKNOWN: hiệu ứng nhỏ hoặc phụ thuộc lịch dừng; chưa mở thêm ngân sách.',
                'unknown_nonfinite_metric':'UNKNOWN: metric không hữu hạn.',
                'unknown_zero_denominator':'UNKNOWN: baseline metric bằng zero; không tính tỷ lệ.'}
            qc='QC: chờ audit sau seal.'
            try:
                import hashlib
                review=json.loads((self.root/'review.json').read_text())
                if (review.get('artifact')==str(out) and review.get('artifact_manifest_sha256')==hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()):
                    qc=f"QC đã audit: {review['files_verified']} hashes, {review['feedback_checks']} support checks, {review['payload_mismatches']} payload mismatch; actor/optimizer/sampler giữ nguyên."
            except (OSError,ValueError,KeyError,TypeError):pass
            self.sim_next.setText('EVAL ĐÃ ĐÓNG 6/6: '+labels.get(decision,decision)+'\n'+qc+' Một seed; chưa promote/hardware.')
        elif state.get('state')=='retained_failure':self.sim_next.setText('EVAL ĐÃ ĐÓNG LỖI: '+state.get('error','unknown')+' · giữ raw/partial; không retry hoặc chạy bù.')
        else:self.sim_next.setText('Đang chờ từng rollout và manifest cuối; không mở job khác.' if self.runner.busy else 'Eval-only cần release riêng pin qualification/A checkpoint/source/tests; chọn profile không tự chạy.')

    def show_drive_readiness_table(self,state):
        self.sim_table.setColumnCount(6)
        self.sim_table.setHorizontalHeaderLabels(['Run / stop plan','Zero ticks','Setup sim s','Drive ACK','Joint age ms','Trạng thái'])
        self.sim_table.setRowCount(0)
        self.sim_guidance_status.setText('Observer có joint chưa đủ: drive phải ACK wheel feedback và zero; physical quiet0,5s, setup cap5sim seconds. Qualification chỉ zero; không actor/optimizer hoặc motion benefit.')
        self.sim_next.setText('Qualification một attempt riêng sau software gate; không dùng lại slot V2. Chưa có dữ liệu qualification.' if state.get('state')=='pending' else 'Đợi worker đóng và manifest; không chạy lại.')
        if state.get('state')=='verified':
            result=json.loads((Path(state['path'])/'qualification_result.json').read_text())
            rows=result['runs'];self.sim_table.setRowCount(len(rows))
            for i,r in enumerate(rows):
                values=[str(r['source_stop_plan_s'])+'s',str(r['zero_control_ticks']),f"{r['setup_controlled_sim_s']:.1f}",str(r['drive_ack_before_first_tick']),str(r['maximum_joint_age_ms']),'Đạt reset/zero; chưa motion']
                for j,value in enumerate(values):self.sim_table.setItem(i,j,Q.QTableWidgetItem(value))
            self.sim_progress.setRange(0,20);self.sim_progress.setValue(result['zero_control_ticks'])
            self.sim_next.setText('Reset ACK + zero qualification đã đóng. Tiếp thiết kế eval-only checkpoint A với B0/cổ điển cùng gate; chưa mở training hoặc hardware.')
            review_file=self.root/'review.json'
            if review_file.is_file():
                review=json.loads(review_file.read_text())
                if (review.get('artifact')==state['path'] and review.get('artifact_manifest_sha256')==
                        hashlib.sha256((Path(state['path'])/'manifest.json').read_bytes()).hexdigest()):
                    self.sim_guidance_status.setText(self.sim_guidance_status.text()+
                        f"\nQC: {review['files_verified']} hashes, {review['feedback_checks']} support checks, closure={review['lifecycle_closed']}. ACK muộn trong Gazebo chưa tái hiện; fixture ACK muộn đã kiểm.")
        elif state.get('state')=='retained_failure':
            self.sim_next.setText('Qualification đã đóng lỗi: '+state.get('error','unknown')+'. Giữ raw, không retry hoặc mở learner mới.')

    def show_coverage_table(self):
        preflight_action,study_action=self.active_sim_actions()
        self.sim_table.setColumnCount(11)
        self.sim_table.setHorizontalHeaderLabels(['Stage / arm','Seed / stop','Ticks','Critic','Actor','Native vRMSE','GT20ms','GT+10ms','Path mm','Coverage','Trạng thái'])
        self.sim_table.setMinimumHeight(300);self.sim_table.setMaximumHeight(420)
        self.sim_guidance_status.setText('Preflight: sampler causal trước action, RNG riêng, replay lưu request sau probe, save/load optimizer và terminal. Evaluation không probe hoặc update. Critic-grid không là outcome counterfactual; ngưỡng5% chỉ là đề xuất nghiên cứu, chưa là yêu cầu ứng dụng.')
        out=None;status='chưa chạy';rows=[]
        try:
            ledger=json.loads((self.root/'state.json').read_text())
            latest_study=next((r for r in reversed(ledger['runs']) if r['action']==study_action),None)
            if latest_study:
                out=(self.root/latest_study['path']).resolve();status=latest_study['status']
                if out.parent!=self.root.resolve():raise ValueError('Artifact path escape')
                trusted=self.states.get(study_action,{}).get('state')
                if status in ('completed','failed','cancelled') and trusted not in ('verified','retained_failure'):
                    self.sim_table.setRowCount(0)
                    self.sim_next.setText('CHƯA XÁC MINH ARTIFACT · không dùng số liệu hoặc nhãn đạt; xem hash/source/lỗi trước.')
                    self.sim_progress.setValue(0)
                    return
        except FileNotFoundError:pass
        except (OSError,ValueError,KeyError,TypeError) as exc:self.sim_next.setText('Ledger chưa hợp lệ: '+str(exc));return
        review={}
        if out and (self.root/'review.json').is_file() and (out/'manifest.json').is_file():
            try:
                candidate=json.loads((self.root/'review.json').read_text())
                if candidate.get('artifact')==str(out) and candidate.get('artifact_manifest_sha256')==hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest():review=candidate
            except (OSError,ValueError,TypeError):pass
        training_order=[('A_gaussian',11),('C_stratified_probes',11),('C_stratified_probes',22),('A_gaussian',22),('A_gaussian',33),('C_stratified_probes',33)]
        ticks=0
        for arm,seed in training_order:
            path=out/f'{arm}_seed_{seed}' if out else None
            result=json.loads((path/'training_result.json').read_text()) if path and (path/'training_result.json').exists() else None
            progress=[]
            if not result and path and (path/'learning_progress.jsonl').exists():
                progress=[json.loads(line) for line in (path/'learning_progress.jsonl').read_text().splitlines()]
            last=result or (progress[-1] if progress else {})
            n=last.get('training_transitions',last.get('transitions',0));ticks+=n
            coverage=result.get('coverage',{}) if result else {}
            display_ticks=f'{n}/1024';label='Đạt learner' if result else status
            if not result and path and path.exists() and review:
                own=next((r for r in review.get('learners',[]) if r.get('arm')==arm and r.get('seed')==seed),review)
                raw=own.get('control_attempts',0);ticks+=raw-n
                display_ticks=f"{raw} raw / {own.get('replay_rows',0)} replay"
                last=dict(critic_updates=own.get('critic_updates',0),actor_updates=own.get('actor_updates',0))
                label='Partial · chưa nghiệm thu; xem lỗi'
            elif not result and status in ('failed','cancelled') and (not path or not path.exists()):label='Chưa chạy · slot đóng'
            rows.append([arm,str(seed),display_ticks,str(last.get('critic_updates',0)),str(last.get('actor_updates',0)),
                '—','—','—','—',str(coverage.get('bin_counts','—')),label])
        if out:
            for path in sorted(out.glob('eval_*/summary.json')):
                result=json.loads(path.read_text());condition=result['evaluation_condition'];grid=result['timestamp_diagnostic']['header_grid']
                ticks+=result['steps']
                rows.append([condition['arm'],f"{condition.get('seed','—')} / {condition['source_stop_s']}s",str(result['steps']),
                    '0','0',f"{result['nominal_velocity_rmse_m_s']:.6f}",f"{grid['0.0']['rmse_m_s']:.6f}",
                    f"{grid['0.01']['rmse_m_s']:.6f}",f"{1000*result['cross_track_rmse_m']:.3f}",'—',
                    'Task / stop đạt' if result['functional_proposal_pass'] else 'Không đạt'])
        self.sim_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):
                item=Q.QTableWidgetItem(value);item.setToolTip(value)
                if j==0 and value in ('A_gaussian','C_stratified_probes'):
                    item.setText('A · Gaussian' if value=='A_gaussian' else 'C · Probe')
                self.sim_table.setItem(i,j,item)
        for column in (2,9,10):
            self.sim_table.horizontalHeader().setSectionResizeMode(column,Q.QHeaderView.ResizeToContents)
        self.sim_progress.setRange(0,8384);self.sim_progress.setValue(ticks)
        self.sim_progress.setFormat(f'{ticks}/8384 control attempts · {status}')
        pre=self.states.get(preflight_action,{})
        if not out:
            if self.runner.busy and self.runner.action==study_action:
                self.sim_next.setText('Worker đang kiểm release/source trước scientific slot; chờ ledger và tiến độ.')
                return
            self.sim_next.setText('Bước1: bấm Kiểm coverage offline, chờ preflight manifest. Chưa có scientific train/eval mới.' if pre.get('state')!='verified' else
                'Preflight offline đạt. Bước2 cần release riêng pin implementation + preflight và review ngưỡng nghiên cứu; nút study hiện khóa. Chưa chạy Gazebo.' if not coverage_release_ready(self.root,study_action) else
                'Preflight và release đã khớp. Bấm Study một lần để chạy6learner rồi16eval; không retry.')
        elif (out/'study_result.json').exists():
            result=json.loads((out/'study_result.json').read_text())
            self.sim_next.setText('Study đã đóng: '+result['comparison']['decision']+' · chưa hardware/promotion.')
        else:
            self.sim_next.setText('Study '+status+'; giữ partial và đóng slot nếu lỗi/hủy. Không tự retry.')
            if review:
                self.sim_next.setText(f"STUDY ĐÃ ĐÓNG · {review.get('diagnosis',review.get('error','xem lỗi'))}. {review.get('control_attempts',0)} control attempt; {review.get('replay_rows',0)} replay / {review.get('critic_updates',0)} critic updates / {review.get('evaluation_runs',0)} eval. Không chạy bù; xem correction offline và protocol tiếp.")
                learned=('Có optimizer updates nhưng study chưa nghiệm thu; không resume/promote.' if review.get('actor_updates',0)>0 else
                    f"Actor giữ nguyên={review.get('actor_unchanged_from_initial')}; không gọi partial là checkpoint đã học.")
                self.sim_guidance_status.setText(self.sim_guidance_status.text()+f"\nQC: {review.get('files_verified',0)} hashes; {review.get('feedback_checks',0)} support checks; closure={review.get('lifecycle_closed')}. "+learned)

    def show_reliable_td3_table(self, state):
        self.sim_table.setColumnCount(10)
        self.sim_table.setHorizontalHeaderLabels(['Seed / arm', 'Stop (s)', 'Train / eval', 'Updates', 'Native vRMSE', 'GT 20 ms', 'GT +10 ms', 'Path RMSE (mm)', 'Task / stop', 'Trạng thái'])
        self.sim_table.setMinimumHeight(250);self.sim_table.setMaximumHeight(360)
        self.sim_guidance_status.setText('Native và GT-header giữ riêng. Requested 1D / mapped / accepted reference được ghi riêng. Không dùng reward để promote. Mỗi epoch mới đóng Gazebo/executor/observer cũ trước khi tạo instance mới; không vá primary bằng independent observer.')
        if not state.get('path'):
            self.sim_next.setText('Bước tiếp: bấm Train TD3 RELIABLE một lần; theo dõi tiến độ và chờ job đóng. 3 seed mới × 1.024 bước; chỉ mở eval nếu đủ cả ba. Budget đã tiêu thụ thì chỉ xem kết quả.' if not guided_td3_consumed(self.root,'sim-reliable-td3') else 'Job đã tiêu thụ; đợi đóng hoặc xem lỗi/manifest. Không chạy lại.')
            return
        try:
            out=Path(state['path']);result_path=out/'pilot_result.json'
            data=json.loads(result_path.read_text()) if result_path.exists() else {}
            review={};review_path=self.root/'review.json'
            if review_path.exists():
                candidate=json.loads(review_path.read_text())
                if candidate.get('artifact')==str(out) and candidate.get('artifact_manifest_sha256')==hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest():review=candidate
            table=[];completed_training_seeds=0
            for seed in (11,22,33):
                path=out/f'seed_{seed}'/'training_result.json'
                if path.exists():
                    m=json.loads(path.read_text())
                    completed_training_seeds+=1
                    table.append([str(seed),'6 / 8',str(m['training_transitions']),str(m['optimizer_updates']),'—','—','—','—',f"{m['full_task_terminals']}/7 full",'Đạt learner / replay'])
                elif (out/f'seed_{seed}').exists():
                    m=review.get('partial_training',{}).get(str(seed),{})
                    table.append([str(seed),'6 / 8',str(m.get('replay_rows','partial')),str(m.get('optimizer_updates','unknown')),'—','—','—','—','Không suy từ partial','Đã đóng / xem lỗi'])
                else:table.append([str(seed),'6 / 8','0','0','—','—','—','—','Chưa chạy','Slot đóng / chờ'])
            for m in data.get('runs',[]):
                c=m['evaluation_condition'];g=m['timestamp_diagnostic'].get('header_grid',{})
                table.append([c['arm']+('/'+str(c['seed']) if 'seed' in c else ''),str(c['source_stop_s']),str(m['steps']),'0',f"{m['nominal_velocity_rmse_m_s']:.6f}",*[f"{g[k]['rmse_m_s']:.6f}" if k in g else 'unknown' for k in ('0.0','0.01')],f"{m['cross_track_rmse_m']*1000:.3f}",str(m['task_success'])+'/'+str(m['stop_completed']),'Đánh giá mô tả'])
            self.sim_table.setRowCount(len(table))
            for row,values in enumerate(table):
                for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
            failed=state.get('state')=='retained_failure'
            self.sim_next.setText(('ĐÃ ĐÓNG DO LỖI · '+str(state.get('error'))+' · giữ partial; các slot còn lại đóng.' if failed else 'Pilot hoàn thành; so từng seed/stop với B0 và cổ điển, kiểm hai grids. Chưa promote hoặc mở train dài.')+' Không resume batch 700 bước cũ.')
            self.sim_progress.setValue(100)
            self.sim_progress.setFormat('ĐÃ ĐÓNG · PARTIAL / KHÔNG RETRY' if failed else 'ĐÃ ĐÓNG · 3.072 train + 1.400 eval')
            if failed and completed_training_seeds==3:
                self.sim_progress.setRange(0,4472);self.sim_progress.setValue(3072)
                self.sim_progress.setFormat('ĐÃ ĐÓNG · TRAIN 3/3 / 3.072 bước · EVAL CHƯA HOÀN TẤT')
                self.sim_next.setText('TRAIN 3/3 ĐẠT · EVAL CHƯA HOÀN TẤT · '+str(state.get('error'))+'. Giữ ba final checkpoints; không train lại. Bước tiếp: protocol eval-only riêng với lifecycle evaluator đã sửa và test offline; chưa release hoặc chạy thêm Gazebo.')
            if review:
                self.sim_guidance_status.setText(self.sim_guidance_status.text()+f"\nQC đã audit: {review.get('files_verified','unknown')} artifact files; {review.get('feedback_checks','unknown')} training support checks; joint age P/I {review.get('maximum_primary_joint_age_ms','unknown')}/{review.get('maximum_independent_joint_age_ms','unknown')} ms. Reader-only stamps theo phase: {review.get('independent_only_stamp_phase_counts','chưa audit')}. Source publish count chưa có, không gọi loss-free.")
        except (OSError,ValueError,KeyError,TypeError) as exc:self.sim_next.setText('Chưa đọc được learner result: '+str(exc))

    def show_joint_reliability_table(self):
        fixture=self.states.get('sim-joint-reliability-fixture',{});qualified=self.states.get('sim-joint-reliability-gazebo',{})
        quality={};review_path=self.root/'review.json'
        if review_path.is_file() and qualified.get('path'):
            try:
                review=json.loads(review_path.read_text());artifact=Path(qualified['path']);pin=review['artifacts']['sim-joint-reliability-gazebo']
                if pin['path']==str(artifact) and pin['manifest_sha256']==hashlib.sha256((artifact/'manifest.json').read_bytes()).hexdigest():quality={r['source_stop_s']:r for r in review['qualification_quality']}
            except (OSError,ValueError,KeyError,TypeError):pass
        rows=[];f=q=None
        try:
            if fixture.get('state')=='verified':
                f=json.loads((Path(fixture['path'])/'fixture_result.json').read_text())
                for role,r in f['readers'].items():
                    end=r['endpoint'] or {};age=end['age_ns']/1e6 if end.get('age_ns') is not None else 'Unknown'
                    rows.append([role,'1000 msg',r['labeled_unique'],len(r['missing_source_stamps_ns']),r['payload_mismatches'],age,'—','—','—','Compatible' if f['candidate_compatible'] else 'No-go/unknown'])
            if qualified.get('state')=='verified':
                q=json.loads((Path(qualified['path'])/'qualification_result.json').read_text())
                for r in q['runs']:
                    audit=quality.get(r['source_stop_s']);age=str(r['maximum_primary_joint_age_ms'])+'/'+str(r['maximum_independent_joint_age_ms'])
                    rows.append(['B0 stop'+str(r['source_stop_s']),str(r['complete_steps'])+' ticks',r['replay_rows_checked'],'Support '+str(r['all_joint_paths_supported']),audit['payload_mismatches'] if audit else 'Chưa audit',age,f"{r['nominal_velocity_rmse_m_s']:.7f}" if 'nominal_velocity_rmse_m_s' in r else 'Unknown',f"{r['cross_track_rmse_m']*1000:.4f}" if 'cross_track_rmse_m' in r else 'Unknown',str(r.get('task_success',False))+'/'+str(r.get('stop_completed',False)),'Đạt' if r['qualification_pass'] else r['error'] or 'Unknown'])
        except (OSError,ValueError,KeyError,TypeError) as exc:self.sim_next.setText('Chưa đọc được reliability result: '+str(exc));return
        self.sim_table.setColumnCount(10);self.sim_table.setRowCount(len(rows));self.sim_table.setMaximumHeight(245)
        self.sim_table.setHorizontalHeaderLabels(['Phase / arm','Nguồn','Nhận / replay','Thiếu / support','Payload lệch','Age P/I(ms)','Native vRMSE','PathRMSE(mm)','Task/stop','Kết quả'])
        for i,row in enumerate(rows):
            for j,value in enumerate(row):
                item=Q.QTableWidgetItem(str(value));item.setToolTip(str(value));self.sim_table.setItem(i,j,item)
        if q:
            self.sim_progress.setRange(0,280);self.sim_progress.setValue(q.get('evaluation_transitions',sum(r['complete_steps'] for r in q['runs'])));self.sim_progress.setFormat(f"ĐÃ ĐÓNG · {self.sim_progress.value()}/280 B0 transitions · train0")
        if q:self.sim_next.setText('Hai stage đã đóng. Candidate B0 '+('đạt qualification' if q['qualification_pass'] else 'chưa đạt/unknown')+'; bước tiếp là learner protocol mới, chưa mở train hoặc resume partial.')
        elif f:self.sim_next.setText('Fixture compatible; bấm 2 để kiểm B0 candidate trong Gazebo.' if f['candidate_compatible'] else 'Fixture đã đóng no-go/unknown; không qualification/không retry.')
        else:self.sim_next.setText('Bấm 1: một fixture paired1000messages +1handshake, source500Hz, pause100ms; đọc kết quả trước stage2.')
        self.sim_guidance_status.setText('Chỉ joint observer đổi BEST_EFFORT→RELIABLE; depth100 và các subscription khác giữ. Source publish attempt không là DDS delivery ACK. BE/RELIABLE cùng đủ1000 chỉ cho compatibility, không chứng minh reliability benefit. B0 đạt không có optimizer load hoặc root-cause proof. Native/header-grid report riêng; partial TD3700ticks vẫn đóng, learner mới cần fresh model/replay và episode/observer epoch riêng.')
    def show_joint_boundary_table(self,data):
        quality={};review_path=self.root/'review.json';current=self.states.get('sim-joint-boundary',{})
        if review_path.is_file() and current.get('path'):
            try:
                review=json.loads(review_path.read_text());artifact=Path(current['path'])
                if review['artifact']==str(artifact) and review['manifest_sha256']==hashlib.sha256((artifact/'manifest.json').read_bytes()).hexdigest():
                    quality={r['launch']:r for r in review['quality']}
            except (OSError,ValueError,KeyError,TypeError):pass
        rows=data['runs'];self.sim_table.setColumnCount(8);self.sim_table.setRowCount(len(rows));self.sim_table.setMaximumHeight(180)
        self.sim_table.setHorizontalHeaderLabels(['Launch','Zero ticks','Feedback checks','Primary age max(ms)','Observer age max(ms)','Payload lệch','Support/closure','Lỗi'])
        for i,r in enumerate(rows):
            q=quality.get(r['launch']);age=q['max_supported_endpoint_age_ms'] if q else {}
            values=[r['launch']+1,r['complete_zero_ticks'],r['feedback_checks'],age.get('primary','Chưa audit'),age.get('independent','Chưa audit'),q['semantic_hash_mismatches'] if q else 'Chưa audit','Đạt' if r['all_support_pass'] and not r['cleanup_error'] else 'Chưa đạt',r['error'] or r['cleanup_error'] or 'Không']
            for j,value in enumerate(values):
                item=Q.QTableWidgetItem(str(value));item.setToolTip(str(value));self.sim_table.setItem(i,j,item)
        self.sim_progress.setRange(0,200);self.sim_progress.setValue(data['complete_zero_control_ticks']);self.sim_progress.setFormat(f"ĐÃ ĐÓNG · {data['complete_zero_control_ticks']}/200zero ticks · không training")
        conclusion='Chưa tái hiện lỗi; nguyên nhân CHƯA RÕ' if data['outcome']=='not_reproduced_unknown' else 'Dừng do lỗi; xem support/IPC từng boundary'
        self.sim_next.setText(f"Diagnostic đã đóng: {data['launches']}/2launches · {conclusion}. Không mở lại TD3 batch hoặc thêm lượt.")
        self.sim_guidance_status.setText('Gate40ms giữ nguyên. Hai ROS reader không có counter publish upstream; clean zero-only không chứng minh acquisition dưới optimizer load. Publisher đã xác nhận RELIABLE, reader BEST_EFFORT/depth100. Bước tiếp: candidate QoS joint RELIABLE riêng +fixture có fault/counter, chưa áp vào frozen backend/chưa mở train. Payload parity dùng canonical fields; hash CDR serialize lại chỉ diagnostic.')
    def show_common_td3_failure(self,data):
        rows=data['episodes'];self.sim_table.setColumnCount(6);self.sim_table.setRowCount(len(rows));self.sim_table.setMaximumHeight(230)
        self.sim_table.setHorizontalHeaderLabels(['Seed11 episode','Stop(s)','Ticks','Native vRMSE(m/s)','PathRMSE(mm)','Task/stop'])
        for i,r in enumerate(rows):
            values=[r['episode'],r['source_stop_s'],r['steps'],r['nominal_velocity_rmse_m_s'],r['path_rmse_mm'],'ĐẠT / ĐẠT']
            for j,value in enumerate(values):self.sim_table.setItem(i,j,Q.QTableWidgetItem(f'{value:.7f}' if isinstance(value,float) else str(value)))
        self.sim_progress.setRange(0,4472);self.sim_progress.setValue(data['training_transitions']);self.sim_progress.setFormat(f"ĐÃ ĐÓNG · Train {data['training_transitions']}/3072 · Eval 0/1400")
        self.sim_next.setText(f"ĐỢT ĐÃ ĐÓNG DO LỖI ĐO: {data['training_transitions']}/3072 train ticks; {data['critic_updates']} critic +{data['actor_optimizer_updates']} actor updates. Eval0/10. Không chạy lại hoặc mở seed22/33.")
        self.sim_guidance_status.setText('Episode6 đã reset/settle, nhưng half-tick warmup đầu chỉ có wheel stamp2,651 tại sim2,701s: age50ms. Lệnh zero; không hạ gate40ms. Partial model/replay700rows đã kiểm hash/ABI/finite, chưa là seed hoàn chỉnh hoặc checkpoint được promote. Bước tiếp: phân biệt source/DDS/consumer bằng diagnostic riêng; chưa mở thêm physics/train.')
    def show_common_td3_table(self,data):
        runs=data['runs'];self.sim_table.setColumnCount(7);self.sim_table.setRowCount(len(runs));self.sim_table.setMaximumHeight(345)
        self.sim_table.setHorizontalHeaderLabels(['Arm / seed','Stop(s)','Native vRMSE','Header20ms','Header+10ms','PathRMSE(mm)','Task/stop'])
        for i,r in enumerate(runs):
            c=r['evaluation_condition'];d=r['timestamp_diagnostic']
            values=[c['arm']+(' '+str(c['seed']) if 'seed' in c else ''),c['source_stop_s'],r['nominal_velocity_rmse_m_s'],d['header_grid']['0.0']['rmse_m_s'],d['header_grid']['0.01']['rmse_m_s'],r['cross_track_rmse_m']*1000,str(r['task_success'])+'/'+str(r['stop_completed'])]
            for j,value in enumerate(values):self.sim_table.setItem(i,j,Q.QTableWidgetItem(f'{value:.7f}' if isinstance(value,float) else str(value)))
        self.sim_next.setText(f"Đã đóng: {data['training_transitions']} train + {data['evaluation_transitions']} eval ticks; {data['optimizer_updates']} critic updates. Chưa mở train dài/hardware; review chênh so cả B0/cổ điển trên mọi grid.")
        self.sim_guidance_status.setText('Learner seeds độc lập: '+', '.join(str(r['seed'])+': '+str(r['training_transitions'])+' ticks/'+str(r['optimizer_updates'])+' updates; replay/save-load '+str(r['model_optimizer_target_replay_parity']) for r in data['training'])+'. H5+preview103D, scalar±0,005m/s, shared window. Mỗi seed cuối44ticks cắt phải được giữ. TRAIN TD3 tự do vẫn là V3/100D/2D; checkpoint hai ABI không đổi chéo.')
    def show_equal_information_table(self,data):
        runs=data['fixture_runs'];self.sim_table.setColumnCount(5)
        self.sim_table.setHorizontalHeaderLabels(['Fixture phần mềm','Source stop(s)','Tick fixture','Tick cửa sổ mở','Request khác0 bị gate chặn'])
        self.sim_table.setRowCount(len(runs));self.sim_table.setMinimumHeight(255);self.sim_table.setMaximumHeight(310)
        labels={'B0':'B0','Classical_scheduled':'Cổ điển','Proposal_probe':'Probe action · không learner'}
        for row,r in enumerate(runs):
            values=[labels[r['arm']],str(r['source_stop_s']),str(r['fixture_steps']),str(r['open_window_ticks']),str(r['closed_window_nonzero_requests'])]
            for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
        self.sim_next.setText(f"CONTRACT OFFLINE ĐÃ KIỂM · {data['observation_size']}D observation / {data['action_size']}D action; {data['synthetic_fixture_transitions']} bước fixture tổng hợp. "+
            'Train/optimizer/Gazebo/hardware0. Chưa có kết quả policy mới hoặc lợi ích vật lý.\nBước tiếp: review remaining gap, mục tiêu đáng quan tâm và protocol Gazebo mới trước train; không nạp checkpoint V3 vào ABI này.')
        blocker_labels={
            'remaining_gap_hypothesis_not_demonstrated':'Xác định tình huống TD3 cần cải thiện so với baseline cổ điển.',
            'minimum_worthwhile_effect_unaccepted':'Chốt tiêu chí cải thiện tạm thời cho nghiên cứu.',
            'training_seed_timestep_budget_unallocated':'Chọn số seed và timesteps trong protocol train mới.',
            'independent_test_conditions_and_budget_unsealed':'Tách development/validation/test và khóa ngân sách test.',
            'new_wrapper_not_yet_qualified_in_Gazebo':'Kiểm wrapper103D/1D trong Gazebo trước khi train.'}
        blockers='\n'.join(str(i+1)+'. '+blocker_labels.get(key,key) for i,key in enumerate(data['release_blockers']))
        self.sim_guidance_status.setText('CÙNG THÔNG TIN · cả hai nhận history100D +2 feature kế hoạch +request scalar trước đó. Common request±0,005m/s qua shared steady/withdrawal gate rồi projection cũ; yaw follower giữ nguyên. Replay lưu request1D, mapped2D và accepted reference riêng; penalty theo thang vật lý0,04m/s. Fixture mở ở2,4s khi nhận source tại0,5s; không ép thành2,5s của Gazebo cũ.\nViệc tiếp theo:\n'+blockers+'\nĐây là hồ sơ offline lúc chốt; xem profile Qualification103D/1D · Gazebo để biết tiến độ tích hợp. TRAIN TD3 tự do vẫn dùng V3/100D/2D; xem profile TD3 common103D/1D để biết pilot mới và lỗi/partial hiện tại.')
    def show_equal_gazebo_table(self,data):
        runs=data['runs'];self.sim_table.setColumnCount(10)
        self.sim_table.setHorizontalHeaderLabels(['Arm / stop(s)','Native v(m/s)','GT20ms v(m/s)','GT+10ms v(m/s)','RMSE path(mm)','Tick window','Window (s)','Request bị chặn','Marker + stop','Tích hợp'])
        self.sim_table.setRowCount(len(runs));self.sim_table.setMinimumHeight(195);self.sim_table.setMaximumHeight(250)
        names={'B0':'B0','Classical_scheduled':'Cổ điển','Proposal_probe':'Probe'}
        for row,r in enumerate(runs):
            c=r['qualification_condition'];d=r['timestamp_diagnostic'];grid=d.get('header_grid',{})
            span='—' if r['first_window_decision_s'] is None else f"{r['first_window_decision_s']:.1f}–{r['last_window_decision_s']:.1f}"
            values=[names[c['arm']]+'/'+str(int(c['source_stop_s'])),f"{r['nominal_velocity_rmse_m_s']:.6f}"]
            values += [f"{grid[k]['rmse_m_s']:.6f}" if k in grid else 'UNKNOWN' for k in ('0.0','0.01')]
            values += [f"{r['cross_track_rmse_m']*1000:.3f}",str(r['common_window_ticks']),span,str(r['blocked_nonzero_requests']),
                'ĐẠT' if r['task_success'] and r['stop_completed'] else 'CHƯA','ĐẠT' if r['integration_pass'] else 'UNKNOWN/FAIL']
            for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
        self.sim_next.setText(f"QUALIFICATION GAZEBO ĐÃ ĐÓNG · {len(runs)}/4 lượt, {data['evaluation_transitions']}/560ticks; replay {data['replay_rows_checked']}rows. "+
            ('Wrapper103D/1D đạt tích hợp trong clear development6/8s.' if data['qualification_pass'] else 'Chưa đạt tích hợp; giữ artifact, không retry hoặc train để che lỗi.')+
            '\nKhông actor/optimizer hoặc policy mới được train. RMSE chỉ diagnostic, không xếp hạng lợi ích. Đây là hồ sơ qualification trước train; xem profile TD3 common103D/1D cho pilot tiếp theo đã đóng/partial.')
        self.sim_guidance_status.setText('103D/1D · cùng planned stop preview và shared window; legacy shadow chỉ kiểm predicate/nominal trên cùng source, không can thiệp. Request scalar → mapped2D → projection/PI giữ riêng. Causal source/clock và replay terminal được kiểm từng tick. Native +GT-header20ms/+10ms report riêng. Probe−1/0/+1 là kiểm thử, không learned policy. TRAIN TD3 tự do vẫn là V3/100D/2D; trainer103D/1D có profile riêng TD3 common, không đổi checkpoint chéo ABI.')
    def draw_diagram(self):
        self.scene.clear();self.scene.setBackgroundBrush(G.QColor('#101827'))
        cards=[('validate','History / projection\nEnvironment trace',0,0),('train-td3','TD3 giảm bậc\nOptimizer + actor',1,0),('train-ppo','PPO đối chứng\nCùng ABI',1,1),('compare','B0 / B1 / Governor\nTD3 / PPO giảm bậc',2,0),('ros-fixture','ROS shadow fixture\nKhông phát cmd motor',2,1),('gazebo-fixture','Gazebo flat fixture\nKhông calibration Nino',3,0),('factory-td3','TD3 FACTORY mixed\nNino + caster + wheel PI',3,1),('sysid','Dữ liệu thật + SysID\nWhole-session holdout',4,1),('hardware','Model / benchmark\nShadow thật → bounded α',4,0)]
        positions={key:(col*205,row*102) for key,_,col,row in cards}
        # Roadmap order. Exact executable dependencies are on button tooltips.
        for a,b in [('validate','train-td3'),('validate','train-ppo'),('train-td3','compare'),('train-ppo','compare'),('train-td3','ros-fixture'),('compare','gazebo-fixture'),('gazebo-fixture','factory-td3'),('sysid','hardware'),('ros-fixture','hardware'),('factory-td3','hardware')]:
            x,y=positions[a];xx,yy=positions[b];self.scene.addLine(x+188,y+38,xx,yy+38,G.QPen(G.QColor('#50647e'),1.4))
            self.scene.addPolygon(G.QPolygonF([C.QPointF(xx,yy+38),C.QPointF(xx-7,yy+34),C.QPointF(xx-7,yy+42)]),G.QPen(G.QColor('#50647e')),G.QBrush(G.QColor('#50647e')))
        for key,text,col,row in cards:
            state=self.states.get(key,{});verified=state.get('state')=='verified'
            color='#695520' if verified and key=='factory-td3' else '#185c55' if verified else '#27354b';x,y=positions[key]
            self.scene.addRect(x,y,188,78,G.QPen(G.QColor('#42b6a6' if verified else '#53637b')),G.QBrush(G.QColor(color)))
            grade='SMOKE ĐẠT / TASK CHƯA RÕ' if verified and key=='factory-td3' else 'ĐẠT PHẦN MỀM' if verified and key!='sysid' else 'CẦN REVIEW' if verified else 'CHỜ BẰNG CHỨNG'
            item=self.scene.addText(text+'\n'+grade,G.QFont('DejaVu Sans',9))
            item.setDefaultTextColor(G.QColor('#e7edf7'));item.setTextWidth(180);item.setPos(x+3,y+1)
            item.setToolTip(state.get('path') or ('Gate triển khai chưa mở; không tự tăng authority' if key=='hardware' else state.get('error','Chưa có artifact')))
        self.scene.setSceneRect(-5,-5,1020,195)
        C.QTimer.singleShot(0,self.fit_diagram)
    def fit_diagram(self):
        if hasattr(self,'diagram'):self.diagram.fitInView(self.scene.sceneRect(),C.Qt.KeepAspectRatio)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        C.QTimer.singleShot(0,self.fit_diagram)
    def refresh(self):
        locked=self.busy or self.hardware_busy() or self.external_busy or self.closing
        if hasattr(self,'trainer'):self.trainer.refresh()
        for action,b in self.buttons.items():
            ready=all(self.states.get(dep,{}).get('state')=='verified' for dep in JOBS[action][1])
            if action=='sim-gain-baselines':ready=ready and not locked and not guided_td3_consumed(self.root,action) and gain_baseline_release_ready(self.root)
            if action=='sim-ready-eval-only':ready=ready and not locked and not guided_td3_consumed(self.root,action) and ready_eval_release_ready(self.root)
            if action=='sim-drive-readiness':ready=ready and not locked and not guided_td3_consumed(self.root,action) and drive_readiness_release_ready(self.root)
            if action in ('sim-coverage-study','sim-coverage-v2-study'):ready=ready and not locked and not guided_td3_consumed(self.root,action) and coverage_release_ready(self.root,action)
            if action=='sim-joint-reliability-gazebo':ready=ready and joint_reliability_fixture_ready(self.root)
            if action=='sysid':ready=ready and (self.root/'registration.json').is_file()
            complete=guided_td3_consumed(self.root,action) or (action.startswith('sim-v2-') or action in ('sim-bias-clear','sim-guidance-contract','sim-v3-baselines','sim-guided-contact')) and self.states.get(action,{}).get('state')=='verified'
            if action in ('sim-coverage-preflight','sim-coverage-v2-preflight') and self.states.get(action,{}).get('state')=='verified':complete=True
            b.setEnabled(not locked and self.error is None and ready and not complete)
        self.register_button.setEnabled(not locked and self.error is None);self.stop.setEnabled(self.runner.busy and not self.runner.cancelling)
        for action,button in self.sim_buttons.items():
            ready=all(self.states.get(dep,{}).get('state')=='verified' for dep in JOBS[action][1])
            state=self.states.get(action,{})
            if action=='sim-gain-baselines':ready=ready and not locked and not guided_td3_consumed(self.root,action) and gain_baseline_release_ready(self.root)
            if action=='sim-ready-eval-only':ready=ready and not locked and not guided_td3_consumed(self.root,action) and ready_eval_release_ready(self.root)
            if action=='sim-drive-readiness':ready=ready and not locked and not guided_td3_consumed(self.root,action) and drive_readiness_release_ready(self.root)
            if action in ('sim-coverage-study','sim-coverage-v2-study'):ready=ready and not locked and not guided_td3_consumed(self.root,action) and coverage_release_ready(self.root,action)
            if action=='sim-joint-reliability-gazebo':ready=ready and joint_reliability_fixture_ready(self.root)
            complete=guided_td3_consumed(self.root,action) or (action.startswith('sim-v2-') or action in ('sim-bias-clear','sim-guidance-contract','sim-v3-baselines','sim-guided-contact')) and state.get('state')=='verified'
            if action in ('sim-coverage-preflight','sim-coverage-v2-preflight') and state.get('state')=='verified':complete=True
            button.setEnabled(not locked and self.error is None and ready and not complete)
            button.setToolTip('Stage đã đóng; bấm Xem kết quả. Không tự chạy lại ngân sách cũ.' if complete else JOBS[action][0])
            self.sim_status[action].setText(state.get('label','CHƯA KIỂM')+(' · chờ bước trước' if not ready and not complete else ''))
            if action in ('sim-coverage-study','sim-coverage-v2-study') and self.states.get(JOBS[action][1][0],{}).get('state')=='verified' and not ready and not complete:
                self.sim_status[action].setText('PREFLIGHT ĐÃ ĐẠT · STUDY CHƯA RELEASE · chưa tiêu thụ training budget')
            self.sim_status[action].setStyleSheet('color:#b34732;font-weight:600' if state.get('state')=='retained_failure' else '')
            self.sim_status[action].setToolTip(str(state.get('path') or state.get('error','Chưa có artifact')))
        self.sim_location.setText('Thư mục kết quả: '+str(self.root)+' · đổi tại tab Công cụ kiểm phần mềm.')
        self.sim_stop.setEnabled(self.runner.busy and self.runner.action.startswith('sim-') and not self.runner.cancelling)
        self.sim_version.setEnabled(not locked)
        active=self.active_sim_actions()
        for action,widget in self.sim_rows.items():widget.setVisible(action in active)
        self.sim_note.setText('Chỉ Gazebo local · không cần Pi/real dataset. '+('V2: reward bám profile chuẩn độc lập; không thưởng progress. 14 s/lượt gồm 6 s pha dừng. B0 2 lượt/môi trường; train 512 bước; evaluate 2 lượt/arm. Một seed, chưa hội tụ hoặc promote.' if active[0].startswith('sim-v2-') else 'V1 lịch sử: progress reward, horizon 10 s, train 256 bước. TD3 từng tăng tốc; dừng nguồn chưa bảo đảm thân dừng. Giữ nguyên kết quả cũ.'))
        if active[0]=='sim-bias-clear':self.sim_note.setText('Checkpoint V2 đóng băng, 4 lượt clear floor, zero optimizer updates. Tách bias policy khỏi gờ. Bước 2 kiểm adapter pose ước lượng → follower → reference → residual; chưa có Gazebo guidance hoặc localization/hardware được xác nhận.')
        if active[0]=='sim-guided-contact':self.sim_note.setText('Guided baseline clear/gờ cylinder 6 mm, tối đa 4 lượt/560 transition. Tuyến thẳng; cùng estimator/PI/limits V3. Gate fail đóng các slot còn lại. Không train hoặc hardware.')
        if active[0]=='sim-v3-contract':self.sim_note.setText('TD3 V3 · cùng guided baseline; head actor zero-init, h5/100D và reward nominal velocity/yaw. 512 train transition/seed 7, rồi B0/TD3 × clear/gờ 6 mm × 2 = 8 lượt. Zero-init không làm warmup/exploration thành zero. Không real data hoặc hardware.')
        if active[0]=='sim-axis-ablation':self.sim_note.setText('Ablation clear floor · B0 / TD3 full / cùng actor common-only × 2 = tối đa 6 lượt / 840 transition. Checkpoint khóa hash; không optimizer. Common-only đặt proposal vi sai bằng zero, giữ yaw follower. Không đổi trọng số, không xuất replay TD3 từ masked action.')
        if active[0]=='sim-gain-baselines':self.sim_note.setText('9 baseline cells: gain1 trước rồi0,98/1,02; B0/fixed/causal, stop8s. Gain chỉ metadata của evaluator. Tối đa1260ticks, lỗi đóng mọi slot còn lại. Không actor/optimizer/retry/hardware. Một run/cell chỉ screening mô tả.')
        if active[0]=='sim-ready-eval-only':self.sim_note.setText('Eval-only: A seed11 đã train hoàn tất / B0 / cổ điển, stop6/8; tối đa6fresh launches/840ticks. Cùng reset drive ACK, 103D/1D/history5/10Hz. Không học/probe/retry/hardware; không resume C partial. Một failure đóng phần còn lại.')
        if active[0]=='sim-drive-readiness':self.sim_note.setText('Candidate riêng: reset chỉ qua khi drive ACK + fresh zero và physical quiet trong cùng cap5s. Tối đa2fresh launches/20zero ticks,0actor/optimizer/retry/hardware. Không reopen V2; xem kết quả trước eval-only.')
        if active[0]=='sim-coverage-preflight':self.sim_note.setText('Coverage: A Gaussian và C probe phân tầng; 103D/1D, history5, warmup64. Đề xuất6144 train +2240 eval /64 launches; cùng5760 critic/2880 actor updates. Preflight chỉ software fixture, không Gazebo. Study bị khóa tới release pin nguồn và preflight.')
        if active[0]=='sim-coverage-preflight' and guided_td3_consumed(self.root,'sim-coverage-study'):
            self.sim_note.setText('V1 đã tiêu thụ attempt và đóng; không retry, resume hoặc dùng lại slot còn dư. Bảng phân biệt raw control attempts với replay/update hợp lệ. Xem lỗi và correction offline trước protocol V2 riêng; chưa mở budget mới.')
        if active[0]=='sim-coverage-v2-preflight':self.sim_note.setText('V2: correction metadata condition trước validator thật; scientific design giữ nguyên103D/1D, history5, 2arm×3seed×1024 +16eval×140. Root/budget riêng, tối đa64launches, không retry/smoke ngoài. Preflight kiểm full train trên plant synthetic; chưa chứng minh Gazebo hoặc lợi ích TD3.')
        if active[0]=='sim-coverage-v2-preflight' and not self.runner.busy and guided_td3_consumed(self.root,'sim-coverage-v2-study'):self.sim_note.setText('V2 đã tiêu thụ hoặc root không tương thích. Giữ artifact và đóng slot; không retry/resume. Xem kết quả/lỗi và QC trước khi quyết định bước mới.')
        if active[0]=='sim-reliable-eval-only':self.sim_note.setText('Evaluation-only: dùng ba final checkpoints đã train đủ, không optimizer hoặc train mới. 10 fresh launches × 140 ticks = tối đa 1.400. B0 / cổ điển / TD3 cùng 103D/1D, history 5 và lifecycle RELIABLE; stop 6/8 s. Native và GT-header giữ riêng. Một lỗi đóng slot còn lại; chưa promote/hardware.')
        if active[0]=='sim-reliable-td3':self.sim_note.setText('Fresh TD3 103D/1D, history 5, common ±0,005 m/s. Joint RELIABLE; backend/context/observer/partition mới mỗi episode. Tối đa 3.072 train + 1.400 eval / 34 launches. Một lỗi đóng mọi slot còn lại; không resume partial cũ, không hardware. Clear-box factory lab, chưa mixed/contact generalization.')
        if active[0]=='sim-joint-reliability-fixture':self.sim_note.setText('Một candidate joint RELIABLE riêng. Stage1:1000syntheticJointState/500Hz +1handshake,2readers và pause100ms, không Gazebo. Stage2 chỉ khi fixturecompatible: B0 clear stop6/8,2launches/280ticks. Giữ40ms/PI/physics/reward; không optimizer hoặc tăng training budget.')
        if active[0]=='sim-joint-boundary':self.sim_note.setText('Zero-only joint diagnostic · tối đa2fresh launches/200native ticks, cùng model/PI/physics1ms/chunk50ms. Observer ROS riêng chỉ đọc; primary có log hash bổ sung. Không actor/optimizer/forward source. Endpoint age40ms; timeout đóng slot. Cần phân biệt source/DDS/consumer, không tự sửa reward hoặc tăng training.')
        if active[0]=='sim-common-td3':self.sim_note.setText('Fresh common-only103D/1D · clear box · stop6/8 xen kẽ. 3seed ×1024train +10fresh eval = tối đa4472controlticks/34launches; CPU32², warmup64. Fail đóng slot còn lại. Không thêm smoke, không hardware. B0/cổ điển/TD3 cùng preview/window; chưa minimum effect được chấp nhận.')
        if active[0]=='sim-equal-gazebo':self.sim_note.setText('Gazebo qualification103D/1D ·4fresh launches/560ticks tối đa, clear box/yaw0/cruise0,2m/s. B0/cổ điển/probe stop6s và probe stop8s; cùng PI/estimator/follower. Source/parity/physical/measurement fail đóng slot chưa chạy. Không actor, optimizer hoặc hardware.')
        if active[0]=='sim-equal-contract':self.sim_note.setText('Contract103D/1D · cùng preview lịch dừng6/8s, common-only±0,005m/s và shared window. Chỉ fixture tổng hợp/replay/save-load; không physics hoặc optimizer. Đây là ABI mới, không resume V3; không coi840 fixture steps là840 bước Gazebo.')
        if active[0]=='sim-stop-transfer':self.sim_note.setText('Chuyển lịch dừng6s · B0 / common +0,005m/s rút5,5s ×3 = tối đa6 lượt/840 ticks. Giữ clear fixture, h5, estimator/follower/projection/PI. Header grids định trước; fail/unknown giữ B0. Không actor/optimizer/hardware.')
        if active[0]=='sim-classical-common':self.sim_note.setText('Đối chứng common cổ điển · B0 / +0,005m/s với planned withdrawal / frozen V3 common-only ×2 = tối đa6 lượt,840 tick. Rút bù7,5s trước source stop8s; giữ giới hạn ramp. Không train, không hardware; map clear fixture đã xem.')
        if active[0]=='sim-v3-baselines':self.sim_note.setText('V3 · 8 lượt clear floor: constant / guided × tuyến ±5° × 2 lần. Estimator causal chỉ wheel+IMU, initial pose theo metadata scenario; không đọc GT để điều khiển. Task 14 s, residual zero, không actor hoặc optimizer.')
    def run(self,action):
        if action.startswith('sim-'):self.sim_log.document().setMaximumBlockCount(300)
        if self.busy or self.hardware_busy() or self.external_busy or self.closing:return
        try:
            if self.runner.start(action):self.sections.setCurrentIndex(3 if action.startswith('sim-') else 1);self.progress.setValue(0);self.log.clear();self.output_tabs.setCurrentIndex(2);self.next.setText('Đang chạy '+JOBS[action][0]+' · đợi process đóng và manifest được kiểm');self.refresh()
        except (ValueError,OSError) as exc:self.next.setText('Chưa chạy: '+str(exc))
    def handle(self,event):
        if event.get('message'):self.log.appendPlainText(event['message'])
        if event.get('message') and (self.runner.action or '').startswith('sim-'):
            self.sim_log.appendPlainText(event['message'])
            if self.runner.busy and event.get('state')!='closed':
                self.sim_next.setText('Đang chạy '+JOBS[self.runner.action][0]+' · '+event['message'])
                if event.get('progress') is None:self.sim_progress.setRange(0,0)
        if event.get('progress') is not None:self.progress.setValue(int(event['progress']*100))
        if event.get('progress') is not None and (self.runner.action or '').startswith('sim-'):
            self.sim_progress.setRange(0,100)
            self.sim_progress.setValue(int(event['progress']*100))
        if event.get('state')=='progress' and event.get('action')=='factory-td3' and event.get('message'):
            self.next.setText('FACTORY · '+event['message']+' · chỉ mô phỏng; chờ process đóng và kiểm manifest.')
        if self.active_sim_actions()[0]=='sim-gain-baselines' and self.runner.action=='sim-gain-baselines':self.show_gain_baseline_table(self.states.get('sim-gain-baselines',{}))
        if self.active_sim_actions()[0]=='sim-ready-eval-only' and self.runner.action=='sim-ready-eval-only':self.show_ready_eval_table(self.states.get('sim-ready-eval-only',{}))
        if self.active_sim_actions()[0] in ('sim-coverage-preflight','sim-coverage-v2-preflight') and (self.runner.action or '').startswith('sim-coverage-'):self.show_coverage_table()
        if event.get('result'):
            body=json.dumps(event['result'],ensure_ascii=False,indent=2)
            self.results.setPlainText(body)
            if (event.get('action') or '').startswith('sim-'):self.sim_log.appendPlainText(body)
        if event.get('state')=='closed':
            self.reload()
            self.output_tabs.setCurrentIndex(1)
            if event.get('returncode')!=0:self.next.setText('Job lỗi/hủy; artifact được giữ. Đọc log và sửa đúng nguyên nhân; không tự retry hoặc coi là pass.')
        self.refresh()
    def job_closed(self):
        if self.closing and not self.active:self.all_closed.emit()
    def show_sim_result(self,action):
        # Static reports must retain their beginning as well as their last runs.
        # The bounded live log limit is restored when starting the next job.
        self.sim_log.document().setMaximumBlockCount(0)
        state=self.states.get(action,{})
        if not state.get('path'):
            self.sim_log.setPlainText(state.get('error','Chưa có artifact'));return
        names={'sim-baselines':'baseline_result.json','sim-train':'training_result.json','sim-evaluate':'evaluation_result.json'}
        names.update({'sim-v2-baselines':'baseline_result.json','sim-v2-train':'training_result.json','sim-v2-evaluate':'evaluation_result.json'})
        names.update({'sim-bias-clear':'evaluation_result.json','sim-guidance-contract':'guidance_result.json'})
        names.update({'sim-v3-baselines':'evaluation_result.json','sim-guided-contact':'evaluation_result.json','sim-v3-contract':'contract_result.json','sim-v3-train':'training_result.json','sim-v3-evaluate':'evaluation_result.json'})
        names['sim-axis-ablation']='evaluation_result.json'
        names['sim-classical-common']='evaluation_result.json'
        names['sim-stop-transfer']='evaluation_result.json'
        names['sim-equal-contract']='qualification.json'
        names['sim-equal-gazebo']='qualification_result.json'
        names['sim-gain-baselines']='job.json' if state.get('state')=='retained_failure' else 'evaluation_result.json'
        names['sim-ready-eval-only']='job.json' if state.get('state')=='retained_failure' else 'evaluation_result.json'
        names['sim-drive-readiness']='job.json' if state.get('state')=='retained_failure' else 'qualification_result.json'
        names['sim-coverage-v2-preflight']='preflight_result.json'
        names['sim-coverage-v2-study']='study_result.json'
        names['sim-coverage-preflight']='preflight_result.json'
        names['sim-coverage-study']='study_result.json'
        if action in ('sim-coverage-preflight','sim-coverage-study','sim-coverage-v2-preflight','sim-coverage-v2-study') and state.get('state')=='retained_failure':names[action]='job.json'
        names['sim-reliable-eval-only']='evaluation_result.json'
        names['sim-reliable-td3']='pilot_result.json'
        names['sim-common-td3']='pilot_result.json'
        names['sim-joint-boundary']='diagnostic_result.json'
        names['sim-joint-reliability-fixture']='fixture_result.json'
        names['sim-joint-reliability-gazebo']='qualification_result.json'
        if action=='sim-reliable-eval-only' and state.get('state')=='retained_failure':
            names[action]='evaluation_progress.json'
        if action=='sim-reliable-td3' and state.get('state')=='retained_failure':
            names[action]='job.json'
        if action=='sim-common-td3' and state.get('state')=='retained_failure':
            self.sim_log.setPlainText(str(state['path'])+'\n'+(self.root/'review.json').read_text());return
        if action in ('sim-coverage-preflight','sim-coverage-study','sim-coverage-v2-preflight','sim-coverage-v2-study') and state.get('state')=='retained_failure':
            try:self.sim_log.setPlainText(self.coverage_failure_text(state))
            except (OSError,ValueError,KeyError,TypeError) as exc:self.sim_log.setPlainText(str(exc))
            return
        try:self.sim_log.setPlainText(str(state['path'])+'\n'+(Path(state['path'])/names[action]).read_text())
        except OSError as exc:self.sim_log.setPlainText(str(exc))
    def coverage_failure_text(self,state):
        path=Path(state['path']).resolve()
        body=str(path)+'\nRaw job (sealed):\n'+(path/'job.json').read_text()
        review_path=self.root/'review.json'
        if review_path.is_file():
            review=json.loads(review_path.read_text())
            if (review.get('artifact')==str(path) and review.get('artifact_manifest_sha256')==
                    hashlib.sha256((path/'manifest.json').read_bytes()).hexdigest()):
                body+='\nDerived audit bound to manifest; not a promotion:\n'+json.dumps(review,ensure_ascii=False,indent=2)
        return body
    def request_close(self):
        self.closing=True;self.runner.cancel()
        if hasattr(self,'trainer'):self.trainer.request_close()
        self.refresh()
    def show_result(self,row,column):
        self.sections.setCurrentIndex(1)
        action=list(JOBS)[row];state=self.states.get(action,{})
        if not state.get('path'):self.results.setPlainText(state.get('error','Chưa có dữ liệu'));return
        path=Path(state['path']);names={'validate':'validation.json','train-td3':'training_result.json','audit-td3':'audit.json','train-ppo':'training_result.json',
            'compare':'comparison.json','ros-fixture':'ros_result.json','gazebo-fixture':'gazebo_result.json','factory-td3':'factory_result.json','sysid':'sysid_result.json',
            'sim-baselines':'baseline_result.json','sim-train':'training_result.json','sim-evaluate':'evaluation_result.json'}
        names.update({'sim-v2-baselines':'baseline_result.json','sim-v2-train':'training_result.json','sim-v2-evaluate':'evaluation_result.json'})
        names.update({'sim-bias-clear':'evaluation_result.json','sim-guidance-contract':'guidance_result.json'})
        names.update({'sim-v3-baselines':'evaluation_result.json','sim-guided-contact':'evaluation_result.json','sim-v3-contract':'contract_result.json','sim-v3-train':'training_result.json','sim-v3-evaluate':'evaluation_result.json'})
        names['sim-axis-ablation']='evaluation_result.json'
        names['sim-classical-common']='evaluation_result.json'
        names['sim-stop-transfer']='evaluation_result.json'
        names['sim-equal-contract']='qualification.json'
        names['sim-equal-gazebo']='qualification_result.json'
        names['sim-gain-baselines']='job.json' if state.get('state')=='retained_failure' else 'evaluation_result.json'
        names['sim-ready-eval-only']='job.json' if state.get('state')=='retained_failure' else 'evaluation_result.json'
        names['sim-drive-readiness']='job.json' if state.get('state')=='retained_failure' else 'qualification_result.json'
        names['sim-coverage-v2-preflight']='preflight_result.json'
        names['sim-coverage-v2-study']='study_result.json'
        names['sim-coverage-preflight']='preflight_result.json'
        names['sim-coverage-study']='study_result.json'
        if action in ('sim-coverage-preflight','sim-coverage-study','sim-coverage-v2-preflight','sim-coverage-v2-study') and state.get('state')=='retained_failure':names[action]='job.json'
        names['sim-reliable-eval-only']='evaluation_result.json'
        names['sim-reliable-td3']='pilot_result.json'
        names['sim-common-td3']='pilot_result.json'
        names['sim-joint-boundary']='diagnostic_result.json'
        names['sim-joint-reliability-fixture']='fixture_result.json'
        names['sim-joint-reliability-gazebo']='qualification_result.json'
        if action=='sim-reliable-eval-only' and state.get('state')=='retained_failure':
            names[action]='evaluation_progress.json'
        if action=='sim-reliable-td3' and state.get('state')=='retained_failure':
            names[action]='job.json'
        if action=='sim-common-td3' and state.get('state')=='retained_failure':
            self.results.setPlainText((self.root/'review.json').read_text());return
        if action in ('sim-coverage-preflight','sim-coverage-study','sim-coverage-v2-preflight','sim-coverage-v2-study') and state.get('state')=='retained_failure':
            try:self.results.setPlainText(self.coverage_failure_text(state));self.output_tabs.setCurrentIndex(1)
            except (OSError,ValueError,KeyError,TypeError) as exc:self.results.setPlainText(str(exc))
            return
        try:
            body=(path/names[action]).read_text();notice=''
            if action=='factory-td3':notice='SMOKE TÍCH HỢP ĐẠT. Task/vượt vật cản và learned benefit chưa được xác nhận.\n\n'
            self.results.setPlainText(notice+str(path)+'\n'+body);self.output_tabs.setCurrentIndex(1)
        except OSError as exc:self.results.setPlainText('Thiếu kết quả: '+str(exc))
    def register(self):
        try:
            csv_path,_=Q.QFileDialog.getOpenFileName(self,'CSV đáp ứng bánh · giữ nguyên raw bag','','CSV (*.csv)')
            if not csv_path:return
            meta,_=Q.QFileDialog.getOpenFileName(self,'Metadata SI / clock / holdout · xem residual_sysid.template.json','','JSON (*.json)')
            if not meta:return
            from nino_rl.residual_sysid import register
            register(self.root,csv_path,meta);self.results.setPlainText((self.root/'registration.json').read_text());self.reload()
        except (OSError,ValueError,KeyError,ImportError) as exc:self.next.setText('Chưa đăng ký: '+str(exc))
