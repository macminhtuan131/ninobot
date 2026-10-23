"""Offline fault injection and production logger payload parity. No ROS node/sim."""
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import signal

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/nino_rl"))
from nino_rl.observer_health import ObserverHealth,check_sidecar,ObserverShutdown


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def advance(self, ns): self.now += ns


@pytest.mark.parametrize("stage", ["raw_write", "raw_flush", "message_convert"])
def test_injected_stage_stall_is_attributed_not_called_idle(stage):
    c = Clock(); h = ObserverHealth(c)
    with h.callback("sensor", "/imu/data", 1.):
        with h.stage(stage): c.advance(3_000_000_000)
    with h.callback("sensor", "/imu/data", 4.): pass
    assert h.records[0]["stages_ns"][stage] == 3_000_000_000
    assert h.records[0]["duration_ns"] == 3_000_000_000
    assert h.records[1]["since_previous_exit_ns"] == 0


def test_service_gap_distinct_from_instrumented_work():
    c = Clock(); h = ObserverHealth(c)
    with h.callback("sensor", "/imu/data", 1.): c.advance(100)
    c.advance(3_000_000_000)
    with h.callback("sensor", "/imu/data", 4.): c.advance(100)
    assert h.records[1]["since_previous_exit_ns"] == 3_000_000_000
    assert max(r["duration_ns"] for r in h.records) == 100


def test_nested_contact_record_counts_one_callback_and_preserves_exception():
    c = Clock(); h = ObserverHealth(c)
    with pytest.raises(OSError):
        with h.callback("contact", "left"):
            with h.callback("sensor", "left"):
                with h.stage("raw_write"):
                    c.advance(100); raise OSError("injected")
    assert len(h.records) == 1 and h.records[0]["kind"] == "contact"
    assert h.records[0]["failed"] and h.errors == 1
    assert h.current is None


def test_overflow_explicit_and_no_sidecar_io_until_close(tmp_path):
    h = ObserverHealth(Clock(), maximum_records=1)
    for _ in range(3):
        with h.callback("sensor"): pass
    assert not list(tmp_path.iterdir())
    result = h.close(tmp_path)
    assert result["overflow"] == 2 and not result["valid"]
    assert result["callback_count"] == 3 and result["recorded"] == 1


def test_sidecar_validator_rejects_truncation_and_source_drift(tmp_path):
    h = ObserverHealth(Clock())
    with h.callback("sensor"): pass
    summary = h.close(tmp_path)
    (tmp_path/"metadata.json").write_text(json.dumps(dict(observer_health=summary,
        observer_health_source_sha256="expected")))
    assert check_sidecar(tmp_path,"expected")["valid"]
    assert not check_sidecar(tmp_path,"wrong")["valid"]
    (tmp_path/"observer_health.jsonl").write_text("")
    assert not check_sidecar(tmp_path,"expected")["valid"]


def test_repeated_signals_request_shutdown_and_restore_handlers():
    previous={s:signal.getsignal(s) for s in (signal.SIGINT,signal.SIGTERM)}
    with ObserverShutdown() as stop:
        signal.raise_signal(signal.SIGINT)
        signal.raise_signal(signal.SIGINT)
        signal.raise_signal(signal.SIGTERM)
        assert stop.requested and len(stop.received)==3
    assert all(signal.getsignal(s)==h for s,h in previous.items())


def test_production_main_closes_after_repeated_sigint_with_live_context(monkeypatch,tmp_path):
    from nino_rl import governor_logger as module
    active=dict(ok=False,closed=False,destroyed=False)
    class FakeLogger:
        def __init__(self):
            self.metadata={};self.health=ObserverHealth(Clock())
            with self.health.callback("sensor"):pass
        def close(self):
            assert active["ok"]
            signal.raise_signal(signal.SIGINT)  # second interrupt DURING close
            signal.raise_signal(signal.SIGTERM)
            assert self.health.close(tmp_path)["valid"]
            active["closed"]=True
        def destroy_node(self):
            assert active["closed"];active["destroyed"]=True
    def init(**kw):
        assert kw["signal_handler_options"]==module.SignalHandlerOptions.NO
        active["ok"]=True
    monkeypatch.setattr(module,"GovernorLogger",FakeLogger)
    monkeypatch.setattr(module.rclpy,"init",init)
    monkeypatch.setattr(module.rclpy,"ok",lambda:active["ok"])
    monkeypatch.setattr(module.rclpy,"spin_once",lambda *a,**k:signal.raise_signal(signal.SIGINT))
    def shutdown():
        assert active["destroyed"];active["ok"]=False
    monkeypatch.setattr(module.rclpy,"shutdown",shutdown)
    module.main()
    assert active==dict(ok=False,closed=True,destroyed=True)


def test_production_logger_sensor_state_contact_payloads_match_executed_source(monkeypatch):
    from nino_rl import governor_logger as new
    old_path = ROOT / "docs/governor_observer_gap_audit_2026-10-20/executed_governor_logger.py"
    spec = importlib.util.spec_from_file_location("prehealth_logger", old_path)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    def setup(module):
        logger = object.__new__(module.GovernorLogger)
        logger.counts = {}; logger.active = {}; logger.last_contact = {}
        logger.last_time = None; logger.interval = .01
        logger.episode = dict(run_id="fixed", attempt=1)
        logger.stream = io.StringIO(); logger.event_stream = io.StringIO()
        logger.health = ObserverHealth(Clock())
        return logger
    a,b = setup(old),setup(new)
    monkeypatch.setattr(old, "message_to_ordereddict", lambda msg: msg.payload)
    monkeypatch.setattr(new, "message_to_ordereddict", lambda msg: msg.payload)
    monkeypatch.setattr(new.GovernorLogger, "get_clock", lambda self: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=2_000_000_000)))
    # Both classes inherit the same Node.get_clock; replace old explicitly too.
    monkeypatch.setattr(old.GovernorLogger, "get_clock", new.GovernorLogger.get_clock)
    header = SimpleNamespace(stamp=SimpleNamespace(sec=2,nanosec=0))
    sensor = SimpleNamespace(header=header,payload=dict(value=float("nan"),speed=3.))
    contact = SimpleNamespace(header=header,payload=dict(contacts=[]),contacts=[SimpleNamespace(
        collision1=SimpleNamespace(name="cable_bumps::C1"),collision2=SimpleNamespace(name="wheel"))])
    for node in (a,b):
        node.record("/imu/data",sensor)
        node.on_state("/nino/governor/state",SimpleNamespace(data=json.dumps(dict(time_s=2.,governor_scale=.9))))
        node.on_state("/nino/governor/state",SimpleNamespace(data="[1,2]"))
        node.on_contacts("left_wheel",contact)
        node.on_contacts("left_wheel",contact)  # exact original contact throttling
    assert a.stream.getvalue() == b.stream.getvalue()
    assert a.event_stream.getvalue() == b.event_stream.getvalue()
    assert a.counts == b.counts and a.active == b.active and a.last_contact == b.last_contact
    assert b.health.callback_count == 5
