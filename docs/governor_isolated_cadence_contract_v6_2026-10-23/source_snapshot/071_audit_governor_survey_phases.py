#!/usr/bin/env python3
"""Offline phase accounting for the frozen 16-run descriptive survey. No ROS.

Reuse the frozen GT-header/joint interpolation and native replay implementations.
Phase decomposition is explanatory, never a new score or candidate selection.
"""
import argparse
import bisect
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src/nino_rl"), str(ROOT / "src/nino_control")]
from audit_governor_phase_slip import load, read_csv, sha256
from audit_gt_timestamp_slip import gt_timestamp_series
from prepare_governor_contact_sequence import signal_stats
from nino_control.governor_core import quaternion_rpy, vertical_acceleration
from nino_rl.slip_reporting import integrate, replay_native_trace, RADIUS, TRACK


PHASES = ("startup_1s", "precontact", "contact_before_brake", "braking",
          "holding", "recovery", "after_recovery")
COMPONENTS = ("left_wheel", "right_wheel", "caster_left_wheel", "caster_right_wheel")
PROTOCOL = dict(
    schema="frozen_survey_phase_audit_v1", no_simulation=True,
    score_or_controller_changes=False, H2_decision=None, thresholds_applied=False,
    pairing="All 8 distinct seed+repeat pairs; no failure or missing-data deletion",
    sampling="Original GT header stamps, keep-last duplicates; joints linearly interpolated at GT stamps, max gap .010001s. Frozen slip formula and boundary-clipped trapezoids, max GT gap .040001s, coverage >=.98; every spike retained",
    original_windows="Whole route, original crossing, tc+.05 to tc+3, and complete contact sequence retained and checked against frozen report",
    phases="startup1s, precontact, contact_before_brake, braking, holding, recovery, after_recovery; exhaustive route partition. Transition uses FIRST SAVED DRIVE PUBLICATION acknowledging the changed governor input, conservative publication bound, not claimed actuator latency",
    executed_mapping="Drive command_received_sim_s as-of governor_input_time_s, max age .100001s; requested v must equal upstream requested v * governor scale; no future control lookup",
    PI_alignment="Use the paired governor's phase offsets relative to each run's own first recorded cable manifold; startup and route end remain own. Event-aligned PI windows are diagnostic, not equal contact identity, pose, or exposure",
    repeats="Every executed sequence supported; retriggers must be rejected explicitly rather than silently cut away. This batch has one sequence per governor",
    context="Command/limit stats at original drive publications; body at original GT stamps; original IMU sample RMS/peak. At each GT timestamp, drive/contact as-of only, bounded age .050001/.020001s. Interpolated joints offline may use later support, explicitly recorded",
    contact="Positive obstacle manifold events retained separately from loaded samples (depth>0 and wrench norm>1e-6 N). Sample force is not impulse. Floor support fraction is sample fraction, not load guarantee",
    limits="Applied/PI/requested Nm are commands, not measured motor torque. limited flags combine torque/rate/soft-speed limits; absence at 50Hz publications cannot exclude transient limiting at 500Hz PI updates",
    interpretation="Integral (s) is additive across phases, slip²/m and RMS are not. No causal attribution from pair delta alone; contact/reset variability and different sampled exposure remain",
)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def stats(values):
    values = np.asarray(values, float)
    if not len(values) or not np.isfinite(values).all():
        return dict(n=len(values), available=False, mean=None, min=None, max=None, rms=None)
    return dict(n=len(values), available=True, mean=float(values.mean()),
                min=float(values.min()), max=float(values.max()),
                rms=float(np.sqrt(np.mean(values ** 2))))


def asof(rows, t, max_age):
    """Rows sorted/deduplicated, no future sample even near a floating boundary."""
    i = bisect.bisect_right(rows, t, key=lambda row: row[0]) - 1
    if i < 0 or t - rows[i][0] > max_age:
        return None
    return rows[i]


def partition(start, first, end, transition):
    cuts = [start, start + 1., first, transition["braking"], transition["holding"],
            transition["recovery"], transition["after_recovery"], end]
    if not all(math.isfinite(v) for v in cuts) or not all(b > a for a, b in zip(cuts, cuts[1:])):
        raise ValueError("Missing/unordered phase boundaries; do not invent or drop a phase")
    return list(zip(PHASES, cuts[:-1], cuts[1:]))


