"""Versioned STM32 authority contract; no ROS or GUI dependencies."""
from dataclasses import dataclass

VERSION = 1
MAGIC = 0x4E494E4F
REQUEST_TOPIC = "/nino/control_request"
STATE_TOPIC = "/nino/control_state"
OPS = {"claim": 1, "heartbeat": 2, "select": 3, "arm": 4,
       "disarm": 5, "stop": 6, "clear": 7, "release": 8}
SOURCES = {0: "DỪNG", 1: "TAY RC", 2: "ROS / GUI"}
RESULTS = {0: "Đã xác nhận", 1: "Yêu cầu không hợp lệ", 2: "GUI khác đang giữ quyền",
           3: "Chưa giữ quyền", 4: "Yêu cầu cũ / trùng", 5: "Cần lệnh zero mới / cần RC ở giữa",
           6: "RC đang chặn", 7: "Feedback hai bánh chưa đủ mới",
           8: "Đang khóa STOP — cần xóa khóa", 9: "Chưa chọn nguồn"}
REASONS = {0: "Sẵn sàng", 1: "Khởi động: DISARM", 2: "Đã DISARM", 3: "Vừa đổi nguồn",
           4: "STOP phần mềm", 5: "Hết hạn kết nối GUI", 6: "Mất lệnh vận tốc",
           7: "RC chặn / mất RC", 8: "Mất feedback bánh", 9: "Lệnh không hữu hạn",
           10: "Đã trả quyền"}
FIELDS = ("version", "magic", "owner", "sequence", "source", "armed", "latched", "reason",
          "rc_online", "rc_armed", "rc_stop", "feedback", "command_age_ms", "lease_age_ms",
          "ack_client", "ack_sequence", "ack_result", "permission", "actuator_mode", "uptime_ms")


@dataclass(frozen=True)
class State:
    values: tuple

    @classmethod
    def decode(cls, values):
        if len(values) != len(FIELDS) or any(type(x) is not int or not 0 <= x <= 0xFFFFFFFF for x in values):
            raise ValueError("Sai cấu trúc control_state")
        d = dict(zip(FIELDS, values))
        if d["version"] != VERSION or d["magic"] != MAGIC:
            raise ValueError("Firmware chưa hỗ trợ authority v1")
        if (d["source"] not in SOURCES or any(d[k] not in (0, 1) for k in
                ("armed", "latched", "rc_online", "rc_armed", "rc_stop", "permission"))
                or d["feedback"] > 3 or d["actuator_mode"] != 0
                or d["reason"] not in REASONS or d["ack_result"] not in RESULTS
                or (d["armed"] and (not d["owner"] or d["latched"] or not d["source"]))
                or (d["permission"] and not d["armed"])):
            raise ValueError("Trạng thái firmware mâu thuẫn / không hỗ trợ")
        return cls(tuple(values))

    def as_dict(self):
        return dict(zip(FIELDS, self.values))


class Session:
    """Owns sequences, matches ACKs, and stops renewing after a broken UI/link."""
    def __init__(self, client, send, emit, clock):
        if not 0 < client <= 0xFFFFFFFF:
            raise ValueError("client must be nonzero uint32")
        self.client, self.send, self.emit, self.clock = client, send, emit, clock
        self.sequence = 0
        self.state = None
        self.state_at = self.pulse_at = self.heartbeat_at = float("-inf")
        self.pending = None
        self.halted = False
        self.ever_owned = False
        self.last_uptime = None

    def fresh(self):
        return self.state is not None and self.clock() - self.state_at < 0.45

    def packet(self, op, arg=0):
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF or 1
        return [VERSION, self.client, self.sequence, OPS[op], arg]

    def receive(self, values):
        state = State.decode(values).as_dict()
        # Replayed/stalled telemetry cannot renew freshness, even if DDS delivers it again.
        if self.last_uptime is not None:
            delta = (state["uptime_ms"] - self.last_uptime) & 0xFFFFFFFF
            if delta == 0:
                return
            if delta >= 0x80000000:
                self.fail("STM32 vừa khởi động lại; cần lấy quyền lại")
                self.pending = None
        self.last_uptime = state["uptime_ms"]
        self.state, self.state_at = state, self.clock()
        if state["owner"] == self.client:
            self.ever_owned = True
        if self.pending and (state["ack_client"], state["ack_sequence"]) == self.pending[:2]:
            self.emit({"type": "ack", "action": self.pending[3], "ok": state["ack_result"] == 0,
                       "message": RESULTS[state["ack_result"]]})
            self.pending = None
        self.emit({"type": "state", "state": state, "client": self.client,
                   "halted": self.halted, "pending": self.pending is not None})

    def request(self, action):
        if action not in ("claim", "ros", "rc", "off", "arm", "disarm", "stop", "clear", "release"):
            raise ValueError("Lệnh GUI không hợp lệ")
        if not self.fresh():
            raise ValueError("Chưa có trạng thái firmware mới, không gửi yêu cầu")
        if self.pending and action not in ("stop", "disarm"):
            raise ValueError("Đang chờ STM32 xác nhận yêu cầu trước")
        if self.halted and action not in ("claim", "stop", "disarm", "release"):
            raise ValueError("Kết nối từng gián đoạn; hãy lấy quyền lại")
        if action not in ("claim", "stop", "disarm") and self.state["owner"] != self.client:
            raise ValueError("Hãy lấy quyền GUI trước")
        op = "select" if action in ("off", "rc", "ros") else action
        arg = {"off": 0, "rc": 1, "ros": 2}.get(action, 0)
        q = self.packet(op, arg)
        if action == "claim":
            self.halted = False
        self.pending = (self.client, q[2], self.clock(), action)
        self.send(q)
        self.emit({"type": "pending", "message": "Chờ STM32 xác nhận…", "action": action})

    def fail(self, message):
        if not self.halted:
            if self.ever_owned or (self.pending and self.pending[3] == "claim"):
                self.send(self.packet("stop"))
            self.halted = True
            self.emit({"type": "error", "message": message})

    def tick(self):
        now = self.clock()
        if self.pending and now - self.pending[2] > 1.0:
            self.fail("Không có ACK: kết quả chưa biết, đã yêu cầu STOP; không tự thử lại")
            self.pending = None
        owner = self.state and self.state["owner"] == self.client
        if owner and (not self.fresh() or now - self.pulse_at > 0.4):
            self.fail("Mất trạng thái STM32 hoặc nhịp GUI; dừng gia hạn quyền")
        if owner and not self.halted and self.fresh() and now - self.pulse_at <= 0.4 and now - self.heartbeat_at >= 0.1:
            self.send(self.packet("heartbeat"))
            self.heartbeat_at = now

    def close(self):
        if (self.state and self.state["owner"] == self.client) or (self.pending and self.pending[3] == "claim"):
            self.send(self.packet("stop"))
            self.send(self.packet("release"))
        self.halted = True
