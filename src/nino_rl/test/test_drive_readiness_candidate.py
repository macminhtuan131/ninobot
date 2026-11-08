"""Synthetic zero setup; no Gazebo/ROS/hardware. Same 5s cap and physics chunks."""
import json
import threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from nino_rl.drive_readiness_candidate import DriveReadinessBackend


def fake(tmp_path,ready_at=4,quiet_at=1):
    f=json.loads((Path(__file__).parent/'fixtures/coverage_v2_initial_permission_failure.json').read_text())
    drive=f['drive_after']['values'];obj=SimpleNamespace(time=0.,lock=threading.Lock(),
        messages={},episode_dir=tmp_path,requests=[],ticks=0)
    def step(n):
        assert n==50;obj.requests.append(n);obj.time=round(obj.time+.05,9)
    def feedback(now):
        obj.ticks+=1
        obj.messages=dict(truth=dict(values=dict(speed_norm=.0 if obj.ticks>=quiet_at else .02,
            yaw_rate=0.,roll=0.,pitch=0.)),wheel=dict(values=[0.,0.]),
            drive=dict(stamp_s=now,values=dict(drive,have_wheel_state=float(obj.ticks>=ready_at))))
    obj.step_world=step;obj._wait_feedback=feedback
    return obj


def test_early_physical_quiet_does_not_allow_task_before_drive_ack(tmp_path):
    obj=fake(tmp_path,ready_at=4)
    DriveReadinessBackend.settle(obj)
    log=json.loads((tmp_path/'settling.json').read_text())
    assert obj.ticks==8 and obj.requests==[50]*16
    assert log['passed'] and len(log['rows'])==8
    assert all(not r['readiness']['ready'] for r in log['rows'][:3])
    assert log['rows'][2]['continuous_ready_quiet_s']==0.
    assert log['rows'][-1]['continuous_ready_quiet_s']==pytest.approx(.5)


def test_drive_ack_does_not_replace_physical_settling(tmp_path):
    obj=fake(tmp_path,ready_at=1,quiet_at=5)
    DriveReadinessBackend.settle(obj)
    assert obj.ticks==9


def test_missing_ack_fails_without_an_extra_setup_loop_or_retry(tmp_path):
    obj=fake(tmp_path,ready_at=51)
    with pytest.raises(RuntimeError,match='within 5 simulation seconds'):DriveReadinessBackend.settle(obj)
    log=json.loads((tmp_path/'settling.json').read_text())
    assert not log['passed'] and obj.ticks==50 and obj.requests==[50]*100
    assert obj.time==5.
