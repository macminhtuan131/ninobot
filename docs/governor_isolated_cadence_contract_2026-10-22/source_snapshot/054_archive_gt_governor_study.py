#!/usr/bin/env python3
"""Archive the bounded v2 study and audit its accounting without rescoring it."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import optuna
import yaml

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--guard", type=Path, required=True)
    args = p.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    decision = json.loads((run / "decision.json").read_text())
    out.mkdir(exist_ok=False, parents=True)
    manifest = {}

    def copy(source, relative):
        if not source.is_file():
            return
        target = out / relative
        target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy2(source, target)
        manifest[str(source)] = sha(source)

    for name in ("contract_before_results.json", "execution_preflight.json",
                 "minimum_hold_diagnostic.json", "runner_snapshot.py", "decision.json",
                 "selection_before_validation.json", "offline_startup_audit.json",
                 "validation_startup_events.json"):
        copy(run / name, name)
    db = sqlite3.connect(run / "study.sqlite3")
    dest = sqlite3.connect(out / "study.sqlite3")
    db.backup(dest)
    dest.close()
    db.close()
    study = optuna.load_study(study_name="nino_gt_target_maxhold_v2",
                             storage="sqlite:///" + str(out / "study.sqlite3"))
    trials = [dict(number=t.number, state=t.state.name, params=t.params,
                   value=t.value, user_attrs=t.user_attrs) for t in study.trials]
    write(out / "trials.json", trials)
    all_rows, blocks, config_fingerprints = [], [], []
    folders = sorted(run.glob("trial_*"))
    if (run / "validation").is_dir():
        folders.append(run / "validation")
    for folder in folders:
        for name in ("config.yaml", "protocol_before_results.json", "score.json",
                     "confirmation_episodes.json", "episodes_gt_native.json"):
            copy(folder / name, folder.name + "/" + name)
        path = folder / "episodes_gt_native.json"
        if path.exists():
            all_rows.extend(dict(stage=folder.name, **r) for r in json.loads(path.read_text()))
        else:
            # A runner error must still retain attempted cases and aborted outcomes.
            for screen in folder.glob("confirmation/*/screen"):
                summary = screen / "summary.json"
                if summary.exists():
                    for r in json.loads(summary.read_text())["results"]:
                        all_rows.append(dict(stage=folder.name, scenario=screen.parent.name,
                            case=str(screen / ("seed_{seed}_{profile}".format(**r))),
                            seed=r["seed"], profile=r["profile"], complete=False,
                            available=False, error=r.get("error"), physical_pass=r.get("passed")))
        for scenario in folder.glob("confirmation/*"):
            prefix = folder.name + "/confirmation/" + scenario.name
            for name in ("scenario.sdf", "scenario.json", "run.log"):
                copy(scenario / name, prefix + "/" + name)
            for name in ("summary.json", "plan.json", "runner_snapshot.py"):
                copy(scenario / "screen" / name, prefix + "/screen/" + name)
            for case in (scenario / "screen").glob("seed_*"):
                base = prefix + "/cases/" + case.name
                if (case / "config.yaml").is_file():
                    cfg = yaml.safe_load((case / "config.yaml").read_text())
                    settings = cfg["governor"]["parameters"]
                    declaration = dict(case=str(case), cruise=cfg["navigation"]["straight_speed_m_s"],
                        target=settings["target_scale"], maximum_hold=settings["maximum_hold_seconds"],
                        minimum_hold=settings["minimum_hold_seconds"], profile=settings["profile"])
                    for key in ("target_scale", "maximum_hold_seconds", "profile"):
                        settings.pop(key)
                    declaration["other_config_sha256"] = hashlib.sha256(
                        json.dumps(cfg, sort_keys=True).encode()).hexdigest()
                    config_fingerprints.append(declaration)
                for name in ("config.yaml", "audit.json", "evaluate.log", "gazebo.log"):
                    copy(case / name, base + "/" + name)
                for log in case.glob("contact/*"):
                    for f in log.iterdir():
                        if f.name not in ("samples.jsonl", "contact_events.jsonl"):
                            copy(f, base + "/contact/" + log.name + "/" + f.name)
                        elif f.is_file():
                            manifest[str(f)] = sha(f)
                for evaluation in case.glob("evaluation/*"):
                    for name in ("summary.json", "failure.json", "episodes.csv", "metadata.json", "config.yaml"):
                        copy(evaluation / name, base + "/evaluation/" + evaluation.name + "/" + name)
                    for f in evaluation.glob("episode-*/*.csv"):
                        copy(f, base + "/evaluation/" + evaluation.name + "/" + f.parent.name + "/" + f.name)

        rows = [r for r in all_rows if r["stage"] == folder.name]
        protocol = json.loads((folder / "protocol_before_results.json").read_text())
        expected = {(s["id"], seed, arm) for s in protocol["scenarios"]
                    for seed in s["seeds"] for arm in ("full", "reactive")}
        actual = [(r["scenario"], r["seed"], r["profile"]) for r in rows]
        blocks.append(dict(stage=folder.name, expected=len(expected), observed=len(actual),
            unique_case_contract=set(actual) == expected and len(actual) == len(expected),
            completed=sum(r.get("complete", False) for r in rows),
            physical_passes=sum(r.get("physical_pass", False) for r in rows),
            aborted_or_unavailable=sum(not r.get("complete", False) for r in rows),
            completed_native_physical_failures=sum(r.get("physical_success") is False for r in rows)))

    write(out / "all_episodes.json", all_rows)
    complete = [r for r in all_rows if r.get("available")]
    keys = ("robot_description_sha256", "governor_core_sha256", "effort_drive_sha256", "control_timing_sha256")
    provenance = {k: sorted({r.get("provenance", {}).get(k) for r in complete
                             if r.get("provenance", {}).get(k)}) for k in keys}
    guard = json.loads(args.guard.read_text())
    changed = [name for name, digest in guard.items()
               if not (ROOT / name).is_file() or sha(ROOT / name) != digest]
    checks = dict(blocks=blocks, planned_case_counts_match=all(b["unique_case_contract"] for b in blocks),
        provenance=provenance, fixed_robot_pi_core=all(len(v) == 1 for v in provenance.values()),
        paired_world_hashes_match=all(len({r.get("world_sha256") for r in complete
            if r["stage"] == stage and r["scenario"] == scenario}) == 1
            for stage, scenario in {(r["stage"], r["scenario"]) for r in complete}),
        complete_native_replays=sum(r.get("native_replay", {}).get("matches_native", False) for r in complete),
        complete_timestamp_checks=sum(r.get("timestamps", {}).get("passed", False) for r in complete),
        gt_route_and_crossing_available=sum(all(r.get("gt_native", {}).get(w, {}).get("available", False)
            for w in ("whole_route", "crossing")) for r in complete),
        case_configs=config_fingerprints,
        only_search_and_profile_config_changes=len({r["other_config_sha256"] for r in config_fingerprints}) == 1,
        all_cruise_0p4_and_minimum_hold_0p8=all(r["cruise"] == .4 and r["minimum_hold"] == .8
                                             for r in config_fingerprints),
        protected_files=len(guard), changed_protected_files=changed,
        decision=decision, no_rescoring=True)
    write(out / "accounting_checks.json", checks)

    fields = ["stage", "scenario", "seed", "profile", "complete", "physical_success", "physical_pass", "available",
        "time_s", "physical_rmse_m", "native_slip_rms", "whole_vertical_rms", "whole_vertical_peak",
        "gt_whole_rms", "gt_crossing_slip2_per_m", "gt_whole_coverage", "gt_crossing_coverage", "error"]
    with (out / "episodes.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in all_rows:
            writer.writerow({k: r.get(k) for k in fields[:13] + ["error"]} | dict(
                gt_whole_rms=r.get("gt_native", {}).get("whole_route", {}).get("rms"),
                gt_crossing_slip2_per_m=r.get("gt_native", {}).get("crossing", {}).get("slip_square_per_m"),
                gt_whole_coverage=r.get("gt_native", {}).get("whole_route", {}).get("coverage_fraction"),
                gt_crossing_coverage=r.get("gt_native", {}).get("crossing", {}).get("coverage_fraction")))
    holds = [dict(stage=r["stage"], scenario=r["scenario"], seed=r["seed"], **h)
             for r in all_rows for h in r.get("executed_holds", [])]
    write(out / "executed_holds.json", holds)
    for file in (Path(__file__), Path(__file__).with_name("tune_gt_governor.py"),
                 Path(__file__).with_name("run_frozen_governor_confirmation.py"),
                 Path(__file__).with_name("audit_gt_timestamp_slip.py"),
                 Path(__file__).with_name("audit_governor_phase_slip.py"),
                 ROOT / "src/nino_rl/nino_rl/slip_reporting.py",
                 ROOT / "src/nino_rl/test/test_gt_governor_tuning.py"):
        copy(file, "analysis_sources/" + file.name)
    write(out / "source_manifest_sha256.json", manifest)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for t in trials:
        label = "{} / {} s".format(t["params"]["target_scale"], t["params"]["maximum_hold_seconds"])
        if t["value"] is None:
            ax.text(t["number"], 1.01, "FAIL\nno score", ha="center", va="bottom", fontsize=9, color="darkred")
        else:
            ax.scatter(t["number"], t["value"], s=90,
                       color="tab:green" if t["user_attrs"].get("eligible") else "tab:orange")
        ax.set_xticks([x["number"] for x in trials],
                     ["T{}\n{} / {} s".format(x["number"], x["params"]["target_scale"],
                       x["params"]["maximum_hold_seconds"]) for x in trials])
    ax.axhline(1., color="grey", linestyle="--", label="Cost threshold (other guards also required)")
    ax.set_ylabel("Development cost (lower is better)")
    ax.set_title("Six fixed candidates; unavailable trials have no numeric score")
    ax.grid(axis="y", alpha=.2)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "development_cost.png", dpi=150)
    plt.close(fig)
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
