#!/usr/bin/env python3
"""Frozen four-run PI audit. No ROS, simulation, rescore or controller changes.

Phase sweeps are diagnostics of saved samples, never reconstructed acquisition
at unseen IMU timestamps. Sampled contact forces are not contact impulses.
"""
import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src/nino_control")]
from nino_control.governor_core import quaternion_rpy, vertical_acceleration


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asof(series, t, max_age=.040001):
    i = bisect.bisect_right([x[0] for x in series], t + 1e-9) - 1
    if i < 0 or t - series[i][0] > max_age:
        return None
    return dict(time_s=series[i][0], age_s=max(0., t-series[i][0]), value=series[i][1])


def force_summary(contact):
    points = []
    for depth, wrench in zip(contact["depths"], contact["wrenches"]):
        f = wrench["body_1_wrench"]["force"]
        norm = math.sqrt(sum(f[k]**2 for k in ("x", "y", "z")))
        points.append(dict(depth_m=depth, norm_N=norm, fz_N=f["z"]))
    loaded = [p for p in points if p["depth_m"] > 0 and p["norm_N"] > 1e-6]
    return dict(loaded=bool(loaded), loaded_force_norm_sum_N=sum(p["norm_N"] for p in loaded),
                max_depth_m=max((p["depth_m"] for p in points), default=None), points=points)


def stats(values):
    a = np.asarray(values, dtype=float)
    if not len(a):
        return dict(available=False)
    return dict(available=True, n=len(a), rms=float(np.sqrt(np.mean(a*a))),
                peak_abs=float(np.max(abs(a))), minimum=float(np.min(a)), maximum=float(np.max(a)))


def phase_sensitivity(imu, start, end):
    a = np.asarray([(t, v["vertical_m_s2"]) for t, v in imu])
    t, v = a[:, 0], a[:, 1]
    chosen = (t >= start) & (t <= end)
    original = stats(v[chosen])
    power = np.sort(v[chosen]**2)
    original["largest_two_sample_square_fraction"] = float(power[-2:].sum()/power.sum()) if power.sum() else 0.
    shifted = []
    # Keep support within original observations. Interpolation is diagnostic only.
    for offset in np.arange(10)*.002:
        grid = start + offset + np.arange(math.floor((end-start-offset)/.02)+1)*.02
        if grid[0] < t[0] or grid[-1] > t[-1]:
            raise ValueError("Phase grid would extrapolate")
        idx = np.searchsorted(t, grid, side="right")
        idx = np.clip(idx, 1, len(t)-1)
        if np.any(t[idx]-t[idx-1] > .025):
            raise ValueError("Missing IMU support in phase diagnostic")
        shifted.append(dict(offset_s=float(offset), **stats(np.interp(grid, t, v))))
    # All five residue classes of existing 50 Hz samples; no interpolated values.
    raw = a[chosen]
    decimated = [dict(residue=i, first_relative_s=float(raw[i, 0]-start),
                      **stats(raw[i::5, 1])) for i in range(5)]
    return dict(original_50Hz_samples=original, linear_50Hz_grid_offsets=shifted,
                decimated_10Hz_residues=decimated,
                acquisition_phase_identifiable=False,
                limitation="Only saved 50Hz values exist. Shifting interpolation or decimating cannot reproduce a different 50Hz sensor acquisition phase or recover unsampled peaks.")


