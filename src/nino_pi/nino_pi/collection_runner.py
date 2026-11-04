"""User-triggered, fixed-job collection process adapter for the guided Qt UI.

This module never opens a connection at import/construction time.  The current
RC firmware path is separate from the opt-in software-authority bridge.
"""
import base64
import json
import os
from pathlib import Path
import shlex
import signal
import sys
from PyQt5 import QtCore as C
from .collection_recipes import RUNTIME, validate_connection


EVENT_PREFIX = "@@NINO_EVENT@@"
JOBS = frozenset(("deploy", "connect-sensors", "inventory", "start-stack", "record-diagnostic", "run-trial",
                  "stationary", "review", "fetch", "status", "observation"))
CONFIRMATIONS = ("rc_auto", "clear_floor", "same_load", "video_ready")


def validated_metadata(job, metadata):
    metadata = dict(metadata or {})
    if job == "record-diagnostic":
        if not all(metadata.get(key) is True for key in CONFIRMATIONS):
            raise ValueError("Xác nhận RC AUTO, vùng trống, cùng tải và video trước khi thu diagnostic")
    if job in ("stationary", "record-diagnostic"):
        for key in ("pose_caster_note", "floor_load_note"):
            if not isinstance(metadata.get(key), str) or not metadata[key].strip():
                raise ValueError("Ghi pose/caster và sàn/tải; chưa biết thì ghi unknown")
            if len(metadata[key]) > 2000:
                raise ValueError("Metadata quá dài")
    if job == "run-trial" and metadata.get("confirm_motion") is not True:
        raise ValueError("Cần bấm xác nhận riêng cho một lần tiến–zero–disable")
    if job == 'observation' and (metadata.get('outcome') not in ('moved_stopped','no_motion','intervention','not_observed')
                                or not isinstance(metadata.get('text'),str) or not metadata['text'].strip()):
        raise ValueError('Chọn outcome và ghi quan sát; chưa biết thì chọn chưa quan sát')
    encoded = json.dumps(metadata, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > 12000:
        raise ValueError("Metadata quá dài")
    return metadata


def job_command(job, connection, metadata=None):
    """Return an argv, never a user-supplied command or an interactive shell."""
    if job not in JOBS:
        raise ValueError("Không có tác vụ thu này")
    host = connection.get("host", "")
    key = str(Path(connection.get("key", "")).expanduser())
    validate_connection(host, key)
    metadata = validated_metadata(job, metadata)
    if connection.get('domain',0)!=0:
        raise ValueError('Prepared RC collection contract uses domain 0; review configuration before changing domain')
    if connection.get('authority_bridge_active') and job not in ('inventory','fetch','status'):
        raise ValueError('Đóng kết nối authority nâng cao trước khi dùng collector RC, tránh hai owner lệnh')
    if job in ("deploy", "fetch"):
        return ["setsid", "/usr/bin/python3", "-u", "-m", "nino_pi.collection_deploy", job,
                "--host", host, "--key", key]
    payload = base64.urlsafe_b64encode(json.dumps(metadata, ensure_ascii=False,
                                                allow_nan=False).encode()).decode()
    # The two substitutions are a fixed enum and URL-safe base64.  SSH still
    # receives one correctly quoted fixed script, without a PTY or shell input.
    remote = 'bash "$HOME/nino_runtime/' + RUNTIME + '/session.sh" '
    remote += shlex.quote(job) + " --gui --metadata-base64 " + shlex.quote(payload)
    return ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=3", "-o", "ServerAliveCountMax=2",
            "-i", key, host, remote]


