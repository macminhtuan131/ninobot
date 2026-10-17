#!/usr/bin/env python3
"""Cold-start PI repeats, including a measured post-arrival stop window.

Run in a dedicated ROS/Gazebo domain. Never stops an existing simulator.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_clear_floor_stability import audit, resolve, settling_audit


def latest_sim_time(path):
    if not path.exists():
        return None
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 262144))
        lines = stream.read().splitlines()[1:]
    times = []
    for line in lines:
        try:
            row = json.loads(line)
            if row["topic"] == "/ground_truth/odom":
                stamp = row["data"]["header"]["stamp"]
                times.append(stamp["sec"] + stamp["nanosec"] * 1e-9)
        except (ValueError, KeyError):
            continue
    return max(times, default=None)


def stop_owned(process):
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=15)


def motion_screen_passed(data,returncode,*,clear_floor):
    """The clear-floor low-tilt diagnostic is not an obstacle arrival rule."""
    physical=(returncode==0 and data["completed_evaluation"] and data["physical_success_rate"]==1.)
    low_tilt=(data["maximum_abs_roll_deg"] is not None and data["maximum_abs_roll_deg"]<5. and
              data["maximum_abs_pitch_deg"] is not None and data["maximum_abs_pitch_deg"]<5.)
    return bool(physical and (low_tilt if clear_floor else True) and
                data.get("post_arrival_stop",{}).get("settled") is True)


def case_schedule(seeds,profiles,shuffle_order=False,order_seed=0):
    rng=random.Random(order_seed)
    cases=[]
    for seed in seeds:
        order=list(profiles)
        if shuffle_order:rng.shuffle(order)
        cases.extend((seed,profile) for profile in order)
    return cases


def configure_profile(values,profile,full_reference_speed=None):
    """Reference speed changes only the transparent Full PI arm."""
    values["governor"]["parameters"].update(profile=profile,pulse_seconds=1.)
    if profile=="full" and full_reference_speed is not None:
        if not 0<full_reference_speed<=values["navigation"]["straight_speed_m_s"]:
            raise ValueError("Reference speed must be positive and no faster than the common cruise")
        values["navigation"]["straight_speed_m_s"]=full_reference_speed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[76000, 76001, 76002])
    parser.add_argument("--variant", choices=["clear", "clear_box", "cable", "cable_box", "cable_box_capsule"], default="clear")
    parser.add_argument("--profiles", nargs="+", choices=["full", "moderate", "pulse", "reactive"], default=["full"])
    parser.add_argument("--oracle-contact", action="store_true",
                        help="Simulation-only H2: suppress sensor triggers and intervene after cable contact")
    parser.add_argument("--config", type=Path, help="Explicit single-cable candidate contract")
    parser.add_argument("--world",type=Path,help="Research-only capsule scenario SDF with JSON sidecar")
    parser.add_argument("--shuffle-order",action="store_true",help="Randomize controller order within each seed block")
    parser.add_argument("--order-seed",type=int,default=0)
    parser.add_argument("--full-reference-speed",type=float,
        help="Constant PI reference in m/s for Full arm only; adaptive arms retain common cruise")
    args = parser.parse_args()
    if args.world:
        args.world=args.world.expanduser().resolve()
        if args.variant!="cable_box_capsule" or not args.world.is_file() or not args.world.with_suffix(".json").is_file():
            parser.error("World override requires capsule variant and existing SDF/JSON pair")
    if args.full_reference_speed is not None and (not math.isfinite(args.full_reference_speed)
            or args.full_reference_speed<=0 or "full" not in args.profiles
            or args.variant!="cable_box_capsule" or args.oracle_contact):
        parser.error("Full-reference speed requires positive finite speed, Full arm and sensor-only capsule experiment")
    if args.oracle_contact and args.variant not in ("cable_box", "cable_box_capsule"):
        parser.error("Contact-oracle screen is restricted to the validated single-cable box floor")
    if args.config and args.variant not in ("cable_box", "cable_box_capsule"):
        parser.error("Explicit candidate contracts require a single-cable box-floor control")
    args.output.mkdir(parents=True, exist_ok=False)
    schedule=case_schedule(args.seeds,args.profiles,args.shuffle_order,args.order_seed)
    results = []
    if args.variant in ("clear", "clear_box") and args.profiles != ["full"]:
        parser.error("Clear-floor arrival screen uses full PI only")
    (args.output/"runner_snapshot.py").write_bytes(Path(__file__).read_bytes())
    sources = {}
    if args.oracle_contact:
        for name in ("nino_rl/research_contact_oracle.py", "nino_rl/evaluation.py", "scripts/evaluate_contact_oracle.py"):
            source = ROOT/"src/nino_rl"/name
            content = source.read_bytes()
            (args.output/(source.stem+"_snapshot.py")).write_bytes(content)
            sources[name] = hashlib.sha256(content).hexdigest()
    (args.output/"plan.json").write_text(json.dumps(dict(
        variant=args.variant,seeds=args.seeds,profiles=args.profiles,oracle_contact=args.oracle_contact,source_sha256=sources,
        shuffle_order=args.shuffle_order,order_seed=args.order_seed,case_order=schedule,
        full_reference_speed_m_s=args.full_reference_speed,
        world_override=str(args.world) if args.world else None,
        ros_domain=os.environ.get("ROS_DOMAIN_ID"),gz_partition=os.environ.get("GZ_PARTITION"),
        caster_wheel_damping=.001,physics_step_s=.001,control_interval_s=.1,
        stop_window_s=2.,qualification="Bounded native PI screen; no learning or Optuna"),indent=2)+"\n")
    for seed, profile in schedule:
        case = args.output / (f"seed_{seed}" if args.variant == "clear" else f"seed_{seed}_{profile}")
        case.mkdir()
        config = ROOT / "src/nino_rl/config/factory_floor_stability_pi_check.yaml"
        if args.variant == "clear_box":
            config=ROOT/"src/nino_rl/config/factory_floor_clear_box_pi_check.yaml"
        if args.variant in ("cable", "cable_box", "cable_box_capsule"):
            import yaml
            from nino_rl.core import load_config
            if args.variant in ("cable_box", "cable_box_capsule"):
                config=ROOT/"src/nino_rl/config/factory_floor_single_cable_box_pi_check.yaml"
            if args.variant=="cable_box_capsule":
                config=ROOT/"src/nino_rl/config/factory_floor_cable_capsule_pi_check.yaml"
            if args.config:
                config=args.config.expanduser().resolve()
            values = load_config(config)
            configure_profile(values,profile,args.full_reference_speed)
            if not args.config and args.variant!="cable_box_capsule":
                values["research_map"]["stage"] = "single_cable_sensor_triggered_screen"
            if args.oracle_contact:
                values["research_map"]["stage"] = "single_cable_post_contact_oracle_h2"
                values["research_experiment"] = dict(kind="post_contact_oracle_h2",
                    oracle_contact_input=True, deployable=False, sensor_trigger_suppressed=True,
                    automatic_trigger_startup_seconds_override=1.e12)
            config = case.resolve() / "config.yaml"
            config.write_text(yaml.safe_dump(values, sort_keys=False))
        result = {"seed": seed, "profile": profile, "passed": False, "evaluation_returncode": None}
        print(f"START {args.variant} E1 seed {seed}, profile {profile}", flush=True)
        launch = None
        interrupted = False
        try:
            with (case / "gazebo.log").open("w") as stream:
                launch = subprocess.Popen([
                    "ros2", "launch", "nino_rl", "factory_floor_governor.launch.py",
                    f"variant:={args.variant}", "caster_wheel_damping:=0.001",
                    f"world_override:={args.world or ''}",
                    f"config:={config}", "headless:=true", f"output_directory:={case.resolve() / 'contact'}"],
                    cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                deadline = time.monotonic() + 360
                while True:
                    if launch.poll() is not None:
                        raise RuntimeError("Owned simulator exited during startup")
                    try:
                        logger = resolve(case / "contact", "metadata.json")
                        metadata = json.loads((logger / "metadata.json").read_text())
                        if (metadata.get("robot_description_validated") and
                                "Effort drive ready:" in (case / "gazebo.log").read_text()):
                            break
                    except (ValueError, FileNotFoundError):
                        pass
                    if time.monotonic() > deadline:
                        raise TimeoutError("Controller/model startup deadline")
                    time.sleep(.5)
                result["logger"] = str(logger)
                with (case / "evaluate.log").open("w") as evaluation_log:
                    entry = ([sys.executable, str(ROOT/"src/nino_rl/scripts/evaluate_contact_oracle.py")]
                             if args.oracle_contact else ["ros2", "run", "nino_rl", "evaluate_baseline"])
                    evaluator = subprocess.Popen(entry + ["--config",
                        str(config),
                        "--route", "E1", "--episodes", "1", "--seed", str(seed),
                        "--control-trace", "--output", str(case.resolve() / "evaluation")],
                        cwd=ROOT, stdout=evaluation_log, stderr=subprocess.STDOUT, start_new_session=True)
                    try:
                        evaluator.wait(timeout=900)
                    finally:
                        stop_owned(evaluator)
                result["evaluation_returncode"] = evaluator.returncode
                evaluation = resolve(case / "evaluation", "summary.json")
                result["evaluation"] = str(evaluation)
                traces=list(evaluation.glob("episode-*/control_trace.csv"))
                if not traces:
                    state=json.loads((evaluation/"summary.json").read_text())
                    result["evaluation_failure"]=state.get("aborted_episode")
                    raise RuntimeError("Evaluation produced no control trace: "+str(state.get("aborted_episode")))
                trace = traces[0]
                rows = list(csv.DictReader(trace.open()))
                if rows:
                    end = float(rows[-1]["sim_time_s"])
                    deadline = time.monotonic() + 120
                    while (latest_sim_time(logger / "samples.jsonl") or 0) < end + 2.1:
                        if time.monotonic() > deadline:
                            raise TimeoutError("No complete two-second simulated stop window")
                        time.sleep(.5)
                    result["stop_window_start_s"] = end
        except KeyboardInterrupt:
            interrupted = True
            result["error"] = "KeyboardInterrupt: screen interrupted; task outcome is not a physical failure"
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        finally:
            if launch is not None:
                stop_owned(launch)
        if not result.get("evaluation"):
            try:
                result["evaluation"] = str(resolve(case / "evaluation", "summary.json"))
            except (ValueError, FileNotFoundError):
                pass
        try:
            if result.get("evaluation"):
                data = audit(result["evaluation"], result["logger"])
                if "stop_window_start_s" in result:
                    data["post_arrival_stop"] = settling_audit(result["logger"], result["stop_window_start_s"])
                (case / "audit.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
                result["audit"] = data
                result["passed"]=motion_screen_passed(data,result["evaluation_returncode"],
                    clear_floor=args.variant in ("clear","clear_box"))
        except Exception as error:
            result["audit_error"] = f"{type(error).__name__}: {error}"
        results.append(result)
        (args.output / "summary.json").write_text(json.dumps({
            "qualification": "Small cold-start screen; not general robustness, causal proof or hardware validation",
            "variant": args.variant, "profiles": args.profiles, "seeds": args.seeds, "results": results,
            "oracle_contact": args.oracle_contact,
            "interrupted": interrupted,
            "all_passed": len(results) == len(args.seeds)*len(args.profiles) and all(r["passed"] for r in results),
            "tilt_diagnostic_limit_deg": 5., "post_arrival_window_s": 2.,
            "low_tilt_required_during_episode":args.variant in ("clear","clear_box"),
            "training_started": False, "optuna_started": False}, indent=2, allow_nan=False) + "\n")
        print(f"END seed {seed}: passed={result['passed']}; {result.get('error', '')}", flush=True)
        if interrupted:
            raise SystemExit(130)


if __name__ == "__main__":
    main()
