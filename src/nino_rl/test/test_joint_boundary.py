"""Diagnostic contracts, causal endpoint gates and a ROS-only process fixture."""
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import pytest
from nino_rl import joint_boundary_observer as observer
from nino_rl import residual_joint_boundary as job


def test_frozen_budget_zero_only_and_source_does_not_advance():
    p=job.protocol();c,g,t,condition=job.configuration()
    assert p['launches_maximum']==2 and p['maximum_complete_control_ticks']==200
    assert p['training_transitions']==p['actor_inference_calls']==p['optimizer_updates']==p['hardware_actions']==0
    assert not p['training_released'] and not p['upstream_publish_counter_available']
    assert c['backend']['command_until_s']==c['task']['command_until_s']==t['command_until_s']==0.
    assert c['backend']['horizon_s']==t['horizon_s']==10.
    assert c['reference_limits']['wheel_acceleration_m_s2']==.1


@pytest.mark.parametrize('stamp,expected',[(100,True),(60,True),(59,False),(101,False),(None,False)])
def test_endpoint_includes_open_tail_and_rejects_future_even_one_ns(stamp,expected):
    record=None if stamp is None else dict(source_stamp_ns=stamp)
    assert observer.endpoint_supported(record,100,40)==expected


def test_snapshot_wait_then_timeout_never_fills_missing_with_zero_or_interpolation():
    request=dict(request_id=3,target_stamp_ns=100,maximum_age_ns=40,request_monotonic_ns=10,deadline_monotonic_ns=20)
    assert observer.snapshot(request,None,0,now_ns=19) is None
    response=observer.snapshot(request,None,0,now_ns=20)
    assert response['timed_out'] and response['last'] is None and response['age_ns'] is None
    valid=observer.snapshot(request,dict(source_stamp_ns=60),1,now_ns=11)
    assert valid['supported'] and not valid['timed_out'] and valid['response_monotonic_ns']==11


@pytest.mark.parametrize('a,b,error,expected',[
 (True,True,None,'both_joint_paths_supported'),
 (False,True,'joint timeout','primary_path_missing_independent_supported'),
 (True,False,None,'independent_path_missing_primary_supported'),
 (False,False,'timeout','both_joint_paths_missing_source_or_shared_delivery_unknown'),
 (True,True,'drive timeout','other_channel_or_wait_failure')])
def test_classification_never_assigns_upstream_cause_from_two_ros_readers(a,b,error,expected):
    assert job.classify(a,b,error)==expected


def test_first_failure_closes_second_launch(tmp_path,monkeypatch):
    monkeypatch.setattr(job,'parent',lambda:tmp_path)
    monkeypatch.setattr(job.parent_task.contract.guided,'dependency_record',lambda p:{})
    monkeypatch.setattr(job,'prepare_worlds',lambda p:dict(clear_box='world'))
    calls=[]
    def rollout(*args):
        calls.append(args[2]);return dict(collection_complete=False,complete_zero_ticks=0,error='source support timeout')
    monkeypatch.setattr(job,'rollout',rollout)
    result=job.execute(tmp_path)
    assert calls==[0] and result['complete_zero_control_ticks']==0
    assert result['outcome']=='stopped_on_failure_review_paths' and not result['training_released']
    assert result['remaining_slots_closed'] and not result['partial_td3_batch_reopened']


def test_consumed_corrupt_budget_not_reopened(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    (tmp_path/'state.json').write_text('broken')
    with pytest.raises(ValueError,match='already consumed'):job.run(tmp_path)


def test_independent_real_ros_process_records_hash_and_checks_endpoint(tmp_path):
    # Synthetic ROS messages only, domain139. No Gazebo, motor, actor or physics.
    import rclpy
    from rclpy.context import Context
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from sensor_msgs.msg import JointState
    context=Context();rclpy.init(context=context,domain_id=139)
    node=Node('nino_joint_boundary_software_fixture',context=context)
    executor=SingleThreadedExecutor(context=context);executor.add_node(node)
    pub=node.create_publisher(JointState,'/joint_states',100)
    p=job.protocol();p['feedback_deadline_s']=.12
    child=job.IndependentProcess(tmp_path/'observer',p,domain=139)
    env=dict(os.environ,ROS_DOMAIN_ID='139',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
    for key in ('FASTRTPS_DEFAULT_PROFILES_FILE','FASTDDS_DEFAULT_PROFILES_FILE'):env.pop(key,None)
    messages={}
    try:
        child.start(env)
        end=time.monotonic()+5
        while pub.get_subscription_count()!=1 and time.monotonic()<end:
            executor.spin_once(timeout_sec=.02)
        assert pub.get_subscription_count()==1
        for i in range(20):
            msg=JointState();msg.header.stamp.sec=10;msg.header.stamp.nanosec=i*2_000_000
            msg.name=['left_wheel_joint','right_wheel_joint'];msg.velocity=[float(i),-float(i)]
            messages[10*10**9+i*2_000_000]=msg;pub.publish(msg)
            executor.spin_once(timeout_sec=.01)
        response=child.response(child.request(10.038))
        assert response['supported'] and response['received_count']>0
        last=response['last'];expected=observer.message_record(messages[last['source_stamp_ns']],1)
        assert last['payload_sha256']==expected['payload_sha256']
        assert last['payload_hash_schema']=='joint_fields_json_v1'
        timeout=child.response(child.request(10.15))
        assert not timeout['supported'] and timeout['timed_out'] and timeout['age_ns']>=112_000_000
    finally:
        child.close();executor.shutdown(timeout_sec=2);node.destroy_node()
        if context.ok():context.shutdown()
    closed=observer.read(tmp_path/'observer/closed.json')
    assert closed['count']>0 and not closed['motor_command_publishers'] and closed['error'] is None
    records=[json.loads(l) for l in (tmp_path/'observer/joint_records.jsonl').open()]
    assert [r['sequence'] for r in records]==list(range(1,len(records)+1))


@pytest.mark.parametrize('primary_supported,independent_supported',[(False,True),(True,False)])
def test_primary_and_independent_failure_cannot_patch_each_other(tmp_path,monkeypatch,primary_supported,independent_supported):
    import io,threading
    backend=object.__new__(job.BoundaryBackend)
    backend.lock=threading.RLock();backend.audit_dir=tmp_path
    backend.primary_count=5;backend.primary_last=dict(source_stamp_ns=100_000_000 if primary_supported else 50_000_000)
    backend.messages=dict(wheel=dict(stamp_s=.1 if primary_supported else .05))
    backend.phase='zero_control';backend.control_tick=0;backend.wait_count=0;backend.boundaries=[];backend.primary_records=io.StringIO()
    backend.independent=SimpleNamespace(request=lambda t:dict(target_stamp_ns=100_000_000),
        response=lambda r:dict(supported=independent_supported))
    def wait(self,target):
        if not primary_supported:raise RuntimeError('primary timeout')
        return dict(wheel=0.,imu=0.,drive=0.,truth=0.)
    monkeypatch.setattr(job.baseline.GuidedBackend,'_wait_feedback',wait)
    with pytest.raises(RuntimeError):backend._wait_feedback(.1)
    row=json.loads((tmp_path/'boundary_checks.jsonl').read_text())
    expected='independent_path_missing_primary_supported' if primary_supported else 'primary_path_missing_independent_supported'
    assert row['classification']==expected
    assert backend.messages['wheel']['stamp_s']==(.1 if primary_supported else .05)
