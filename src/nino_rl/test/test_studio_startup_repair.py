import json
import threading
from types import SimpleNamespace
import pytest
from nino_rl import studio_startup_repair as repair


def backend(tmp_path,monkeypatch):
    # Only fixture the startup state machine, never start ROS or Gazebo here.
    b=object.__new__(repair.StudioStartupBackend)
    b.lock=threading.RLock();b.messages={k:{} for k in ('imu','wheel','truth','drive')}
    b.counts={k:5 for k in b.messages};b.clock=0.;b.iterations=0;b.request=(0.,0.)
    b.publisher=SimpleNamespace(get_subscription_count=lambda:1)
    b.episode_dir=tmp_path;b._startup_active=True;b._startup_ros_since=None
    b._startup_rearmed=False;b._startup_rearmed_at=None;b._startup_last_saved=0.;b._startup_events=[]
    b.error=None;b.launch=None;b.independent=SimpleNamespace(check=lambda:None)
    now=[100.];monkeypatch.setattr(repair.time,'monotonic',lambda:now[0])
    calls=[];b._rearm_startup_transport=lambda:calls.append(now[0])
    return b,now,calls


def test_silent_stats_rearm_once_then_require_real_clock(tmp_path,monkeypatch):
    b,now,calls=backend(tmp_path,monkeypatch)
    b._check();now[0]+=8.1;b._check();assert len(calls)==1
    now[0]+=5;b._check();assert len(calls)==1
    b.clock=.1;b.iterations=100;now[0]+=1.1;b._check()
    assert json.loads((tmp_path/'startup_diagnostics.json').read_text())['phase']=='clock_ready'


def test_no_in_task_repair_and_no_extra_retries(tmp_path,monkeypatch):
    b,now,calls=backend(tmp_path,monkeypatch)
    b._startup_active=False;b._check();now[0]+=100;b._check();assert calls==[]
    b._startup_active=True;b._check();now[0]+=9;b._check();now[0]+=15
    with pytest.raises(TimeoutError):b._check()
    assert len(calls)==1


def test_nonzero_command_cannot_use_startup_recovery(tmp_path,monkeypatch):
    b,now,calls=backend(tmp_path,monkeypatch);b.request=(.1,0.)
    with pytest.raises(RuntimeError,match='Nonzero'):b._check()
    assert calls==[]


def test_clock_ready_or_missing_ros_does_not_rearm(tmp_path,monkeypatch):
    b,now,calls=backend(tmp_path,monkeypatch);b.clock=.1;b.iterations=100
    b._check();now[0]+=20;b._check();assert calls==[]
    b.clock=0.;b.messages.pop('drive');b._check();now[0]+=20;b._check();assert calls==[]


def test_diagnostics_before_publisher_creation_do_not_mask_startup_error(tmp_path,monkeypatch):
    b,now,calls=backend(tmp_path,monkeypatch);del b.publisher
    b._save_startup('failed',error='original startup failure')
    assert json.loads((tmp_path/'startup_diagnostics.json').read_text())['command_subscribers'] is None


def test_failure_to_write_diagnostics_preserves_original_exception(tmp_path,monkeypatch):
    b,now,calls=backend(tmp_path,monkeypatch)
    def fail_reset(*a,**kw):raise RuntimeError('original startup error')
    def fail_log(*a,**kw):raise OSError('disk error')
    monkeypatch.setattr(repair.DriveReadinessBackend,'reset',fail_reset);b._save_startup=fail_log
    with pytest.raises(RuntimeError,match='original startup error') as caught:b.reset()
    assert 'disk error' in caught.value.__notes__[0]
