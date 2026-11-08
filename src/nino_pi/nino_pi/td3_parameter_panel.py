"""Offline TD3 parameter editor, sequential tuning hierarchy, E1-E3 matrix, and 7 deployment safety gates.

Never starts training or changes a runtime / hardware authority.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from PyQt5 import QtWidgets as Q
import yaml


class TD3ParameterPanel(Q.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        layout=Q.QVBoxLayout(self)
        try:
            from nino_rl.td3_config import load_profiles
            self.profiles=load_profiles()
        except (ImportError,OSError,ValueError) as exc:
            self.profiles={};message=Q.QLabel('Chưa có catalog nino_rl: '+str(exc)+'\nStudio thu dữ liệu vẫn dùng được.');message.setWordWrap(True)
            layout.addWidget(message);return
        note=Q.QLabel('TD3 PARAMETER SYSTEM · profile có phiên bản / hash + Ma trận E1–E3 & 7 Cổng An Toàn\n'
            'Thứ tự tune bắt buộc: (1) Observation/Action Contract → (2) Dynamics/SysID → (3) Reward & Termination → (4) Hyperparameters. '
            'h5 đang dùng; h1/h8 là ablation E2 cần ABI mới. Editor chỉ lưu draft, không mở budget hoặc hardware authority (= 0).')
        note.setWordWrap(True);layout.addWidget(note)
        self.tabs=Q.QTabWidget();layout.addWidget(self.tabs,1)

        # Tab 0: Profile YAML & ABI (preserves all existing attributes for backward compatibility)
        profile_page=Q.QWidget();p_layout=Q.QVBoxLayout(profile_page)
        self.choose=Q.QComboBox();self.choose.addItems(self.profiles);p_layout.addWidget(self.choose)
        self.editor=Q.QPlainTextEdit();p_layout.addWidget(self.editor,1)
        row=Q.QHBoxLayout();self.validate=Q.QPushButton('Kiểm schema + hiện hash');self.validate.clicked.connect(self.check)
        self.save=Q.QPushButton('Lưu profile draft mới');self.save.clicked.connect(self.save_draft)
        self.prepare=Q.QPushButton('Tạo effective config + ABI');self.prepare.clicked.connect(self.prepare_profile)
        row.addWidget(self.validate);row.addWidget(self.save);row.addWidget(self.prepare);p_layout.addLayout(row)
        self.result=Q.QPlainTextEdit();self.result.setReadOnly(True);self.result.setMaximumHeight(165);p_layout.addWidget(self.result)
        self.tabs.addTab(profile_page,'1 · Profile YAML & ABI')

        # Tab 1: Sequential Tuning Order, Experiment Matrix E1-E3 & 7 Deployment Safety Gates
        matrix_page=Q.QWidget();m_layout=Q.QVBoxLayout(matrix_page)
        self.stage_checks={}
        stage_box=Q.QGroupBox('Thứ tự hiệu chỉnh tuần tự (chặn tune hyperparameter khi contract/SysID chưa đạt)')
        stage_lay=Q.QVBoxLayout(stage_box)
        for sid,label in [
            ('observation_action_contract','Bước 1 · Observation/Action Contract (10 Hz causal, missing mask, frozen stats, projection)'),
            ('dynamics_model_sysid','Bước 2 · Mô hình động lực & SysID (delay, deadzone, body reference độc lập)'),
            ('reward_and_termination','Bước 3 · Reward đa mục tiêu & tách terminated / truncated'),
            ('algorithm_hyperparameters','Bước 4 · Hyperparameters thuật toán TD3 (>=3 seeds, >=20 episodes/seed)'),
        ]:
            cb=Q.QCheckBox(label);cb.stateChanged.connect(self.refresh_governance)
            self.stage_checks[sid]=cb;stage_lay.addWidget(cb)
        m_layout.addWidget(stage_box)

        self.gate_checks={}
        gate_box=Q.QGroupBox('7 Cổng an toàn bắt buộc trước khi xem xét thử nghiệm trên robot (hardware_authority = 0)')
        gate_lay=Q.QVBoxLayout(gate_box)
        for gid,label in [
            ('offline_sim_and_replay_verified','Gate 1 · Kiểm chứng offline replay & calibrated sim không phân kỳ / NaN'),
            ('beats_tuned_classical_on_heldout','Gate 2 · Thắng Classical đã tune công bằng trên tập held-out (E1, >=3 seeds)'),
            ('pi_zero_authority_shadow_verified','Gate 3 · Đánh giá Shadow mode (zero authority) trên Raspberry Pi đạt timing/latency'),
            ('software_and_gui_fault_tests_passed','Gate 4 · Vượt qua fault tests (mất kết nối GUI, rớt topic, dừng bag không dừng xe)'),
            ('hardware_interlocks_active','Gate 5 · E-stop vật lý, RC override, command_gate & collision_monitor đang hoạt động'),
            ('operator_supervision_and_clear_zone','Gate 6 · Người vận hành giám sát trực tiếp trong vùng thử an toàn theo protocol đã duyệt'),
            ('instant_classical_fallback_verified','Gate 7 · Đã kiểm chứng chuyển tức thời về Classical (residual = 0) khi có sự kiện an toàn'),
        ]:
            cb=Q.QCheckBox(label);cb.stateChanged.connect(self.refresh_governance)
            self.gate_checks[gid]=cb;gate_lay.addWidget(cb)
        m_layout.addWidget(gate_box)

        self.governance_view=Q.QPlainTextEdit();self.governance_view.setReadOnly(True)
        m_layout.addWidget(self.governance_view,1)
        self.tabs.addTab(matrix_page,'2 · Ma trận E1–E3 & 7 Cổng An Toàn')

        self.choose.currentTextChanged.connect(self.load);self.load(self.choose.currentText())
        self.refresh_governance()

    def load(self,name):
        self.editor.setPlainText(yaml.safe_dump(self.profiles[name],sort_keys=False,allow_unicode=True));self.check()

    def check(self):
        from nino_rl.td3_config import validate_profile
        from nino_rl.td3_experiment_matrix import check_profile_within_bounds
        try:
            value=yaml.safe_load(self.editor.toPlainText());report=validate_profile(value)
            if isinstance(value,dict) and isinstance(value.get('algorithm'),dict):
                report['search_bounds_check']=check_profile_within_bounds(value)
            self.result.setPlainText(json.dumps(report,ensure_ascii=False,indent=2));return value
        except (ValueError,TypeError,KeyError,yaml.YAMLError) as exc:
            self.result.setPlainText('KHÔNG ĐẠT: '+str(exc));return None

    def refresh_governance(self):
        try:
            from nino_rl.td3_experiment_matrix import (
                evaluate_deployment_gates,
                evaluate_tuning_readiness,
                load_matrix,
                validate_matrix,
            )
            matrix=load_matrix()
            summary=dict(
                matrix_validation=validate_matrix(matrix),
                tuning_readiness=evaluate_tuning_readiness({k:cb.isChecked() for k,cb in self.stage_checks.items()}),
                experiments=matrix['experiments'],
                deployment_gates=evaluate_deployment_gates({k:cb.isChecked() for k,cb in self.gate_checks.items()}),
            )
            self.governance_view.setPlainText(json.dumps(summary,ensure_ascii=False,indent=2))
        except Exception as exc:
            self.governance_view.setPlainText('Lỗi kiểm tra ma trận: '+str(exc))

    def save_draft(self):
        value=self.check()
        if value is None:return
        path,_=Q.QFileDialog.getSaveFileName(self,'Lưu draft mới',str(Path.home()/(value['profile_id']+'.yaml')),'YAML (*.yaml)')
        if path:
            try:
                with Path(path).open('x') as stream:yaml.safe_dump(value,stream,sort_keys=False)
                self.result.appendPlainText('Đã lưu draft: '+path+'; không áp vào job đang chạy.')
            except OSError as exc:self.result.appendPlainText(str(exc))

    def prepare_profile(self):
        value=self.check()
        if value is None:return
        if value!=self.profiles[self.choose.currentText()]:
            self.result.appendPlainText('Editor đã thay đổi: lưu draft để review; không gán tên/hash profile catalog cho tham số khác.');return
        parent=Q.QFileDialog.getExistingDirectory(self,'Chọn thư mục cha cho config/ABI draft',str(Path.home()))
        if not parent:return
        from nino_rl.td3_config import prepare_profile
        try:
            out=Path(parent)/('td3_profile_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            self.result.setPlainText(json.dumps(prepare_profile(self.choose.currentText(),out),ensure_ascii=False,indent=2))
        except (OSError,ValueError,KeyError) as exc:self.result.setPlainText(str(exc))
