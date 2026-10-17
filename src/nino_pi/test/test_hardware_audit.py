"""Measurement/report checks use synthetic data; no ROS or motion commands."""
import ast
import inspect
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from nino_pi import hardware_audit as audit


def imu(**overrides):
    data = dict(stamp_ns=1_000_000_000,frame_id="imu_link",acceleration=[0.,0.,9.81],
                gyro=[0.,0.,0.],orientation=[0.,0.,0.,1.],orientation_available=True,
                acceleration_available=True,gyro_available=True)
    data.update(overrides)
    return data


def test_rates_age_duplicates_backwards_and_missing_header():
    stats = audit.TopicStats()
    for i,stamp in enumerate([1_000_000_000,1_020_000_000,1_020_000_000,1_010_000_000,0]):
        stats.add(imu(stamp_ns=stamp),"imu",10_000_000_000+i*20_000_000,stamp+100_000_000,"gid")
    result = stats.report(10_100_000_000,.5)
    assert result["receipt_hz"] == pytest.approx(50)
    assert result["header_hz"] == pytest.approx(50)
    assert result["duplicate_stamps"] == 1
    assert result["backward_stamps"] == 2
    assert result["zero_stamps"] == 1
    assert result["stamp_age_s"]["median"] == pytest.approx(.1)
    assert result["axis_statistics"]["acceleration_z"]["mean"] == 9.81
    empty = audit.TopicStats().report(100,.5)
    assert empty["receipt_hz"] is None and empty["stamp_age_s"]["p95"] is None
    assert empty["received"] == 0


def test_future_and_stale_not_silently_accepted():
    stats = audit.TopicStats()
    stats.add(imu(),"imu",1,900_000_000,"a")
    stats.add(imu(),"imu",2,2_000_000_000,"a")
    result = stats.report(3,.5)
    assert result["future_stamps"] == result["older_than_threshold"] == 1


def test_unstamped_command_has_no_fabricated_source_age():
    msg = NS(linear=NS(x=.1,y=0.,z=0.),angular=NS(x=0.,y=0.,z=.2))
    data = audit.extract(msg,"command")
    stats = audit.TopicStats()
    stats.add(data,"command",10,100,"source")
    result = stats.report(20,.5)
    assert result["header_hz"] is None
    assert result["stamp_age_s"]["median"] is None
    assert result["nonzero_commands"] == 1


def test_covariance_unavailable_and_nonfinite_and_joint_missing():
    assert audit.measurement_issues(imu(orientation_available=False),"imu") == ["orientation_unavailable"]
    assert "quaternion_not_normalized" in audit.measurement_issues(imu(orientation=[0,0,0,0]),"imu")
    assert "nonfinite_measurement" in audit.measurement_issues(imu(gyro=[math.nan,0,0]),"imu")
    issues = audit.measurement_issues(dict(names=["left","right"],position=[0],velocity=[],effort=[]),"encoder")
    assert "joint_position_length_mismatch" in issues and "joint_velocity_unavailable" in issues


def test_scan_positive_inf_is_no_return_nan_is_not():
    msg = NS(header=NS(stamp=NS(sec=1,nanosec=2),frame_id="laser"),ranges=[math.inf,1.,math.nan,-math.inf,0.],
             range_min=.1,range_max=10.,angle_min=-1.,angle_max=1.,angle_increment=.1,scan_time=.1,time_increment=.001)
    data = audit.extract(msg,"lidar")
    assert data["positive_infinity_count"] == 1
    assert data["finite_in_range"] == 1
    assert data["nan_count"] == 1 and data["invalid_range_count"] == 2
    assert "invalid_scan_ranges" in audit.measurement_issues(data,"lidar")
    msg.ranges = [math.inf]*5
    assert audit.measurement_issues(audit.extract(msg,"lidar"),"lidar") == []


@pytest.mark.parametrize("raw,current,historical",[("throttled=0x0",False,False),
    ("throttled=0x10000",False,True),("throttled=0x10001",True,True)])
def test_power_current_vs_since_boot(raw,current,historical):
    result = audit.throttled(raw)
    assert result["under_voltage_now"] is current
    assert result["under_voltage_since_boot"] is historical


def test_power_unavailable_is_not_healthy():
    assert audit.throttled("permission denied") == {"status":"unavailable"}


def test_graph_escaping_and_direction():
    graph = {"/cmd_vel":dict(publishers=[dict(node='/a\"]-->evil')],subscribers=[dict(node="/motor")])}
    text = audit.graph_mermaid(graph)
    assert '/a\"]-->evil' not in text
    assert "n1 --> n0" in text and "n0 --> n2" in text


def test_callback_signature_delivers_info():
    seen = []
    callback = audit.subscription_callback("/imu","imu",lambda *args:seen.append(args))
    assert len(inspect.signature(callback).parameters) == 2
    callback("message","info")
    assert seen == [("/imu","imu","message","info")]


def test_jazzy_message_info_dict_gid():
    assert audit.publisher_gid({"publisher_gid":[1,2,255]}) == "0102ff"
    assert audit.publisher_gid(NS(publisher_gid=b"\x01\x02\xff")) == "0102ff"
    assert audit.publisher_gid({"source_timestamp":100}) is None


def test_strict_json_keeps_nonfinite_explicit(tmp_path):
    target = tmp_path/"report.json"
    audit.save(target,{"value":math.nan,"inf":math.inf,"missing":None})
    data = json.loads(target.read_text(),parse_constant=lambda _:pytest.fail("invalid JSON number"))
    assert data["value"] == {"nonfinite":"nan"} and data["missing"] is None


def test_code_never_creates_command_publisher_or_parameter_write():
    tree = ast.parse(Path(audit.__file__).read_text())
    forbidden = {"create_publisher","publish","set_parameters","set_parameters_atomically","create_service"}
    assert not [(n.lineno,n.func.attr) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    # Both service types are read-only (list only allowlisted names, then get).
    calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr == "create_client"]
    assert len(calls) == 2 and {n.args[0].id for n in calls} == {"GetParameters","ListParameters"}


def test_output_reuse_rejected_before_ros(tmp_path):
    with pytest.raises(FileExistsError):
        audit.main(["--output",str(tmp_path),"--duration","5"])


@pytest.mark.parametrize("option,value",[("--duration","nan"),("--duration","301"),("--stale-seconds","0"),("--max-samples","0")])
def test_invalid_limits(option,value,tmp_path):
    with pytest.raises(SystemExit):
        audit.main(["--output",str(tmp_path/"new"),option,value])
    assert not (tmp_path/"new").exists()
