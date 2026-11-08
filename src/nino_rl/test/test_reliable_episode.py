"""Lifecycle orchestration only: no ROS processes, Gazebo, or learner budget."""
from types import SimpleNamespace
import json
import pytest
from nino_rl import reliable_episode as life
from nino_rl import residual_reliable_td3 as job


def lifecycle_fixture(tmp_path, monkeypatch, fail=None):
    events, backends, observers = [], [], []
    class Observer:
        def __init__(self, directory, p):
            self.directory = directory
            self.closed = False
            observers.append(self)
        def start(self, env):
            events.append(('ready', len(backends)))
            if fail == 'ready': raise RuntimeError('ready failed')
            return dict(motor_command_publishers=0)
        def close(self):
            self.closed = True
            events.append(('observer_close', len(backends)))
            if fail == 'observer_close': raise RuntimeError('observer close failed')
    class Backend:
        def __init__(self, c, directory, world, g, task, condition, observer):
            assert all(o.closed for o in observers[:-1])
            assert all(b.closed for b in backends)
            self.config, self.protocol, self.condition = c, task, condition
            self.primary_count, self.primary_last, self.boundaries = 0, None, []
            self.partition, self.environment = 'partition_' + str(len(backends)), {}
            self.node, self.estimator, self.closed = object(), SimpleNamespace(epoch='local0'), False
            backends.append(self);events.append(('created', len(backends)))
        def reset(self, seed=None):
            if fail == 'reset': raise RuntimeError('reset failed')
            self.primary_count = 2;self.primary_last = dict(source_stamp_ns=100)
            return {}, dict(estimator_initialization='declared')
        def advance_reference(self, *args):
            if fail == 'control': raise RuntimeError('control failed')
            self.boundaries.append(dict(epoch=self.partition))
            return ('step',)
        def close(self):
            self.closed = True;events.append(('backend_close', len(backends)))
            if fail == 'backend_close': raise RuntimeError('backend close failed')
    monkeypatch.setattr(life, 'graph', lambda n: [dict(qos=dict(reliability=1))])
    c,g,t,condition=job.configuration(6.)
    lifecycle=life.EpisodeLifecycle(c,tmp_path/'epochs','world',g,t,condition,job.protocol(),Backend,Observer)
    return lifecycle, events, backends, observers


def test_eight_fresh_epochs_close_before_next_observer_and_no_cached_support(tmp_path, monkeypatch):
    lifecycle, events, backends, observers=lifecycle_fixture(tmp_path,monkeypatch)
    epochs=[]
    for i in range(8):
        job.configure_episode(lifecycle,i)
        _, info=lifecycle.reset(seed=11 if i==0 else None)
        epochs.append(info['learner_episode_epoch'])
        assert lifecycle.current.primary_count == 2
        assert lifecycle.current.boundaries == []
        assert lifecycle.tick == 0
        lifecycle.advance_reference(0,0,.1)
        assert lifecycle.tick == 1 and lifecycle.current.control_tick == 0
    lifecycle.close();lifecycle.close()
    assert all(b.closed for b in backends) and all(o.closed for o in observers)
    assert len({(e['namespace'],e['partition']) for e in epochs}) == 8
    assert all(not e['old_support_reused'] for e in epochs)
    assert [b.protocol['command_until_s'] for b in backends] == [6.,8.]*4
    phases=[e['phase'] for e in lifecycle.events]
    assert phases == ['created','observer_ready','reset_complete','closed']*8
    assert len(list((tmp_path/'epochs').glob('episode_*/epoch.json'))) == 8
    with pytest.raises(RuntimeError,match='cannot reset'):lifecycle.reset()


@pytest.mark.parametrize('failure',['ready','reset','control','backend_close','observer_close'])
def test_any_failure_or_closure_failure_closes_other_owner_and_prevents_retry(tmp_path,monkeypatch,failure):
    lifecycle,events,backends,observers=lifecycle_fixture(tmp_path,monkeypatch,failure)
    with pytest.raises(RuntimeError,match='failed'):
        lifecycle.reset()
        if failure=='control':lifecycle.advance_reference(0,0,.1)
        else:lifecycle.reset()
    assert lifecycle.failed
    lifecycle.close()
    assert all(b.closed for b in backends) and all(o.closed for o in observers)
    assert len(backends)==1
    with pytest.raises(RuntimeError,match='cannot reset'):lifecycle.reset()


def test_keyboard_interrupt_during_reset_closes_both_and_no_new_epoch(tmp_path,monkeypatch):
    lifecycle,events,backends,observers=lifecycle_fixture(tmp_path,monkeypatch)
    original=lifecycle.backend_factory
    def factory(*args):
        b=original(*args)
        def interrupt(seed=None):raise KeyboardInterrupt()
        b.reset=interrupt
        return b
    lifecycle.backend_factory=factory
    with pytest.raises(KeyboardInterrupt):lifecycle.reset()
    assert lifecycle.failed and backends[0].closed and observers[0].closed
    with pytest.raises(RuntimeError):lifecycle.reset()


def test_launch_limit_closes_last_epoch_without_ninth_creation(tmp_path,monkeypatch):
    lifecycle,events,backends,observers=lifecycle_fixture(tmp_path,monkeypatch)
    for _ in range(8):lifecycle.reset()
    with pytest.raises(ValueError,match='budget exhausted'):lifecycle.reset()
    assert len(backends)==8 and all(b.closed for b in backends)


def test_preexisting_support_in_new_backend_is_rejected(tmp_path,monkeypatch):
    lifecycle,events,backends,observers=lifecycle_fixture(tmp_path,monkeypatch)
    original=lifecycle.backend_factory
    def contaminated(*args):
        b=original(*args);b.primary_last=dict(source_stamp_ns=100)
        return b
    lifecycle.backend_factory=contaminated
    with pytest.raises(ValueError,match='previous-epoch support'):lifecycle.reset()
    assert backends[0].closed and observers[0].closed
    assert not any(e[0]=='ready' for e in events)
