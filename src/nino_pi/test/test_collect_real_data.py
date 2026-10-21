"""Collection contract/fault tests; no real robot, Gazebo or actuation."""
import ast
import copy
import json
from pathlib import Path
import signal
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

from nino_pi import collect_real_data as collect


CONFIG = Path(__file__).resolve().parents[1] / "config"


def make_bag(tmp_path, metadata=True):
    directory = tmp_path / "bag"
    directory.mkdir()
    if metadata:
        (directory / "metadata.yaml").write_text("rosbag2_bagfile_information:\n  message_count: 3\n  relative_file_paths: [data.db3]\n")
    with sqlite3.connect(directory / "data.db3") as db:
        db.execute("CREATE TABLE topics (id INTEGER, name TEXT, type TEXT)")
        db.execute("CREATE TABLE messages (id INTEGER, topic_id INTEGER, timestamp INTEGER)")
        db.execute("INSERT INTO topics VALUES (1,'/imu/data','sensor_msgs/msg/Imu')")
        db.executemany("INSERT INTO messages VALUES (?,1,?)", [(1, 200), (2, 100), (3, 200)])
    return directory


def test_default_configuration_and_no_simulated_clock_or_all_topics(tmp_path):
    config = collect.load_config(CONFIG / "real_collection.json")
    argv = collect.bag_command(tmp_path, config, CONFIG / "real_collection_qos.yaml")
    assert argv[:3] == ["ros2", "bag", "record"]
    assert not {"-a", "--all", "--use-sim-time", "--no-discovery"}.intersection(argv)
    assert "/tf_static" in argv and "--disable-keyboard-controls" in argv
    assert "--storage" in argv and "sqlite3" in argv


@pytest.mark.parametrize("change", [
    {"duration_s": 0}, {"duration_s": float("nan")}, {"reserve_disk_mb": -1},
    {"max_session_mb": True}, {"schema_version": 2}, {"topics": []},
    {"topics": [{"name": "relative", "required": True, "purpose": "test"}]},
    {"topics": [{"name": "/a", "required": "true", "purpose": "test"}]},
    {"topics": [{"name": "/a", "required": True, "purpose": "a"}] * 2},
])
def test_invalid_config_rejected(change, tmp_path):
    config = json.loads((CONFIG / "real_collection.json").read_text())
    config.update(change)
    target = tmp_path / "config.json"
    target.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        collect.load_config(target)


def test_bag_keeps_every_count_duplicate_and_backwards_time(tmp_path):
    config = collect.load_config(CONFIG / "real_collection.json")
    result = collect.inspect_bag(make_bag(tmp_path), config)
    assert result["topics"]["/imu/data"]["count"] == 3
    assert result["topics"]["/imu/data"]["first_bag_time_ns"] == 100
    assert result["topics"]["/imu/data"]["last_bag_time_ns"] == 200
    assert "/joint_states" in result["missing_required_topics"]
    assert "/battery_state" in result["missing_topics"]
    assert "/battery_state" not in result["missing_required_topics"]


def test_metadata_missing_and_corrupt_storage_are_faults(tmp_path):
    directory = make_bag(tmp_path, metadata=False)
    (directory / "broken.db3").write_text("not sqlite")
    result = collect.inspect_bag(directory, collect.load_config(CONFIG / "real_collection.json"))
    assert "bag_metadata_not_closed" in result["errors"]
    assert any("broken.db3" in e for e in result["errors"])


def test_metadata_count_mismatch_remains_failure(tmp_path):
    directory = make_bag(tmp_path)
    path = directory / "metadata.yaml"
    path.write_text(path.read_text().replace("message_count: 3", "message_count: 2"))
    result = collect.inspect_bag(directory, collect.load_config(CONFIG / "real_collection.json"))
    assert "metadata_storage_count_mismatch" in result["errors"]


@pytest.mark.parametrize("text", ["[invalid", "null", "rosbag2_bagfile_information: {message_count: 3, relative_file_paths: false}"])
def test_malformed_metadata_is_reported_not_a_report_crash(tmp_path, text):
    directory = make_bag(tmp_path)
    (directory / "metadata.yaml").write_text(text)
    result = collect.inspect_bag(directory, collect.load_config(CONFIG / "real_collection.json"))
    assert any(e.startswith("bag_metadata_invalid:") for e in result["errors"])


