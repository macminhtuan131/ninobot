"""GUI adapter for the existing isolated rosbag/audit collector, not a new logger."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import signal
import sqlite3
import subprocess
import sys
import time
from .data_workflow import MODES
from .data_quality import assess_capture


def save(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile(mode):
    if mode not in MODES:
        raise ValueError("Chế độ thu không hợp lệ")
    required = {"/imu/data", "/motor_fb", "/motor_status", "/scan_raw", "/nino/control_state"}
    if mode in ("zero", "forward", "manual"):
        required.update(("/cmd_vel_teleop", "/cmd_vel_selected", "/cmd_vel_smoothed", "/cmd_vel"))
    if mode == "external":
        required.add("/cmd_vel")
    optional = {"/tf", "/tf_static", "/joint_states", "/imu/bridge", "/imu/debug",
                "/odom/unfiltered", "/odom", "/scan", "/nino/control_request",
                "/collision_monitor_state", "/cmd_vel_nav", "/motor_enable", "/cmd_mit", "/cmd_torque"}
    optional.update(("/cmd_vel", "/cmd_vel_teleop", "/cmd_vel_selected", "/cmd_vel_smoothed"))
    return dict(schema_version=1, profile_id="gui_data_v2_" + mode, duration_s=60,
                max_session_mb=1024, reserve_disk_mb=1024, storage_preset_profile="resilient",
                claim_scope="Source/final ROS requests, reported wheel/IMU and authority state. Not body ground truth, executed target, slip or certified stop.",
                topics=[dict(name=t, required=t in required, purpose="Raw channel; retain header, payload and receipt clock. Interpret only against session firmware/frame metadata.")
                        for t in sorted(required | optional)])


class Capture:
    def __init__(self, emit, root=None):
        self.emit = emit
        self.root = root or Path.home() / "nino_real_data/gui_sessions"
        self.directory = None
        self.child = None
        self.stream = None
        self.config = None
        self.ready = False
        self.started = 0.
        self.last_check = 0.
        self.mode = None
        self.result = None
        self.stop_requested = False
        self.final_context = {}

    def active(self):
        return self.child is not None

    def remaining(self):
        return max(0., 60 - (time.monotonic() - self.started)) if self.active() else 0.

    def start(self, mode, metadata):
        if self.active():
            raise ValueError("Recorder đang chạy hoặc đang đóng")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("pose_caster_note"), str) or not metadata["pose_caster_note"].strip():
            raise ValueError("Ghi pose/caster; chưa biết thì ghi unknown")
        if not isinstance(metadata.get("floor_load_note"), str) or not metadata["floor_load_note"].strip():
            raise ValueError("Ghi sàn/tải; chưa biết thì ghi unknown")
        self.config = profile(mode)
        session_id = "gui_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.directory = self.root / session_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.mode, self.ready, self.result = mode, False, None
        self.stop_requested = False
        self.final_context = {}
        save(self.directory / "topics.json", self.config)
        save(self.directory / "gui_result.json", {"status": "started_not_closed", "body_motion_verified": False})
        save(self.directory / "session.json", dict(session_id=session_id, gui_mode=mode,
             protocol="gui_data_v2", operator_metadata=metadata, body_reference=None,
             firmware_binary_sha256=None, prior_pilot_budget_reused=False))
        qos = ""
        for topic in ("/imu/data", "/motor_fb", "/joint_states", "/scan_raw", "/scan", "/imu/bridge", "/imu/debug"):
            qos += f"{topic}:\n  reliability: best_effort\n  durability: volatile\n  history: keep_last\n  depth: 1000\n"
        qos += "/tf_static:\n  reliability: reliable\n  durability: transient_local\n  history: keep_last\n  depth: 100\n"
        (self.directory / "qos.yaml").write_text(qos)
        self.stream = (self.directory / "collector.log").open("x")
        argv = [sys.executable, "-u", "-m", "nino_pi.collect_real_data", "--config", str(self.directory / "topics.json"),
                "--session", str(self.directory / "session.json"), "--qos", str(self.directory / "qos.yaml"),
                "--output", str(self.directory / "capture")]
        try:
            self.child = subprocess.Popen(argv, stdout=self.stream, stderr=subprocess.STDOUT, start_new_session=True)
        except Exception:
            self.stream.close()
            self.stream = None
            raise
        self.started = time.monotonic()
        self.event("capture_start", {"mode": mode, "duration_s": 60, "collector_argv": argv})

    def event(self, name, data):
        if self.directory:
            with (self.directory / "events.jsonl").open("a") as stream:
                stream.write(json.dumps(dict(event=name, data=data, wall_ns=time.time_ns(),
                                             monotonic_ns=time.monotonic_ns()), ensure_ascii=False, allow_nan=False) + "\n")

    def poll(self):
        if not self.active():
            return
        now = time.monotonic()
        if now - self.last_check < .5:
            return
        self.last_check = now
        counts = {}
        try:
            for path in (self.directory / "capture/bag").glob("*.db3"):
                with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=.02) as db:
                    for topic, count in db.execute("SELECT t.name,count(m.id) FROM topics t LEFT JOIN messages m ON m.topic_id=t.id GROUP BY t.id"):
                        counts[topic] = counts.get(topic, 0) + count
        except sqlite3.Error:
            counts = {}
        missing = [r["name"] for r in self.config["topics"] if r["required"] and not counts.get(r["name"])]
        # Actual committed rows, not a recorder node name or graph presence.
        self.ready = not self.stop_requested and not missing and self.child.poll() is None and self.remaining() > 0
        if self.child.poll() is not None:
            manifest = {}
            rc = self.child.returncode
            self.stream.close()
            self.stream = None
            self.child = None
            self.ready = False
            try:
                manifest = json.loads((self.directory / "capture/manifest.json").read_text())
                hashes = json.loads((self.directory / "capture/sha256.json").read_text())
                failed = []
                checked = 0
                for name, digest in hashes.items():
                    if name in ("collector_source", "audit_source"):
                        continue
                    path = self.directory / "capture" / name
                    if not path.is_file() or digest_file(path) != digest:
                        failed.append(name)
                    checked += 1
                if not checked:
                    failed.append("no_artifact_hashes")
                status = manifest.get("status", "incomplete") if not failed and rc == 0 else "incomplete"
                self.result = dict(status=status, collector_exit=rc, integrity_issues=manifest.get("issues", []),
                                   hash_mismatches=failed, checked_hashes=checked, body_motion_verified=False)
            except (OSError, ValueError) as e:
                self.result = dict(status="incomplete", collector_exit=rc, error=str(e), body_motion_verified=False)
            self.result.update(self.final_context)
            self.result["quality_report"] = assess_capture(self.result, manifest, self.config)
            save(self.directory / "gui_quality_report.json", self.result["quality_report"])
            self.event("capture_closed", self.result)
            save(self.directory / "gui_result.json", self.result)
            self.rehash()
        self.emit({"type": "capture", "active": self.active(), "ready": self.ready,
                   "remaining_s": round(self.remaining(), 1), "missing": missing,
                   "directory": str(self.directory), "mode": self.mode, "result": self.result})

    def stop(self):
        if self.active() and self.child.poll() is None and not self.stop_requested:
            self.event("capture_cancel_requested", {})
            self.stop_requested = True
            os.killpg(self.child.pid, signal.SIGINT)
            self.ready = False

    def observation(self, text):
        if not self.directory or self.active() or not isinstance(text, str) or not text.strip():
            raise ValueError("Chờ recorder đóng rồi ghi quan sát")
        self.event("operator_observation", {"text": text, "measured_body_reference": False})
        self.rehash()

    def rehash(self):
        # Sidecar hashes are separate from the collector's immutable raw hashes.
        files = ("session.json", "topics.json", "qos.yaml", "events.jsonl", "gui_result.json", "gui_quality_report.json", "collector.log")
        save(self.directory / "sidecar_sha256.json", {n: digest_file(self.directory/n)
             for n in files if (self.directory/n).is_file()})
