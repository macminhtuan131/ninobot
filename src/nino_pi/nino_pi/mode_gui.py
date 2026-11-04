"""Desktop authority panel. SSH transports JSON; ROS runs on the Pi."""
import argparse
import json
from pathlib import Path
import shlex
import sys
import time
from PyQt5 import QtCore, QtGui, QtWidgets as Q
from .mode_protocol import SOURCES, REASONS, State
from .mode_data_panel import DataPanel
from .project_panel import ProjectPanel
from .guided_collection import GuidedCollection
from .research_panel import ResearchPanel
from .studio_panel import StudioPanel

STYLE = """QWidget { background:#101827; color:#e7edf7; font-family:'DejaVu Sans'; font-size:13px; }
QFrame#card { background:#192437; border:1px solid #2e3c52; border-radius:14px; }
QLabel { background:transparent; }
QLabel#muted { color:#a6b6cc; }
QLabel#title { font-size:25px; font-weight:700; }
QPushButton { background:#2c405c; border:1px solid #49617e; border-radius:9px; padding:12px 15px; font-weight:600; }
QPushButton:hover { background:#3b5677; }
QPushButton:disabled { background:#202c3e; color:#6e8099; border-color:#2d3c50; }
QPushButton#primary { background:#196d70; border-color:#33acaa; }
QPushButton#danger { background:#a73142; border-color:#ee697a; font-size:18px; }
QPushButton#primary:disabled,QPushButton#danger:disabled { background:#202c3e; color:#6e8099; border-color:#2d3c50; }
QPushButton#source[active="true"] { background:#215b65; border:2px solid #66d8c5; }
QLineEdit,QSpinBox { background:#0f1929; border:1px solid #40516a; border-radius:5px; padding:6px; }
QPlainTextEdit { background:#111c2e; border:1px solid #2e3c52; border-radius:7px; color:#b8c7dd; font-size:11px; }
QGroupBox { border:1px solid #34465e; border-radius:8px; margin-top:12px; padding-top:12px; }
QGroupBox::title { subcontrol-origin:margin; left:12px; }
QTabWidget::pane { border:1px solid #2e3c52; border-radius:8px; }
QTabBar::tab { background:#202e43; padding:10px 25px; border:1px solid #34465e; }
QTabBar::tab:selected { background:#215b65; color:#e7fff8; }
QComboBox { background:#192437; padding:8px; border:1px solid #40516a; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:17px; height:17px; }
QCheckBox::indicator:unchecked { background:#121f32; border:1px solid #879db7; border-radius:3px; }
QCheckBox::indicator:checked { background:#2ca68f; border:2px solid #b5fff0; border-radius:3px; }
QProgressBar { border:1px solid #40516a; border-radius:4px; text-align:center; min-height:22px; }
QProgressBar::chunk { background:#196d70; }
"""


def label(text, name=None):
    w = Q.QLabel(text)
    w.setWordWrap(True)
    if name:
        w.setObjectName(name)
    return w


def card():
    w = Q.QFrame()
    w.setObjectName("card")
    layout = Q.QVBoxLayout(w)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return w, layout


