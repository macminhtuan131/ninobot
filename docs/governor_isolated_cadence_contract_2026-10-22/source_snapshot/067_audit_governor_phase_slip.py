#!/usr/bin/env python3
"""Offline slip accounting on a common time grid; never launches or rescores runs."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nino_rl.slip_reporting import (
    RADIUS, TRACK, MAX_GAP, interpolate, integrate, slip_square, synchronized_series,
)


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def series(data, period=.02, offset=0., nearest_ground=False):
    if nearest_ground:
        times = data["joints"][:, 0]
        times = times[(times >= data["start"]) & (times <= data["end"])]
        right = np.searchsorted(data["ground"][:, 0], times)
        upper = np.minimum(right, len(data["ground"])-1)
        lower = np.maximum(right-1, 0)
        at = np.where(abs(data["ground"][lower, 0]-times) <= abs(data["ground"][upper, 0]-times), lower, upper)
        ground = data["ground"][at, 1:].copy()
        ground[abs(data["ground"][at, 0]-times) > .025] = np.nan
    else:
        return synchronized_series(data, period=period, offset=offset)
    wheels = interpolate(data["joints"], times, .010001)
    return dict(time=times, q=slip_square(wheels, ground), xy=ground[:, 2:4])


def load(case, baseline):
    evaluation = Path(baseline["evaluation"])
    logger = Path(baseline["logger"])
    controls = read_csv(next(evaluation.glob("episode-*/control_trace.csv")))
    if not controls:
        raise ValueError("No saved control samples; route window unavailable")
    start = float(controls[0].get("governor_input_time_s") or
                  (float(controls[0]["sim_time_s"])-float(controls[0]["elapsed_s"])))
    end = float(controls[-1]["sim_time_s"])
    ground, joints = {}, {}
    counts = {"ground": 0, "joints": 0}
    malformed = 0
    for line in (logger/"samples.jsonl").open():
        try:
            row = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if row["topic"] not in ("/joint_states", "/ground_truth/odom"):
            continue
        d = row["data"]
        t = d["header"]["stamp"]["sec"]+d["header"]["stamp"]["nanosec"]*1e-9
        if not start-.06 <= t <= end+.06:
            continue
        if row["topic"] == "/joint_states":
            counts["joints"] += 1
            v = dict(zip(d["name"], d["velocity"]))
            joints[t] = (t, v.get("left_wheel_joint", np.nan), v.get("right_wheel_joint", np.nan))
        else:
            counts["ground"] += 1
            tw, p = d["twist"]["twist"], d["pose"]["pose"]["position"]
            ground[t] = (t, tw["linear"]["x"], tw["angular"]["z"], p["x"], p["y"])
    native_rows = read_csv(evaluation/"episodes.csv")
    if len(native_rows) != 1:
        raise ValueError("Screen loader requires exactly one saved episode per case")
    native = native_rows[0]
    return dict(case=str(case), seed=baseline["seed"], profile=baseline["profile"],
                start=start, end=end, controls=controls,
                ground=np.array(sorted(ground.values())).reshape(-1, 5),
                joints=np.array(sorted(joints.values())).reshape(-1, 3),
                first=(baseline.get("first_contact") or {}).get("time_s"),
                clear=(baseline.get("postcontact_until_clearance") or {}).get("end_time_s"),
                native=native, logger=logger, evaluation=evaluation,
                sampling=dict(raw_rows=counts, duplicate_stamps_kept_last={
                    "ground": counts["ground"]-len(ground), "joints": counts["joints"]-len(joints)},
                    malformed_lines=malformed,
                    max_ground_gap_s=float(np.max(np.diff(sorted(ground)))) if len(ground) > 1 else None,
                    max_joint_gap_s=float(np.max(np.diff(sorted(joints)))) if len(joints) > 1 else None))


def crossing_time(data, x):
    g = data["ground"]
    for a, b in zip(g, g[1:]):
        if a[3] < x <= b[3] and b[0]-a[0] <= MAX_GAP:
            return float(a[0]+(x-a[3])/(b[3]-a[3])*(b[0]-a[0]))
    raise ValueError(f"No covered forward crossing x={x}: {data['case']}")


def phase_windows(data, governor):
    controls = governor["controls"]
    brake = next(float(r["governor_input_time_s"]) for r in controls if r["governor_phase"] == "HOLD")
    hold = next(float(r["governor_input_time_s"]) for r in controls
                if float(r["governor_scale"]) <= .900001)
    recover = next(float(r["governor_input_time_s"]) for r in controls if r["governor_phase"] == "RECOVER")
    cruise = next(float(r["governor_input_time_s"]) for r in controls
                  if float(r["governor_input_time_s"]) > recover and r["governor_phase"] == "CRUISE")
    # PI has no braking/holding; translate the paired governor's boundaries relative to contact.
    shift = data["first"]-governor["first"]
    cuts = [data["start"], data["start"]+1., data["first"], brake+shift,
            hold+shift, recover+shift, cruise+shift, data["clear"], crossing_time(data, 5.95), data["end"]]
    if not np.all(np.diff(cuts) > 0):
        raise ValueError("Unexpected/repeated phases; manual review required, not silently relabeled")
    names = ["startup_1s", "precontact_cruise", "contact_before_brake", "braking_command",
             "holding_command", "recovery_command", "crossing_after_recovery",
             "postclear_cruise", "final_0p5m"]
    return list(zip(names, cuts[:-1], cuts[1:]))


def spatial_windows(data):
    cuts = [data["start"], data["start"]+1., crossing_time(data, 2.40),
            crossing_time(data, 3.40), crossing_time(data, 5.95), data["end"]]
    return list(zip(["startup_1s", "pre_obstacle", "obstacle_2p4_to_3p4m",
                     "post_obstacle", "final_0p5m"], cuts[:-1], cuts[1:]))


def summarize(results, key):
    output = {}
    for profile in ("full", "reactive"):
        arm = [r for r in results if r["profile"] == profile]
        names = arm[0][key].keys()
        output[profile] = {}
        for name in names:
            rows = [r[key][name] for r in arm]
            output[profile][name] = dict(n=len(rows),
                **{field: float(np.mean([r[field] for r in rows]))
                   if all(r[field] is not None for r in rows) else None
                   for field in ("duration_s", "coverage_fraction", "slip_square_integral_s", "rms", "distance_m", "slip_square_per_m")})
    return output


def plots(data, signals, results, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"full": "#404040", "reactive": "#1676aa"}
    fig, axes = plt.subplots(3, 2, figsize=(13, 9), constrained_layout=True)
    for i, seed in enumerate(sorted({d["seed"] for d in data})):
        pair = [d for d in data if d["seed"] == seed]
        for d in pair:
            s = signals[d["case"]]
            axes[i, 0].plot(s["time"]-d["first"], np.sqrt(s["q"]), lw=.8,
                           color=colors[d["profile"]], label=d["profile"])
            axes[i, 1].plot(d["ground"][:, 0]-d["first"], d["ground"][:, 1],
                           color=colors[d["profile"]], lw=1., label=d["profile"]+" body")
            drive = read_csv(next(d["evaluation"].glob("episode-*/drive_trace.csv")))
            axes[i, 1].plot([float(r["sim_time_s"])-d["first"] for r in drive],
                           [RADIUS*.5*(float(r["left_actual_rad_s"])+float(r["right_actual_rad_s"])) for r in drive],
                           color=colors[d["profile"]], ls="--", lw=.7, label=d["profile"]+" wheels")
        gov = next(d for d in pair if d["profile"] == "reactive")
        for name, a, b in phase_windows(gov, gov):
            if name in ("braking_command", "holding_command", "recovery_command"):
                for ax in axes[i]:
                    ax.axvspan(a-gov["first"], b-gov["first"], alpha=.10,
                               color={"braking_command":"red", "holding_command":"orange", "recovery_command":"green"}[name])
        for ax in axes[i]:
            ax.axvline(0., color="black", ls=":"); ax.grid(alpha=.2)
            ax.set_title(f"Seed {seed}"); ax.set_xlim(-1., 3.)
        axes[i, 0].set_ylabel("Slip RMS across two wheels")
        axes[i, 1].set_ylabel("Speed (m/s)")
    axes[0, 0].legend(); axes[0, 1].legend(fontsize=8, ncol=2)
    for ax in axes[-1]: ax.set_xlabel("Seconds after first recorded cable contact")
    fig.suptitle("Same 50 Hz reconstruction — no sample trimming\nRed: command braking; orange: hold; green: recovery. PI uses paired event windows.")
    fig.savefig(output/"contact_phases.png", dpi=150); plt.close(fig)
    summary = summarize(results, "phases")
    names = list(summary["full"])
    fig, ax = plt.subplots(figsize=(12, 5), constrained_layout=True)
    x = np.arange(len(names))
    for offset, profile in ((-.19, "full"), (.19, "reactive")):
        ax.bar(x+offset, [summary[profile][name]["slip_square_integral_s"] for name in names],
               width=.38, color=colors[profile], label=profile)
    ax.set_xticks(x, names, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("Mean integral of wheel slip² (s); n=3 episodes per arm")
    ax.set_title("Whole-route accounting: phases sum to the whole integral; 50 Hz common grid")
    ax.legend(); ax.grid(axis="y", alpha=.2)
    fig.savefig(output/"whole_route_phase_integrals.png", dpi=150); plt.close(fig)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""): digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = args.stage/"analysis/contact_analysis.json"
    baselines = json.loads(source.read_text())["results"]
    data = [load(Path(b["case"]), b) for b in baselines]
    results, signals = [], {}
    for d in data:
        governor = next(g for g in data if g["seed"] == d["seed"] and g["profile"] == "reactive")
        s = series(d); signals[d["case"]] = s
        whole = integrate(s, d["start"], d["end"])
        phases = {name: integrate(s, a, b) for name, a, b in phase_windows(d, governor)}
        space = {name: integrate(s, a, b) for name, a, b in spatial_windows(d)}
        for partition in (phases, space):
            assert abs(sum(r["observed_slip_square_integral_s"] or 0. for r in partition.values())
                       -(whole["observed_slip_square_integral_s"] or 0.)) < 1e-8
        sensitivity = {}
        for period, offset in ((.02, .01), *[(.1, k*.02) for k in range(5)]):
            alt = series(d, period, offset)
            valid = alt["q"][np.isfinite(alt["q"])]
            sensitivity[f"sample_rms_{period:g}s_offset_{offset:g}s"] = float(np.sqrt(np.mean(valid))) if len(valid) else None
        dense = series(d, nearest_ground=True)
        near = integrate(dense, d["start"], d["end"])
        rows = d["controls"]
        endpoint_times = np.array([float(r["sim_time_s"]) for r in rows])
        endpoint_q = slip_square(interpolate(d["joints"], endpoint_times, .010001),
                                 interpolate(d["ground"], endpoint_times))
        endpoint_valid = endpoint_q[np.isfinite(endpoint_q)]
        saved_body = np.array([[float(r["physical_speed_m_s"]), float(r["physical_yaw_rate_rad_s"])] for r in rows])
        synced_body = interpolate(d["ground"], endpoint_times)[:, :2]
        vx_delta = saved_body[:, 0]-synced_body[:, 0]
        hybrid_q = slip_square(interpolate(d["joints"], endpoint_times, .010001), saved_body)
        shifted = series(d, .02, .01)
        result = dict(case=d["case"], seed=d["seed"], profile=d["profile"],
                      native_outcome=d["native"], sampling=d["sampling"], whole=whole,
                      phases=phases, spatial=space,
                      native_rms=float(d["native"]["rms_wheel_slip"]),
                      reconstructed_control_endpoint_rms=float(np.sqrt(np.mean(endpoint_valid))),
                      reconstructed_control_endpoint_valid_fraction=float(len(endpoint_valid)/len(rows)),
                      native_body_diagnostic=dict(
                          saved_vs_synchronized_vx_rms_difference_m_s=float(np.sqrt(np.nanmean(vx_delta**2))),
                          saved_vs_synchronized_vx_max_difference_m_s=float(np.nanmax(abs(vx_delta))),
                          hybrid_saved_body_synced_wheels_rms=float(np.sqrt(np.nanmean(hybrid_q))),
                          qualification="Hybrid diagnostic only; native wheel snapshot timestamps are not in control_trace. Not exact native reconstruction or proof of callback error."),
                      diagnostic_old_joint_nearest_gt=near, sampling_sensitivity=sensitivity,
                      shifted_50hz_whole=integrate(shifted, d["start"], d["end"]),
                      shifted_50hz_phases={name: integrate(shifted, a, b)
                                          for name, a, b in phase_windows(d, governor)},
                      nearest_gt_phases={name: integrate(dense, a, b)
                                         for name, a, b in phase_windows(d, governor)},
                      local_same_sampling=integrate(s, d["first"]+.05, d["clear"]))
        results.append(result)
        print(d["seed"], d["profile"], "native", result["native_rms"], "50Hz", whole["rms"], "integral", whole["slip_square_integral_s"])
        with (args.output/(Path(d["case"]).name+"_50hz.csv")).open("w") as stream:
            writer = csv.writer(stream); writer.writerow(["sim_time_s", "elapsed_s", "slip_mean_square", "ground_x_m", "ground_y_m"])
            for t, q, xy in zip(s["time"], s["q"], s["xy"]):
                writer.writerow([t, t-d["start"], q if np.isfinite(q) else "", *[v if np.isfinite(v) else "" for v in xy]])
    payload = dict(no_simulation=True, scores_changed=False,
                   protocol=dict(grid_s=.02, origin="first control input time of each episode",
                                 interpolation="linear sensor values, then slip; no extrapolation",
                                 max_ground_gap_s=MAX_GAP, max_joint_gap_s=.010001,
                                 minimum_coverage=.98, duplicate_policy="last row at stamp",
                                 formula="mean of squared clipped longitudinal wheel ratios, core.py convention",
                                 phase_rule="Governor command windows; PI paired contact-relative windows, not PI actions",
                                 space_rule="startup 1s, x<2.4, 2.4<=x<3.4, 3.4<=x<5.95, final x>=5.95",
                                 interval="first control input through final action end; postarrival 2s excluded as in native route metric"),
                   episodes=results, phase_means=summarize(results, "phases"),
                   shifted_50hz_phase_means=summarize(results, "shifted_50hz_phases"),
                   nearest_gt_phase_means=summarize(results, "nearest_gt_phases"),
                   spatial_means=summarize(results, "spatial"))
    (args.output/"result.json").write_text(json.dumps(payload, indent=2, allow_nan=False)+"\n")
    with (args.output/"phase_metrics.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=["seed", "profile", "partition", "phase", *results[0]["whole"].keys()])
        writer.writeheader()
        for r in results:
            for partition in ("phases", "spatial"):
                for phase, metrics in r[partition].items():
                    writer.writerow(dict(seed=r["seed"], profile=r["profile"], partition=partition, phase=phase, **metrics))
    plots(data, signals, results, args.output)
    inputs = [source, Path(__file__), args.stage/"contract.json"]
    for d in data:
        inputs.extend([d["logger"]/"samples.jsonl", d["logger"]/"contact_events.jsonl",
                       d["evaluation"]/"episodes.csv", d["evaluation"]/"config.yaml",
                       *d["evaluation"].glob("episode-*/*trace.csv")])
    # The contract is one directory above validation in this frozen study.
    inputs = [p if p.exists() else args.stage.parent/p.name for p in inputs]
    (args.output/"provenance.json").write_text(json.dumps({str(p.resolve()): sha256(p) for p in inputs}, indent=2)+"\n")
    (args.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())


if __name__ == "__main__":
    main()