def executed_transitions(controls, drive):
    """Resolve complete single sequence using command receipt, not control endpoints."""
    cs = sorted((float(c["governor_input_time_s"]), c) for c in controls)
    previous = ("CRUISE", 1.)
    changes = []
    for t, c in cs:
        key = (c["governor_phase"], float(c["governor_scale"]))
        if key != previous:
            changes.append((t, key, c))
        previous = key
    # Explicitly fail on any extra/retriggered sequence or unexpected action formulation.
    expected = [("HOLD", .96), ("HOLD", .92), ("HOLD", .9),
                ("RECOVER", .94), ("RECOVER", .98), ("CRUISE", 1.)]
    if len(changes) != len(expected) or any(
            key[0] != want[0] or abs(key[1] - want[1]) > 1e-6
            for (_, key, _), want in zip(changes, expected)):
        raise ValueError("Unexpected/repeated sequence; preserve data, require explicit phase protocol")
    result = {}
    detail = []
    for j, (input_t, key, c) in enumerate(changes):
        found = None
        for t, d in drive:
            received = d["command_received_sim_s"]
            if received > t + 1e-9:
                raise ValueError("Future command receipt")
            mapped = asof(cs, received, .100001)
            if mapped is None or abs(mapped[0] - input_t) > 1e-8:
                continue
            if abs(d["requested_linear_m_s"] - float(c["governor_requested_linear_m_s"]) * key[1]) > 1e-6:
                continue
            found = dict(input_s=input_t, received_s=received, publication_s=t,
                         phase=key[0], scale=key[1], executed_reference_m_s=d["executed_linear_m_s"])
            break
        if found is None:
            raise ValueError("Changed governor command not found in saved drive publications")
        detail.append(found)
        if j in (0, 2, 3, 5):
            result[{0: "braking", 2: "holding", 3: "recovery", 5: "after_recovery"}[j]] = found["publication_s"]
    return result, detail


def phase_at(windows, t):
    for i, (name, a, b) in enumerate(windows):
        if a <= t < b or (i == len(windows)-1 and t == b):
            return name
    return None


def parse_context(data):
    """Read original IMU, body, caster and component contact samples, without filtering."""
    config = json.loads((data["logger"] / "resolved_config.json").read_text())
    gravity = config["policy_v2"]["imu_includes_gravity"]
    imu, body, casters = [], {}, {}
    contacts = {c: [] for c in COMPONENTS}
    for line in (data["logger"] / "samples.jsonl").open():
        p = json.loads(line)
        topic, d = p["topic"], p["data"]
        if "header" not in d:
            continue
        stamp = d["header"]["stamp"]
        t = stamp["sec"] + stamp["nanosec"] * 1e-9
        if not data["start"] - .06 <= t <= data["end"] + .06:
            continue
        if topic == "/imu/data":
            roll, pitch, _ = quaternion_rpy(tuple(d["orientation"][k] for k in ("x", "y", "z", "w")))
            imu.append((t, vertical_acceleration(tuple(d["linear_acceleration"][k] for k in ("x", "y", "z")), roll, pitch, gravity)))
        elif topic == "/ground_truth/odom":
            tw = d["twist"]["twist"]
            roll, pitch, _ = quaternion_rpy(tuple(d["pose"]["pose"]["orientation"][k] for k in ("x", "y", "z", "w")))
            body[t] = dict(v=tw["linear"]["x"], vz=tw["linear"]["z"],
                           roll=roll, pitch=pitch, wx=tw["angular"]["x"], wy=tw["angular"]["y"])
        elif topic == "/joint_states":
            v, pos = dict(zip(d["name"], d["velocity"])), dict(zip(d["name"], d["position"]))
            casters[t] = {side: dict(rolling_rad_s=v[f"caster_{side}_wheel_joint"],
                                    swivel_rad=pos[f"caster_{side}_swivel_joint"],
                                    swivel_rad_s=v[f"caster_{side}_swivel_joint"])
                          for side in ("left", "right")}
        elif topic.startswith("/nino/contact_lab/") and topic.rsplit("/", 1)[-1] in contacts:
            value = dict(obstacle_manifold=False, obstacle_loaded=False, floor_loaded=False,
                         obstacle_force_norm_N=0., floor_force_norm_N=0., max_depth_m=None)
            for c in d["contacts"]:
                names = [c[k]["name"] for k in ("collision1", "collision2")]
                obstacle = any("cable_bumps" in n for n in names)
                floor = any("terrain_collision" in n for n in names)
                if obstacle:
                    value["obstacle_manifold"] = True
                for depth, wrench in zip(c["depths"], c["wrenches"]):
                    force = math.sqrt(sum(wrench["body_1_wrench"]["force"][k]**2 for k in ("x", "y", "z")))
                    for kind, relevant in (("obstacle", obstacle), ("floor", floor)):
                        if relevant:
                            value[kind + "_force_norm_N"] += force
                            value[kind + "_loaded"] |= depth > 0 and force > 1e-6
                    if obstacle:
                        value["max_depth_m"] = max(depth, value["max_depth_m"]) if value["max_depth_m"] is not None else depth
            contacts[topic.rsplit("/", 1)[-1]].append((t, value))
    events = [json.loads(line) for line in (data["logger"] / "contact_events.jsonl").open()]
    return dict(imu=sorted(imu, key=lambda row:row[0]), body=sorted(body.items()), casters=sorted(casters.items()),
                contacts={k: sorted(v,key=lambda row:row[0]) for k, v in contacts.items()}, events=events)


