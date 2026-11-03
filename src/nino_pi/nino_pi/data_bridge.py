"""Coordinates GUI capture and bounded operator actions; does not allocate old pilot slots."""
import time
from .data_workflow import MODES, Workflow
from .gui_capture import Capture


class DemoIO:
    def __init__(self):
        self.prepared = False
        self.target = (0., 0.)

    def problems(self):
        return []

    def final_zero(self):
        return self.target == (0., 0.)

    def prepare(self):
        self.prepared = True

    def reset_gate(self):
        self.disable()

    def disable(self):
        self.prepared = False
        self.target = (0., 0.)

    def command(self, v, w):
        self.target = (v, w)

    def tick(self):
        pass


class DemoCapture:
    def __init__(self, emit):
        self.emit = emit
        self.ready = False
        self.started = None
        self.mode = None
        self.directory = "DEMO — không có bag thật"
        self.result = None

    def active(self):
        return self.started is not None

    def remaining(self):
        return max(0., 60-(time.monotonic()-self.started)) if self.active() else 0.

    def start(self, mode, metadata):
        if self.active() or mode not in MODES:
            raise ValueError("Demo capture không sẵn sàng")
        self.mode, self.started, self.ready, self.result = mode, time.monotonic(), True, None

    def event(self, name, value):
        pass

    def poll(self):
        if self.active() and not self.remaining():
            self.stop()
        self.emit(dict(type="capture", active=self.active(), ready=self.ready,
                       remaining_s=round(self.remaining(), 1), missing=[], directory=self.directory,
                       mode=self.mode, result=self.result))

    def stop(self):
        self.started, self.ready = None, False
        self.result = {"status": "DEMO_ONLY_NO_DATA", "body_motion_verified": False}

    def observation(self, text):
        if not self.mode:
            raise ValueError("Chưa có phiên demo")


class DataBridge:
    ACTIONS = {"prepare_data", "reset_gate", "capture_start", "capture_stop", "workflow_start", "hold", "hold_release", "observation"}

    def __init__(self, session, emit, io, demo=False):
        self.session, self.emit, self.io = session, emit, io
        self.demo = demo
        self.capture = DemoCapture(emit) if demo else Capture(emit)
        self.workflow = Workflow(time.monotonic, io.command, self.request, self.event)
        self.last_status = 0.
        self.still_stop_sent = False

    def event(self, name, value):
        if self.capture.active():
            self.capture.event(name, value)
        self.emit({"type": "workflow_event", "event": name, "data": value})

    def request(self, action):
        try:
            self.session.request(action)
        except ValueError as e:
            self.emit({"type": "error", "message": str(e)})
            self.session.fail("Không gửi được yêu cầu workflow; ngừng gia hạn quyền")

    def context(self):
        s = self.session.state or {}
        return dict(s, recording_ready=self.capture.ready, remaining_s=self.capture.remaining(),
                    owned=s.get("owner") == self.session.client, state_fresh=self.session.fresh() and not self.session.halted,
                    prepared=self.io.prepared, final_zero=self.io.final_zero(), problems=self.io.problems())

    def handle(self, message):
        action = message["action"]
        s = self.session.state or {}
        if action in ("prepare_data", "reset_gate"):
            if not self.session.fresh() or s.get("owner") != self.session.client or s.get("armed"):
                raise ValueError("Lấy quyền GUI và DISARM trước khi chuẩn bị đường lệnh")
            self.io.prepare() if action == "prepare_data" else self.io.reset_gate()
        elif action == "capture_start":
            if self.capture.active():
                raise ValueError("Phiên thu đang chạy / đóng; không reset số thao tác")
            if not self.session.fresh() or s.get("armed"):
                raise ValueError("Cần trạng thái STM32 mới xác nhận DISARM trước khi bắt đầu thu")
            mode = message.get("mode")
            if mode in ("stationary", "external") and (self.io.prepared or getattr(self.io, "prepare_queue", None) or getattr(self.io, "prepare_future", None)):
                raise ValueError("Chọn DISARM để tắt đường teleop GUI trước phiên chỉ ghi nhận")
            self.workflow.reset(mode)
            self.capture.start(mode, message.get("metadata", {}))
            self.capture.event("command_stack_snapshot", {"parameters": getattr(self.io, "params", {}),
                                                         "demo": self.demo, "not_executed_target": True})
            self.still_stop_sent = False
        elif action == "workflow_start":
            if message.get("clear_confirmed") is not True or message.get("parameters_confirmed") is not True:
                raise ValueError("Xác nhận vùng trống và profile trước khi thao tác")
            if self.session.pending:
                raise ValueError("Đang chờ ACK thao tác trước")
            self.workflow.start(self.context())
        elif action == "hold":
            self.workflow.hold(float(message.get("v", 0)), float(message.get("w", 0)))
        elif action == "hold_release":
            self.workflow.release()
        elif action == "capture_stop":
            self.workflow.abort("Người vận hành kết thúc sớm")
            self.io.disable()
            if s.get("owner") == self.session.client:
                self.request("stop")
            self.capture.stop()
        elif action == "observation":
            self.capture.observation(message.get("text"))
            self.emit({"type": "observation_saved"})
            self.emit({"type": "info", "message": "Đã lưu quan sát người vận hành; không phải body ground truth"})

    def operator_action(self, action):
        if action in ("stop", "disarm", "release"):
            self.workflow.abort("Người vận hành chọn " + action)
            self.io.disable()
        elif self.workflow.phase in ("arming", "running", "stopping"):
            raise ValueError("Hãy STOP / DISARM quy trình trước khi đổi nguồn hoặc lấy quyền lại")
        self.session.request(action)
        if self.capture.active():
            self.capture.event("operator_authority_request", {"action": action})

    def tick(self):
        if self.session.halted or time.monotonic() - self.session.pulse_at > .4:
            self.workflow.abort("GUI/link không còn mới")
            if self.io.prepared or getattr(self.io, "prepare_queue", None) or getattr(self.io, "prepare_future", None):
                self.io.disable()
        if self.capture.active() and self.capture.mode == "stationary" and self.session.state and self.session.state["armed"] and not self.still_stop_sent:
            self.still_stop_sent = True
            self.event("stationary_armed_violation", {"requested_stop": False, "capture_invalidated": True})
            self.capture.stop()
            self.emit({"type": "error", "message": "Có ARM trong phiên chỉ thu đứng yên: hủy phiên, kiểm trạng thái xe; observer không tự phát lệnh motor"})
        child = getattr(self.capture, "child", None)
        if child is not None and child.poll() is not None:
            self.workflow.abort("Collector kết thúc; không tiếp tục chuyển động")
            self.io.disable()
        self.workflow.tick(self.context())
        # Do not treat a completed/aborted sequence as permission for free driving.
        if self.workflow.phase in ("aborted", "done"):
            self.io.command(0., 0.)
        self.io.tick()
        self.capture.final_context = {"workflow_status": self.workflow.phase, "sequence_used": self.workflow.used}
        self.capture.poll()
        now = time.monotonic()
        if now - self.last_status >= .25:
            self.last_status = now
            ctx = self.context()
            self.emit({"type": "data_status", "prepared": self.io.prepared,
                       "preparing": bool(getattr(self.io, "prepare_queue", None) or getattr(self.io, "prepare_future", None)),
                       "problems": ctx["problems"], "final_zero": ctx["final_zero"],
                       "phase": self.workflow.phase, "used": self.workflow.used,
                       "mode": self.workflow.mode, "demo": self.demo})

    def close(self):
        self.workflow.abort("Đóng GUI / mất stdin")
        self.io.disable()
        self.capture.stop()
