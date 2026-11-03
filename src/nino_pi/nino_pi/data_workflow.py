"""Bounded GUI collection workflows. Pure logic; no ROS or hardware imports."""
from math import isfinite

MODES = {
    "stationary": "Đứng yên · chỉ thu 60 s",
    "zero": "Zero → ARM 4 s → DISARM",
    "forward": "Tiến 0,05 m/s · 2 s → zero / DISARM",
    "manual": "Teleop giữ nút · thu 60 s",
    "external": "ROS ngoài / Nav2 · chỉ ghi nhận",
}


class Workflow:
    """One movement sequence per capture; blocked trials cannot auto resume."""
    def __init__(self, clock, command, request, event):
        self.clock, self.command, self.request, self.event = clock, command, request, event
        self.mode = "stationary"
        self.phase = "idle"
        self.started = 0.
        self.used = False
        self.direction = (0., 0.)
        self.hold_at = float("-inf")

    def reset(self, mode):
        if mode not in MODES:
            raise ValueError("Chế độ thu không hợp lệ")
        if self.phase in ("arming", "running", "stopping"):
            raise ValueError("Đang có quy trình; phải dừng trước")
        self.mode, self.phase, self.used = mode, "idle", False
        self.direction = (0., 0.)

    @staticmethod
    def problems(ctx, arm_required=False):
        errors = list(ctx.get("problems", []))
        if not ctx.get("recording_ready"):
            errors.append("Recorder chưa ghi đủ kênh bắt buộc")
        if ctx.get("remaining_s", 0) < 5:
            errors.append("Còn dưới 5 s thu, kết thúc thao tác")
        if not ctx.get("owned") or not ctx.get("state_fresh"):
            errors.append("Thiếu quyền / trạng thái STM32 mới")
        if ctx.get("source") != 2 or ctx.get("latched"):
            errors.append("Cần nguồn ROS, không khóa STOP")
        if ctx.get("feedback") != 3:
            errors.append("Feedback hai bánh chưa đủ mới")
        if not ctx.get("prepared"):
            errors.append("Chưa chuẩn bị gate / smoother / monitor")
        if arm_required and (not ctx.get("armed") or not ctx.get("permission")):
            errors.append("STM32 chưa xác nhận ARM / permission")
        return errors

    def start(self, ctx):
        if self.mode in ("stationary", "external"):
            raise ValueError("Chế độ này chỉ ghi nhận, không phát chuyển động")
        if self.used:
            raise ValueError("Phiên này đã dùng thao tác; cần review trước phiên kế tiếp")
        errors = self.problems(ctx)
        if ctx.get("remaining_s", 0) < 12:
            errors.append("Cần ít nhất 12 s còn lại để bắt đầu thao tác")
        if errors:
            raise ValueError("; ".join(errors))
        if ctx.get("armed"):
            raise ValueError("Phải DISARM trước khi bắt đầu quy trình")
        if not ctx.get("final_zero"):
            raise ValueError("Cần final cmd_vel zero mới trước ARM")
        self.command(0., 0.)
        self.request("arm")
        self.used, self.phase, self.started = True, "arming", self.clock()
        self.event("workflow_start", {"mode": self.mode, "linear_m_s": .05,
                                       "ramp_m_s2": .10, "forward_reference_s": 2.,
                                       "one_sequence_per_capture": True})

    def hold(self, v, w):
        if not all(isfinite(x) for x in (v, w)) or abs(v) > .05 or abs(w) > .1 or (v and w):
            raise ValueError("Teleop chỉ nhận một trục, |v|≤0,05, |ω|≤0,10")
        if self.phase != "running" or self.mode != "manual":
            raise ValueError("Chưa bắt đầu teleop trong phiên thu")
        if v < 0:
            v = max(v, -.01)  # retain the previous clear-floor reverse bound
        self.direction, self.hold_at = (v, w), self.clock()

    def release(self):
        self.direction = (0., 0.)
        self.command(0., 0.)

    def abort(self, reason):
        if self.phase not in ("arming", "running", "stopping"):
            return
        self.direction = (0., 0.)
        self.command(0., 0.)
        self.request("stop")
        self.phase = "aborted"
        self.event("workflow_abort", {"reason": str(reason), "auto_resume": False})

    def tick(self, ctx):
        if self.phase not in ("arming", "running", "stopping"):
            return
        errors = self.problems(ctx)
        if errors:
            self.abort("; ".join(errors))
            return
        now = self.clock()
        if self.phase == "arming":
            self.command(0., 0.)
            if ctx.get("armed") and ctx.get("permission"):
                self.phase, self.started = "running", now
                self.event("arm_observed", {"policy_only": True})
            elif now - self.started > 1.5:
                self.abort("Không nhận ARM / permission")
            return
        if self.phase == "stopping":
            self.command(0., 0.)
            if not ctx.get("armed"):
                self.phase = "done"
                self.event("workflow_done", {"body_stop_verified": False})
            elif now - self.started > 1.5:
                self.abort("Không nhận DISARM")
            return
        if not ctx.get("armed") or not ctx.get("permission"):
            self.abort("ARM / permission đã mất trong thao tác")
            return
        elapsed = now - self.started
        if self.mode == "zero":
            v, w, duration = 0., 0., 4.
        elif self.mode == "forward":
            v, w, duration = .05, 0., 2.
        else:
            v, w = self.direction if now - self.hold_at < .2 else (0., 0.)
            duration = 2.  # bounded total teleop segment; not free driving for 60 s
        if elapsed >= duration:
            self.command(0., 0.)
            self.request("disarm")
            self.phase, self.started = "stopping", now
            self.event("zero_disable_requested", {"elapsed_s": elapsed})
        else:
            self.command(v, w)


class ClearWindow:
    """Five seconds of raw scan geometry + real monitor state; no invented CLEAR."""
    def __init__(self, clock):
        self.clock = clock
        self.rows = []
        self.action = None
        self.last_stop = None

    def scan(self, inside, valid):
        now = self.clock()
        self.rows.append((now, int(inside) if valid else 999))
        self.rows = [r for r in self.rows if now - r[0] <= 5.5][-100:]

    def monitor(self, action):
        self.action = action
        if action == 1:
            self.last_stop = self.clock()

    def problems(self):
        now = self.clock()
        rows = self.rows
        errors = []
        if self.action is None:
            errors.append("Chưa nhận trạng thái Collision Monitor")
        elif self.action == 1:
            errors.append("Collision Monitor STOP")
        if self.last_stop is not None and now - self.last_stop < 5:
            errors.append("Có STOP trong 5 s gần nhất")
        if len(rows) < 20 or rows[-1][0] - rows[0][0] < 5:
            errors.append("Chưa có 5 s scan để kiểm vùng trống")
        if not rows or now - rows[-1][0] > .5 or any(b[0]-a[0] > .5 for a,b in zip(rows, rows[1:])):
            errors.append("Scan thiếu / cũ / có gap")
        if not rows or max(r[1] for r in rows) >= 3:
            errors.append("Có ≥3 điểm trong StopZone hoặc scan/TF không hợp lệ")
        return errors
