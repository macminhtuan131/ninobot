#!/usr/bin/env python3
"""Write a separate offline slip report; never alter native evaluation/study files."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nino_rl.slip_reporting import SLIP_REPORTING_PROTOCOL, synchronized_windows, replay_native_trace
from audit_governor_phase_slip import load, phase_windows, sha256


def csv_value(value):
    return float(value) if np.isfinite(value) else None


def run(stage, output):
    source = stage/"analysis/contact_analysis.json"
    baselines = json.loads(source.read_text())["results"]
    # A report must not overwrite the audit/study that it reads, or an earlier report.
    output = output.resolve()
    protected = [stage.parent.resolve()]
    if any(output == p or output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
        raise ValueError("Output overlaps raw study inputs")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be new/empty; preserve earlier reports")
    output.mkdir(parents=True, exist_ok=True)
    loaded, results, inputs = {}, [], {source}
    for baseline in baselines:
        case = Path(baseline["case"])
        try:
            loaded[str(case)] = load(case, baseline)
        except (OSError, ValueError, KeyError, StopIteration) as error:
            results.append(dict(case=str(case), seed=baseline.get("seed"), profile=baseline.get("profile"),
                                native_outcome=baseline.get("outcome"), available=False,
                                synchronized=None, reason=f"{type(error).__name__}: {error}"))
    for case, data in loaded.items():
        windows = {"whole_route": (data["start"], data["end"]),
                   "post_contact_to_clearance": (data["first"]+.05, data["clear"])
                   if data["first"] is not None and data["clear"] is not None else None}
        governor = next((g for g in loaded.values()
                         if g["seed"] == data["seed"] and g["profile"] == "reactive"), None)
        phase_reason = None
        if governor is not None:
            try:
                windows.update({"phase/"+name: (a, b) for name, a, b in phase_windows(data, governor)})
            except (ValueError, TypeError, StopIteration) as error:
                phase_reason = f"phase boundaries unavailable: {error}"
        else:
            phase_reason = "paired governor unavailable; no inferred action phases"
        signal, metrics = synchronized_windows(data, windows)
        replay = replay_native_trace(data["controls"])
        native = float(data["native"]["rms_wheel_slip"])
        if replay["available"]:
            replay["matches_saved_native_rms"] = bool(np.isclose(replay["rms"], native, rtol=1e-10, atol=1e-10))
        shifted = synchronized_windows(data, windows, offset=.01)[1]
        results.append(dict(case=case, seed=data["seed"], profile=data["profile"],
                            available=metrics["whole_route"]["available"],
                            native_outcome=data["native"], native_rms_wheel_slip=native,
                            native_snapshot_replay=replay, synchronized=metrics,
                            diagnostic_grid_offset_10ms=shifted, sampling=data["sampling"],
                            phase_boundary_qualification=phase_reason))
        with (output/(Path(case).name+"_synchronized_samples.csv")).open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["sim_time_s", "elapsed_s", "slip_mean_square", "ground_x_m", "ground_y_m",
                             "ground_lower_stamp_s", "ground_upper_stamp_s", "joint_lower_stamp_s", "joint_upper_stamp_s"])
            for t, q, xy, ground_stamps, joint_stamps in zip(signal["time"], signal["q"], signal["xy"],
                    signal["ground_support_stamps"], signal["joint_support_stamps"]):
                writer.writerow([csv_value(v) for v in [t, t-data["start"], q, *xy, *ground_stamps, *joint_stamps]])
        inputs.update([data["logger"]/"samples.jsonl", data["logger"]/"contact_events.jsonl",
                       data["evaluation"]/"episodes.csv", data["evaluation"]/"config.yaml",
                       *data["evaluation"].glob("episode-*/*trace.csv")])
    results.sort(key=lambda r: (r["seed"], r["profile"]))
    payload = dict(schema="slip_report_bundle_v1", no_simulation=True, native_scores_changed=False,
                   protocol=SLIP_REPORTING_PROTOCOL, numpy_version=np.__version__,
                   windows={"whole_route": "first control input to final action end; excludes postarrival stop",
                            "post_contact_to_clearance": "first recorded cable contact +0.05s to saved x>=3.40m clearance",
                            "phases": "paired governor command windows relative to own contact; diagnostic only"},
                   episodes=results)
    (output/"report.json").write_text(json.dumps(payload, indent=2, allow_nan=False)+"\n")
    with (output/"windows.csv").open("w", newline="") as stream:
        columns = ["seed", "profile", "window", "available", "native_rms_wheel_slip",
                   "duration_s", "coverage_s", "coverage_fraction", "slip_square_integral_s", "rms",
                   "distance_m", "slip_square_per_m", "reason"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for r in results:
            if r["synchronized"] is None:
                writer.writerow(dict(seed=r["seed"], profile=r["profile"], available=False, reason=r["reason"]))
                continue
            for name, metric in r["synchronized"].items():
                writer.writerow(dict(seed=r["seed"], profile=r["profile"], window=name,
                    native_rms_wheel_slip=r["native_rms_wheel_slip"] if name == "whole_route" else None,
                    **{k: metric.get(k) for k in columns[3:] if k != "native_rms_wheel_slip"}))
    module = Path(__file__).resolve().parents[1]/"nino_rl/slip_reporting.py"
    inputs.update([Path(__file__).resolve(), module, Path(__file__).with_name("audit_governor_phase_slip.py")])
    sources = output/"sources"
    sources.mkdir()
    for p in [Path(__file__), module, Path(__file__).with_name("audit_governor_phase_slip.py")]:
        shutil.copy2(p, sources/p.name)
    (output/"provenance.json").write_text(json.dumps({str(p.resolve()): sha256(p) for p in sorted(inputs)}, indent=2)+"\n")
    print(f"Offline report: {output}; {len(results)} episodes retained, "
          f"{sum(r['available'] for r in results)} whole-route windows available")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.stage, args.output)


if __name__ == "__main__":
    main()
