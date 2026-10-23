"""Offline storage faults and epoch isolation; no simulator or ROS nodes."""
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"src/nino_rl"))
from nino_rl.acquisition_frames import FrameWriter,read_frames,validate_episode


def test_payload_timestamps_order_and_equal_source_stamps_preserved(tmp_path):
    w=FrameWriter(tmp_path/"capture")
    for i,topic in enumerate((1,2,1)):
        w.append(topic,bytes([i,0,255]),123,900+i,1000+i,1)
    w.close()
    rows=list(read_frames(w.directory))
    assert [r["payload"] for r in rows]==[bytes([i,0,255]) for i in range(3)]
    assert [r["source_ns"] for r in rows]==[123]*3
    assert [r["sequence"] for r in rows]==[1,2,3]


@pytest.mark.parametrize("fault",["truncate","bitflip","manifest_count","incomplete"])
def test_corruption_never_becomes_valid_prefix(tmp_path,fault):
    w=FrameWriter(tmp_path/"capture");w.append(1,b"payload",100,101,102,1);w.close()
    raw=w.directory/"joint_gt.frames";meta=w.directory/"capture_manifest.json"
    if fault=="truncate":raw.write_bytes(raw.read_bytes()[:-1])
    elif fault=="bitflip":
        a=bytearray(raw.read_bytes());a[-5]^=1;raw.write_bytes(a)
    else:
        m=json.loads(meta.read_text());m["frames"]=2 if fault=="manifest_count" else m["frames"]
        if fault=="incomplete":m["complete"]=False
        meta.write_text(json.dumps(m))
    with pytest.raises(ValueError):list(read_frames(w.directory))


def test_byte_budget_exhaustion_is_explicit_without_eviction(tmp_path):
    w=FrameWriter(tmp_path/"capture",maximum_bytes=1)
    with pytest.raises(OverflowError):w.append(1,b"x",1,1,1,0)
    assert not w.close()["complete"]
    with pytest.raises(ValueError):list(read_frames(w.directory))


def test_disk_failure_is_failed_capture_not_success(tmp_path):
    w=FrameWriter(tmp_path/"capture")
    class Broken:
        def write(self,packet):raise OSError("injected disk failure")
        def __getattr__(self,k):return getattr(real,k)
    real=w.stream;w.stream=Broken()
    with pytest.raises(OSError):w.append(1,b"x",1,1,1,0)
    result=w.close()
    assert not result["complete"] and "injected disk failure" in result["error"]


def scope():
    markers=[dict(run_id="r",attempt=2,event="reset",epoch=2,sequence=5,source_ns=100),
             dict(run_id="r",attempt=2,event="end",epoch=2,sequence=10,source_ns=200)]
    rows=[dict(topic="/joint_states",source_ns=120,epoch=2,sequence=6),
          dict(topic="/ground_truth/odom",source_ns=140,epoch=2,sequence=7)]
    return rows,markers


def test_epoch_identity_and_missing_lifecycle_fail_closed():
    rows,markers=scope()
    assert validate_episode(rows,markers,"r",2,110,190)["valid"]
    with pytest.raises(ValueError):validate_episode(rows,markers,"wrong",2,110,190)
    with pytest.raises(ValueError):validate_episode(rows,markers[:-1],"r",2,110,190)


@pytest.mark.parametrize("fault",["wrong_epoch","before_reset","regression","missing_stream","reversed_markers"])
def test_no_pre_reset_or_reused_clock_data_admitted(fault):
    rows,markers=scope()
    if fault=="wrong_epoch":rows[0]["epoch"]=1
    elif fault=="before_reset":rows[0]["sequence"]=4
    elif fault=="regression":rows.append(dict(rows[0],sequence=8,source_ns=115))
    elif fault=="missing_stream":rows=rows[:1]
    else:markers[1]["sequence"]=1
    with pytest.raises(ValueError):validate_episode(rows,markers,"r",2,110,190)


def test_ros_decode_preserves_fields_timestamps_and_does_not_resample(tmp_path):
    from rclpy.serialization import serialize_message
    from sensor_msgs.msg import JointState
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
    from nino_rl.isolated_acquisition import decode
    w=FrameWriter(tmp_path/"capture")
    reset=String(data=json.dumps(dict(event="reset",run_id="r",attempt=1,time_s=1.)))
    end=String(data=json.dumps(dict(event="end",run_id="r",attempt=1,time_s=2.)))
    a=JointState();a.header.stamp.sec=1;a.header.stamp.nanosec=100
    a.name=["left_wheel_joint"];a.position=[float("nan")];a.velocity=[6.4];a.effort=[.3]
    b=Odometry();b.header.stamp.sec=1;b.header.stamp.nanosec=200;b.pose.pose.position.x=3.
    for number,(topic,msg,ns) in enumerate(((3,reset,1_000_000_000),(1,a,1_000_000_100),
            (2,b,1_000_000_200),(3,end,2_000_000_000))):
        w.append(topic,serialize_message(msg),ns,ns+10,1000+number,1)
    w.close()
    result=decode(w.directory,tmp_path/"decoded","r",1,1_000_000_000,2_000_000_000)
    assert result["valid"]
    rows=[json.loads(x) for x in (tmp_path/"decoded/samples.jsonl").open()]
    assert len(rows)==4
    assert rows[1]["data"]["header"]["stamp"]==dict(sec=1,nanosec=100)
    assert rows[1]["data"]["position"]==[None]
    assert rows[1]["data"]["velocity"]==[6.4] and rows[1]["data"]["effort"]==[.3]
    assert rows[2]["data"]["pose"]["pose"]["position"]["x"]==3.
    from nino_rl.isolated_acquisition import compose_view
    parent=tmp_path/"parent";parent.mkdir()
    (parent/"metadata.json").write_text(json.dumps(dict(complete=True)))
    legacy=[dict(topic="/nino/governor/episode",data=json.loads(reset.data)),
        dict(topic="/joint_states",data=dict(velocity=[999.])),
        dict(topic="/nino/contact_lab/right_wheel",data=dict(contacts=[])),
        dict(topic="/nino/governor/episode",data=json.loads(end.data))]
    original="".join(json.dumps(r)+"\n" for r in legacy)
    (parent/"samples.jsonl").write_text(original)
    view=compose_view(parent,w.directory,tmp_path/"view","r",1,1_000_000_000,2_000_000_000)
    merged=[json.loads(s) for s in (tmp_path/"view/samples.jsonl").open()]
    assert view["complete"] and not view["valid_for_existing_scoring"]
    assert len([r for r in merged if r["topic"]=="/joint_states"])==1
    assert next(r for r in merged if r["topic"]=="/joint_states")["data"]["velocity"]==[6.4]
    assert [r for r in merged if r["topic"] not in ("/joint_states","/ground_truth/odom")]==[r for r in legacy if r["topic"]!="/joint_states"]
    assert (parent/"samples.jsonl").read_text()==original
    assert not (tmp_path/"view/metadata.json").exists()  # cannot masquerade as legacy logger
    with pytest.raises(ValueError):compose_view(parent,w.directory,tmp_path/"wrong_run","other",1,1_000_000_000,2_000_000_000)
    (parent/"metadata.json").write_text(json.dumps(dict(complete=False)))
    with pytest.raises(ValueError):compose_view(parent,w.directory,tmp_path/"unclosed","r",1,1_000_000_000,2_000_000_000)