def load_row(row):
    case = Path(row["case"])
    logger = next(case.glob("contact/*/metadata.json")).parent
    evaluation = next(case.glob("evaluation/*/summary.json")).parent
    raw = logger / "samples.jsonl"
    config = json.loads((logger/"resolved_config.json").read_text())
    tc = row["first_contact_s"]
    start = row["reset_gate"]["released_sim_s"]
    end = float(list(csv.DictReader(next(evaluation.glob("episode-*/control_trace.csv")).open()))[-1]["sim_time_s"])
    imu, gt, joints, contacts, contact_empty = {}, {}, {}, [], []
    receipt_ages, duplicates = [], dict(imu=0, gt=0, joints=0)
    for line in raw.open():
        packet = json.loads(line)
        d, topic = packet["data"], packet["topic"]
        if "header" not in d:
            continue
        stamp = d["header"]["stamp"]
        t = stamp["sec"] + stamp["nanosec"]*1e-9
        if not start-.06 <= t <= end+.06:
            continue
        if topic == "/imu/data":
            r, p, _ = quaternion_rpy(tuple(d["orientation"][k] for k in ("x", "y", "z", "w")))
            acc = tuple(d["linear_acceleration"][k] for k in ("x", "y", "z"))
            duplicates["imu"] += int(t in imu)
            imu[t] = dict(vertical_m_s2=vertical_acceleration(acc, r, p, config["policy_v2"]["imu_includes_gravity"]),
                          roll_rad=r, pitch_rad=p, acceleration=list(acc))
            receipt_ages.append(packet["receipt_time_s"]-t)
        elif topic == "/ground_truth/odom":
            pose, tw = d["pose"]["pose"], d["twist"]["twist"]
            r, p, y = quaternion_rpy(tuple(pose["orientation"][k] for k in ("x", "y", "z", "w")))
            duplicates["gt"] += int(t in gt)
            gt[t] = dict(**{k:pose["position"][k] for k in ("x", "y", "z")},
                         vx=tw["linear"]["x"], vz=tw["linear"]["z"],
                         wx=tw["angular"]["x"], wy=tw["angular"]["y"], wz=tw["angular"]["z"],
                         roll=r, pitch=p, yaw=y)
        elif topic == "/joint_states":
            duplicates["joints"] += int(t in joints)
            joints[t] = dict(position=dict(zip(d["name"], d["position"])), velocity=dict(zip(d["name"], d["velocity"])))
        elif topic.startswith("/nino/contact_lab/"):
            component = topic.rsplit("/", 1)[-1]
            contact_empty.append((t, component, len(d["contacts"])))
            for contact in d["contacts"]:
                names = [contact[k]["name"] for k in ("collision1", "collision2")]
                kind = "cable" if any("cable_bumps" in n for n in names) else "floor" if any("terrain_collision" in n for n in names) else "other"
                contacts.append(dict(time_s=t, relative_s=t-tc, component=component, kind=kind,
                                     collisions=names, **force_summary(contact)))
    imu, gt, joints = sorted(imu.items()), sorted(gt.items()), sorted(joints.items())
    contacts.sort(key=lambda x:x["time_s"])
    drive_path = next(evaluation.glob("episode-*/drive_trace.csv"))
    drive = [(float(c["sim_time_s"]), {k:float(v) for k,v in c.items() if k != "seed"}) for c in csv.DictReader(drive_path.open())]
    events = [json.loads(l) for l in (logger/"contact_events.jsonl").open()]
    events = [dict(e, relative_s=e["time_s"]-tc) for e in events if tc-.5 <= e["time_s"] <= tc+3.]
    files = [raw, logger/"contact_events.jsonl", logger/"metadata.json", logger/"resolved_config.json",
             logger/"robot_description.urdf", drive_path, evaluation/"episodes.csv", evaluation/"summary.json",
             next(evaluation.glob("episode-*/control_trace.csv"))]
    return dict(row=row, tc=tc, start=start, end=end, imu=imu, gt=gt, joints=joints, drive=drive,
                contacts=contacts, events=events, contact_messages=contact_empty, files=files,
                duplicate_stamps_kept_last=duplicates, receipt_ages=stats(receipt_ages))


def snapshot(data, t):
    return dict(time_s=t, relative_s=t-data["tc"], ground=asof(data["gt"], t, .025),
                joints=asof(data["joints"], t, .010001), drive=asof(data["drive"], t, .030001))


def peak_context(data, a, b):
    t, value = max(((t,v) for t,v in data["imu"] if a <= t <= b), key=lambda x:abs(x[1]["vertical_m_s2"]))
    local = [c for c in data["contacts"] if t-.06 <= c["time_s"] <= t+.06]
    strongest = {}
    for c in local:
        key = c["component"]+"/"+c["kind"]
        if key not in strongest or c["loaded_force_norm_sum_N"] > strongest[key]["loaded_force_norm_sum_N"]:
            strongest[key] = c
    return dict(peak=dict(time_s=t, relative_s=t-data["tc"], **value),
                physical_at_minus20ms=snapshot(data,t-.02), physical_at_peak=snapshot(data,t),
                physical_at_plus20ms=snapshot(data,t+.02), physical_at_plus40ms=snapshot(data,t+.04),
                strongest_contacts_within60ms=[dict(c, offset_from_peak_s=c["time_s"]-t) for c in strongest.values()],
                contacts_within60ms=local,
                qualification="Temporal association only. Plus-time states and contacts are future relative to peak; not causal inputs. Force values are sampled wrench norms, not impulse.")


