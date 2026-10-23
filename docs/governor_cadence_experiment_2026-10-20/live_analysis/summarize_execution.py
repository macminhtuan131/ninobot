"""Read-only execution review; retain the assigned population and missing outcomes."""
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src/nino_rl/scripts"), str(ROOT / "src/nino_rl")]
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
import numpy as np


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    output = Path(__file__).resolve().parent
    run = ROOT / "rl_runs/governor_cadence_experiment_2026-10-20"
    ledger = json.loads((run / "ledger.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    report = json.loads((output / "report.json").read_text())
    inputs = {run / "ledger.json", run / "summary.json", output / "report.json",
              run / "authorization_snapshot.json", run / "protocol_snapshot.json",
              Path(__file__).resolve()}
    rows = []
    for slot, episode in zip(ledger["slots"], report["episodes"]):
        assert slot["attempt"] == episode["attempt"]
        result = slot.get("result") or {}
        integrity = result.get("integrity") or {}
        timing = report["timing"][str(slot["attempt"])]
        first = timing.get("first_contact_s")
        reduced = timing.get("first_reduced_input_s")
        published = (timing.get("first_executed") or {}).get("time_s")
        future = (timing.get("next_loaded_contact") or {}).get("loaded") or {}
        rows.append(dict(attempt=slot["attempt"], seed=slot["seed"], repeat=slot["repeat"],
            arm=slot["arm"], status=slot["status"], arrival=slot["physical_success"],
            stop_pass=result.get("stop_pass"), setup_pass=result.get("setup_pass"),
            provenance_pass=result.get("provenance_pass"),
            measurement_integrity_pass=result.get("measurement_integrity_pass"),
            quality_available=result.get("quality_available"),
            cadence_integrity=result.get("cadence_integrity"),
            native_replay_matches=integrity.get("native_match"),
            GT_slip_coverage=integrity.get("whole_GT", {}).get("coverage_fraction"),
            cleanup_confirmed=result.get("cleanup_confirmed"), metrics=episode["metrics"],
            first_input_after_contact_ms=1000 * (reduced-first) if reduced is not None else None,
            first_publication_after_contact_ms=1000 * (published-first) if published is not None else None,
            next_loaded_component=future.get("component"),
            next_loaded_contact_after_first_ms=1000 * (future["time_s"]-first) if future else None,
            timing_available=timing.get("available"), timing_error=timing.get("error"),
            response_snapshots=timing.get("response_snapshots")))
        if slot["adapter_requested"]:
            inputs.update([run / f"attempt_{slot['attempt']:02d}/result.json",
                           Path(result["logger"]) / "samples.jsonl",
                           Path(result["logger"]) / "contact_events.jsonl",
                           Path(result["logger"]) / "metadata.json",
                           Path(result["evaluation"]) / "episodes.csv"])
            inputs.update(Path(result["evaluation"]).glob("episode-*/*trace.csv"))

    failed = ledger["slots"][8]["result"]
    data = load(Path(failed["case"]), dict(seed=77601, profile="reactive",
                evaluation=failed["evaluation"], logger=failed["logger"]))
    gap_evidence = {}
    for key, maximum in (("ground", .040001), ("joints", .010001)):
        times = np.asarray(data[key])[:, 0]
        selected = (times[:-1] < data["end"]) & (times[1:] > data["start"])
        indices = np.where(selected & (np.diff(times) > maximum))[0]
        gap_evidence[key] = dict(maximum_allowed_gap_s=maximum,
            gaps=[dict(start_s=float(times[i]), end_s=float(times[i+1]),
                       duration_s=float(times[i+1]-times[i])) for i in indices])
    signal = gt_timestamp_series(data)
    inside = (signal["time"] >= data["start"]) & (signal["time"] <= data["end"])
    gap_evidence.update(route_start_s=data["start"], route_end_s=data["end"],
        whole_slip=failed["integrity"]["whole_GT"],
        invalid_joint_interpolation_GT_stamps_s=signal["time"][inside][~np.isfinite(signal["q"][inside])].tolist(),
        qualification="Saved observer trace has gaps. No identified transport/logger root cause; do not infer physical sensor outage or fill gaps.")

    review = dict(summary=summary, assigned_rows=rows, attempt9_gap_evidence=gap_evidence,
        conclusions=dict(command_timing="Two valid fast/reference pairs: reduced drive publication40/42ms earlier; remaining planned pairs unavailable.",
            physical_response="Not established as earlier causal speed response: contact disturbed body/wheel speed before command, snapshots nonmonotonic, incomplete batch.",
            quality="Planned aggregate comparisons/CI unavailable. Opposite slip directions in first two valid pairs; do not average a selected subset or promote candidate.",
            decision="Stop this released batch at the measurement hard stop. Slots10–12 remain unattempted; no resume, retries, replacement, extra smoke or new tuning.",
            next_step="A bounded offline check of observer acquisition/queue/backpressure over the attempt9 gap; preserve controller, scoring, coverage and dataset. No new simulation budget."),
        H2_decision="not_assessed", thresholds_applied=False, sampling_changed=False)
    (output / "execution_review.json").write_text(json.dumps(review, indent=2, allow_nan=False)+"\n")
    with (output / "assigned_attempts.csv").open("w", newline="") as stream:
        fields = ["attempt", "seed", "repeat", "arm", "status", "arrival", "stop_pass",
                  "measurement_integrity_pass", "GT_slip_coverage", "time", "tracking",
                  "post_slip", "post_vibration", "whole_slip", "whole_vibration",
                  "first_input_after_contact_ms", "first_publication_after_contact_ms"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row["metrics"].get(k) if k in row["metrics"] else row.get(k) for k in fields})
    (output / "execution_review_inputs_sha256.json").write_text(json.dumps(
        {str(p): digest(p) for p in sorted(inputs)}, indent=2)+"\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