def response(data, context, a, b):
    ds = [v for t, v in data["drive"] if a <= t < b]
    gs = [v for t, v in context["body"] if a <= t < b]
    numeric = ("executed_linear_m_s", "requested_linear_m_s", "executed_yaw_rad_s",
               "left_target_rad_s", "right_target_rad_s", "left_actual_rad_s", "right_actual_rad_s",
               "left_pi_nm", "right_pi_nm", "left_requested_effort_nm", "right_requested_effort_nm",
               "left_applied_nm", "right_applied_nm", "left_limited", "right_limited",
               "cmd_fresh", "have_wheel_state", "control_raw_dt_max_s", "control_dt_over_4ms",
               "control_future_joint_updates", "control_joint_age_max_s")
    out = {key: stats([d[key] for d in ds]) for key in numeric}
    for side in ("left", "right"):
        j = 1 if side == "left" else 2
        joint = data["joints"][(data["joints"][:,0] >= a) & (data["joints"][:,0] < b),j]
        out[side + "_original_joint_rad_s"] = stats(joint)
        out[side + "_joint_samples_over_12_rad_s"] = int(np.sum(abs(joint) > 12.))
        out[side + "_tracking_error_rad_s"] = stats([d[side+"_target_rad_s"] - d[side+"_actual_rad_s"] for d in ds])
        out[side + "_sampled_torque_cap_hits"] = sum(abs(d[side+"_applied_nm"]) >= 4.-1e-9 for d in ds)
        out[side + "_sampled_requested_over_torque_cap"] = sum(abs(d[side+"_requested_effort_nm"]) > 4.+1e-9 for d in ds)
        out[side + "_limited_samples_below_torque_and_speed_caps"] = sum(
            d[side+"_limited"] > 0 and abs(d[side+"_requested_effort_nm"]) < 4.-1e-9
            and abs(d[side+"_actual_rad_s"]) < 12.-1e-9 for d in ds)
    out["body"] = {k: stats([v[k] for v in gs]) for k in ("v", "vz", "roll", "pitch", "wx", "wy")}
    out["vertical"] = signal_stats(context["imu"], a, b)
    out["contacts"] = {}
    for component, rows in context["contacts"].items():
        vals = [v for t, v in rows if a <= t < b]
        out["contacts"][component] = dict(n=len(vals),
            obstacle_loaded_samples=sum(v["obstacle_loaded"] for v in vals),
            floor_loaded_fraction=float(np.mean([v["floor_loaded"] for v in vals])) if vals else None,
            obstacle_force_max_N=max((v["obstacle_force_norm_N"] for v in vals), default=None),
            floor_force_max_N=max((v["floor_force_norm_N"] for v in vals), default=None))
    out["obstacle_events"] = [e for e in context["events"] if e["named_positive_obstacle"] and a <= e["time_s"] < b]
    return out


def equal(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)


