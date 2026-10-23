#!/usr/bin/env python3
"""Read saved observer/evaluator records; never launch, repair, or rescore episodes."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def source_stamp(row):
    d = row["data"]
    if "header" in d:
        s = d["header"]["stamp"]
        return s["sec"] + s["nanosec"] * 1e-9
    if row["topic"] == "/nino_drive/diagnostics":
        names = d["layout"]["dim"][0]["label"].split(",")
        return d["data"][names.index("sim_time_s")]
    return d.get("time_s", d.get("sim_time_s"))


def largest_gap(times):
    ts = sorted(set(times))
    if len(ts) < 2:
        return None
    a, b = max(zip(ts, ts[1:]), key=lambda p: p[1]-p[0])
    return dict(start_s=a, end_s=b, gap_s=b-a)


def analyze(run, output):
    ledger_path = run / "ledger.json"
    ledger = json.loads(ledger_path.read_text())
    review = ROOT / "docs/governor_cadence_experiment_2026-10-20/live_analysis/execution_review_inputs_sha256.json"
    protected = json.loads(review.read_text())
    for name, expected in protected.items():
        if sha(Path(name)) != expected:
            raise ValueError("Saved input drift: " + name)
    output.mkdir(parents=True, exist_ok=False)
    save(output / "scope.json", dict(mode="offline_observer_gap_audit", focus_attempt=9,
        comparison="Other eight saved attempts only for acquisition-gap context",
        simulation_launches=0, controller_changed=False, sampling_changed=False,
        coverage_requirement_changed=False, metric_recalculation=False,
        missing_values_filled=False, prior_input_hashes_verified=len(protected)))
    inputs = {ledger_path, review, Path(__file__).resolve(), run / "summary.json"}
    summaries = []
    target = None
    for slot in ledger["slots"]:
        if not slot["adapter_requested"]:
            continue
        result = slot["result"]
        logger = Path(result["logger"])
        evaluation = Path(result["evaluation"])
        controls_path = next(evaluation.glob("episode-*/control_trace.csv"))
        controls = list(csv.DictReader(controls_path.open()))
        start = float(controls[0]["governor_input_time_s"])
        end = float(controls[-1]["sim_time_s"])
        raw_path = logger / "samples.jsonl"
        meta_path = logger / "metadata.json"
        metadata = json.loads(meta_path.read_text())
        inputs.update([raw_path, meta_path, controls_path, run / f"attempt_{slot['attempt']:02d}/result.json"])
        by_topic = defaultdict(list)
        raw = []
        counts = Counter()
        offset = 0
        with raw_path.open("rb") as stream:
            for line_number, line in enumerate(stream, 1):
                row = json.loads(line)  # malformed/missing rows are never skipped
                stamp = source_stamp(row)
                point = dict(line=line_number, byte_offset=offset, bytes=len(line), topic=row["topic"],
                             source_stamp_s=stamp, receipt_sim_s=row.get("receipt_time_s"))
                offset += len(line)
                counts[row["topic"]] += 1
                if stamp is not None and start <= stamp <= end:
                    by_topic[row["topic"]].append(point)
                if slot["attempt"] == 9:
                    raw.append(point)
        delta = {k: dict(file_count=counts[k], metadata_count=metadata["message_counts"].get(k, 0))
                 for k in counts.keys() | metadata["message_counts"].keys()
                 if counts[k] != metadata["message_counts"].get(k, 0)}
        summary = dict(attempt=slot["attempt"], arm=slot["arm"], route_start_s=start, route_end_s=end,
            logger_complete=metadata["complete"], raw_bytes=offset, malformed_lines=0,
            metadata_count_differences=delta, channels={})
        for topic, points in by_topic.items():
            if topic.endswith("/episode"):
                continue  # two sparse lifecycle events are not a high-rate stream
            summary["channels"][topic] = dict(rows=len(points),
                largest_header_gap=largest_gap([p["source_stamp_s"] for p in points]),
                largest_receipt_sim_gap=largest_gap([p["receipt_sim_s"] for p in points
                                                   if p["receipt_sim_s"] is not None]))
        summaries.append(summary)
        if slot["attempt"] != 9:
            continue
        target = result
        receipt_points = [p for p in raw if p["receipt_sim_s"] is not None
                          and start <= p["receipt_sim_s"] <= end]
        a, b = max(zip(receipt_points, receipt_points[1:]),
                   key=lambda p: p[1]["receipt_sim_s"]-p[0]["receipt_sim_s"])
        lo, hi = a["receipt_sim_s"], b["receipt_sim_s"]
        resume = [p for p in raw if p["receipt_sim_s"] is not None
                  and abs(p["receipt_sim_s"]-hi) < 1e-9]
        backlog = {topic: [p["source_stamp_s"] for p in resume if p["topic"] == topic]
                   for topic in ("/imu/data", "/ground_truth/odom", "/joint_states")}
        state_backlog = [p["source_stamp_s"] for p in raw if p["topic"] == "/nino/governor/state"
                         and hi-.200001 <= p["source_stamp_s"] < hi]
        save(output / "gap_boundary.json", dict(last_record=a, first_record=b,
            gap_in_receipt_sim_s=hi-lo, first_receipt_batch=resume,
            sensor_backlog_stamps=backlog, state_backlog_stamps=state_backlog,
            raw_line_excerpt=raw[a["line"]-5:b["line"]+30],
            qualification="receipt_sim_s uses ROS simulation clock; no wall-time stall duration is identifiable"))
        evidence = {}
        for filename, column in (("control_trace.csv", "sim_time_s"),
                                 ("governor_update_trace.csv", "governor_input_time_s"),
                                 ("drive_trace.csv", "sim_time_s")):
            path = next(evaluation.glob("episode-*/"+filename))
            inputs.add(path)
            rows = list(csv.DictReader(path.open()))
            chosen = [r for r in rows if lo < float(r[column]) < hi]
            ages = {}
            keys = (("imu_stamp_s", "joint_stamp_s", "governor_feedback_stamp_s")
                    if filename == "governor_update_trace.csv" else ())
            for key in keys:
                values = [float(r[column])-float(r[key]) for r in chosen]
                ages[key] = [min(values), max(values)]
            if filename == "control_trace.csv":
                ages.update({key: [min(float(r[key]) for r in chosen), max(float(r[key]) for r in chosen)]
                             for key in ("slip_joint_age_s", "slip_ground_truth_age_s")})
            evidence[filename] = dict(rows_in_observer_gap=len(chosen),
                first_stamp_s=float(chosen[0][column]), last_stamp_s=float(chosen[-1][column]),
                largest_gap=largest_gap([float(r[column]) for r in chosen]), sensor_age_ranges_s=ages)
            with (output / filename.replace(".csv", "_gap_evidence.csv")).open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(chosen)  # verbatim field values; no new grid or interpolation
        save(output / "evaluator_continuity.json", evidence)
        assert all(len(backlog[k]) == 5 for k in backlog)
        assert len(state_backlog) == 10
        assert not delta
        assert evidence["governor_update_trace.csv"]["rows_in_observer_gap"] == 165
        assert evidence["control_trace.csv"]["rows_in_observer_gap"] == 33
        assert evidence["drive_trace.csv"]["rows_in_observer_gap"] == 166

    if target is None:
        raise ValueError("Attempt9 was not collected")
    logger_source = ROOT / "src/nino_rl/nino_rl/governor_logger.py"
    inputs.add(logger_source)
    logged_hash = json.loads((Path(target["logger"]) / "metadata.json").read_text())["logger_sha256"]
    if sha(logger_source) != logged_hash:
        raise ValueError("Current logger source differs from executed source")
    (output / "executed_governor_logger.py").write_bytes(logger_source.read_bytes())
    save(output / "report.json", dict(attempts=summaries, attempt9_native_outcome_preserved=dict(
        physical_success=target["physical_success"], stop_pass=target["stop_pass"],
        native_replay_matches=target["integrity"]["native_match"],
        whole_GT=target["integrity"]["whole_GT"]),
        logger_source_matches_executed_hash=True,
        decision="Observer-side acquisition interruption with shallow retained queues; no evidence of a global sensor/control outage. Exact blocking component unidentifiable from saved wall-time-free records.",
        next_correction_proposal="Observer-only monotonic callback-entry/exit and serialization/write/flush duration telemetry with sequence/overflow counters. No queue/QoS or control change justified yet.",
        simulation_launches=0, metrics_changed=False, H2_decision="not_assessed"))
    # Require every protected input to match again after the complete read-only audit.
    for name, expected in protected.items():
        if sha(Path(name)) != expected:
            raise ValueError("Audit mutated saved input: "+name)
    save(output / "inputs_sha256.json", {str(p): sha(p) for p in sorted(inputs)})
    print(json.dumps(dict(saved_attempts_read=len(summaries), focus=9,
        observer_gap_sim_seconds=hi-lo, simulation_launches=0,
        protected_inputs_verified_before_and_after=len(protected), all_gap_checks_passed=True), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.run.resolve(), args.output.resolve())
