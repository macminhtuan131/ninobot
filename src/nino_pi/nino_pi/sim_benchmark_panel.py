"""Read-only benchmark decision and future gates; never starts collection/jobs."""
import json
from pathlib import Path
from PyQt5 import QtCore as C, QtGui as G, QtWidgets as Q


class SimBenchmarkPanel(Q.QWidget):
    def __init__(self,parent=None,load_on_init=True):
        super().__init__(parent)
        layout=Q.QVBoxLayout(self)
        title=Q.QLabel('SIM · Quyết định benchmark trước khi train tiếp')
        title.setStyleSheet('font-size:20px;font-weight:700');layout.addWidget(title)
        self.status=Q.QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.assessment_metrics=Q.QTableWidget(0,4)
        self.assessment_metrics.setHorizontalHeaderLabels(['Stop (s)','TD3 20k','TD3 30k','Classical / block30k'])
        self.assessment_metrics.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.assessment_metrics.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Stretch)
        self.assessment_metrics.setVisible(False);layout.addWidget(self.assessment_metrics)
        self.assessment_report=Q.QPushButton('Mở phân tích offline 20k / 25k / 30k')
        self.assessment_report.clicked.connect(lambda:self.document('NINO_TD3_OFFLINE_PHASE_REVIEW_2026-11-07.md'))
        self.assessment_report.setVisible(False);layout.addWidget(self.assessment_report)
        self.gates=Q.QTableWidget(4,3)
        self.gates.setHorizontalHeaderLabels(['Bước','Trạng thái','Đầu ra / điều kiện chuyển bước'])
        self.gates.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.gates.setWordWrap(True)
        self.gates.horizontalHeader().setSectionResizeMode(0,Q.QHeaderView.ResizeToContents)
        self.gates.horizontalHeader().setSectionResizeMode(1,Q.QHeaderView.ResizeToContents)
        self.gates.horizontalHeader().setSectionResizeMode(2,Q.QHeaderView.Stretch)
        self.gates.setMinimumHeight(285);layout.addWidget(self.gates)
        self.scope=Q.QLabel();self.scope.setWordWrap(True);layout.addWidget(self.scope)
        self.cost=Q.QTableWidget(0,6)
        self.cost.setHorizontalHeaderLabels(['Arm / stop','Tick mở','Tick đóng','Khoảng mở (s)','Cost khi mở (%)','Cost khi đóng (%)'])
        self.cost.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.cost.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Stretch)
        self.cost.setMinimumHeight(240);layout.addWidget(self.cost)
        self.limits=Q.QLabel();self.limits.setWordWrap(True);layout.addWidget(self.limits)
        buttons=Q.QHBoxLayout()
        self.refresh=Q.QPushButton('Kiểm lại hồ sơ offline');self.refresh.clicked.connect(self.reload);buttons.addWidget(self.refresh)
        self.decision=Q.QPushButton('Mở quyết định benchmark');self.decision.clicked.connect(lambda:self.document('NINO_SIM_BENCHMARK_DECISION_2026-11-06.md'));buttons.addWidget(self.decision)
        self.protocol=Q.QPushButton('Mở qualification baseline dự kiến');self.protocol.clicked.connect(lambda:self.document('NINO_SIM_GAIN_BASELINE_QUALIFICATION_DRAFT_2026-11-06.md'));buttons.addWidget(self.protocol)
        layout.addLayout(buttons)
        self.context_result=Q.QPushButton('Xem kết quả backend/context gain · parity offline')
        self.context_result.clicked.connect(lambda:self.document('NINO_SIM_GAIN_CONTEXT_OFFLINE_RESULT_2026-11-06.md'))
        layout.addWidget(self.context_result)
        self.gain_result=Q.QPushButton('Xem qualification gain trong Gazebo · kết quả / giới hạn')
        self.gain_result.clicked.connect(lambda:self.document('NINO_SIM_GAIN_BASELINE_RESULT_2026-11-06.md'))
        layout.addWidget(self.gain_result)
        self.held_status=Q.QLabel();self.held_status.setWordWrap(True);layout.addWidget(self.held_status)
        self.held_result=Q.QPushButton('Tiến độ hiện tại / correction offline / việc còn lại')
        self.held_result.clicked.connect(lambda:self.document('NINO_SIM_STATUS_AND_TODO_2026-11-07.md'))
        layout.addWidget(self.held_result)
        self.dynamics_status=Q.QLabel();self.dynamics_status.setWordWrap(True);layout.addWidget(self.dynamics_status)
        self.dynamics_result=Q.QPushButton('Dynamics: kết quả / raw UNKNOWN / đề xuất wheel PI')
        self.dynamics_result.clicked.connect(lambda:self.document('NINO_SIM_DYNAMICS_AUDIT_RESULT_2026-11-07.md'))
        layout.addWidget(self.dynamics_result)
        self.pi_status=Q.QLabel();self.pi_status.setWordWrap(True);layout.addWidget(self.pi_status)
        self.pi_draft=Q.QPushButton('PI screen · kết quả software / bước tiếp theo')
        self.pi_draft.clicked.connect(lambda:self.document('NINO_SIM_PI_SCREEN_OFFLINE_RESULT_2026-11-07.md'))
        layout.addWidget(self.pi_draft)
        self.pi_runner_status=Q.QLabel();self.pi_runner_status.setWordWrap(True);layout.addWidget(self.pi_runner_status)
        self.pi_runner_protocol=Q.QPushButton('PI runner · protocol, ledger và điều kiện chạy')
        self.pi_runner_protocol.clicked.connect(lambda:self.document('NINO_SIM_PI_SCREEN_RUNNER_PROTOCOL_2026-11-07.md'))
        layout.addWidget(self.pi_runner_protocol)
        self.pi_screen_status=Q.QLabel();self.pi_screen_status.setWordWrap(True);layout.addWidget(self.pi_screen_status)
        self.pi_metrics=Q.QTableWidget(0,6)
        self.pi_metrics.setHorizontalHeaderLabels(['Cell / Ki','Native (mm/s)','GT20ms (mm/s)','GT+10ms (mm/s)','Path RMSE (mm)','Task / stop'])
        self.pi_metrics.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.pi_metrics.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Stretch)
        layout.addWidget(self.pi_metrics)
        self.pi_screen_result=Q.QPushButton('PI screen stop8s · kết quả Gazebo đã đóng / giới hạn')
        self.pi_screen_result.clicked.connect(lambda:self.document('NINO_SIM_PI_SCREEN_RESULT_2026-11-07.md'))
        layout.addWidget(self.pi_screen_result);layout.addStretch(1)
        # Latest measured outcome belongs before the historical benchmark rows.
        for index,widget in enumerate((self.pi_screen_status,self.pi_metrics,self.pi_screen_result),2):
            layout.removeWidget(widget);layout.insertWidget(index,widget)
        self.pi_validation_status=Q.QLabel();self.pi_validation_status.setWordWrap(True)
        layout.insertWidget(2,self.pi_validation_status)
        self.pi_validation_protocol=Q.QPushButton('Validation stop6s · protocol / kiểm offline / bước tiếp theo')
        self.pi_validation_protocol.clicked.connect(lambda:self.document('NINO_SIM_PI_STOP6_VALIDATION_PREPARATION_2026-11-07.md'))
        layout.insertWidget(3,self.pi_validation_protocol)
        self.td3_training_status=Q.QLabel();self.td3_training_status.setWordWrap(True)
        layout.insertWidget(2,self.td3_training_status)
        self.verified=False
        if load_on_init:self.reload()
        else:
            self.status.setText('Chưa kiểm hồ sơ benchmark. Mở trang này để kiểm artifact; training không chờ quét lịch sử.')
            self.limits.setText('Chưa có kết quả xác minh trong lần mở này; trang chỉ đọc.')
            for widget in (self.pi_screen_status,self.pi_metrics,self.pi_screen_result,
                    self.pi_validation_status,self.pi_validation_protocol,self.td3_training_status):widget.setVisible(False)

    def latest_td3_training_record(self,plan):
        from .studio_training_evidence import completed_training
        completed=completed_training(plan)
        if completed:return completed
        record=plan.get('td3_training_evidence')
        if not record:return None
        import hashlib
        path=Path(record['training_result'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['training_result_sha256']:
            raise ValueError('TD3 training counter artifact changed')
        actual=json.loads(path.read_text())
        for key in ('seed','training_transitions','critic_updates','actor_updates'):
            if actual[key]!=record[key]:raise ValueError('TD3 training counter mismatch: '+key)
        return actual

    def latest_pi_validation_record(self,plan):
        snapshot=plan.get('sim_pi_stop_validation_preflight')
        if not snapshot:return None
        from nino_rl.pi_stop_validation_preflight import verified_report,job
        out=Path(snapshot['artifact'])
        if job.parent.sha(out/'manifest.json')!=snapshot['manifest_sha256']:
            raise ValueError('Stop6 validation offline manifest changed')
        report=verified_report(out);release=job.release_record()
        if release['released'] is not False or release['allocated_physics_slots']!=0:
            raise ValueError('Stop6 validation release changed; needs a reviewed runtime stage')
        if (release['fingerprint']!=job.fingerprint()
                or release['protocol_sha256']!=report['protocol_sha256']
                or Path(snapshot['result_root']).exists()):
            raise ValueError('Stop6 validation preparation/source/root changed')
        return report

    def latest_held_record(self,plan):
        if not plan.get('sim_held_gain_offline'):return None
        from nino_rl.held_gain_preflight import verified_report
        return verified_report(Path(plan['sim_held_gain_offline']['artifact']))

    def latest_dynamics_record(self,plan):
        if not plan.get('sim_chain_dynamics_audit'):return None
        from nino_rl.sim_chain_dynamics_audit_v2 import verified_report
        return verified_report(Path(plan['sim_chain_dynamics_audit']['artifact']))

    def latest_pi_record(self,plan):
        snapshot=plan.get('sim_pi_screen_preflight')
        if not snapshot:return None
        from nino_rl.pi_screen_preflight import verified_report,context
        root=Path(snapshot['artifact'])
        if context.benchmark.sha(root/'manifest.json')!=snapshot['manifest_sha256']:
            raise ValueError('PI software manifest differs from reviewed snapshot')
        return verified_report(root)

    def latest_pi_runner_record(self,plan):
        snapshot=plan.get('sim_pi_screen_runner_preflight')
        if not snapshot:return None
        from nino_rl.pi_screen_runner_preflight import verified_report,job
        root=Path(snapshot['artifact'])
        if job.parent.sha(root/'manifest.json')!=snapshot['manifest_sha256']:
            raise ValueError('PI runner manifest differs from reviewed snapshot')
        report=verified_report(root)
        if job.release_record()['released'] is not False:
            raise ValueError('PI release state changed; preparation view needs a new reviewed stage')
        return report

    def latest_pi_screen_record(self,plan):
        snapshot=plan.get('sim_pi_screen')
        if not snapshot:return None
        from nino_rl import pi_screen_runner as job
        root=Path(snapshot['result_root'])
        if snapshot['status']=='completed':out=job.validated_latest(root,check_runtime=False)
        else:
            failure=job.retained_failure(root)
            if failure is None:raise ValueError('PI failure artifact not verified')
            out=Path(failure['path'])
        if str(out)!=snapshot['artifact'] or job.parent.sha(out/'manifest.json')!=snapshot['manifest_sha256']:
            raise ValueError('PI screen manifest differs from reviewed result')
        path=Path(snapshot['audit'])
        if job.parent.sha(path)!=snapshot['audit_sha256']:raise ValueError('PI audit changed')
        report=job.parent.read(path)
        if report['manifest_sha256']!=snapshot['manifest_sha256']:raise ValueError('PI audit provenance mismatch')
        ambiguity=Path(snapshot['ambiguity_audit'])
        if job.parent.sha(ambiguity)!=snapshot['ambiguity_audit_sha256']:raise ValueError('PI ambiguity audit changed')
        return dict(report,source_ambiguity=job.parent.read(ambiguity))

    def latest_gain_record(self,plan):
        if not plan.get('sim_gain_baseline_qualification'):return None
        from nino_rl.gain_baseline_qualification import validated_latest,retained_failure
        root=Path(plan['sim_gain_baseline_qualification']['result_root'])
        try:
            out=validated_latest(root,check_runtime=False)
            result=json.loads((out/'evaluation_result.json').read_text())
            return dict(status='completed',cells=len(result['runs']),ticks=result['evaluation_transitions'],
                decision=result['comparison']['decision'],artifact=str(out))
        except (OSError,ValueError,KeyError,TypeError):
            failed=retained_failure(root)
            if failed is None:raise ValueError('Gain qualification chưa có artifact sealed hợp lệ')
            out=Path(failed['path']);progress=json.loads((out/'evaluation_progress.json').read_text())
            return dict(status='failed',cells=len(progress['runs']),
                ticks=sum(r['steps'] for r in progress['runs']),decision=failed['error'],artifact=str(out))

    def reload(self):
        self.cost.setRowCount(0);self.verified=False
        self.assessment_metrics.setRowCount(0);self.assessment_metrics.hide();self.assessment_report.hide()
        for row in range(4):
            for col in range(3):self.gates.setItem(row,col,Q.QTableWidgetItem('Chưa xác minh'))
        self.scope.setText('Không suy trạng thái hoàn thành từ việc có source/config.')
        self.limits.setText('Trang chỉ đọc hồ sơ; không train, chạy Gazebo, enable hoặc điều khiển robot.')
        self.held_status.setText('Correction hold/update: chưa xác minh artifact offline.')
        self.dynamics_status.setText('Dynamics audit: chưa xác minh artifact.')
        self.pi_status.setText('PI screen software: chưa xác minh artifact; physics chưa release.')
        self.pi_runner_status.setText('PI runner: chưa xác minh artifact; chưa có lượt physics mới.')
        self.pi_metrics.setRowCount(0)
        self.pi_screen_status.setText('PI screen: chưa xác minh outcome Gazebo.')
        self.pi_screen_status.setVisible(False);self.pi_metrics.setVisible(False);self.pi_screen_result.setVisible(False)
        self.pi_validation_status.setText('Validation stop6s: chưa xác minh phần chuẩn bị.')
        self.pi_validation_status.setVisible(False);self.pi_validation_protocol.setVisible(False)
        self.td3_training_status.clear();self.td3_training_status.setVisible(False)
        try:
            plan=json.loads(Path(__file__).with_name('research_plan.json').read_text())
            from .studio_training_evidence import scientific_assessment
            assessment=scientific_assessment(plan)
            if assessment:
                self.show_assessment(assessment)
                return
            from nino_rl.sim_benchmark_decision import verified_report
            report=verified_report(Path(plan['sim_benchmark_decision']['artifact']))
            self.status.setText('ĐÃ KIỂM OFFLINE · Bài sàn sạch có lịch dừng: giữ cổ điển.\n'
                'Đã chốt câu hỏi gain cố định chưa biết; baseline cổ điển đi trước. Chưa có qualification Gazebo mới hoặc lý do mở learner.')
            rows=[
                ('1 · Checkpoint pilot cũ','Đã eval 6/6','Checkpoint A sau1.024 train transitions có velocity RMSE cao hơn cổ điển. Một pilot ngắn/seed không kết luận TD3 đã hội tụ hoặc không thể thắng.'),
                ('2 · Thiết kế / đại số','Đã kiểm offline','Một yếu tố gain 0,98 / 1 / 1,02; causal encoder baseline dùng cùng 103D, không biết injected gain hoặc GT. Shadow chưa là outcome.'),
                ('3 · Backend / baseline','Chưa chạy; chưa release','Cần backend mới, gain=1 parity, telemetry requested/effective tách biệt. Draft tối đa 9 lượt / 1.260 tick; không có slot physics được mở ở đây.'),
                ('4 · Learning / holdout','Chưa mở','Chỉ xem xét nếu baseline mạnh còn khoảng trống và có useful authority. Ideal static gain có lời giải cổ điển; không tự tăng history hoặc chuyển sang PPO.')]
            for i,row in enumerate(rows):
                for j,value in enumerate(row):self.gates.setItem(i,j,Q.QTableWidgetItem(value))
                self.gates.setRowHeight(i,60)
            self.scope.setText('Cùng clear-box, nominal 0,2 m/s, common ±0,005 m/s, 10 Hz, history 5 / 103D. '
                'Dải gain ±2% là giả định nghiên cứu Sim, chưa đo trên robot. Hình dạng ABI giống nhau không cho phép nạp checkpoint cũ vào context mới.')
            self.cost.setRowCount(len(report['runs']))
            for i,r in enumerate(report['runs']):
                c=r['condition'];clock=f"{r['open_decision_first_s']:.1f}–{r['open_decision_last_s']:.1f}"
                values=[c['arm']+' / '+str(c['source_stop_s']),str(r['open_ticks']),str(r['closed_ticks']),clock,
                        f"{100*r['observed_open_cost_fraction']:.2f}",f"{100*r['observed_closed_cost_fraction']:.2f}"]
                for j,value in enumerate(values):self.cost.setItem(i,j,Q.QTableWidgetItem(value))
            self.limits.setText('Bảng phân rã error² trên trajectory cũ: không phải counterfactual, trần lợi ích hoặc metric thay primary. '
                'Gain estimator dùng encoder proxy, không là body speed/slip GT. Chưa có benefit mới, physics, training hoặc data thật; real cutoff 02/11.')
            if plan.get('sim_gain_context_preflight'):
                from nino_rl.gain_context_preflight import verified_report as gain_report
                gain=gain_report(Path(plan['sim_gain_context_preflight']['artifact']))
                self.status.setText(self.status.text()+'\nBackend/context gain: PARITY OFFLINE ĐẠT · chưa qualification Gazebo hoặc train mới.')
                self.gates.setItem(2,1,Q.QTableWidgetItem('Offline đạt; Gazebo chưa chạy'))
                self.gates.setItem(2,2,Q.QTableWidgetItem(
                    f"Kernel {gain['synthetic_driver_callbacks']:,} callbacks và wrapper {gain['synthetic_wrapper_transitions']} bước fixture đã đối chiếu; chỉ đổi một target-map call. "
                    'Giữ source lệnh trước gain; effective target là telemetry riêng. Tiếp runner/release cho draft 9 lượt, không train.'))
            qualification=self.latest_gain_record(plan)
            if qualification:
                self.status.setText('ĐÃ KIỂM OFFLINE + HỒ SƠ GAZEBO · '+qualification['decision']+
                    '\nGain là stress giả lập; chưa mở learner, holdout hoặc hardware.')
                self.gates.setItem(2,1,Q.QTableWidgetItem(
                    'Gazebo đã đóng9/9' if qualification['status']=='completed' else 'Gazebo đã đóng do lỗi'))
                self.gates.setItem(2,2,Q.QTableWidgetItem(
                    f"{qualification['cells']}/9 cell hoàn tất; {qualification['ticks']}/1260 tick của cell hoàn tất. "
                    'Xem từng gain/native/header/task ở profile Gain baseline. Không retry hoặc chạy bù.'))
                self.limits.setText(self.limits.text().replace('Chưa có benefit mới, physics, training hoặc data thật;',
                    'Đã có physics riêng; chưa xác nhận benefit/generalization/training hoặc data thật mới;'))
            held=self.latest_held_record(plan)
            if held:
                self.held_status.setText(f"CORRECTION OFFLINE ĐÃ ĐÓNG: {held['synthetic_decisions']} quyết định synthetic + "
                    f"{held['shadow_decisions']} shadow. Update và hold đã tách; reset/stop/stale xóa cache. "
                    'Nhận dạng gain còn UNKNOWN; shadow không là outcome. Chưa có Gazebo/TD3/hardware mới. '
                    'Đây là giai đoạn trước; xem dynamics và PI bên dưới để biết bước hiện tại.')
            dynamics=self.latest_dynamics_record(plan)
            if dynamics:
                fixed=[r for r in dynamics['runs'] if r['relaxation_models']['eligible']]
                target=[1000*r['raw_target_encoder_rmse_m_s'] for r in fixed]
                body=[1000*r['raw_encoder_body_rmse_m_s'] for r in fixed]
                if len(fixed)!=6:raise ValueError('Dynamics report lacks six declared classical plateaus')
                self.dynamics_status.setText(
                    f"DYNAMICS OFFLINE: {dynamics['native_rows_checked']} native rows giữ nguyên; "
                    f"{dynamics['complete_raw_query_cells']}/9 raw query đủ, {dynamics['unknown_raw_query_cells']} UNKNOWN. "
                    f"Giữ {dynamics['raw_conflicting_stamps']} conflicting stamps. RMS target→encoder {min(target):.2f}–{max(target):.2f} mm/s; "
                    f"encoder→body {min(body):.3f}–{max(body):.3f} mm/s trong 6 lượt classical. "
                    'Ưu tiên draft PI Sim; chưa đổi gain/current, chạy physics hoặc mở TD3.')
            pi=self.latest_pi_record(plan)
            if pi:
                self.pi_status.setText(
                    f"PI SOFTWARE ĐẠT: {pi['synthetic_kernel_callbacks']:,} callbacks kernel; "
                    f"{pi['synthetic_wrapper_transitions']} transitions wrapper synthetic. "
                    'Ki 0,10 giữ đúng state/effort/diagnostics/odom; candidate 0,15 đi vào kernel. '
                    'Fixture không đo đáp ứng plant. Tiếp runner/protocol/release riêng cho 4 lượt tối đa560ticks; '
                    'chưa chạy Gazebo, chưa train hoặc thay hardware.')
                self.status.setText(self.status.text()+'\nHIỆN TẠI: PI parity offline đạt; chuẩn bị bounded runner/release, chưa mở learner.')
            runner=self.latest_pi_runner_record(plan)
            if runner:
                self.pi_runner_status.setText(
                    f"PI RUNNER OFFLINE ĐẠT: {runner['synthetic_cells']} cell / {runner['synthetic_decisions']} decisions synthetic; "
                    'ledger đóng sau lỗi/hủy, chặn retry/root cũ và concurrent job. '
                    'Summary/timing/closure là fixture, không là outcome hoặc closure Gazebo. '
                    'Protocol Ki0,10→0,15→0,15→0,10, tối đa4lượt/560ticks đã chuẩn bị; '
                    'release=false, chưa cấp slot/chạy physics hoặc train TD3.')
                self.status.setText(self.status.text().replace(
                    'HIỆN TẠI: PI parity offline đạt; chuẩn bị bounded runner/release, chưa mở learner.',
                    'HIỆN TẠI: PI runner/protocol đã kiểm offline; tiếp review/release riêng, chưa chạy screen hoặc mở learner.'))
            screen=self.latest_pi_screen_record(plan)
            if screen:
                self.pi_screen_status.setVisible(True);self.pi_metrics.setVisible(True);self.pi_screen_result.setVisible(True)
                comparison=screen['comparison'];ambiguity=screen['source_ambiguity']
                decision=comparison['decision'] if comparison else 'unknown_incomplete_screen'
                native=[-100*p['relative_candidate_vs_baseline'][0] for p in comparison['pairs']] if comparison else []
                native_text=' / '.join(f'{x:.1f}%' for x in native) if native else 'UNKNOWN'
                self.pi_screen_status.setText(
                    f"PI GAZEBO STOP8s · SCREEN ĐÃ ĐÓNG: {screen['completed_cells']}/4 cell, {screen['valid_ticks']}/560 native ticks; {decision}. "
                    f"Native benefit theo block: {native_text}. Giữ {ambiguity['total_joint_conflicting_stamps']} conflicting joint stamps; "
                    'không có stamp đó trong native current/next wheel support; GT-header query không có payload conflict. '
                    'Không gọi toàn raw loss-free. Candidate chưa promote, chưa train/hardware; tiếp validation riêng.')
                self.pi_metrics.setRowCount(len(screen['metrics']))
                for i,r in enumerate(screen['metrics']):
                    values=[f"{r['condition']['cell']} / {r['condition']['ki']:.2f}",
                        f"{1000*r['native_vrmse_m_s']:.3f}",f"{1000*r['GT20ms_vrmse_m_s']:.3f}",
                        f"{1000*r['GTshift10ms_vrmse_m_s']:.3f}",f"{r['path_rmse_mm']:.3f}",
                        'Đạt' if r['task_pass'] else 'Không đạt / unknown']
                    for j,value in enumerate(values):self.pi_metrics.setItem(i,j,Q.QTableWidgetItem(value))
                self.pi_metrics.setMaximumHeight(165)
                title={'descriptive_PI_candidate_separate_validation_required':'Ki0,15 đạt screening mô tả; cần validation riêng'}.get(decision,decision)
                self.status.setText('HIỆN TẠI · PI SCREEN STOP8s GAZEBO ĐÃ ĐÓNG · '+title+
                    '\nCandidate Ki0,15 chỉ đạt screening mô tả trong envelope đã thử. Chưa promote hoặc mở TD3.')
                self.gates.setItem(2,1,Q.QTableWidgetItem('Gain9/9; PI'+str(screen['completed_cells'])+'/4'))
                self.gates.setItem(2,2,Q.QTableWidgetItem('PI screen: '+str(screen['valid_ticks'])+
                    '/560 ticks. Native và hai GT grids giữ riêng; xem bảng PI. Budget đã đóng, không retry.'))
                self.pi_status.setText(self.pi_status.text().split('Tiếp runner/protocol')[0]+'Giai đoạn offline trước; outcome Gazebo ở bên dưới.')
                self.pi_runner_status.setText('RUNNER: đã cấp và đóng4slots; offline proof vẫn giữ riêng khỏi outcome Gazebo. Không retry/training/hardware.')
                self.dynamics_status.setText(self.dynamics_status.text().replace(
                    'Ưu tiên draft PI Sim; chưa đổi gain/current, chạy physics hoặc mở TD3.',
                    'Đây là audit source cũ; PI screen mới ở bên dưới. Chưa đổi current/hardware hoặc mở TD3.'))
            validation=self.latest_pi_validation_record(plan)
            if validation:
                self.pi_validation_status.setVisible(True);self.pi_validation_protocol.setVisible(True)
                self.pi_validation_status.setText(
                    f"VALIDATION STOP6s · OFFLINE ĐẠT: {validation['software_tests_passed']} tests; "
                    f"{validation['synthetic_cells']} cell / {validation['synthetic_decisions']} decisions synthetic. "
                    'Đã kiểm lịch rút lệnh 6s; chưa đo đáp ứng plant ở lịch này. '
                    'Ki0,10/0,15, gain1, B0zero, horizon14s; đề xuất tối đa4launches/560ticks. '
                    'release=false, 0slot đã cấp, chưa chạy Gazebo/train/hardware. '
                    'Tiếp review/release riêng; không chạy lại screen8s đã đóng.')
                self.status.setText(self.status.text()+
                    '\nBƯỚC TIẾP: review/release validation stop6s đã chuẩn bị; chưa cấp budget, chưa promote Ki hoặc mở TD3.')
            training=self.latest_td3_training_record(plan)
            if training:
                self.td3_training_status.setVisible(True)
                if training.get('studio_completed'):
                    from .studio_training_evidence import continuation_summary
                    continuation=continuation_summary(plan)
                    next_message=continuation or 'Đề xuất continuation10k riêng, chưa chạy.'
                    self.td3_training_status.setText(
                        f"TD3 STUDIO ĐÃ HOÀN TẤT · seed{training['seed']}: {training['training_transitions']:,} transitions, "
                        f"{training['critic_updates']:,} critic / {training['actor_updates']:,} actor updates. "
                        'Counters đã kiểm bằng hash/result/manifest; hiệu quả xem báo cáo evaluation riêng. Chưa promote. '
                        'Một seed/seen conditions; chưa kết luận hội tụ. '+next_message)
                    self.status.setText(self.status.text().split('\nBƯỚC TIẾP:')[0]+
                        '\nBƯỚC TIẾP: '+next_message)
                    self.gates.setItem(3,2,Q.QTableWidgetItem(
                        'Pilot20k hoàn tất. Classical vẫn là baseline mạnh. '+next_message))
                else:
                    self.td3_training_status.setText(
                        f"TD3 ĐÃ TRAIN THẬT · A seed{training['seed']}: {training['training_transitions']:,} transitions, "
                        f"{training['critic_updates']} critic / {training['actor_updates']} actor updates. "
                        'Đây là pilot rất ngắn, chưa đủ để đánh giá hội tụ hay kết luận khả năng của TD3. '
                        'Kết quả eval chỉ áp dụng checkpoint này. Tiếp thiết kế pilot train có ngân sách trên baseline frozen; '
                        'validation Ki0,15 không là điều kiện bắt buộc để train với Ki0,10.')
                    self.status.setText(self.status.text().split('\nBƯỚC TIẾP:')[0]+
                        '\nBƯỚC TIẾP: thiết kế pilot TD3 có ngân sách trên baseline frozen; chưa tự cấp training budget.')
                    self.gates.setItem(3,2,Q.QTableWidgetItem(
                        'Chốt contract, ngân sách và eval định kỳ cho pilot TD3. Không yêu cầu TD3 thắng trước khi cho train; '
                        'chưa kết luận từ checkpoint1.024steps. Validation PI là nhánh riêng.'))
            self.verified=True
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.cost.setRowCount(0)
            for i in range(4):
                for j in range(3):self.gates.setItem(i,j,Q.QTableWidgetItem('Chưa xác minh'))
            self.status.setText('HỒ SƠ BENCHMARK CHƯA XÁC MINH: '+str(exc))
            self.held_status.setText('Correction offline chưa xác minh; không giữ trạng thái pass cũ.')
            self.dynamics_status.setText('Dynamics artifact chưa xác minh; không giữ trạng thái pass cũ.')
            self.pi_status.setText('PI software artifact chưa xác minh; không giữ trạng thái pass cũ.')
            self.pi_runner_status.setText('PI runner artifact chưa xác minh; không giữ trạng thái pass cũ.')
            self.pi_metrics.setRowCount(0)
            self.pi_screen_status.setText('PI screen artifact chưa xác minh; không giữ trạng thái pass cũ.')
            self.pi_screen_status.setVisible(True)
            self.pi_validation_status.setText('Validation stop6s chưa xác minh; không giữ trạng thái pass cũ.')
            self.pi_validation_status.setVisible(True)
            self.td3_training_status.setText('Số bước TD3 chưa xác minh; không giữ số đếm cũ.')
            self.td3_training_status.setVisible(True)

    def show_assessment(self,assessment):
        self.verified=True;self.status.setText(assessment['summary'])
        rows=assessment['decision']['per_stop'];self.assessment_metrics.setRowCount(len(rows))
        for i,row in enumerate(rows):
            values=[str(row['stop'])]+[f"{row[key]:.3f}" for key in
                ('TD3_20k_open_RMSE_mm_s','TD3_30k_open_RMSE_mm_s','Classical_30k_open_RMSE_mm_s')]
            for j,value in enumerate(values):self.assessment_metrics.setItem(i,j,Q.QTableWidgetItem(value))
        self.assessment_metrics.show();self.assessment_report.show()
        self.scope.setText('Bảng: native velocity RMSE trong phase mở residual, mm/s; thấp hơn tốt hơn. '
            '20k và 30k là các fresh launch khác nhau; 25k chỉ được phân tích trên corpus chung, chưa có rollout riêng. '
            'Một learner seed11, common103D/1D, history5/10Hz, Ki0,10; chưa suy rộng obstacle hoặc robot thật.')
        self.limits.setText('Mapping/reward khớp trong phạm vi audit; critic ranking chưa đáng tin. '
            'Giảm reward cost khi gate đóng không chứng minh cải thiện chuyển động. '
            'Giữ checkpoint; mở lại TD3 cần câu hỏi ứng dụng/quyền điều khiển cụ thể và protocol riêng. '
            'Xem outline và báo cáo wheel/body riêng: chuẩn bị reference độc lập, kiểm live readiness trước một diagnostic có ngân sách riêng; chưa mở lượt thu mới.')
        for widget in (self.gates,self.cost,self.refresh,self.decision,self.protocol,self.context_result,self.gain_result,
                self.held_status,self.held_result,self.dynamics_status,self.dynamics_result,self.pi_status,self.pi_draft,
                self.pi_runner_status,self.pi_runner_protocol,self.pi_screen_status,self.pi_metrics,self.pi_screen_result,
                self.pi_validation_status,self.pi_validation_protocol,self.td3_training_status):widget.hide()
        self.refresh.show()

    def document(self,name):
        from .research_jobs import repository
        try:
            path=repository()/'docs'/name
            if not path.is_file():raise ValueError('Thiếu '+name)
            G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(path)))
        except (OSError,ValueError) as exc:self.status.setText(str(exc))
