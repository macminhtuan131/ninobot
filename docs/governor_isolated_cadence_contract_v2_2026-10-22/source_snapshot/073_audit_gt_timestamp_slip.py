#!/usr/bin/env python3
"""Offline GT-header-time slip audit. No control, native score or study mutations."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nino_rl.slip_reporting import interpolate, interpolation_stamps, slip_square, integrate, synchronized_series
from audit_governor_phase_slip import load, sha256


def gt_timestamp_series(data):
    """Keep real GT samples untouched; interpolate only joint velocities at their stamps.

    Preserve the saved GT support outside the route for boundary-clipped
    quadrature. Do not create new GT measurements at window boundaries.
    """
    ground = np.asarray(data["ground"], dtype=float).reshape(-1, 5)
    joints = np.asarray(data["joints"], dtype=float).reshape(-1, 3)
    if len(ground) and (not np.isfinite(ground[:,0]).all() or np.any(np.diff(ground[:,0]) <= 0)):
        raise ValueError("GT stamps must be sorted, finite, deduplicated")
    times = ground[:,0].copy()
    wheels = interpolate(joints, times, .010001)
    return dict(time=times, q=slip_square(wheels, ground[:,1:]), xy=ground[:,3:5].copy(),
                ground_values=ground[:,1:].copy(), wheel_rad_s=wheels,
                joint_support_stamps=interpolation_stamps(joints,times))


def common_bounds(signals, start, end):
    """Common edge support only; internal invalid samples still lower coverage."""
    bounds = []
    for signal in signals:
        valid = np.isfinite(signal["q"]) & np.isfinite(signal["xy"]).all(axis=1)
        if not valid.any(): return None
        times = signal["time"][valid]
        bounds.append((times[0],times[-1]))
    lo,hi = max(start,*[b[0] for b in bounds]),min(end,*[b[1] for b in bounds])
    return (float(lo),float(hi)) if hi > lo else None


def groups(rows, section):
    result = {}
    for profile in ("full","reactive"):
        arm = [r for r in rows if r["profile"]==profile]
        result[profile] = dict(episodes=len(arm), physical_failures=sum(r["source_outcome"].get("physical_success") is False for r in arm), methods={})
        for method in ("primary","shifted","gt_native"):
            result[profile]["methods"][method] = {}
            for window in ("whole_route","crossing"):
                observed = [r.get(section,{}).get(method,{}).get(window,{}) for r in arm]
                entry = dict(available_episodes=sum(m.get("available",False) for m in observed))
                for key in ("rms","slip_square_integral_s","slip_square_per_m","distance_m","coverage_fraction"):
                    vals = [m.get(key) for m in observed]
                    entry[key] = float(np.mean(vals)) if vals and all(v is not None for v in vals) else None
                result[profile]["methods"][method][window] = entry
    return result


def pair_ratios(rows):
    results = []
    for seed in sorted({r["seed"] for r in rows}):
        arms = {r["profile"]:r for r in rows if r["seed"]==seed}
        entry = dict(seed=seed, scenario=next(iter(arms.values()))["scenario"], ratios={})
        for method in ("primary","shifted","gt_native"):
            entry["ratios"][method] = {}
            for label,window,key in (("whole_rms","whole_route","rms"),("crossing_per_m","crossing","slip_square_per_m")):
                vals = [arms.get(p,{}).get("windows",{}).get(method,{}).get(window,{}).get(key) for p in ("full","reactive")]
                entry["ratios"][method][label] = vals[1]/vals[0] if all(v is not None for v in vals) and vals[0]>0 else None
        results.append(entry)
    return results


def plot(pairs, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure,axes = plt.subplots(2,1,figsize=(11,7),constrained_layout=True)
    for ax,key,title in zip(axes,("whole_rms","crossing_per_m"),("Whole-route slip RMS","Crossing slip² integral/metre")):
        for offset,method,label in ((-.15,"primary","20 ms grid"),(0.,"shifted","20 ms grid +10 ms"),(.15,"gt_native","Original GT timestamps")):
            vals = [p["ratios"][method][key] for p in pairs]
            ax.scatter([i+offset for i,v in enumerate(vals) if v is not None],[v for v in vals if v is not None],label=label,s=40)
        ax.axhline(1.,color="black",ls="--",lw=1);ax.grid(alpha=.2)
        ax.set_xticks(range(len(pairs)),[f"{p['scenario']}\n{p['seed']}" for p in pairs])
        ax.set_ylabel("Governor / paired PI");ax.set_title(title)
    axes[0].legend(ncol=3,fontsize=9)
    figure.suptitle("Same 16 saved episodes, fixed windows and slip formula\nGT-native changes only the evaluation time base; below1 favours governor")
    figure.savefig(output/"paired_timebase_comparison.png",dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    source = json.loads(args.episodes.read_text())
    args.output.mkdir(parents=True,exist_ok=False)
    protocol = dict(schema="gt_timestamp_slip_audit_v1", no_simulation=True, native_or_study_changed=False,
        sampling="Original GT header timestamps only, including saved boundary support; GT velocity/pose never resampled",
        joint_alignment="linear interpolation at GT stamps; no extrapolation; max joint gap10ms",
        duplicate_policy="keep last row at stamp; same raw loader as frozen audit",
        integration="same slip formula and gap/coverage/distance rules as frozen audit; quadrature clips segments at fixed boundaries",
        boundaries="unchanged first control input/final action end, first contact+50ms/declared cable-normal clearance from frozen results",
        edge_control="also report all three methods on their shared edge support to isolate boundary-coverage differences",
        qualification="Post-hoc diagnostic, not replacement objective or new candidate selection. Original GT still approximately50Hz, not continuous physical slip.")
    (args.output/"protocol_before_calculation.json").write_text(json.dumps(protocol,indent=2)+"\n")
    inputs = {args.episodes.resolve(),Path(__file__).resolve()}
    rows = []
    for old in source:
        case = Path(old["case"])
        row = dict(seed=old["seed"],scenario=old["scenario"],profile=old["profile"],
                   source_outcome=old, available=False)
        try:
            evaluation = next(case.glob("evaluation/*/summary.json")).parent
            logger = next(case.glob("contact/*/metadata.json")).parent
            data = load(case,dict(evaluation=str(evaluation),logger=str(logger),seed=old["seed"],profile=old["profile"],
                        first_contact={"time_s":old["first_contact_s"]},
                        postcontact_until_clearance={"end_time_s":old["clearance_s"]}))
            signals = dict(primary=synchronized_series(data),shifted=synchronized_series(data,offset=.01),gt_native=gt_timestamp_series(data))
            windows = dict(whole_route=(data["start"],data["end"]),crossing=(old["first_contact_s"]+.05,old["clearance_s"]))
            metrics = {method:{name:integrate(signal,*bounds) for name,bounds in windows.items()} for method,signal in signals.items()}
            # Exact replay of the old offline metrics is a prerequisite, not a new score.
            for method in ("primary","shifted"):
                for name in windows:
                    if metrics[method][name] != old[method][name]:
                        raise ValueError(f"Frozen {method}/{name} failed exact reproduction")
            common = {name:common_bounds(list(signals.values()),*bounds) for name,bounds in windows.items()}
            matched = {method:{name:integrate(signal,*bounds) if bounds is not None else dict(available=False)
                               for name,bounds in common.items()} for method,signal in signals.items()}
            native = signals["gt_native"]
            selected = (native["time"]>=data["start"]) & (native["time"]<=data["end"])
            dt = np.diff(native["time"])
            row.update(available=all(m["available"] for m in metrics["gt_native"].values()),
                windows=metrics, common_support_windows=matched, common_support_bounds=common, sampling=data["sampling"],
                gt_native_samples_inside_route=int(selected.sum()),
                gt_interval_range_s=[float(dt.min()),float(dt.max())] if len(dt) else None,
                exact_joint_match_fraction=float(np.mean(np.isclose(native["joint_support_stamps"][selected,0],native["time"][selected],atol=1e-8,rtol=0.))) if selected.any() else None,
                native_gt_values_untouched=bool(np.array_equal(native["ground_values"],data["ground"][:,1:])))
            with (args.output/(case.name+"_gt_timestamps.csv")).open("w",newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["sim_time_s","inside_route","ground_vx_m_s","ground_yaw_rad_s","ground_x_m","ground_y_m",
                                 "left_wheel_rad_s","right_wheel_rad_s","joint_lower_stamp_s","joint_upper_stamp_s","slip_mean_square"])
                for t,g,w,j,q in zip(native["time"],native["ground_values"],native["wheel_rad_s"],native["joint_support_stamps"],native["q"]):
                    values = [t,bool(data["start"]<=t<=data["end"]),*g,*w,*j,q]
                    writer.writerow([v if isinstance(v,bool) or np.isfinite(v) else None for v in values])
            inputs.update([logger/"samples.jsonl",logger/"metadata.json",evaluation/"episodes.csv",*evaluation.glob("episode-*/control_trace.csv")])
            print(old["seed"],old["profile"],"GT-native RMS",metrics["gt_native"]["whole_route"]["rms"],flush=True)
        except (OSError,ValueError,KeyError,StopIteration) as error:
            row["reason"] = f"{type(error).__name__}: {error}"
        rows.append(row)
    pairs = pair_ratios(rows)
    result = dict(protocol=protocol,episodes=rows,full_window_means=groups(rows,"windows"),
                  common_support_means=groups(rows,"common_support_windows"),pairs=pairs,
                  scenario_means={s:groups([r for r in rows if r["scenario"]==s],"windows") for s in sorted({r["scenario"] for r in rows})})
    (args.output/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    with (args.output/"window_metrics.csv").open("w",newline="") as stream:
        fields=["seed","scenario","profile","method","window","available","rms","slip_square_integral_s","slip_square_per_m","coverage_fraction","distance_m"]
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in rows:
            for method,windows in r.get("windows",{}).items():
                for name,metric in windows.items():
                    writer.writerow(dict(seed=r["seed"],scenario=r["scenario"],profile=r["profile"],method=method,window=name,
                                         **{key:metric.get(key) for key in fields[5:]}))
    plot(pairs,args.output)
    sources=args.output/"sources";sources.mkdir()
    for p in [Path(__file__),Path(__file__).with_name("audit_governor_phase_slip.py"),Path(__file__).resolve().parents[1]/"nino_rl/slip_reporting.py"]:
        inputs.add(p.resolve());shutil.copy2(p,sources/p.name)
    (args.output/"provenance.json").write_text(json.dumps({str(p):sha256(p) for p in sorted(inputs)},indent=2)+"\n")
    print("Completed offline:",sum(r["available"] for r in rows),"/",len(rows),flush=True)


if __name__=="__main__":main()