def analyze(data):
    tc = data["tc"]
    first_manifold, first_loaded = {}, {}
    for e in data["events"]:
        if e["event"] == "begin" and e["named_positive_obstacle"] and e["time_s"] >= tc-1e-9:
            first_manifold.setdefault(e["component"], e["relative_s"])
    for c in data["contacts"]:
        if c["kind"] == "cable" and c["loaded"] and c["time_s"] >= tc-1e-9:
            first_loaded.setdefault(c["component"], dict(relative_s=c["relative_s"], force_N=c["loaded_force_norm_sum_N"]))
    phases = {}
    for name,a,b in (("early_clean_floor",data["start"]+1.,data["start"]+1.5),
                     ("approach",tc-.3,tc-.05), ("first_caster_phase",tc,tc+.2),
                     ("driven_wheel_phase",tc+.5,tc+.9)):
        states=[(t,v) for t,v in data["joints"] if a <= t <= b]
        phases[name]=dict(window_s=[a,b],casters={})
        for side in ("left", "right"):
            prefix="caster_"+side
            msgs=[t for t,c,n in data["contact_messages"] if c==prefix+"_wheel" and a<=t<=b]
            loads={c["time_s"] for c in data["contacts"] if c["component"]==prefix+"_wheel" and c["kind"]=="floor" and c["loaded"] and a<=c["time_s"]<=b}
            phases[name]["casters"][side]=dict(rolling_rad_s=stats([v["velocity"][prefix+"_wheel_joint"] for t,v in states]),
                swivel_rad=stats([v["position"][prefix+"_swivel_joint"] for t,v in states]),
                floor_loaded_sample_fraction=len(loads)/len(set(msgs)) if msgs else None,
                floor_messages=len(msgs))
    landmarks={"gate_release":snapshot(data,data["start"]), "approach_minus300ms":snapshot(data,tc-.3),
               "approach_minus50ms":snapshot(data,tc-.05), "first_manifold":snapshot(data,tc)}
    for x in (1.,2.4,2.7):
        t=next(t for t,g in data["gt"] if t>=data["start"] and g["x"]>=x)
        landmarks[f"first_GT_x_ge_{x:g}m"]=snapshot(data,t)
    times=np.array([t for t,_ in data["imu"]])
    future=times[times>=tc]
    gaps=np.diff(times)
    # Fixed same-phase window, reported for every run, not selected per peak.
    wheel_window={}
    for side in ("left", "right"):
        samples=[(t-tc,v["velocity"][side+"_wheel_joint"]) for t,v in data["joints"] if tc+.8<=t<=tc+1.]
        lowest=min(samples,key=lambda x:x[1])
        wheel_window[side]=dict(minimum_rad_s=lowest[1],minimum_relative_s=lowest[0],
            first_negative=next((dict(relative_s=t,rad_s=v) for t,v in samples if v<0),None))
    return dict(seed=data["row"]["seed"],repeat=data["row"]["repeat"],case=data["row"]["case"],
        native_unchanged={k:data["row"][k] for k in ("physical_pass","reporting_pass","physical_rmse_m","time_s","whole_vertical_rms","whole_vertical_peak","native_slip_rms")},
        first_contact_s=tc,first_manifold_by_component_s=first_manifold,first_loaded_cable_by_component=first_loaded,
        imu_cadence=dict(median_gap_s=float(np.median(gaps)),min_gap_s=float(min(gaps)),max_gap_s=float(max(gaps)),
            next_sample_after_first_contact_s=float(future[0]-tc),duplicates=data["duplicate_stamps_kept_last"],receipt_age=data["receipt_ages"]),
        phases=phases,landmarks=landmarks,driven_wheels_800_1000ms=wheel_window,
        whole_peak=peak_context(data,data["start"],data["end"]),
        postcontact_peak=peak_context(data,tc,tc+3.),phase_sensitivity=phase_sensitivity(data["imu"],tc,tc+3.))


