"""Summarize new observer telemetry, never change sample windows or native scores."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(run, output):
    output.mkdir(exist_ok=False, parents=True)
    ledger = json.loads((run/"ledger.json").read_text())
    inputs = {run/"ledger.json", run/"summary.json", Path(__file__).resolve()}
    results = []
    for slot in ledger["slots"]:
        result = slot.get("result") or {}
        item = dict(attempt=slot["attempt"], arm=slot["arm"], status=slot["status"],
                    arrival=slot["physical_success"], observer_health=result.get("observer_health_integrity"))
        if not result.get("logger"):
            results.append(item)
            continue
        logger = Path(result["logger"])
        path = logger/"observer_health.jsonl"
        inputs.update([logger/"samples.jsonl",logger/"metadata.json"])
        if not path.exists():
            item["unavailable"] = "observer_sidecar_missing"
            results.append(item)
            continue
        summary_path = logger/"observer_health_summary.json"
        inputs.add(path)
        if not summary_path.exists():
            prefix=0;malformed=None
            for number,line in enumerate(path.open(),1):
                try:json.loads(line)
                except ValueError:
                    malformed=number;break
                prefix+=1
            item.update(unavailable="health_summary_missing_after_interrupted_close",
                valid_prefix_rows=prefix,first_malformed_line=malformed,
                qualification="Partial prefix is not complete observer telemetry; no costs inferred for the run")
            results.append(item)
            continue
        rows = [json.loads(line) for line in path.open()]
        inputs.add(summary_path)
        stages = {}
        for row in rows:
            for name, value in row["stages_ns"].items():
                entry = stages.setdefault(name, dict(calls=0,total_ns=0,maximum_ns=0))
                entry["calls"] += 1; entry["total_ns"] += value
                entry["maximum_ns"] = max(entry["maximum_ns"], value)
        top_work = sorted(rows, key=lambda r:r["duration_ns"], reverse=True)[:10]
        top_idle = sorted(rows, key=lambda r:r["since_previous_exit_ns"] or 0, reverse=True)[:10]
        item.update(summary=json.loads(summary_path.read_text()), stage_costs=stages,
                    longest_callbacks=top_work, longest_inter_callback_gaps=top_idle)
        # Saved raw header gaps: independent check, no interpolation or score replacement.
        stamps = {t:[] for t in ("/ground_truth/odom", "/joint_states", "/imu/data")}
        for line in (logger/"samples.jsonl").open():
            row = json.loads(line)
            if row["topic"] in stamps:
                s=row["data"]["header"]["stamp"]
                stamps[row["topic"]].append(s["sec"]+s["nanosec"]*1e-9)
        item["raw_header_max_gap_s"] = {}
        for topic,ts in stamps.items():
            ts=sorted(set(ts))
            item["raw_header_max_gap_s"][topic]=max((b-a for a,b in zip(ts,ts[1:])),default=None)
        item["native_measurement_integrity_pass"] = result.get("measurement_integrity_pass")
        item["whole_GT_coverage"] = result.get("integrity",{}).get("whole_GT",{}).get("coverage_fraction")
        results.append(item)
    report = dict(attempts=results, simulator_launches=0, metrics_changed=False,
        qualification="Measured observer costs and inter-callback intervals only. An idle interval alone is not proof of scheduling or DDS loss; a stage duration is observer work/blocking including descheduling during that stage. This is telemetry, not a new quality gate.")
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    (output/"inputs_sha256.json").write_text(json.dumps({str(p):digest(p) for p in sorted(inputs)},indent=2)+"\n")
    return dict(attempted=sum(x["status"]!="not_attempted" for x in results),
        complete_health=sum(bool(x.get("summary")) for x in results),total_assigned=len(results))


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(analyze(a.run.resolve(),a.output.resolve()),indent=2))
