#!/usr/bin/env python3
"""One sequential instrumentation pair; never tunes, retries or trains."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/"src/nino_rl"), str(ROOT/"src/nino_control")]
from nino_rl.core import load_config
from nino_rl.slip_reporting import integrate
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
from run_frozen_governor_confirmation import make_world, analyze_batch


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--domain", type=int, default=100)
    args = p.parse_args()
    root = args.output.resolve()
    root.mkdir(exist_ok=True, parents=True)
    if (root/"protocol_before_results.json").exists():
        raise ValueError("This bounded pair was already prepared; no implicit retry")
    config = load_config(ROOT/"rl_runs/gt_governor_optuna_v2_2026-10-16/trial_000/config.yaml")
    original = deepcopy(config)
    config["research_map"].update(revision="startup_feedback_readiness_v1",
        training_allowed=False, optuna_allowed=False)
    settings = config["governor"]["parameters"]
    assert settings["target_scale"] == .9 and settings["maximum_hold_seconds"] == 1.
    assert config["navigation"]["straight_speed_m_s"] == .4
    assert all(config[k] == original[k] for k in config if k != "research_map")
    path = root/"config.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    scenario = dict(id="instrumentation", x_m=3.10, angle_deg=8., seeds=[77200])
    sources = {}
    after = root/"after_sources"
    after.mkdir()
    for name in ("ros_interface.py", "ros_env.py", "evaluation.py"):
        source = ROOT/"src/nino_rl/nino_rl"/name
        shutil.copy2(source, after/name)
        sources[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    write(root/"protocol_before_results.json", dict(revision="startup_feedback_readiness_v1",
        scenarios=[scenario], max_attempts=2, controllers=["full", "reactive"],
        order="full then reactive; sequential cold starts", domain=args.domain,
        selected_settings=settings, cruise_both_m_s=.4, stop_window_sim_seconds=2.,
        physics_step_s=.001, control_interval_s=.1, source_sha256=sources,
        correction="Estimator origin lifecycle and bounded paused-world diagnostics delivery; physical estimator math and governor/PI unchanged",
        gate="Both complete arrival/stop; exact native replay; timestamp checks; GT whole/cross coverage; command feedback age<=.1 and no future/previous-interval drive samples",
        no_retry=True, no_parameter_selection=True, no_quality_promotion=True,
        no_optuna=True, no_training=True,
        qualification="Instrumentation screen, not an unseen test bank or robustness/quality confirmation"))
    stage = root/"confirmation"/scenario["id"]
    stage.mkdir(parents=True)
    make_world(stage/"scenario.sdf", scenario)
    (root/"runner_snapshot.py").write_bytes(Path(__file__).read_bytes())
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID=str(args.domain), NINO_ROS_DOMAIN_ID=str(args.domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST", GZ_PARTITION=f"nino_governor_readiness_{args.domain}")
    command = [sys.executable, str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),
        "--variant", "cable_box_capsule", "--config", str(path), "--profiles", "full", "reactive",
        "--full-reference-speed", ".4", "--seeds", "77200", "--world", str(stage/"scenario.sdf"),
        "--output", str(stage/"screen")]
    with (root/"run.log").open("w") as stream:
        result = subprocess.run(command, env=env, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    analyze_batch(root)
    rows = json.loads((root/"confirmation_episodes.json").read_text())
    for r in rows:
        try:
            case = Path(r["case"])
            evaluation = next(case.glob("evaluation/*/summary.json")).parent
            logger = next(case.glob("contact/*/metadata.json")).parent
            data = load(case, dict(evaluation=str(evaluation), logger=str(logger),
                seed=r["seed"], profile=r["profile"]))
            signal = gt_timestamp_series(data)
            r["gt_native"] = dict(whole_route=integrate(signal, data["start"], data["end"]),
                crossing=integrate(signal, r["first_contact_s"]+.05, r["clearance_s"]))
            controls = data["controls"]
            feedback_ages = [float(c["governor_feedback_age_s"]) for c in controls]
            interval_ages = [float(c["drive_interval_latest_age_s"]) for c in controls]
            no_failsafe = all(not c["governor_fault"] for c in controls)
            r["readiness"] = dict(samples=len(controls), no_failsafe=no_failsafe,
                feedback_age_range_s=[min(feedback_ages), max(feedback_ages)],
                interval_age_range_s=[min(interval_ages), max(interval_ages)],
                min_interval_samples=min(int(c["drive_interval_sample_count"]) for c in controls),
                passed=no_failsafe and all(-1e-9 <= a <= .100000001 for a in feedback_ages+interval_ages))
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            r["readiness_error"] = f"{type(error).__name__}:{error}"
    write(root/"episodes.json", rows)
    passed = result.returncode == 0 and len(rows) == 2 and {r["profile"] for r in rows} == {"full", "reactive"} and all(
        r.get("complete") and r.get("physical_pass") and r.get("native_replay", {}).get("matches_native")
        and r.get("timestamps", {}).get("passed") and r.get("readiness", {}).get("passed")
        and all(r.get("gt_native", {}).get(w, {}).get("available") for w in ("whole_route", "crossing")) for r in rows)
    write(root/"decision.json", dict(instrumentation_pass=bool(passed), attempts=len(rows),
        completed=sum(r.get("complete", False) for r in rows),
        physical_passes=sum(r.get("physical_pass", False) for r in rows),
        quality_conclusion="Not evaluated as a promotion gate by this pair",
        next_step="Prepare a separately budgeted validation protocol" if passed else "Stop; inspect saved failure without automatic retry",
        tuning_started=False, training_started=False, predictor_started=False,
        default_promoted=False, extra_attempts=False))
    print((root/"decision.json").read_text())


if __name__ == "__main__":
    main()