def make_plots(data,out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(4,2,figsize=(13,11),sharex=True,constrained_layout=True)
    for column,seed in enumerate((77400,77401)):
        for d in (d for d in data if d["row"]["seed"]==seed):
            color={1:"#2369ac",2:"#c55a11"}[d["row"]["repeat"]]
            tc=d["tc"]; label=f"repeat {d['row']['repeat']}"
            axes[0,column].plot([t-tc for t,v in d["imu"]],[v["vertical_m_s2"] for t,v in d["imu"]],".-",ms=2,lw=.8,color=color,label=label)
            axes[1,column].plot([t-tc for t,v in d["gt"]],[v["vz"] for t,v in d["gt"]],color=color,lw=.8)
            axes[2,column].plot([t-tc for t,v in d["joints"]],[v["velocity"]["right_wheel_joint"] for t,v in d["joints"]],color=color,lw=.8,label=label+" right actual")
            axes[2,column].plot([t-tc for t,v in d["drive"]],[v["right_target_rad_s"] for t,v in d["drive"]],color=color,ls="--",lw=.8)
            cs=[c for c in d["contacts"] if c["kind"]=="cable" and c["loaded"]]
            axes[3,column].scatter([c["relative_s"] for c in cs],[c["loaded_force_norm_sum_N"] for c in cs],s=5,color=color,alpha=.65)
        axes[0,column].set_title(f"Seed {seed}");axes[0,column].legend()
        for row,label in enumerate(("IMU vertical (m/s²)","GT body vz (m/s)","Right wheel (rad/s)","Sampled cable load norm (N)")):
            axes[row,column].set_ylabel(label);axes[row,column].set_xlim(-.3,1.1);axes[row,column].grid(alpha=.2);axes[row,column].axvline(0,color="black",ls=":")
        axes[-1,column].set_xlabel("Seconds after first recorded cable manifold")
    fig.suptitle("Frozen PI traces: original timestamps, no spike removal\nSampled load norms are not impulses; dashed wheel curves are targets")
    fig.savefig(out/"contact_aligned_pairs.png",dpi=155);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    rows=json.loads(args.rows.read_text())
    assert len(rows)==4 and {(r["seed"],r["repeat"]) for r in rows}=={(s,r) for s in (77400,77401) for r in (1,2)}
    # Protect all existing raw batch and previous audit files before reading them.
    dirs=[ROOT/"rl_runs/governor_pi_repeatability_2026-10-17",ROOT/"docs/governor_pi_repeatability_2026-10-17",
          ROOT/"src/nino_control",ROOT/"src/nino_rl/config"]
    paths={p for directory in dirs for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    paths.update(ROOT/"src/nino_rl/nino_rl"/n for n in ("ros_env.py","ros_interface.py","evaluation.py"))
    guard={str(p):sha(p) for p in sorted(paths)}
    write(out/"protocol_before_analysis.json",dict(scope="Exactly four saved PI runs; original contacts, GT, joints and IMU",
        phase_window="first cable manifold to +3s; diagnostic, native metrics retained",
        phase_checks="All 10 interpolated 50Hz grid offsets 0:2:18ms; all 5 original-sample 10Hz decimation residues",
        peak_context="Whole-route and fixed postcontact peak; +/-60ms contact wrench samples; causal past and explicitly labeled future body/wheel states",
        no_simulation=True,no_new_candidate=True,no_native_rescoring=True,
        limitation="50Hz acquisition phase cannot be recovered from existing 50Hz samples; no high-frequency reconstruction or force impulse claims"))
    write(out/"preservation_before.json",guard)
    data=[load_row(r) for r in rows]
    results=[analyze(d) for d in data]
    for d in data:
        label=f"seed_{d['row']['seed']}_repeat_{d['row']['repeat']}"
        write(out/(label+"_contact_timeline.json"),d["events"])
        with (out/(label+"_IMU_GT_joint_timeline.csv")).open("w") as stream:
            fields=["time_s","relative_s","vertical_m_s2","body_vx","body_vz","left_actual","right_actual","GT_age_s","joint_age_s"]
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for t,v in d["imu"]:
                if not -.5<=t-d["tc"]<=3.:continue
                g=asof(d["gt"],t,.025);j=asof(d["joints"],t,.010001)
                writer.writerow(dict(time_s=t,relative_s=t-d["tc"],vertical_m_s2=v["vertical_m_s2"],
                    body_vx=g["value"]["vx"] if g else None,body_vz=g["value"]["vz"] if g else None,
                    left_actual=j["value"]["velocity"]["left_wheel_joint"] if j else None,
                    right_actual=j["value"]["velocity"]["right_wheel_joint"] if j else None,
                    GT_age_s=g["age_s"] if g else None,joint_age_s=j["age_s"] if j else None))
    write(out/"analysis.json",results);make_plots(data,out)
    changed=[p for p,h in guard.items() if sha(Path(p))!=h]
    write(out/"verification.json",dict(protected_files=len(guard),changed=changed,episodes_read=len(data),
        all_native_arrivals_retained=all(r["native_unchanged"]["physical_pass"] for r in results),
        extra_simulation_episodes=0,controller_changes=False,native_metric_changes=False))
    assert not changed
    print(json.dumps(dict(output=str(out),protected_files=len(guard),changed=changed)))


if __name__=="__main__":
    main()
