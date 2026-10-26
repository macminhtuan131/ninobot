"""Opt-in two-process acquisition lifecycle. No ROS, world steps or control writes."""
import hashlib
import json
import os
import csv
import shutil
from pathlib import Path
import time
import uuid

from nino_rl.acquisition_frames import atomic_json

SCHEMA = "isolated_joint_gt_integration_v1"
SENSOR_TOPICS = {"/joint_states", "/ground_truth/odom"}
ROLE_SOURCES = {
    "primary": ("governor_logger.py", "observer_health.py", "acquisition_contract.py"),
    "joint_gt": ("isolated_acquisition.py", "acquisition_frames.py", "acquisition_contract.py"),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_session(path):
    value = json.loads(Path(path).read_text())
    if value.get("schema") != SCHEMA or not value.get("session_id"):
        raise ValueError("Invalid acquisition session")
    for name in ("protocol", "config", "world"):
        if sha(value[name+"_path"]) != value[name+"_sha256"]:
            raise ValueError("Acquisition binding drift: " + name)
    return value


def create_session(directory, protocol, config, world, job):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    value = dict(schema=SCHEMA, session_id=uuid.uuid4().hex, directory=str(directory),
                 job=job, roles=list(ROLE_SOURCES), timeout_s=10., max_status_age_s=2.,
                 max_source_age_s=.1, source_sha256={})
    for name, path in (("protocol", protocol), ("config", config), ("world", world)):
        path = Path(path).resolve()
        value[name+"_path"], value[name+"_sha256"] = str(path), sha(path)
    for role, files in ROLE_SOURCES.items():
        value["source_sha256"][role] = {name: sha(Path(__file__).with_name(name)) for name in files}
    path = directory/"session.json"
    atomic_json(path, value)
    return path


class Lifecycle:
    """Status writes on a steady timer; sample callbacks only update small counters."""
    def __init__(self, session_path, role, output):
        self.path = Path(session_path)
        self.session = read_session(self.path)
        actual = {name: sha(Path(__file__).with_name(name)) for name in ROLE_SOURCES[role]}
        if actual != self.session["source_sha256"][role]:
            raise ValueError("Runtime logger source differs from frozen session")
        self.role = role
        self.status = dict(schema=SCHEMA, session_id=self.session["session_id"],
            protocol_sha256=self.session["protocol_sha256"], role=role,
            source_sha256=actual, output=str(Path(output).resolve()), pid=os.getpid(),
            counts={}, latest_source_ns={}, ready=False, closed=False, error=None,
            lifecycle=[])

    def sample(self, topic, source_ns):
        if topic in SENSOR_TOPICS:
            self.status["counts"][topic] = self.status["counts"].get(topic, 0)+1
            self.status["latest_source_ns"][topic] = source_ns

    def publish(self, now_ns):
        self.status.update(now_ns=now_ns, monotonic_ns=time.monotonic_ns(),
            ready=all(self.status["counts"].get(t, 0) > 0 for t in SENSOR_TOPICS))
        atomic_json(Path(self.session["directory"])/(self.role+"_status.json"), self.status)

    def marker(self, marker, now_ns):
        self.status["lifecycle"].append(marker)
        self.publish(now_ns)
        atomic_json(Path(self.session["directory"])/(self.role+"_"+marker["event"]+".json"),
                    dict(self.status, marker=marker))

    def close(self, now_ns, error=None):
        self.status.update(closed=True, error=error)
        self.publish(now_ns)


def check_status(session, status, role, *, now_mono_ns=None, marker=None, closed=False):
    if (status.get("schema") != SCHEMA or status.get("session_id") != session["session_id"]
            or status.get("protocol_sha256") != session["protocol_sha256"]
            or status.get("role") != role
            or status.get("source_sha256") != session["source_sha256"][role]
            or status.get("error") or status.get("ready") is not True
            or status.get("closed") is not closed):
        raise ValueError("Logger identity/readiness/closure invalid: " + role)
    if not closed:
        now_mono_ns = time.monotonic_ns() if now_mono_ns is None else now_mono_ns
        age = (now_mono_ns-status["monotonic_ns"])*1e-9
        if not 0 <= age <= session["max_status_age_s"]:
            raise ValueError("Stale logger status: " + role)
    for topic in SENSOR_TOPICS:
        source = status["latest_source_ns"].get(topic)
        if source is None or not status["counts"].get(topic):
            raise ValueError("Missing fresh sensor: " + topic)
        # Marker ACKs establish delivery, not a new sampling gate. Readiness
        # uses the same100ms source-age bound; epoch validation follows offline.
        if marker is None and not closed:
            age = (status["now_ns"]-source)*1e-9
            if not -1e-9 <= age <= session["max_source_age_s"]+1e-9:
                raise ValueError("Stale/future logger sensor: " + topic)
    if marker is not None and status.get("marker") != marker:
        raise ValueError("Missing or foreign lifecycle ACK: " + role)
    return True


def check_delivery(session, live, receipt, role, marker, *, now_mono_ns=None):
    """Bind an immutable marker ACK to a fresh heartbeat from the same process.

    Evaluator native persistence may take longer than the heartbeat age bound.
    The receipt establishes exact delivery at its recorded instant; it cannot
    establish current liveness. Keep the original wall-age limit on live status.
    """
    check_status(session, receipt, role, marker=marker,
                 now_mono_ns=receipt["monotonic_ns"])
    for key in ("schema", "session_id", "protocol_sha256", "role", "source_sha256", "pid", "output"):
        if live.get(key) != receipt.get(key):
            raise ValueError("Live/receipt identity mismatch: " + key)
    if live.get("error") or live.get("ready") is not True or live.get("closed") is not False:
        raise ValueError("Live process is not ready/open/error-free")
    now_mono_ns = time.monotonic_ns() if now_mono_ns is None else now_mono_ns
    age = (now_mono_ns-live["monotonic_ns"])*1e-9
    if not 0 <= age <= session["max_status_age_s"]:
        raise ValueError("Stale/future live heartbeat: " + role)
    if receipt["monotonic_ns"] > live["monotonic_ns"]:
        raise ValueError("Receipt newer than live evidence: " + role)
    if marker not in live.get("lifecycle", []):
        raise ValueError("Live process does not acknowledge expected marker: " + role)
    for topic in SENSOR_TOPICS:
        if (not live["counts"].get(topic)
                or live["counts"][topic] < receipt["counts"][topic]
                or live["latest_source_ns"].get(topic) is None
                or live["latest_source_ns"][topic] < receipt["latest_source_ns"][topic]):
            raise ValueError("Live stream missing/regressed: " + topic)
    return True


def wait_pair(session_path, *, marker=None, alive=lambda: True, pump=None):
    session = read_session(session_path)
    end = time.monotonic()+session["timeout_s"]
    last = None
    while time.monotonic() < end:
        if not alive():
            raise RuntimeError("Acquisition process exited before lifecycle completed")
        try:
            values = {}
            for role in ROLE_SOURCES:
                suffix = marker["event"] if marker else "status"
                value = json.loads((Path(session["directory"])/(role+"_"+suffix+".json")).read_text())
                if marker is None:
                    check_status(session, value, role)
                else:
                    live = json.loads((Path(session["directory"])/(role+"_status.json")).read_text())
                    check_delivery(session, live, value, role, marker)
                values[role] = value
            if values["primary"]["pid"] == values["joint_gt"]["pid"]:
                raise ValueError("Joint/GT acquisition is not process isolated")
            return values
        except (OSError, ValueError, KeyError, TypeError) as error:
            last = str(error)
        if pump:
            pump()
        else:
            time.sleep(.01)
    raise TimeoutError("Both logger readiness/lifecycle required, no retry: " + str(last))


def publish_episode(publisher, marker, ros):
    """Wait for discovery and both ACKs without advancing simulated time."""
    from std_msgs.msg import String
    session = os.environ.get("NINO_ACQUISITION_SESSION")
    if session:
        settings = read_session(session)
        deadline = time.monotonic()+settings["timeout_s"]
        while publisher.get_subscription_count() < 2:
            if time.monotonic() >= deadline:
                raise TimeoutError("Both episode subscribers must be discovered")
            time.sleep(.01)
    publisher.publish(String(data=json.dumps(marker)))
    if session:
        if marker["event"]=="end":
            # Do not turn an observed task outcome into a lost native row if
            # the observer is broken. The runner waits AFTER native persistence.
            settings=read_session(session)
            atomic_json(Path(settings["directory"])/"expected_end.json",marker)
        else:wait_pair(session, marker=marker)


def episode_publisher(publisher,ros):
    if not os.environ.get("NINO_ACQUISITION_SESSION"):
        return publisher
    class AcknowledgedPublisher:
        def publish(self,message):
            publish_episode(publisher,json.loads(message.data),ros)
    return AcknowledgedPublisher()


def metadata_for_view(directory):
    directory = Path(directory)
    path = directory/("primary_metadata.json" if (directory/"view_manifest.json").exists() else "metadata.json")
    return json.loads(path.read_text())


def finalize_view(case, evaluation, primary, session_path):
    """Close/provenance gate before admitting the explicit new measurement view."""
    from nino_rl.isolated_acquisition import compose_view
    from nino_rl.observer_health import check_sidecar
    case, evaluation, primary = Path(case), Path(evaluation), Path(primary)
    session = read_session(session_path)
    traces = list(evaluation.glob("episode-*/control_trace.csv"))
    if len(traces) != 1:
        raise ValueError("Exactly one control trace required for acquisition identity")
    control_path = traces[0]
    controls = list(csv.DictReader(control_path.open()))
    if not controls:
        raise ValueError("Missing native controls, no inferred lifecycle window")
    native_path = evaluation/"episodes.csv"
    native = list(csv.DictReader(native_path.open()))
    if len(native) != 1:
        raise ValueError("Exactly one native outcome required for acquisition identity")
    run_id = native[0].get("governor_run_id", "")
    if (not run_id or run_id.strip() != run_id
            or int(native[0]["seed"]) != session["job"]["seed"]
            or int(native[0]["attempt"]) != 1):
        raise ValueError("Native outcome identity missing or foreign")
    # Production traces carry input/end timestamps but no run ID column.
    # If a future trace includes one, it must agree on EVERY row.
    if any("governor_run_id" in row and row["governor_run_id"] != run_id for row in controls):
        raise ValueError("Control/native run identity disagreement")
    start = float(controls[0]["governor_input_time_s"])
    end = float(controls[-1]["sim_time_s"])
    capture = case/"joint_gt"
    primary_metadata = json.loads((primary/"metadata.json").read_text())
    capture_metadata = json.loads((capture/"capture_manifest.json").read_text())
    statuses = {}
    readiness_path=Path(session["directory"])/"readiness_pair.json"
    readiness=json.loads(readiness_path.read_text())
    expected_end_path=Path(session["directory"])/"expected_end.json"
    expected_end=json.loads(expected_end_path.read_text())
    if (expected_end.get("run_id") != run_id
            or expected_end.get("metrics", {}).get("governor_run_id") != run_id):
        raise ValueError("Native outcome differs from terminal marker identity")
    inputs = [Path(session_path),readiness_path,expected_end_path,native_path,control_path]
    for role, source in (("primary", primary), ("joint_gt", capture)):
        status_path = Path(session["directory"])/(role+"_status.json")
        value = json.loads(status_path.read_text())
        check_status(session, value, role, closed=True)
        check_status(session,readiness[role],role,now_mono_ns=readiness[role]["monotonic_ns"])
        if readiness[role]["pid"]!=value["pid"] or readiness[role]["output"]!=value["output"]:
            raise ValueError("Logger restarted or output changed after readiness")
        if Path(value["output"]).resolve() != source.resolve():
            raise ValueError("Closed logger output differs from assigned source")
        markers = value["lifecycle"]
        if (len(markers) != 2 or [m.get("event") for m in markers] != ["reset", "end"]
                or any(m.get("run_id") != run_id or m.get("attempt") != 1 for m in markers)
                or markers[0].get("seed") != session["job"]["seed"]):
            raise ValueError("Closed logger reset/end identity mismatch")
        if markers[-1]!=expected_end:
            raise ValueError("End ACK differs from evaluator terminal marker")
        if role == "primary" and (markers[0].get("settings") != json.loads(
                (source/"resolved_config.json").read_text())["governor"]):
            raise ValueError("Lifecycle settings differ from assigned configuration")
        statuses[role] = value
        inputs.append(status_path)
        for event, marker in zip(("reset", "end"), markers):
            path = Path(session["directory"])/(role+"_"+event+".json")
            ack = json.loads(path.read_text())
            check_status(session, ack, role, marker=marker, now_mono_ns=ack["monotonic_ns"])
            inputs.append(path)
    if statuses["primary"]["pid"] == statuses["joint_gt"]["pid"]:
        raise ValueError("Both acquisition roles share a process")
    if statuses["primary"]["lifecycle"] != statuses["joint_gt"]["lifecycle"]:
        raise ValueError("Logger lifecycle disagreement")
    for metadata in (primary_metadata, capture_metadata):
        if (metadata.get("acquisition_session_id") != session["session_id"]
                or metadata.get("acquisition_protocol_sha256") != session["protocol_sha256"]):
            raise ValueError("Logger metadata not bound to acquisition session")
    if (primary_metadata.get("logger_sha256") != session["source_sha256"]["primary"]["governor_logger.py"]
            or capture_metadata.get("source_sha256") != session["source_sha256"]["joint_gt"]["isolated_acquisition.py"]
            or capture_metadata.get("frames_source_sha256") != session["source_sha256"]["joint_gt"]["acquisition_frames.py"]
            or primary_metadata.get("source_config_sha256") != session["config_sha256"]
            or primary_metadata.get("world_sha256") != session["world_sha256"]):
        raise ValueError("Logger config/world/source provenance mismatch")
    health = check_sidecar(primary, session["source_sha256"]["primary"]["observer_health.py"])
    if not health["valid"]:
        raise ValueError("Primary health/closure invalid: " + str(health.get("error")))
    output = case/"measurement_view"
    result = compose_view(primary, capture, output, run_id, 1, round(start*1e9), round(end*1e9),
                          selected_epoch_only=True)
    # Files are copied verbatim; view deliberately has no legacy metadata.json.
    auxiliary = ("contact_events.jsonl", "world_metadata.json", "resolved_config.json", "source_config.yaml",
                 "robot_description.urdf", "observer_health_summary.json", "observer_health.jsonl")
    for name in auxiliary:
        inputs.append(primary/name)
        shutil.copy2(primary/name, output/name)
    inputs += [primary/"samples.jsonl", primary/"metadata.json",
               capture/"joint_gt.frames", capture/"capture_manifest.json"]
    inputs += [Path(session[k+"_path"]) for k in ("protocol", "config", "world")]
    result.update(schema=SCHEMA, valid_for_existing_scoring=False,
        native_identity_source=str(native_path.resolve()),
        admitted_for_new_contract=True, session_id=session["session_id"],
        protocol_sha256=session["protocol_sha256"], primary_logger=str(primary.resolve()),
        session_path=str(Path(session_path).resolve()), both_loggers_closed=True,
        input_sha256={str(p.resolve()): sha(p) for p in inputs},
        derived_sha256={str(p.relative_to(output)): sha(p) for p in output.rglob("*")
                        if p.is_file() and p.name != "view_manifest.json"},
        qualification="Explicit two-process contract only. CRC/closure are not sampling coverage. Original native replay, timestamp, per-window coverage and stopping gates remain mandatory.")
    atomic_json(output/"view_manifest.json", result)
    verify_view(output)
    return output


def verify_view(directory):
    directory = Path(directory)
    result = json.loads((directory/"view_manifest.json").read_text())
    if (result.get("schema") != SCHEMA or result.get("complete") is not True
            or result.get("admitted_for_new_contract") is not True
            or result.get("both_loggers_closed") is not True
            or result.get("valid_for_existing_scoring") is not False
            or result.get("measurement_authority") != {t:"isolated_capture_only" for t in SENSOR_TOPICS}
            or result.get("missing_values_filled") is not False or result.get("resampling") is not False):
        raise ValueError("Not an admitted isolated acquisition view")
    for name, expected in result["input_sha256"].items():
        if sha(name) != expected:
            raise ValueError("Acquisition input changed: " + name)
    for name, expected in result["derived_sha256"].items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory.resolve()) or sha(path) != expected:
            raise ValueError("Derived measurement view changed: " + name)
    session = read_session(result["session_path"])
    if (session["session_id"] != result["session_id"]
            or session["protocol_sha256"] != result["protocol_sha256"]):
        raise ValueError("View/session protocol identity mismatch")
    return result