class ModeWindow(Q.QMainWindow):
    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.process = None
        self.state = None
        self.client = None
        self.received_at = float("-inf")
        self.pending = False
        self.halted = False
        self.output_buffer = b""
        self.closing_for_capture = False
        self.setWindowTitle("Nino Real Data Studio · v7" + (" · DEMO" if demo else ""))
        self.resize(1180, 980)
        self.setMinimumSize(900, 740)
        self.setStyleSheet(STYLE)
        central = Q.QWidget()
        self.setCentralWidget(central)
        root = Q.QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        heading = Q.QHBoxLayout()
        titles = Q.QVBoxLayout()
        titles.addWidget(label("NINO / DỮ LIỆU ROBOT", "muted"))
        titles.addWidget(label("Real Data Studio", "title"))
        heading.addLayout(titles, 1)
        self.badge = label("DEMO · KHÔNG NỐI ROBOT" if demo else "CHƯA KẾT NỐI")
        self.badge.setStyleSheet("color:#72ded0; font-weight:700")
        heading.addWidget(self.badge)
        root.addLayout(heading)

        connection, c = card()
        c.setContentsMargins(12,8,12,8)
        row = Q.QHBoxLayout()
        self.host = Q.QLineEdit("d@192.168.0.109")
        self.host.setMinimumWidth(180)
        self.host.setPlaceholderText("user@IP của Pi")
        self.connect_button = Q.QPushButton("Mở authority demo" if demo else "Kết nối firmware GUI · nâng cao")
        self.connect_button.setObjectName("primary")
        self.connect_button.clicked.connect(self.toggle_connection)
        self.settings_button = Q.QPushButton("Thiết lập SSH")
        self.settings_button.clicked.connect(self.settings)
        row.addWidget(label("Raspberry Pi"))
        row.addWidget(self.host, 1)
        row.addWidget(self.settings_button)
        self.collection_home = Q.QPushButton("Thu dữ liệu")
        self.collection_home.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        row.addWidget(self.collection_home)
        self.abort_collection=Q.QPushButton('Dừng ghi · không dừng xe')
        self.abort_collection.setObjectName('danger')
        self.abort_collection.setStyleSheet('font-size:13px')
        self.abort_collection.clicked.connect(self.stop_collection)
        row.addWidget(self.abort_collection)
        c.addLayout(row)
        self.connection_note = label("Studio chỉ đọc: chuẩn bị observer → kiểm sensor → ghi → QC → tải/export. Commissioning có chuyển động nằm ở trang riêng.", "muted")
        c.addWidget(self.connection_note)
        root.addWidget(connection)

        columns = Q.QHBoxLayout()
        controls, left = card()
        left.addWidget(label("01 / CHỌN NGUỒN", "muted"))
        owner_row = Q.QHBoxLayout()
        self.buttons = {}
        owner_row.addWidget(self.button("claim", "Lấy quyền GUI"))
        owner_row.addWidget(self.button("release", "Trả quyền"))
        left.addLayout(owner_row)
        self.source_buttons = {}
        for action, source, title, subtitle in (
            ("off", 0, "DỪNG", "Không nhận lệnh chuyển động"),
            ("ros", 2, "ROS / GUI", "Không cần tay RC · nhận lệnh teleop / navigation"),
            ("rc", 1, "TAY RC", "Dùng cần điều khiển · cần RC online và arm")):
            b = self.button(action, title + "\n" + subtitle)
            b.setObjectName("source")
            b.setMinimumHeight(64)
            self.source_buttons[source] = b
            left.addWidget(b)
        left.addWidget(label("Đổi nguồn luôn DISARM. Chọn ROS không tự phát lệnh tiến.", "muted"))
        left.addStretch(1)
        columns.addWidget(controls, 3)

        status, right = card()
        right.addWidget(label("02 / XÁC NHẬN TỪ STM32", "muted"))
        self.mode_label = label("Chưa biết chế độ", "title")
        right.addWidget(self.mode_label)
        self.arm_label = label("DISARM chưa được xác minh")
        self.arm_label.setStyleSheet("font-size:18px; color:#b6c8df")
        right.addWidget(self.arm_label)
        self.details = label("Chờ topic /nino/control_state từ firmware hỗ trợ GUI.", "muted")
        right.addWidget(self.details)
        arm_row = Q.QHBoxLayout()
        arm_row.addWidget(self.button("arm", "ARM · cho phép motor"))
        arm_row.addWidget(self.button("disarm", "DISARM"))
        right.addLayout(arm_row)
        self.buttons["arm"].setObjectName("primary")
        self.stop_button = self.button("stop", "DỪNG PHẦN MỀM / STOP")
        self.stop_button.setObjectName("danger")
        self.stop_button.setMinimumHeight(60)
        right.addWidget(self.stop_button)
        right.addWidget(self.button("clear", "Xóa khóa STOP · vẫn DISARM"))
        right.addWidget(label("STOP trên GUI không thay thế nút dừng khẩn cấp vật lý.", "muted"))
        columns.addWidget(status, 4)
        self.tabs = Q.QTabWidget()
        self.guided = GuidedCollection(self.command_connection, demo=demo)
        guided_scroll = Q.QScrollArea()
        guided_scroll.setWidgetResizable(True)
        guided_scroll.setWidget(self.guided)
        self.guided_scroll=guided_scroll
        self.acquisition_tabs=Q.QTabWidget()
        self.studio=StudioPanel(self.command_connection,demo=demo,external_busy=lambda:bool(
            self.guided.runner.active_jobs or self.process or (hasattr(self,'data_panel') and self.data_panel.capture.get('active')) or
            (hasattr(self,'research') and self.research.runner.busy)))
        self.acquisition_tabs.addTab(self.studio,'Studio · recorder chỉ đọc')
        self.acquisition_tabs.addTab(guided_scroll,'Commissioning cũ · protocol / motion riêng')
        self.tabs.addTab(self.acquisition_tabs, "Thu dữ liệu thật")
        self.studio.runner.closed.connect(lambda:QtCore.QTimer.singleShot(0,self.close) if self.studio.closing else None)
        self.guided.progress.connect(self.collection_progress)
        self.guided.all_closed.connect(lambda: QtCore.QTimer.singleShot(0,self.close) if self.guided.closing else None)
        control_page = Q.QWidget()
        control_layout = Q.QVBoxLayout(control_page)
        control_layout.addWidget(label("Backend nâng cao này cần firmware authority mới; không dùng để thu qua RC hiện có.","muted"))
        control_layout.addWidget(self.connect_button)
        control_layout.addLayout(columns)
        self.data_panel = DataPanel(self.send_message, demo=demo)
        data_scroll = Q.QScrollArea()
        data_scroll.setWidgetResizable(True)
        data_scroll.setWidget(self.data_panel)
        self.project_panel = ProjectPanel(demo=demo, connection=self.command_connection)
        project_scroll = Q.QScrollArea()
        project_scroll.setWidgetResizable(True)
        project_scroll.setWidget(self.project_panel)
        self.tabs.addTab(project_scroll, "Dữ liệu / kết quả / to-do")
        self.project_panel.collectionRequested.connect(self.open_collection_recipe)
        advanced = Q.QTabWidget()
        advanced.addTab(control_page, "Authority firmware mới")
        advanced.addTab(data_scroll, "Teleop / collector authority")
        self.tabs.addTab(advanced, "Authority nâng cao")
        self.research = ResearchPanel(hardware_busy=lambda:bool(self.guided.runner.active_jobs or self.studio.runner.busy or self.process or self.data_panel.capture.get('active')))
        self.research.collectionRequested.connect(self.open_collection_recipe)
        self.research.all_closed.connect(lambda:QtCore.QTimer.singleShot(0,self.close) if self.research.closing else None)
        research_scroll=Q.QScrollArea();research_scroll.setWidgetResizable(True);research_scroll.setWidget(self.research)
        self.tabs.addTab(research_scroll,'Xây project / sơ đồ')
        self.connection_note.hide()
        root.addWidget(self.tabs, 1)

        self.notice = label("Chưa nối robot. Giao diện không tự lấy quyền, bật motor hoặc phát cmd_vel.")
        self.notice.setMinimumHeight(18)
        root.addWidget(self.notice)
        self.log = Q.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(55)
        self.log.document().setMaximumBlockCount(150)
        root.addWidget(self.log)
        self.log.hide()
        self.tabs.currentChanged.connect(lambda index:self.log.setVisible(index==2))
        root.addWidget(label("Raw → QC → SysID/evaluation. Dừng ghi không dừng xe. RL chưa triển khai thật.", "muted"))
        self.key_path = str(Path.home() / ".ssh/nino_pi_flash_ed25519")
        self.env_path = "/home/d/pi5-stm32-slam-main/scripts/env.sh"
        self.remote_root = "/home/d/nino_runtime/mode_gui_v1"
        self.domain = 0
        self.load_settings()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.refresh()

    def button(self, action, text):
        b = Q.QPushButton(text)
        b.clicked.connect(lambda checked=False, a=action: self.action(a))
        self.buttons[action] = b
        return b

    def command_connection(self):
        return dict(host=self.host.text().strip(), key=getattr(self, 'key_path', str(Path.home()/'.ssh/nino_pi_flash_ed25519')),
                    domain=getattr(self,'domain',0),authority_bridge_active=self.process is not None)

    def open_collection_recipe(self, name):
        if name=='studio':
            self.acquisition_tabs.setCurrentIndex(0);self.tabs.setCurrentIndex(0)
            return
        self.acquisition_tabs.setCurrentIndex(1)
        self.guided.select_recipe(name)
        self.tabs.setCurrentIndex(0)

    def stop_collection(self):
        if self.studio.runner.busy:
            self.studio.runner.stop_recording()
        else:
            self.guided.cancel()

    def collection_progress(self, event):
        data=event.get('data') or {}
        if self.tabs.currentIndex()==0:self.notice.setText(event.get('message',''))
        if data.get('quality_report'):
            self.project_panel.handle(dict(type='capture',active=False,directory=data.get('review_directory',''),
                result=dict(status='DEMO_ONLY_NO_DATA' if self.demo else 'reviewed_raw_only',quality_report=data['quality_report'])))
        if event.get('kind') in ('error','finished'):
            self.log_message(event['job']+' · '+event.get('message',''))

    def log_message(self, text):
        self.log.appendPlainText(time.strftime("%H:%M:%S") + "  " + text)

    def load_settings(self):
        s = QtCore.QSettings("Nino", "ControlModes")
        self.host.setText(s.value("host", self.host.text()))
        self.key_path = s.value("key", self.key_path)
        self.env_path = s.value("env", self.env_path)
        self.remote_root = s.value("root", self.remote_root)
        self.domain = int(s.value("domain", self.domain))

    def settings(self):
        dialog = Q.QDialog(self)
        dialog.setWindowTitle("Kết nối bridge trên Pi")
        form = Q.QFormLayout(dialog)
        edits = [Q.QLineEdit(x) for x in (self.key_path, self.env_path, self.remote_root)]
        for title, edit in zip(("SSH private key", "ROS env.sh trên Pi", "Thư mục bridge trên Pi"), edits):
            edit.setMinimumWidth(450)
            form.addRow(title, edit)
        domain = Q.QSpinBox()
        domain.setRange(0, 232)
        domain.setValue(self.domain)
        form.addRow("ROS_DOMAIN_ID của driver", domain)
        form.addRow(label("Cần cài backend vào Pi trước. Không thay đổi firmware khi kết nối."))
        box = Q.QDialogButtonBox(Q.QDialogButtonBox.Ok | Q.QDialogButtonBox.Cancel)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        form.addRow(box)
        if dialog.exec_() == Q.QDialog.Accepted:
            self.key_path, self.env_path, self.remote_root = [e.text().strip() for e in edits]
            self.domain = domain.value()

    def toggle_connection(self):
        if self.process:
            self.disconnect()
            return
        if not self.demo and (not self.host.text().strip() or self.host.text().startswith("-") or any(c.isspace() for c in self.host.text())):
            self.notice.setText("Địa chỉ SSH cần có dạng user@IP, không có khoảng trắng.")
            return
        self.state, self.client, self.pending, self.halted = None, None, False, False
        self.received_at = float("-inf")
        self.output_buffer = b""
        p = QtCore.QProcess(self)
        self.process = p
        p.readyReadStandardOutput.connect(self.read_output)
        p.readyReadStandardError.connect(lambda: self.log_message(bytes(p.readAllStandardError()).decode(errors="replace").strip()))
        p.finished.connect(self.finished)
        p.errorOccurred.connect(self.process_error)
        if self.demo:
            p.start(sys.executable, ["-u", "-m", "nino_pi.mode_bridge", "--demo"])
        else:
            # Quotes are shell quotes, not JSON quotes. Host stays a separate SSH argv.
            script = ("set -e; source " + shlex.quote(self.env_path) + "; "
                      + "export ROS_DOMAIN_ID=" + str(self.domain) + "; "
                      + "export PYTHONPATH=" + shlex.quote(self.remote_root) + ':"${PYTHONPATH:-}"; '
                      + "exec /usr/bin/python3 -u -m nino_pi.mode_bridge")
            args = ["-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=1",
                    "-o", "ServerAliveCountMax=2", "-i", self.key_path, self.host.text().strip(),
                    "bash -c " + shlex.quote(script)]
            p.start("ssh", args)
        self.notice.setText("Đang nối… Chưa có quyền điều khiển.")
        self.connect_button.setText("Ngắt kết nối")
        self.refresh()

    def send(self, action):
        self.send_message({"action": action})

    def send_message(self, message):
        if self.process and self.process.state() == QtCore.QProcess.Running:
            self.process.write((json.dumps(message, ensure_ascii=False) + "\n").encode())

    def action(self, action):
        if not self.buttons[action].isEnabled():
            return
        if action == "arm" and not self.demo:
            answer = Q.QMessageBox.question(self, "ARM motor", "Nguồn lệnh đang ở zero và vùng thử đã trống?\nARM cho phép nhận lệnh từ nguồn đã chọn.", Q.QMessageBox.Yes | Q.QMessageBox.No, Q.QMessageBox.No)
            if answer != Q.QMessageBox.Yes:
                return
        self.pending = True
        self.send(action)
        self.notice.setText("Đang chờ STM32 xác nhận; trạng thái chưa thay đổi.")
        self.log_message("Gửi yêu cầu: " + action)
        self.refresh()

    def read_output(self):
        self.output_buffer += bytes(self.process.readAllStandardOutput())
        if len(self.output_buffer) > 65536:
            self.disconnect()
            return
        while b"\n" in self.output_buffer:
            line, self.output_buffer = self.output_buffer.split(b"\n", 1)
            try:
                self.handle(json.loads(line))
            except (ValueError, TypeError, KeyError):
                self.log_message(line.decode(errors="replace")[:300])

    def handle(self, msg):
        self.data_panel.handle(msg)
        self.project_panel.handle(msg)
        kind = msg.get("type")
        if kind == "state":
            # Validate again at the GUI boundary. No optimistic state changes.
            from .mode_protocol import FIELDS
            self.state = State.decode([msg["state"][k] for k in FIELDS]).as_dict()
            self.client = msg["client"]
            self.received_at = time.monotonic()
            self.pending = msg["pending"]
            self.halted = msg["halted"]
        elif kind in ("connected", "ack", "error", "pending", "info"):
            text = msg.get("message", "")
            self.notice.setText(text)
            if kind != "pending":
                self.log_message(text)
            if kind in ("ack", "error"):
                self.pending = False
        elif kind == "workflow_event":
            text = msg.get("event", "") + ": " + str(msg.get("data", {}))
            self.log_message(text)
            self.notice.setText(text)
        self.refresh()

    def tick(self):
        self.send("pulse")
        self.refresh()

    def refresh(self):
        fresh = self.state is not None and time.monotonic() - self.received_at < 0.45
        s = self.state or {}
        ours = fresh and s.get("owner") == self.client
        idle = fresh and not self.pending
        workflow_busy = self.data_panel.status.get("phase") in ("arming", "running", "stopping")
        for a, b in self.buttons.items():
            if a in ("stop", "disarm"):
                enabled = fresh
            elif a == "claim":
                enabled = idle and (not s.get("owner") or ours)
            else:
                enabled = idle and ours and not self.halted
            if a == "arm":
                enabled = enabled and not s.get("armed") and not s.get("latched") and s.get("source") in (1, 2) and s.get("feedback") == 3
                if s.get("source") == 2:
                    enabled = enabled and s.get("command_age_ms", 999999) <= 500
                if s.get("source") == 1 or s.get("rc_online"):
                    enabled = enabled and s.get("rc_online") and s.get("rc_armed") and not s.get("rc_stop")
            if a == "clear":
                enabled = enabled and s.get("latched") and not s.get("armed")
            if workflow_busy and a not in ("stop", "disarm", "release"):
                enabled = False
            if a == "arm" and self.data_panel.capture.get("active"):
                enabled = False  # the capture workflow owns the zero/ARM/stop sequence
            b.setEnabled(bool(enabled))
        for source, b in self.source_buttons.items():
            active = fresh and s.get("source") == source
            if b.property("active") != active:
                b.setProperty("active", active)
                b.style().unpolish(b)
                b.style().polish(b)
        guided_busy=bool(self.guided.runner.active_jobs)
        studio_busy=self.studio.runner.busy
        research_busy=self.research.runner.busy
        self.guided.external_busy=research_busy or studio_busy;self.guided.refresh();self.research.refresh();self.studio.refresh()
        if guided_busy or research_busy or studio_busy:
            for b in self.buttons.values():b.setEnabled(False)
        self.abort_collection.setEnabled((guided_busy and not self.guided.stopping) or (studio_busy and self.studio.runner.action=='record'))
        self.abort_collection.setText('Dừng ghi' if self.acquisition_tabs.currentIndex()==0 else 'Hủy commissioning')
        self.abort_collection.setToolTip('Dừng ghi không dừng robot. Commissioning có cleanup riêng theo protocol.')
        self.connect_button.setEnabled(not guided_busy and not research_busy and not studio_busy)
        self.settings_button.setEnabled(self.process is None and not guided_busy and not research_busy and not studio_busy)
        self.data_panel.set_authority(self.state, fresh, ours)
        self.host.setEnabled(self.process is None and not guided_busy and not research_busy and not studio_busy)
        if fresh:
            self.badge.setText("DEMO · KHÔNG NỐI ROBOT" if self.demo else "STM32 · ĐANG CẬP NHẬT")
            self.mode_label.setText(SOURCES[s["source"]])
            self.arm_label.setText("ARM · firmware cho phép" if s["armed"] else "DISARM" + (" · khóa STOP" if s["latched"] else ""))
            owner = "GUI này" if ours else ("GUI khác" if s["owner"] else "Chưa có")
            cmd_age = "chưa có" if s["command_age_ms"] == 0xFFFFFFFF else str(s["command_age_ms"]) + " ms"
            self.details.setText(f"Quyền: {owner} · {REASONS[s['reason']]}\n"
                                 f"Feedback: {'hai bánh mới' if s['feedback'] == 3 else 'thiếu / cũ'}\n"
                                 f"RC: {'online' if s['rc_online'] else 'không có tín hiệu'} · "
                                 f"{'ARM' if s['rc_armed'] else 'DISARM'} · stop={s['rc_stop']}\n"
                                 f"Tuổi lệnh ROS: {cmd_age} · quyền thực thi firmware: {s['permission']}\n"
                                 "Quyền firmware không phải readback dòng điện hoặc chuyển động motor.")
        else:
            self.badge.setText("DEMO · CHƯA NỐI" if self.demo else "CHƯA CÓ TRẠNG THÁI MỚI")
            self.arm_label.setText("Trạng thái motor: CHƯA BIẾT")
            self.details.setText("Chờ firmware GUI v1. Firmware cũ không có topic authority nên các nút bị khóa.\n"
                                 "Nếu vừa mất kết nối: dùng nút dừng vật lý khi cần; không tự chạy lại.")
        if self.tabs.currentIndex()==0:
            self.badge.setText("DEMO · KHÔNG CÓ DATA THẬT" if self.demo else ("ĐANG XỬ LÝ PHIÊN THU" if guided_busy or studio_busy else "STUDIO · CHỈ ĐỌC"))

    def disconnect(self):
        if self.process:
            self.send("close")
            # Nonblocking wait; a hung SSH process is terminated after the lease can expire.
            p = self.process
            timeout = 55000 if self.data_panel.capture.get("active") else 1200
            if timeout > 1200:
                self.notice.setText("Đang dừng / đóng recorder; giữ kết nối để chờ manifest và hash.")
            QtCore.QTimer.singleShot(timeout, lambda: p.kill() if p.state() != QtCore.QProcess.NotRunning else None)

    def process_error(self, error):
        message = self.process.errorString() if self.process else "process unavailable"
        if self.process and self.process.state() == QtCore.QProcess.NotRunning:
            self.finished()
        self.notice.setText("Lỗi kết nối: " + message)

    def finished(self, *_):
        self.process = None
        self.state = None
        self.pending = False
        self.data_panel.supported = False
        self.connect_button.setText("Mở demo" if self.demo else "Kết nối Pi")
        self.notice.setText("Đã ngắt kết nối. Không tự lấy quyền hoặc ARM lại.")
        self.refresh()
        if self.closing_for_capture:
            QtCore.QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if self.studio.runner.busy:
            self.studio.request_close()
            event.ignore()
            return
        if self.research.runner.busy:
            if not self.research.closing:self.research.request_close()
            event.ignore()
            return
        if self.guided.runner.active_jobs:
            if not self.guided.closing:self.guided.request_close()
            event.ignore()
            return
        self.guided.runner.dispose()
        self.data_panel.release()
        if self.process and self.process.state() != QtCore.QProcess.NotRunning and self.data_panel.capture.get("active"):
            if not self.closing_for_capture:
                self.closing_for_capture = True
                self.timer.stop()
                self.data_panel.hold_timer.stop()
                self.disconnect()
                self.state = None
                self.refresh()
            event.ignore()
            return
        self.send("close")
        if self.process:
            process = self.process
            process.closeWriteChannel()
            if not process.waitForFinished(1200):
                process.kill()
                process.waitForFinished(500)
        if not self.demo:
            s = QtCore.QSettings("Nino", "ControlModes")
            for k, v in (("host", self.host.text()), ("key", self.key_path), ("env", self.env_path), ("root", self.remote_root), ("domain", self.domain)):
                s.setValue(k, v)
        event.accept()

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.ActivationChange and not self.isActiveWindow() and hasattr(self, "data_panel"):
            self.data_panel.release()
        super().changeEvent(event)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--demo", action="store_true", help="UI demo, no SSH/ROS/motor")
    p.add_argument("--project", action="store_true", help="Mở hồ sơ tiến độ local; không tự kết nối Pi")
    p.add_argument('--build',action='store_true',help='Mở sơ đồ tiến độ và jobs History/TD3/PPO local')
    from .collection_recipes import RECIPES
    p.add_argument("--commands", choices=list(RECIPES), help="Tương thích shortcut cũ: mở phiên thu bằng nút, không copy lệnh")
    args = p.parse_args(argv)
    app = Q.QApplication(sys.argv[:1])
    app.setApplicationName("Nino Control Modes")
    window = ModeWindow(demo=args.demo)
    if args.project or args.commands:
        window.tabs.setCurrentIndex(1)
    if args.commands:
        window.open_collection_recipe(args.commands)
    if args.build:window.tabs.setCurrentIndex(3)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