class CollectionRunner(C.QObject):
    job_event = C.pyqtSignal(dict)

    def __init__(self, parent=None, demo=False):
        super().__init__(parent)
        self.demo = bool(demo)
        self._jobs = {}
        self._serial = 0
        self._closed = False
        self._demo_recorded = False
        self._pulse = C.QTimer(self)
        self._pulse.timeout.connect(self._send_pulses)
        self._pulse.start(250)

    @property
    def active_jobs(self):
        return {job: {"state": entry.get("state", "RUNNING"), "pid": entry.get("pid", 0),
                      "cancel_requested": entry.get("cancel_requested", False)}
                for job, entry in self._jobs.items()}

    def _emit(self, job, kind, **data):
        self.job_event.emit(dict(job=job, kind=kind, **data))

    def _check_start(self, job, metadata):
        if self._closed:
            raise ValueError("Cửa sổ đang đóng; chờ các process kết thúc")
        if job in self._jobs:
            raise ValueError("Tác vụ này đang chạy; không chạy trùng")
        if job in ("stationary", "record-diagnostic") and any(
                name in self._jobs for name in ("stationary", "record-diagnostic", "run-trial")):
            raise ValueError("Recorder hoặc trial hiện tại chưa đóng")
        if job=='connect-sensors' and any(name!='connect-sensors' for name in self._jobs):
            raise ValueError('Chỉ kết nối sensor trước stack/record/trial')
        if job == "start-stack" and "run-trial" in self._jobs:
            raise ValueError("Chờ trial đóng trước khi thay stack")
        if job in ("deploy", "review", "fetch", "observation") and any(
                name in self._jobs for name in ("stationary", "record-diagnostic", "run-trial")):
            raise ValueError("Chờ recorder/trial FINISHED trước deploy/review/fetch")
        if job=='deploy' and self._jobs:
            raise ValueError('Đóng các process của phiên trước khi thay runtime')
        if job == "run-trial":
            entry = self._jobs.get("record-diagnostic", {})
            if entry.get("state") != "RECORDING_READY" or entry.get("cancel_requested"):
                raise ValueError("Chưa có recorder diagnostic báo RECORDING_READY trong GUI này")
            if entry.get("motion_started"):
                raise ValueError("Phiên này đã có một yêu cầu trial; không tự thử lại")

    def start(self, job, connection, metadata=None):
        try:
            if job not in JOBS:
                raise ValueError("Không có tác vụ này")
            metadata = validated_metadata(job, metadata)
            argv = job_command(job, connection, metadata)
            self._check_start(job, metadata)
            if job == "run-trial":
                self._jobs["record-diagnostic"]["motion_started"] = True
            self._serial += 1
            token = self._serial
            entry = {"token": token, "state": "STARTING", "pid": 0,
                     "stdout": "", "stderr": "", "cancel_requested": False}
            self._jobs[job] = entry
            if self.demo:
                self._emit(job, "started", state="DEMO", message="DEMO: không SSH, không ghi bag hoặc chuyển động")
                self._start_demo(job, token)
                return True
            process = C.QProcess(self)
            entry["process"] = process
            env = C.QProcessEnvironment.systemEnvironment()
            package = str(Path(__file__).resolve().parents[1])
            env.insert("PYTHONPATH", package + (":" + env.value("PYTHONPATH") if env.value("PYTHONPATH") else ""))
            env.insert("PYTHONUNBUFFERED", "1")
            process.setProcessEnvironment(env)
            process.started.connect(lambda: self._started(job, token))
            process.readyReadStandardOutput.connect(lambda: self._read(job, token, "stdout"))
            process.readyReadStandardError.connect(lambda: self._read(job, token, "stderr"))
            process.errorOccurred.connect(lambda error: self._process_error(job, token, error))
            process.finished.connect(lambda code, status: self._finished(job, token, code, status))
            process.start(argv[0], argv[1:])
            return True
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self._emit(job, "error", state="BLOCKED", message=str(exc))
            return False

    def _entry(self, job, token):
        entry = self._jobs.get(job)
        return entry if entry and entry["token"] == token else None

    def _send_pulses(self):
        for job,entry in list(self._jobs.items()):
            if job not in ('deploy','fetch') and not entry['cancel_requested'] and entry.get('process'):
                entry['process'].write(b'{"command":"pulse"}\n')

    def _started(self, job, token):
        entry = self._entry(job, token)
        if entry:
            entry.update(state="RUNNING", pid=int(entry["process"].processId()))
            self._emit(job, "started", state="RUNNING", pid=entry["pid"], message="Đang chạy tác vụ được chọn")

    def _read(self, job, token, stream):
        entry = self._entry(job, token)
        if not entry:
            return
        process = entry["process"]
        block = process.readAllStandardOutput() if stream == "stdout" else process.readAllStandardError()
        entry[stream] += bytes(block).decode("utf-8", errors="replace")
        while "\n" in entry[stream]:
            line, entry[stream] = entry[stream].split("\n", 1)
            self._line(job, entry, stream, line)
        # Bound a malicious/no-newline output without discarding the evidence.
        if len(entry[stream]) > 65536:
            self._line(job, entry, stream, entry[stream][:65536])
            entry[stream] = entry[stream][65536:]

    def _line(self, job, entry, stream, line):
        if stream == "stdout" and line.startswith(EVENT_PREFIX):
            try:
                value = json.loads(line[len(EVENT_PREFIX):])
                if not isinstance(value, dict) or value.get("job") != job:
                    raise ValueError("Unexpected structured event")
                # Structured records do not get to forge GUI-level job closure.
                if value.get("kind") not in ("progress", "output", "error"):
                    raise ValueError("Unexpected event kind")
                if value.get("state"):
                    entry["state"] = value["state"]
                if value.get("data"):
                    entry["data"] = value["data"]
                self.job_event.emit(value)
                return
            except (ValueError, TypeError):
                pass
        self._emit(job, "output", stream=stream, message=line)

    def _process_error(self, job, token, error):
        entry = self._entry(job, token)
        if entry:
            self._emit(job, "error", state="PROCESS_ERROR", message=entry["process"].errorString())
            if error == C.QProcess.FailedToStart:
                self._finished(job, token, -1, C.QProcess.CrashExit)

    def _finished(self, job, token, code, status):
        entry = self._entry(job, token)
        if not entry:
            return
        if "process" in entry:
            self._read(job, token, "stdout")
            self._read(job, token, "stderr")
            for stream in ("stdout", "stderr"):
                if entry[stream]:
                    self._line(job, entry, stream, entry[stream])
            entry["process"].deleteLater()
        if code == 0 and job in ("deploy", "fetch") and not entry["cancel_requested"]:
            state = "DEPLOYED" if job == "deploy" else "FETCHED"
            entry["state"] = state
            self._emit(job, "progress", state=state, message="Hoàn tất; chưa có lệnh chuyển động")
        del self._jobs[job]
        self._emit(job, "finished", returncode=code, state=entry["state"], data=entry.get("data", {}),
                   cancelled=entry["cancel_requested"], demo=self.demo,
                   message="Process đã đóng; kết quả vận động/chất lượng chỉ theo review riêng" if code == 0
                   else "Tác vụ lỗi hoặc bị hủy; giữ raw/log, không tự chạy lại")

    def stop(self, job=None):
        # Stop motion first, then record/stack, so their supervisors can close
        # raw files and run their own zero/disable finalizers.
        names = [job] if job else sorted(self._jobs, key=lambda name: (name != "run-trial", name == "start-stack"))
        for name in names:
            entry = self._jobs.get(name)
            if not entry or entry["cancel_requested"]:
                continue
            entry["cancel_requested"] = True
            entry["state"] = "CANCELLING"
            self._emit(name, "progress", state="CANCELLING", message="Yêu cầu đóng process sở hữu; mất SSH không bảo đảm zero/disable đã đến STM32")
            if self.demo:
                self._finished(name, entry["token"], 1, C.QProcess.NormalExit)
            elif name in ("deploy", "fetch"):
                try:
                    if entry.get("pid"):
                        os.killpg(entry["pid"], signal.SIGINT)
                    else:
                        entry["process"].terminate()
                except ProcessLookupError:
                    pass
            else:
                entry["process"].write(b'{"command":"cancel"}\n')
                entry["process"].closeWriteChannel()

    def close(self):
        self._closed = True
        self.stop()

    def dispose(self):
        if self._jobs:raise ValueError('Wait for process closure before dispose')
        self._pulse.stop()

    def _start_demo(self, job, token):
        def progress(state, **data):
            entry = self._entry(job, token)
            if entry and not entry["cancel_requested"]:
                entry["state"] = state
                entry["data"] = dict(demo=True, real_data=False, **data)
                self._emit(job, "progress", state=state, data=entry["data"], message="DEMO · " + state)
        def finish():
            if self._entry(job, token):
                self._finished(job, token, 0, C.QProcess.NormalExit)
        if job=='connect-sensors':
            C.QTimer.singleShot(100,lambda:progress('SENSORS_AVAILABLE'))
        elif job == "start-stack":
            C.QTimer.singleShot(100, lambda: progress("STACK_READY"))
        elif job in ("stationary", "record-diagnostic"):
            C.QTimer.singleShot(100, lambda: progress("RECORDING_READY", remaining_s=60))
            # Demo stays ready for a separate user click; it never auto-starts a trial.
            # Qt coarse timers can coalesce/reorder nearby deadlines under load.
            # Emit the final demo state and closure in one callback, in order.
            def finish_recording():
                progress("FINISHED", manifest_status="DEMO_ONLY_NO_DATA")
                finish()
            C.QTimer.singleShot(6000, finish_recording)
        elif job == "run-trial":
            C.QTimer.singleShot(100, lambda: progress("FORWARD"))
            C.QTimer.singleShot(800, lambda: progress("ZERO_DISABLED"))
            C.QTimer.singleShot(1000, finish)
        else:
            states = {"inventory": "INVENTORY_READY", "review": "REVIEW_READY", "status": "STATUS_READY", "observation":"OBSERVATION_SAVED"}
            if job in states:
                C.QTimer.singleShot(100, lambda: progress(states[job], quality_report={"level": "Q0", "demo": True}))
            C.QTimer.singleShot(180, finish)
