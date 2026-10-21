"""Bounded, read-only real robot collection. No driver launch or motion commands.

Raw serialization/storage runs in a separate rosbag2 process from the compact
hardware audit. This supervisor never changes ROS domain, clocks or parameters.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

from nino_pi import hardware_audit


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def load_config(path):
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    topics = config.get("topics")
    if not isinstance(topics, list) or not 1 <= len(topics) <= 128:
        raise ValueError("topics must have 1..128 entries")
    names = set()
    for row in topics:
        if not isinstance(row, dict):
            raise ValueError("each topic must be an object")
        name = row.get("name", "")
        if not isinstance(name, str) or not name.startswith("/") or any(c.isspace() for c in name) or name in names:
            raise ValueError("topic names must be distinct, absolute and contain no spaces")
        if not isinstance(row.get("required"), bool) or not isinstance(row.get("purpose"), str):
            raise ValueError("each topic needs required (bool) and purpose (string)")
        names.add(name)
    for key, lo, hi in (("duration_s", 5, 300), ("max_session_mb", 1, 32768), ("reserve_disk_mb", 1, 32768)):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{key} must be finite in {lo}..{hi}")
    return config


def bag_command(directory, config, qos):
    return ["ros2", "bag", "record", "--storage", "sqlite3", "--output", str(directory / "bag"),
            "--disable-keyboard-controls", "--node-name", "nino_real_data_recorder",
            "--max-cache-size", "16777216", "--qos-profile-overrides-path", str(qos),
            "--topics", *[row["name"] for row in config["topics"]]]


def stop_child(child, grace=15):
    """Signal our own process group only; forced shutdown invalidates the session."""
    if child.poll() is not None:
        return {"returncode": child.returncode, "forced": False}
    try:
        os.killpg(child.pid, signal.SIGINT)
    except ProcessLookupError:
        return {"returncode": child.wait(timeout=grace), "forced": False}
    try:
        return {"returncode": child.wait(timeout=grace), "forced": False}
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)
        return {"returncode": child.returncode, "forced": True}


def inspect_bag(directory, config):
    """Read original SQLite messages without conversion, filtering or resampling."""
    topics, errors = {}, []
    files = sorted(directory.glob("*.db3"))
    if not files:
        errors.append("no_sqlite_storage")
    metadata = None
    if not (directory / "metadata.yaml").is_file():
        errors.append("bag_metadata_not_closed")
    else:
        import yaml
        try:
            metadata = yaml.safe_load((directory / "metadata.yaml").read_text())["rosbag2_bagfile_information"]
            if (not isinstance(metadata, dict) or type(metadata.get("message_count")) is not int
                    or metadata["message_count"] < 0
                    or not isinstance(metadata.get("relative_file_paths"), list)
                    or not all(isinstance(p, str) for p in metadata["relative_file_paths"])):
                raise ValueError("metadata needs nonnegative message_count and a list of storage file names")
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
            errors.append("bag_metadata_invalid:" + str(exc))
            metadata = None
    for path in files:
        try:
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    errors.append(path.name + ":sqlite_integrity_failed")
                rows = db.execute("SELECT t.name,t.type,COUNT(m.id),MIN(m.timestamp),MAX(m.timestamp) "
                                  "FROM topics t LEFT JOIN messages m ON m.topic_id=t.id GROUP BY t.id")
                for name, msg_type, count, first, last in rows:
                    item = topics.setdefault(name, dict(type=msg_type, count=0, first_bag_time_ns=None, last_bag_time_ns=None))
                    if item["type"] != msg_type:
                        errors.append(name + ":type_changed")
                    item["count"] += count
                    if count:
                        item["first_bag_time_ns"] = min(v for v in (item["first_bag_time_ns"], first) if v is not None)
                        item["last_bag_time_ns"] = max(v for v in (item["last_bag_time_ns"], last) if v is not None)
        except sqlite3.Error as exc:
            errors.append(path.name + ":" + str(exc))
    if metadata is not None:
        if metadata["message_count"] != sum(row["count"] for row in topics.values()):
            errors.append("metadata_storage_count_mismatch")
        if set(metadata.get("relative_file_paths", [])) != {p.name for p in files}:
            errors.append("metadata_storage_files_mismatch")
    missing = [row["name"] for row in config["topics"] if not topics.get(row["name"], {}).get("count")]
    required = [row["name"] for row in config["topics"] if row["required"] and row["name"] in missing]
    return dict(topics=topics, missing_topics=missing, missing_required_topics=required, errors=errors,
                note="Counts are recorded messages, not sensor-produced counts or a coverage guarantee. Bag time is recorder receipt time; original source headers remain in CDR payloads.")


def session_issues(reason, children, bag, audit):
    issues = [] if reason == "duration_reached" else [reason]
    for name, status in children.items():
        # A normal rosbag SIGINT exits 0 on Jazzy. Other exits remain failures.
        if status["forced"] or status["returncode"] != 0:
            issues.append(name + ":shutdown_or_process_error")
    issues.extend(bag["errors"])
    issues.extend("missing_required:" + name for name in bag["missing_required_topics"])
    if audit.get("status") != "collected_not_hardware_certified":
        issues.append("hardware_audit_incomplete")
    if audit.get("raw_samples_omitted", 0):
        issues.append("audit_raw_log_limit")
    if not any(row.get("count", 0) for row in bag["topics"].values()):
        issues.append("no_recorded_messages")
    return issues


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--session", required=True, type=Path, help="filled manual measurement/session JSON; unknowns stay null")
    parser.add_argument("--qos", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new directory, ideally outside checkout")
    parser.add_argument("--signals", type=Path, help="optional state_monitor driver mapping, copied for interpretation")
    parser.add_argument("--check", action="store_true", help="validate inputs and show plan; no ROS processes or output directory")
    opt = parser.parse_args(args)
    try:
        import yaml
    except ImportError:
        parser.error("install python3-yaml with scripts/install_collection_dependencies.sh first")
    try:
        config = load_config(opt.config)
        session = json.loads(opt.session.read_text())
        if not isinstance(session, dict) or not isinstance(session.get("session_id"), str) or not session["session_id"].strip():
            raise ValueError("session JSON requires a nonempty session_id")
        qos = yaml.safe_load(opt.qos.read_text())
        if not isinstance(qos, dict):
            raise ValueError("QoS must be a YAML topic-to-profile mapping")
        if opt.signals:
            from nino_pi.state_monitor import load_signals
            signals = load_signals(opt.signals)
            absent = sorted({s["topic"] for s in signals} - {t["name"] for t in config["topics"]})
            if absent:
                raise ValueError("add mapped signal topics to collection config: " + ", ".join(absent))
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    directory = opt.output.expanduser().resolve()
    command = bag_command(directory, config, opt.qos.expanduser().resolve())
    if opt.check:
        print(json.dumps(dict(config=config, bag_command=command, motion_commands_sent=0,
                              note="Validation only; driver availability, QoS compatibility and hardware calibration are not verified."), indent=2))
        return 0
    if not shutil.which("ros2") or not os.environ.get("ROS_DISTRO"):
        parser.error("source /opt/ros/jazzy/setup.bash and the real driver workspace first")
    check = subprocess.run(["ros2", "bag", "record", "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=15)
    if check.returncode:
        parser.error("rosbag2 unavailable: " + check.stderr[-500:])
    directory.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory.parent).free < (config["reserve_disk_mb"] + config["max_session_mb"]) * 1024**2:
        parser.error("insufficient free disk for configured session budget plus reserve")
    directory.mkdir(exist_ok=False)
    save(directory / "collection_config.json", config)
    save(directory / "session.json", session)
    shutil.copyfile(opt.qos, directory / "qos.yaml")
    if opt.signals:
        shutil.copyfile(opt.signals, directory / "motor_signals.json")
    command = bag_command(directory, config, directory / "qos.yaml")
    audit_command = [sys.executable, str(Path(hardware_audit.__file__).resolve()), "--duration", str(config["duration_s"]),
                     "--output", str(directory / "audit")]
    started = time.monotonic_ns()
    manifest = dict(schema_version=1, started_utc=datetime.now(timezone.utc).isoformat(), started_wall_ns=time.time_ns(),
                    started_monotonic_ns=started, host=hardware_audit.host_inventory(),
                    commands=dict(bag=command, audit=audit_command), motion_commands_sent=0,
                    status="started", note="Read-only observers do not prevent another node from driving the robot.")
    save(directory / "manifest.json", manifest)
    children, streams, statuses, powers = {}, [], {}, []
    reason, errors = "duration_reached", []
    old_handlers = {}

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, interrupted)
        for name, argv in (("bag", command), ("audit", audit_command)):
            stream = (directory / (name + ".log")).open("x")
            streams.append(stream)
            children[name] = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        next_power = 0
        while (time.monotonic_ns() - started) / 1e9 < config["duration_s"]:
            if time.monotonic() >= next_power:
                powers.append(dict(receipt_monotonic_ns=time.monotonic_ns(), **hardware_audit.power_snapshot()))
                save(directory / "power_timeline.json", powers)
                next_power = time.monotonic() + 5
            for name, child in children.items():
                if child.poll() is not None and (name == "bag" or child.returncode != 0):
                    raise RuntimeError(name + ":exited_early")
            size = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
            if size > config["max_session_mb"] * 1024**2:
                reason = "session_size_limit"
                break
            if shutil.disk_usage(directory).free < config["reserve_disk_mb"] * 1024**2:
                reason = "disk_reserve_limit"
                break
            time.sleep(.2)
    except KeyboardInterrupt:
        reason = "interrupted_partial_session"
    except Exception as exc:
        reason = "collection_error"
        errors.append(str(exc))
    finally:
        # A second Ctrl+C cannot bypass closing files. No signal to driver nodes.
        for sig in old_handlers:
            signal.signal(sig, signal.SIG_IGN)
        for name, child in children.items():
            if name == "audit" and reason == "duration_reached":
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
            statuses[name] = stop_child(child)
        for stream in streams:
            stream.close()
        for sig, previous in old_handlers.items():
            signal.signal(sig, previous)
    bag = inspect_bag(directory / "bag", config)
    audit = {}
    try:
        audit = json.loads((directory / "audit" / "report.json").read_text())
    except (OSError, ValueError) as exc:
        errors.append("audit_report:" + str(exc))
    issues = session_issues(reason, statuses, bag, audit) + errors
    manifest.update(status="incomplete" if issues else "captured_not_calibrated", reason=reason, issues=issues,
                    finished_utc=datetime.now(timezone.utc).isoformat(), finished_wall_ns=time.time_ns(),
                    finished_monotonic_ns=time.monotonic_ns(), children=statuses, bag=bag,
                    audit_warnings=audit.get("warnings", []),
                    timing_note="Supervisor and compact audit record wall/monotonic anchors. Bag receipt clock and original headers are distinct; no header rewriting or resampling. No per-message monotonic timestamp in bag.")
    save(directory / "manifest.json", manifest)
    hashes = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024**2), b""):
                    digest.update(chunk)
            hashes[str(path.relative_to(directory))] = digest.hexdigest()
    hashes["collector_source"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    hashes["audit_source"] = hashlib.sha256(Path(hardware_audit.__file__).read_bytes()).hexdigest()
    save(directory / "sha256.json", hashes)
    print(f"{manifest['status']}: {directory / 'manifest.json'}")
    print("Missing required:", bag["missing_required_topics"], "Issues:", issues)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