def accounting(signal, windows, start, end):
    pieces = {name: integrate(signal, a, b) for name, a, b in windows}
    whole = integrate(signal, start, end)
    if all(p["available"] for p in pieces.values()) and whole["available"]:
        if not equal(sum(p["slip_square_integral_s"] for p in pieces.values()), whole["slip_square_integral_s"]):
            raise ValueError("Phase quadrature is not additive")
        if not equal(sum(p["distance_m"] for p in pieces.values()), whole["distance_m"]):
            raise ValueError("Phase distance is not additive")
    return pieces, whole


def flat_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def context_rows(data, signal, context, windows):
    """Export EVERY original GT support sample in route; do not select/remove spikes."""
    output = []
    for i, t in enumerate(signal["time"]):
        if not data["start"] <= t <= data["end"]:
            continue
        row = dict(attempt=data["attempt"], seed=data["seed"], repeat=data["repeat"], profile=data["profile"],
                   time_s=float(t), after_first_contact_s=float(t-data["first"]), phase=phase_at(windows, t),
                   slip_square=float(signal["q"][i]) if math.isfinite(signal["q"][i]) else None,
                   body_speed_m_s=float(data["ground"][i, 1]), body_yaw_rad_s=float(data["ground"][i, 2]),
                   left_joint_rad_s=float(signal["wheel_rad_s"][i, 0]), right_joint_rad_s=float(signal["wheel_rad_s"][i, 1]),
                   joint_support_left_s=float(signal["joint_support_stamps"][i, 0]),
                   joint_support_right_s=float(signal["joint_support_stamps"][i, 1]))
        for j, side in enumerate(("left", "right")):
            body_at_wheel = data["ground"][i, 1] + (-1 if side == "left" else 1) * TRACK/2 * data["ground"][i, 2]
            row[side+"_wheel_minus_body_m_s"] = float(RADIUS*signal["wheel_rad_s"][i, j] - body_at_wheel)
        drive = asof(data["drive"], t, .050001)
        row["drive_age_s"] = float(t-drive[0]) if drive else None
        if drive:
            row.update({"drive_" + k: v for k, v in drive[1].items() if k != "sim_time_s"})
        body = asof(context["body"], t, 0.)
        if body:
            row.update({"body_"+k: v for k,v in body[1].items()})
        caster = asof(context["casters"], t, .010001)
        row["caster_age_s"] = float(t-caster[0]) if caster else None
        if caster:
            row.update({"caster_"+side+"_"+k: v for side, values in caster[1].items() for k,v in values.items()})
        for component, samples in context["contacts"].items():
            c = asof(samples, t, .020001)
            row[component+"_age_s"] = float(t-c[0]) if c else None
            if c:
                row.update({component+"_"+k: v for k, v in c[1].items()})
        output.append(row)
    return output


def contact_summary(context, first, start, end):
    out = {}
    for component, samples in context["contacts"].items():
        loaded = [(t,v) for t,v in samples if start <= t <= end and v["obstacle_loaded"]]
        out[component] = dict(
            first_loaded_offset_s=loaded[0][0]-first if loaded else None,
            last_loaded_offset_s=loaded[-1][0]-first if loaded else None,
            loaded_samples=len(loaded),
            maximum_sample_force_N=max((v["obstacle_force_norm_N"] for t,v in samples if start <= t <= end),default=None))
    return out


