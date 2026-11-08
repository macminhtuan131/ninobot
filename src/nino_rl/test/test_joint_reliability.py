"""Counter/coverage, QoS-only mutation and finite-stage rules; no live stream."""
from copy import deepcopy
from pathlib import Path
import pytest
from nino_rl import residual_joint_reliability as job
from nino_rl.joint_reliability_candidate import replace_joint_subscription, qos_record


def metric_fixture():
    f=job.protocol()['fixture']
    source=[dict(source_index=-1,source_stamp_ns=9_000_000_000,payload_sha256='handshake',before_publish_ns=800_000_000,after_publish_ns=800_000_001)]
    source += [dict(source_index=i,source_stamp_ns=10_000_000_000+i*2_000_000,payload_sha256=str(i),before_publish_ns=1_000_000_000+i*2_000_000,after_publish_ns=1_000_000_000+i*2_000_000+1000) for i in range(1000)]
    rr=[dict(source_stamp_ns=r['source_stamp_ns'],payload_sha256=r['payload_sha256']) for r in source]
    readers={name:deepcopy(rr) for name in ('best_effort','reliable')}
    pauses={name:dict(planned_start_ns=2_000_000_000,actual_start_ns=2_000_000_000,actual_end_ns=2_100_000_000) for name in readers}
    replies={name:dict(supported=True) for name in readers}
    return f,source,readers,pauses,replies


def test_finite_budgets_and_unchanged_parent_identity():
    p=job.protocol()
    assert p['fixture']['messages']+p['fixture']['handshake_messages']==1001
    assert p['qualification']['source_stop_order_s']==[6.,8.] and p['qualification']['maximum_transitions']==280
    assert p['maximum_support_age_ns']==40_000_000 and not p['training_released']
    assert job.diagnostic.fingerprint()==p['parent_fingerprint']


def test_both_complete_means_compatibility_not_reliability_benefit():
    f,s,r,p,a=metric_fixture();v=job.fixture_metrics(s,r,p,a,f)
    assert v['candidate_compatible'] and v['fixture_valid'] and not v['reliability_benefit_in_this_fixture']
    assert not v['general_reliability_benefit_verified']
    assert all(q['labeled_unique']==1000 and q['messages_published_during_pause']==50 for q in v['readers'].values())


@pytest.mark.parametrize('kind',['missing_reliable','payload_mismatch','duplicate','publish_block','pause_missing','pause_late','source_order'])
def test_incomplete_corrupt_or_invalid_fault_does_not_release_physics(kind):
    f,s,r,p,a=metric_fixture()
    if kind=='missing_reliable':r['reliable'].pop(550)
    if kind=='payload_mismatch':r['reliable'][500]['payload_sha256']='bad'
    if kind=='duplicate':r['reliable'].insert(500,dict(r['reliable'][500]))
    if kind=='publish_block':s[300]['after_publish_ns']+=101_000_000
    if kind=='pause_missing':p.pop('reliable')
    if kind=='pause_late':p['reliable']['actual_start_ns']+=50_000_000;p['reliable']['actual_end_ns']+=50_000_000
    if kind=='source_order':s[500]['before_publish_ns']=0
    v=job.fixture_metrics(s,r,p,a,f)
    assert not v['candidate_compatible']


def test_best_effort_missing_kept_but_claim_limited_to_this_fixture():
    f,s,r,p,a=metric_fixture();r['best_effort'].pop(500)
    v=job.fixture_metrics(s,r,p,a,f)
    assert v['candidate_compatible'] and v['reliability_benefit_in_this_fixture']
    assert not v['general_reliability_benefit_verified'] and len(v['readers']['best_effort']['missing_source_stamps_ns'])==1


def test_real_ros_subscription_mutation_preserves_nonjoint_entity_and_depth():
    import rclpy
    from rclpy.context import Context
    from rclpy.node import Node
    from rclpy.qos import QoSProfile,ReliabilityPolicy
    from sensor_msgs.msg import JointState,Imu
    from rclpy.executors import SingleThreadedExecutor
    import threading
    context=Context();rclpy.init(context=context,domain_id=140)
    node=Node('nino_candidate_qos_unit_fixture',context=context)
    q=QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT)
    node.create_subscription(JointState,'/joint_states',lambda m:None,q)
    other=node.create_subscription(Imu,'/imu/data',lambda m:None,q)
    executor=SingleThreadedExecutor(context=context);executor.add_node(node)
    thread=threading.Thread(target=executor.spin,daemon=True);thread.start()
    try:
        result=replace_joint_subscription(node,lambda m:None)
        assert result['before']['reliability']==2 and result['after']==dict(result['before'],reliability=1)
        assert result['nonjoint_subscriptions_unchanged']
        assert any(s is other for s in node.subscriptions) and qos_record(other.qos_profile)['reliability']==2
        with pytest.raises(ValueError,match='Unexpected frozen'):replace_joint_subscription(node,lambda m:None)
    finally:
        executor.shutdown(timeout_sec=2);thread.join(timeout=2)
        assert not thread.is_alive()
        node.destroy_node()
        if context.ok():context.shutdown()


def test_consumed_stage_never_reopens(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    (tmp_path/'state.json').write_text(json.dumps(dict(latest={},runs=[dict(action=job.ACTIONS[0],status='failed')])))
    with pytest.raises(ValueError,match='already consumed'):job.run(tmp_path,job.ACTIONS[0])


def test_no_go_fixture_prevents_any_world_preparation(tmp_path,monkeypatch):
    artifact=tmp_path/'fixture';artifact.mkdir();(artifact/'fixture_result.json').write_text('{"candidate_compatible":false}')
    monkeypatch.setattr(job,'validated_latest',lambda *a,**k:artifact)
    monkeypatch.setattr(job,'prepare_worlds',lambda p:pytest.fail('Physics preparation after no-go fixture'))
    with pytest.raises(ValueError,match='no qualification'):job.qualification(tmp_path,tmp_path)