def test_session_never_claims_missing_torque_is_measured_or_missing_data_complete():
    children = dict(bag=dict(returncode=0, forced=False), audit=dict(returncode=0, forced=False))
    bag = dict(errors=[], missing_required_topics=[], topics={"/imu": dict(count=10)})
    audit = dict(status="collected_not_hardware_certified", raw_samples_omitted=0)
    assert collect.session_issues("duration_reached", children, bag, audit) == []
    incomplete = copy.deepcopy(bag)
    incomplete["missing_required_topics"] = ["/joints"]
    assert "missing_required:/joints" in collect.session_issues("duration_reached", children, incomplete, audit)
    assert "interrupted_partial_session" in collect.session_issues("interrupted_partial_session", children, bag, audit)
    assert "audit_raw_log_limit" in collect.session_issues("duration_reached", children, bag, dict(audit, raw_samples_omitted=1))
    children["bag"]["forced"] = True
    assert "bag:shutdown_or_process_error" in collect.session_issues("duration_reached", children, bag, audit)


def test_child_shutdown_escalation_is_reported(monkeypatch):
    seen = []
    monkeypatch.setattr(collect.os, "killpg", lambda pid, sig: seen.append((pid, sig)))
    class Stuck:
        pid = 123
        returncode = None
        calls = 0

        def poll(self):
            return None

        def wait(self, timeout):
            self.calls += 1
            if self.calls < 3:
                raise subprocess.TimeoutExpired("child", timeout)
            self.returncode = -9
            return -9
    assert collect.stop_child(Stuck(), grace=.01) == dict(returncode=-9, forced=True)
    assert [sig for _, sig in seen] == [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]
    assert collect.stop_child(SimpleNamespace(poll=lambda: 0, returncode=0)) == dict(returncode=0, forced=False)


def test_check_creates_no_session_and_does_not_launch_processes(tmp_path, monkeypatch):
    monkeypatch.setattr(collect.subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch processes"))
    target = tmp_path / "new"
    assert collect.main(["--check", "--config", str(CONFIG / "real_collection.json"),
                         "--session", str(CONFIG / "real_session.template.json"),
                         "--qos", str(CONFIG / "real_collection_qos.yaml"), "--output", str(target)]) == 0
    assert not target.exists()


def test_custom_motor_topics_cannot_be_silently_omitted(tmp_path):
    with pytest.raises(SystemExit):
        collect.main(["--check", "--config", str(CONFIG / "real_collection.json"),
                      "--session", str(CONFIG / "real_session.template.json"),
                      "--qos", str(CONFIG / "real_collection_qos.yaml"), "--output", str(tmp_path / "new"),
                      "--signals", str(CONFIG / "motor_telemetry.example.json")])
    assert not (tmp_path / "new").exists()


def test_no_motor_publisher_service_write_or_driver_launch():
    tree = ast.parse(Path(collect.__file__).read_text())
    forbidden = {"create_publisher", "publish", "set_parameters", "set_parameters_atomically", "create_client"}
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in forbidden]
    assert "ros2 launch" not in Path(collect.__file__).read_text()


def test_failed_recorder_start_retains_manifest_and_reports_incomplete(tmp_path, monkeypatch):
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setattr(collect.shutil, "which", lambda _: "/fake/ros2")
    monkeypatch.setattr(collect.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    monkeypatch.setattr(collect.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(collect.hardware_audit, "host_inventory", lambda: {})
    def fail(*args, **kwargs):
        raise OSError("recorder executable missing")
    monkeypatch.setattr(collect.subprocess, "Popen", fail)
    output = tmp_path / "failed_start"
    code = collect.main(["--config", str(CONFIG / "real_collection.json"),
                         "--session", str(CONFIG / "real_session.template.json"),
                         "--qos", str(CONFIG / "real_collection_qos.yaml"), "--output", str(output)])
    assert code == 1
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "incomplete"
    assert "recorder executable missing" in manifest["issues"]
    assert (output / "sha256.json").exists()


def test_low_disk_rejects_before_starting_collection(tmp_path, monkeypatch):
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setattr(collect.shutil, "which", lambda _: "/fake/ros2")
    monkeypatch.setattr(collect.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    monkeypatch.setattr(collect.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(collect.subprocess, "Popen", lambda *a, **k: pytest.fail("must not start collection"))
    output = tmp_path / "disk_full"
    with pytest.raises(SystemExit):
        collect.main(["--config", str(CONFIG / "real_collection.json"),
                      "--session", str(CONFIG / "real_session.template.json"),
                      "--qos", str(CONFIG / "real_collection_qos.yaml"), "--output", str(output)])
    assert not output.exists()