def plots(datasets, contexts, signals, episodes, pairs, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"full": "#404040", "reactive": "#087da0"}
    for pair in pairs:
        fig, axes = plt.subplots(6, 1, figsize=(13, 15), sharex=True, constrained_layout=True)
        gov = next(e for e in episodes if e["attempt"] == pair["attempts"]["reactive"])
        for profile in ("full", "reactive"):
            i = pair["attempts"][profile]
            d, ctx, s = datasets[i], contexts[i], signals[i]
            tc, color = d["first"], colors[profile]
            axes[0].plot(s["time"]-tc, s["q"], color=color, lw=.9, label=profile)
            axes[1].plot(d["ground"][:,0]-tc, d["ground"][:,1], color=color, label=profile+" body", lw=1.1)
            for side,j,ls in (("left",0,"--"),("right",1,":")):
                axes[1].plot(s["time"]-tc, RADIUS*s["wheel_rad_s"][:,j], color=color, ls=ls, lw=.7, label=profile+" "+side+" wheel")
                t = [t-tc for t,v in d["drive"]]
                axes[2].plot(t, [v[side+"_target_rad_s"] for _,v in d["drive"]], color=color, ls=":", lw=.65, label=profile+" "+side+" target")
                axes[2].plot(t, [v[side+"_actual_rad_s"] for _,v in d["drive"]], color=color,
                             ls="-" if side=="left" else "--", lw=.8, alpha=.8, label=profile+" "+side+" actual")
                axes[3].plot(t, [v[side+"_applied_nm"] for _,v in d["drive"]], color=color, ls=ls, lw=.9, label=profile+" "+side+" applied command")
                axes[3].plot(t, [v[side+"_requested_effort_nm"] for _,v in d["drive"]], color=color, ls=ls, lw=.45, alpha=.45)
                limited = [(t-tc,v[side+"_applied_nm"]) for t,v in d["drive"] if v[side+"_limited"] > 0]
                if limited:
                    axes[3].scatter(*zip(*limited), s=9, marker="x", color=color, alpha=.7)
            for j,component in enumerate(COMPONENTS):
                loaded = [t-tc for t,v in ctx["contacts"][component] if v["obstacle_loaded"]]
                floor = [t-tc for t,v in ctx["contacts"][component] if v["floor_loaded"]]
                offset = .18 if profile == "reactive" else -.18
                axes[4].scatter(floor, [j+offset]*len(floor), color=color, s=3, alpha=.2)
                axes[4].scatter(loaded, [j+offset]*len(loaded), color=color, s=10, marker="|")
                begin = [e["time_s"]-tc for e in ctx["events"] if e["component"]==component and e["named_positive_obstacle"] and e["event"]=="begin"]
                axes[4].scatter(begin, [j+offset]*len(begin), color=color, s=25, marker="v")
            axes[5].plot([t-tc for t,v in ctx["imu"]], [v for t,v in ctx["imu"]], color=color, lw=.8, label=profile)
        for ax in axes:
            ax.axvline(0, color="black", lw=.7, ls=":")
            for phase,a,b in gov["windows"]:
                if phase in ("braking","holding","recovery"):
                    ax.axvspan(a-gov["first_contact_s"], b-gov["first_contact_s"], alpha=.08,
                               color={"braking":"red","holding":"orange","recovery":"green"}[phase])
            ax.grid(alpha=.2)
            ax.set_xlim(-.35,2.35)
        axes[0].set_ylabel("Mean squared slip ratio")
        axes[1].set_ylabel("Body / wheel speed (m/s)")
        axes[2].set_ylabel("Wheel target / actual (rad/s)")
        axes[3].set_ylabel("Torque commands (Nm)")
        axes[4].set_yticks(range(4), COMPONENTS, fontsize=8)
        axes[4].set_ylabel("Floor dots / cable bars\nbegin triangles")
        axes[5].set_ylabel("Vertical IMU (m/s²)")
        axes[5].set_xlabel("Seconds from each run's own first recorded cable manifold")
        for j in (0,1,2,3,5):
            axes[j].legend(fontsize=7, ncol=3, loc="upper right")
        fig.suptitle(f"Seed {pair['seed']}, repeat {pair['repeat']} — saved attempts {pair['attempts']}\n"
                     "Original samples, no spike trimming. Shading: drive-publication braking / hold / recovery.\n"
                     "Torque: thin requested, bold applied command, x = limited publication. PI shading is event translation.", fontsize=11)
        fig.savefig(output/f"pair_{pair['seed']}_r{pair['repeat']}.png", dpi=145)
        plt.close(fig)
    vals = np.array([[p["phases"][n]["delta"]["slip_square_integral_s"]*1000 for n in PHASES] for p in pairs])
    fig,ax = plt.subplots(figsize=(12,6), constrained_layout=True)
    cap = float(np.max(abs(vals)))
    im = ax.imshow(vals, cmap="RdBu_r", vmin=-cap, vmax=cap, aspect="auto")
    for i in range(8):
        for j in range(7):
            ax.text(j,i,f"{vals[i,j]:+.3f}",ha="center",va="center",fontsize=8,
                    color="white" if abs(vals[i,j])>.65*cap else "black")
    ax.set_xticks(range(7),PHASES,rotation=25,ha="right")
    ax.set_yticks(range(8),[f"{p['seed']} r{p['repeat']}" for p in pairs])
    ax.set_title("Governor minus paired PI slip² integral by phase (×10⁻³ s)\nRed: governor higher; blue: lower. Every phase retained; integral is additive.")
    fig.colorbar(im,ax=ax,label="Δ integral (×10⁻³ s)")
    fig.savefig(output/"all_eight_pair_phase_deltas.png",dpi=155)
    plt.close(fig)


