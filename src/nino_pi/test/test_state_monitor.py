import ast
import json
import math
from pathlib import Path

import pytest

from nino_pi import state_monitor as monitor


def joints(effort=None):
    return dict(header=dict(stamp=dict(sec=1,nanosec=0)),name=["right","left"],
                position=[.2,.1],velocity=[2.,1.],effort=[] if effort is None else effort)


def specs(role="joints",signals=None):
    return {"/test":dict(role=role,types=[],signals=signals or [])}


def test_joint_order_missing_effort_and_classification():
    row=monitor.summarize("joints",joints())
    assert row["joints"][0]["name"]=="right"
    assert row["joints"][0]["velocity_rad_s"]==2.
    assert row["joints"][0]["effort_Nm"] is None
    assert row["effort_kind"]=="reported_unverified"
    assert monitor.summarize("joints",joints([.3,.4]))["joints"][1]["effort_Nm"]==.4
    assert monitor.summarize("joints",joints([.3]))["schema_valid"] is False


def test_drive_labels_no_index_guessing_and_no_measured_torque_claim():
    msg=dict(layout=dict(dim=[dict(label="left_applied_nm,left_actual_rad_s")]),data=[.3,2.])
    row=monitor.summarize("drive",msg)
    assert row["fields"]["left_applied_nm"]==.3
    assert "not measured torque" in row["note"]
    msg["layout"]["dim"][0]["label"]="duplicate,duplicate"
    assert monitor.summarize("drive",msg)["fields"]=={}
    assert monitor.summarize("drive",dict(data=[1,2]))["schema_valid"] is False
    assert monitor.summarize("torque_command",dict(data=[1.,2.]))["kind"]=="command"


def test_imu_unavailable_and_invalid_quaternion():
    msg=dict(header=dict(frame_id="imu"),orientation=dict(x=0,y=0,z=0,w=1),orientation_covariance=[-1],
             linear_acceleration=dict(x=0,y=0,z=9.81),linear_acceleration_covariance=[-1],
             angular_velocity=dict(x=0,y=0,z=0),angular_velocity_covariance=[0])
    row=monitor.summarize("imu",msg)
    assert row["rpy_in_reported_imu_frame_deg"] is None and row["acceleration_m_s2"] is None
    assert row["gyro_rad_s"]==[0.,0.,0.]
    assert monitor.rpy_degrees(dict(x=0,y=0,z=0,w=0)) is None
    assert monitor.rpy_degrees(dict(x=0,y=0,z=0,w=1))==[0.,0.,0.]


def test_stale_retains_values_not_zero_and_stamp_diagnostics():
    store=monitor.StateStore(specs(),"reported_unverified")
    assert store.snapshot(1,1,.5)["topics"]["/test"]["status"]=="WAITING"
    store.put("/test",joints(),1_000_000_000,1_000_000_000)
    row=store.snapshot(2_000_000_000,2_000_000_000,.5)["topics"]["/test"]
    assert row["status"]=="STALE" and row["values"]["joints"][0]["velocity_rad_s"]==2.
    assert "OLD_HEADER_OR_CLOCK_MISMATCH" in row["warnings"]
    store.put("/test",joints(),2_000_000_000,2_000_000_000)
    assert store.snapshot(2_000_000_000,0,.5)["topics"]["/test"]["warnings"]==["FUTURE_OR_CLOCK_MISMATCH"]
    msg=joints(); msg["header"]["stamp"]["sec"]=0
    store.put("/test",msg,3_000_000_000,3_000_000_000)
    row=store.snapshot(3_000_000_000,3_000_000_000,.5)["topics"]["/test"]
    assert row["duplicates"]==1 and row["backwards"]==1 and "ZERO_STAMP" in row["warnings"]


def test_field_mapping_supports_indices_without_eval():
    assert monitor.field_at(dict(motor=dict(current=[1,2])),"motor.current[1]")==2
    for path in ("__dict__", "data[-1]", "data()", "data;exit", "data[0].__class__"):
        with pytest.raises(ValueError): monitor.field_at({},path)


def test_custom_current_and_missing_field():
    signals=[dict(name="current",field="effort[0]",unit="A",kind="reported_unverified"),
             dict(name="missing",field="missing",unit="A",kind="reported_unverified")]
    store=monitor.StateStore(specs(signals=signals),"reported_unverified")
    store.put("/test",joints([.2,.3]),1,1)
    values=store.snapshot(1,1,.5)["topics"]["/test"]["signals"]
    assert values[0]["value"]==.2 and values[0]["classification_origin"]=="user_config_not_verified_by_monitor"
    assert values[1]["value"] is None and "field_unavailable" in values[1]["error"]


def test_nonfinite_and_unstamped_are_not_fabricated():
    assert monitor.number(math.nan) is None and monitor.number(True) is None
    assert monitor.stamp_ns({}) is None
    assert json.loads(monitor.encode(dict(value=math.nan)))["value"]=={"nonfinite":"nan"}


def test_recording_bound_and_no_overwrite(tmp_path):
    folder=tmp_path/"record"
    recorder=monitor.Recorder(folder,150,{"read_only":True})
    recorder.add(dict(value=math.nan)); recorder.add(dict(value="x"*200)); recorder.close(dict(errors=[]))
    assert (folder/"messages.jsonl").stat().st_size<=150
    assert json.loads((folder/"recording_status.json").read_text())["omitted_messages"]==1
    assert json.loads((folder/"messages.jsonl").read_text())["value"]=={"nonfinite":"nan"}
    with pytest.raises(FileExistsError): monitor.Recorder(folder,150,{})


def test_config_requires_explicit_kind_and_units(tmp_path):
    path=tmp_path/"signals.json"
    entry=dict(name="motor",topic="/motor",type="std_msgs/msg/Float32",field="data",unit="A",kind="estimate")
    path.write_text(json.dumps(dict(signals=[entry])))
    assert monitor.load_signals(path)==[entry]
    for key,value in (("kind","actual"),("field","__class__"),("topic","relative"),("unit","")):
        path.write_text(json.dumps(dict(signals=[dict(entry,**{key:value})])))
        with pytest.raises(ValueError): monitor.load_signals(path)


def test_no_publisher_or_service_calls():
    tree=ast.parse(Path(monitor.__file__).read_text())
    forbidden={"create_publisher","publish","create_client","call_async","create_service","set_parameters","set_parameters_atomically"}
    assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]


@pytest.mark.parametrize("option,value",[("--duration","nan"),("--duration","-1"),("--display-hz","0"),("--max-log-mb","inf")])
def test_invalid_cli_limits(option,value):
    with pytest.raises(SystemExit): monitor.main([option,value])
