"""Bounded, observer-only timing probes; no ROS, motor or scoring dependencies."""
from collections import Counter
from contextlib import contextmanager
from functools import wraps
import json
import signal
from time import monotonic_ns


class ObserverShutdown:
    """Signals request orderly logger shutdown; repeated signals cannot truncate close."""
    def __init__(self):
        self.requested = False
        self.received = []

    def __enter__(self):
        self.previous = {s:signal.getsignal(s) for s in (signal.SIGINT,signal.SIGTERM)}
        def request(signum, frame):
            self.received.append(signum)
            self.requested = True
        for s in self.previous:
            signal.signal(s, request)
        return self

    def __exit__(self, *error):
        for s, handler in self.previous.items():
            signal.signal(s, handler)


class ObserverHealth:
    def __init__(self, clock=monotonic_ns, maximum_records=100000):
        self.clock = clock
        self.maximum_records = maximum_records
        self.records = []
        self.current = None
        self.callback_count = 0
        self.overflow = 0
        self.errors = 0
        self.last_exit = None

    @contextmanager
    def callback(self, kind, topic=None, source_stamp_s=None):
        # Contact callback can call record(); count one outer ROS callback.
        if self.current is not None:
            yield
            return
        begin = self.clock()
        self.callback_count += 1
        row = dict(sequence=self.callback_count, kind=kind, topic=topic,
                   source_stamp_s=source_stamp_s, enter_monotonic_ns=begin,
                   since_previous_exit_ns=None if self.last_exit is None else begin-self.last_exit,
                   stages_ns={}, failed=False)
        self.current = row
        try:
            yield
        except BaseException:
            row["failed"] = True
            self.errors += 1
            raise
        finally:
            end = self.clock()
            row.update(exit_monotonic_ns=end, duration_ns=end-begin)
            self.last_exit = end
            self.current = None
            if len(self.records) < self.maximum_records:
                self.records.append(row)
            else:
                self.overflow += 1  # visible integrity failure, never silent eviction

    @contextmanager
    def stage(self, name):
        if self.current is None:
            yield
            return
        row = self.current
        begin = self.clock()
        try:
            yield
        finally:
            row["stages_ns"][name] = row["stages_ns"].get(name, 0) + self.clock()-begin

    def annotate(self, **fields):
        if self.current is not None:
            self.current.update(fields)

    def close(self, directory):
        """Write the sidecar only after raw collection has stopped."""
        with (directory / "observer_health.jsonl").open("x") as stream:
            for row in self.records:
                stream.write(json.dumps(row, allow_nan=False)+"\n")
        summary = dict(schema="observer_health_v1", complete=True,
            callback_count=self.callback_count, recorded=len(self.records),
            overflow=self.overflow, errors=self.errors, maximum_records=self.maximum_records,
            callback_kinds=dict(Counter(r["kind"] for r in self.records)),
            valid=self.overflow == 0 and self.errors == 0,
            sidecar_written_after_collection=True,
            qualification="Monotonic durations diagnose observer service; inter-callback gaps alone cannot distinguish scheduling from absent delivery. Not a control or coverage metric.")
        (directory / "observer_health_summary.json").write_text(json.dumps(summary, indent=2)+"\n")
        return summary


def observed_callback(kind):
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            topic = args[0] if kind in ("sensor", "state") else (
                "/nino/contact_lab/"+args[0] if kind == "contact" else kind)
            msg = args[1] if kind in ("sensor", "state", "contact") else None
            header = getattr(msg, "header", None)
            stamp = header.stamp.sec+header.stamp.nanosec*1e-9 if header else None
            with self.health.callback(kind, topic, stamp):
                return method(self, *args, **kwargs)
        return wrapped
    return decorate


def check_sidecar(directory, expected_source_sha256):
    """Hard integrity checks; long durations are evidence, not a new score gate."""
    try:
        metadata = json.loads((directory / "metadata.json").read_text())
        summary = json.loads((directory / "observer_health_summary.json").read_text())
        previous = 0
        count = 0
        longest_callback = None
        longest_idle = None
        with (directory / "observer_health.jsonl").open() as stream:
            for count, line in enumerate(stream, 1):
                row = json.loads(line)
                assert row["sequence"] == count
                assert previous <= row["enter_monotonic_ns"] <= row["exit_monotonic_ns"]
                assert row["duration_ns"] == row["exit_monotonic_ns"]-row["enter_monotonic_ns"]
                assert not row["failed"]
                assert all(value >= 0 for value in row["stages_ns"].values())
                previous = row["exit_monotonic_ns"]
                if longest_callback is None or row["duration_ns"] > longest_callback["duration_ns"]:
                    longest_callback = row
                if longest_idle is None or (row["since_previous_exit_ns"] or 0) > (longest_idle["since_previous_exit_ns"] or 0):
                    longest_idle = row
        assert summary["complete"] and summary["valid"] and summary["errors"] == summary["overflow"] == 0
        assert summary["callback_count"] == summary["recorded"] == count and count > 0
        assert metadata["observer_health"] == summary
        assert metadata["observer_health_source_sha256"] == expected_source_sha256
        assert not metadata.get("observer_runtime_error")
        return dict(valid=True, summary=summary, longest_callback=longest_callback,
                    longest_inter_callback=longest_idle)
    except (OSError, ValueError, KeyError, AssertionError, TypeError) as error:
        return dict(valid=False, error=f"{type(error).__name__}: {error}")