def markdown(report, output):
    lines = ["# Offline phase audit — all eight frozen survey pairs", "",
             "Original sampling, scores, spikes and failures retained. No simulation or tuning.", "",
             "PI windows use the paired governor's offsets from each run's own first contact; they are not identical physical exposures.", "",
             "## Additive phase differences", "",
             "Values below are governor minus PI slip² integral, ×10⁻³ s. Rates/RMS are in the CSV/JSON, not added together.", "",
             "| Seed / repeat | Startup | Precontact | Contact before brake | Braking | Holding | Recovery | After recovery | Route |", 
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for p in report["pairs"]:
        vals = [p["phases"][n]["delta"]["slip_square_integral_s"] for n in PHASES]+[p["whole_integral_delta_s"]]
        lines.append(f"| {p['seed']} / {p['repeat']} | "+" | ".join(f"{v*1000:+.4f}" if v is not None else "unavailable" for v in vals)+" |")
    lines += ["", "![All pairs](all_eight_pair_phase_deltas.png)", "", "## Full response plots", ""]
    for p in report["pairs"]:
        lines.append(f"- [{p['seed']} / repeat {p['repeat']}](pair_{p['seed']}_r{p['repeat']}.png)")
    lines += ["", "## Integrity", "", f"Attempts: {report['attempts']}; pairs: {len(report['pairs'])}; failures retained: {report['failures']}.",
              f"Native, whole-route, crossing, fixed post-contact and complete-sequence metrics replayed: {report['all_original_metrics_replayed']}.",
              "", "Every original GT sample has an exported context row; all original IMU/contact samples and manifold events remain available. No outlier rejection.",
              "", "Torque fields are commands. 50 Hz limiter publications do not expose every 500 Hz motor-loop update. Missing/stale contact support stays unavailable.",
              "", "Interpretation and decision: [Vietnamese report](../GOVERNOR_SURVEY_PHASE_AUDIT_2026-10-20.md)."]
    (output/"REPORT.md").write_text("\n".join(lines)+"\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, default=ROOT/"rl_runs/governor_descriptive_survey_2026-10-18")
    p.add_argument("--frozen", type=Path, default=ROOT/"docs/governor_descriptive_survey_2026-10-18/analysis")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output/"protocol_before_calculation.json", PROTOCOL)
    old_manifest = json.loads((args.frozen/"input_sha256.json").read_text())
    if any(not Path(k).is_file() or sha256(Path(k)) != v for k, v in old_manifest.items()):
        raise ValueError("Frozen input provenance mismatch")
    manifest = dict(old_manifest)
    for path in (Path(__file__), args.frozen/"report.json", args.frozen/"input_sha256.json",
                 Path(__file__).with_name("audit_governor_phase_slip.py"),
                 Path(__file__).with_name("audit_gt_timestamp_slip.py"),
                 Path(__file__).with_name("prepare_governor_contact_sequence.py"),
                 ROOT/"src/nino_rl/nino_rl/slip_reporting.py", ROOT/"src/nino_control/nino_control/governor_core.py"):
        manifest[str(path.resolve())] = sha256(path)
    slots = json.loads((args.run/"ledger.json").read_text())["slots"]
    original = json.loads((args.frozen/"report.json").read_text())
    if len(slots) != 16 or len({(s["seed"], s["repeat"], s["profile"]) for s in slots}) != 16:
        raise ValueError("Expected every one of the frozen 16 distinct attempts")
    datasets, contexts, signals, episodes, all_events = {}, {}, {}, [], []
    for slot in slots:
        r = slot["result"]
        existing = r["quality"]["existing_reports"]
        d = load(Path(r["case"]), dict(r, seed=slot["seed"], profile=slot["profile"]))
        d.update(attempt=slot["attempt"], repeat=slot["repeat"], first=existing["first_contact_s"])
        path = next(d["evaluation"].glob("episode-*/drive_trace.csv"))
        d["drive"] = sorted({float(row["sim_time_s"]): {k: float(v) for k, v in row.items() if k != "seed"}
                             for row in read_csv(path)}.items())
        for path in (path, d["logger"]/"samples.jsonl", d["logger"]/"contact_events.jsonl", d["logger"]/"resolved_config.json",
                     d["evaluation"]/"episodes.csv", next(d["evaluation"].glob("episode-*/control_trace.csv"))):
            manifest[str(path.resolve())] = sha256(path)
        key = slot["attempt"]
        datasets[key], contexts[key], signals[key] = d, parse_context(d), gt_timestamp_series(d)
        print(f"Read saved attempt {key:02d}/16", flush=True)
    phase_csv = []
    for slot in slots:
        i = slot["attempt"]
        d, ctx, signal = datasets[i], contexts[i], signals[i]
        gov = next(s for s in slots if s["seed"] == slot["seed"] and s["repeat"] == slot["repeat"] and s["profile"] == "reactive")
        g = datasets[gov["attempt"]]
        transitions, detail = executed_transitions(g["controls"], g["drive"])
        shift = d["first"] - g["first"]
        transitions = {k: v+shift for k, v in transitions.items()}
        windows = partition(d["start"], d["first"], d["end"], transitions)
        pieces, whole = accounting(signal, windows, d["start"], d["end"])
        frozen = slot["result"]["quality"]["existing_reports"]
        post = integrate(signal, d["first"]+.05, d["first"]+3.)
        crossing = integrate(signal, frozen["gt_native"]["crossing"]["start_s"], frozen["gt_native"]["crossing"]["end_s"])
        seq_bounds = frozen["sequence"]["windows"]
        sequence = integrate(signal, seq_bounds["contact_start_s"], seq_bounds["contact_end_s"])
        native = replay_native_trace(d["controls"])
        orig = next(e for e in original["episodes"] if e["attempt"] == i)
        checks = dict(whole=equal(whole["rms"], orig["metrics"]["whole_slip"]),
                      post=equal(post["slip_square_per_m"], orig["metrics"]["post_slip"]),
                      crossing=equal(crossing["slip_square_per_m"], orig["metrics"]["crossing_slip"]),
                      sequence=equal(sequence["slip_square_per_m"], orig["metrics"]["sequence_slip"]),
                      native=native["available"] and equal(native["rms"], orig["metrics"]["native_slip"]))
        post_vertical = signal_stats(ctx["imu"], d["first"]+.05, d["first"]+3.)
        checks.update(post_vertical_rms=equal(post_vertical["rms"],orig["metrics"]["post_vibration"]),
                      post_vertical_peak=equal(post_vertical["peak"],orig["metrics"]["post_peak"]))
        if not all(checks.values()):
            raise ValueError(f"Frozen metric replay failed attempt {i}: {checks}")
        phases = {}
        for name, a, b in windows:
            measures = response(d, ctx, a, b)
            phases[name] = dict(slip=pieces[name], response=measures)
            entry = dict(attempt=i, seed=d["seed"], repeat=d["repeat"], profile=d["profile"], phase=name, **pieces[name])
            for k in ("executed_linear_m_s", "left_target_rad_s", "right_target_rad_s", "left_actual_rad_s", "right_actual_rad_s",
                      "left_tracking_error_rad_s", "right_tracking_error_rad_s", "left_pi_nm", "right_pi_nm", "left_applied_nm", "right_applied_nm", "left_limited", "right_limited"):
                entry.update({k+"_"+s: measures[k][s] for s in ("mean", "min", "max", "rms")})
            entry.update(body_mean_m_s=measures["body"]["v"]["mean"], body_min_m_s=measures["body"]["v"]["min"],
                         body_max_m_s=measures["body"]["v"]["max"], vertical_rms=measures["vertical"]["rms"], vertical_peak=measures["vertical"]["peak"])
            phase_csv.append(entry)
        rows = context_rows(d, signal, ctx, windows)
        flat_csv(args.output/f"attempt_{i:02d}_all_gt_context.csv", rows)
        flat_csv(args.output/f"attempt_{i:02d}_all_imu.csv", [dict(time_s=t,
                 after_first_contact_s=t-d["first"], phase=phase_at(windows,t), vertical_m_s2=v)
                 for t,v in ctx["imu"] if d["start"] <= t <= d["end"]])
        flat_csv(args.output/f"attempt_{i:02d}_all_contact_samples.csv", [dict(time_s=t, component=component,
                 after_first_contact_s=t-d["first"], phase=phase_at(windows,t), **v)
                 for component, samples in ctx["contacts"].items() for t,v in samples if d["start"] <= t <= d["end"]])
        events = [dict(attempt=i, seed=d["seed"], repeat=d["repeat"], profile=d["profile"],
                       phase=phase_at(windows, e["time_s"]), after_first_contact_s=e["time_s"]-d["first"], **e)
                  for e in ctx["events"] if d["start"] <= e["time_s"] <= d["end"]]
        all_events.extend(events)
        top = sorted((row for row in rows if row["slip_square"] is not None), key=lambda row: row["slip_square"], reverse=True)[:5]
        episodes.append(dict(attempt=i, seed=d["seed"], repeat=d["repeat"], profile=d["profile"],
                             physical_success=slot["physical_success"], termination=slot["termination"], stop_pass=slot["stop_pass"],
                             first_contact_s=d["first"], windows=windows, transitions=detail if d["profile"] == "reactive" else [],
                             paired_governor_attempt=gov["attempt"], paired_window_shift_s=shift,
                             phases=phases, whole=whole, post=post, post_vertical=post_vertical, crossing=crossing, sequence=sequence, native=native,
                             original_metric_replay=checks, sampling=d["sampling"],
                             top5_slip_samples_context=top,
                             contact_sequence=contact_summary(ctx,d["first"],d["start"],d["end"]),
                             approach=orig["approach"], native_outcome=orig["native_outcome"]))
    pairs, pair_csv = [], []
    for seed in sorted({s["seed"] for s in slots}):
        for repeat in range(1, 5):
            arms = {e["profile"]: e for e in episodes if e["seed"] == seed and e["repeat"] == repeat}
            if set(arms) != {"full", "reactive"}:
                raise ValueError("Incomplete pair; do not drop failures")
            phases = {}
            for name in PHASES:
                p0, g0 = (arms[p]["phases"][name]["slip"] for p in ("full", "reactive"))
                delta = {k: g0[k]-p0[k] if g0[k] is not None and p0[k] is not None else None
                         for k in ("slip_square_integral_s", "rms", "distance_m", "slip_square_per_m")}
                phases[name] = dict(full=p0, reactive=g0, delta=delta)
                pair_csv.append(dict(seed=seed, repeat=repeat, phase=name,
                                     full_integral_s=p0["slip_square_integral_s"], reactive_integral_s=g0["slip_square_integral_s"],
                                     **{"delta_"+k: v for k, v in delta.items()}))
            route_delta = arms["reactive"]["whole"]["slip_square_integral_s"]-arms["full"]["whole"]["slip_square_integral_s"]
            if all(x["delta"]["slip_square_integral_s"] is not None for x in phases.values()) and not equal(
                    sum(x["delta"]["slip_square_integral_s"] for x in phases.values()), route_delta):
                raise ValueError("Pair delta does not conserve original route integral")
            pairs.append(dict(seed=seed, repeat=repeat, attempts={p: e["attempt"] for p,e in arms.items()},
                              phases=phases, whole_integral_delta_s=route_delta,
                              post_delta=arms["reactive"]["post"]["slip_square_per_m"]-arms["full"]["post"]["slip_square_per_m"]))
    flat_csv(args.output/"phase_metrics.csv", phase_csv)
    flat_csv(args.output/"pair_deltas.csv", pair_csv)
    write(args.output/"all_contact_events.json", all_events)
    report = dict(protocol=PROTOCOL, attempts=len(episodes), pairs=pairs, episodes=episodes,
                  failures=sum(not e["physical_success"] for e in episodes),
                  all_original_metrics_replayed=all(all(e["original_metric_replay"].values()) for e in episodes),
                  original_survey_estimates=original["estimates"])
    write(args.output/"report.json", report)
    plots(datasets, contexts, signals, episodes, pairs, args.output)
    markdown(report, args.output)
    changed = [p for p,h in manifest.items() if sha256(Path(p)) != h]
    write(args.output/"provenance.json", dict(inputs_sha256=manifest, frozen_manifest_verified=True,
                                             changed_during_audit=changed, inputs_unchanged=not changed))
    if changed:
        raise ValueError("Input changed during audit")
    print(json.dumps(dict(attempts=16, pairs=8, original_metrics_replayed=report["all_original_metrics_replayed"],
                          inputs_unchanged=True, output=str(args.output))))


if __name__ == "__main__":
    main()
