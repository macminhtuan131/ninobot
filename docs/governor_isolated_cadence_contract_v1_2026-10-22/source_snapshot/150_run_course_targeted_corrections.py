#!/usr/bin/env python3
"""Validate N1 alignment, then run one fixed-budget flat slip-weight pilot."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]
FLAT_REFERENCE = ROOT / "rl_runs/flat_value_scaled_seed43_v1"
ROUGH_REFERENCE = ROOT / "rl_runs/rough_trial8_validation_v1"
DEFAULT_OUTPUT = ROOT / "rl_runs/course_targeted_corrections_v1"


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def flat_change(original, candidate):
    """Only slip weight may differ from the same-seed completed control."""
    expected = deepcopy(original)
    expected["reward_v2"]["slip_weight"] *= 1.5
    if candidate != expected:
        raise ValueError("Targeted flat pilot may only increase slip weight by 50%")
    if candidate["seed"] != 43 or candidate["training_reward_scale"] != 0.01:
        raise ValueError("Preserve seed 43 and measured learner reward units")
    return expected


def rough_change(original, override):
    if override != {"routes": {"revision": "fixed_n1_s1_alignment_v17", "stop_align_route_ids": ["N1", "S1"]}}:
        raise ValueError("Only the declared N1/S1 alignment profile is allowed")
    if original["routes"]["stop_align_route_ids"] != ["S1"] or not original["routes"]["curvature_speed_limit"]:
        raise ValueError("Expected the qualified S1-only frozen v16 controller")
    config = deepcopy(original)
    config["routes"].update(override["routes"])
    return config


def verify_assets(assets):
    from nino_rl.tuning_trials import digest
    for path, expected in assets.items():
        if digest(path) != expected:
            raise ValueError("Frozen targeted-correction input changed: " + path)


def prepare_flat(output):
    import yaml
    from nino_rl.core import load_config
    from nino_rl.tuning_trials import digest
    from run_flat_seed_repeat import verify
    reference = read(FLAT_REFERENCE / "repeat_plan.json")
    verify(reference)
    candidate_path = ROOT / "src/nino_rl/config/combined_flat_slip_targeted_pilot.yaml"
    candidate = flat_change(reference["training_config"], load_config(candidate_path))
    output.mkdir(parents=True, exist_ok=True)
    overlay = output / "python"
    if not overlay.exists():
        temporary = output / "python.preparing"
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(FLAT_REFERENCE / "python", temporary, ignore=shutil.ignore_patterns("__pycache__"))
        path = temporary / "nino_rl/training_contract.py"
        code = path.read_text()
        if code.count('contract["revision"] = 38') != 1:
            raise ValueError("Expected the frozen reward-unit contract")
        path.write_text(code.replace('contract["revision"] = 38', 'contract["revision"] = 40'))
        temporary.rename(overlay)
    for path in (overlay / "nino_rl").glob("*.py"):
        source = FLAT_REFERENCE / "python/nino_rl" / path.name
        expected = (source.read_text().replace('contract["revision"] = 38', 'contract["revision"] = 40').encode()
                    if path.name == "training_contract.py" else source.read_bytes())
        if path.read_bytes() != expected:
            raise ValueError("Targeted snapshot changed controller, estimator or reward implementation: " + path.name)
        compile(path.read_text(), str(path), "exec")
    plan = deepcopy(reference)
    plan.update(revision="flat_slip_weight_targeted_v1", original_run=str(FLAT_REFERENCE),
        original_training_seed=43, training_config=candidate,
        correction={"parameter": "reward_v2.slip_weight", "before": reference["training_config"]["reward_v2"]["slip_weight"],
                    "after": candidate["reward_v2"]["slip_weight"], "training_contract_revision": 40},
        original_assets={str(path): digest(path) for path in
            [FLAT_REFERENCE / name for name in ("repeat_plan.json", "pilot.yaml", "evaluation.yaml", "comparison.json")]},
        snapshot_assets={str(p): digest(p) for p in sorted((overlay / "nino_rl").glob("*.py"))},
        workflow_assets={str(p): digest(p) for p in [Path(__file__), candidate_path,
            Path(__file__).with_name("run_flat_seed_repeat.py"), Path(__file__).with_name("train_rough_curriculum.py"),
            Path(__file__).with_name("wait_for_drive_profile.py")]})
    path = output / "targeted_plan.json"
    if path.exists() and read(path) != plan:
        raise ValueError("Targeted flat plan changed; use a new output directory")
    write(path, plan)
    for name, settings in (("pilot.yaml", candidate), ("evaluation.yaml", plan["evaluation_config"])):
        text = yaml.safe_dump(settings, sort_keys=False)
        path = output / name
        if path.exists() and path.read_text() != text:
            raise ValueError("Targeted configuration changed: " + name)
        path.write_text(text)
    verify(plan)
    return plan


def flat_run(output, save):
    from run_flat_seed_repeat import run
    plan = prepare_flat(output)
    # Reuse the already checked isolated executor, transfer audits and original gates.
    run(output, plan, save)
    result = read(output / "comparison.json")
    reference = read(FLAT_REFERENCE / "comparison.json")
    from nino_rl.evaluation import compare_summaries
    result.pop("both_training_seeds_qualified", None)
    result["correction"] = plan["correction"]
    result["same_seed_reference"] = str(FLAT_REFERENCE / "comparison.json")
    result["versus_same_seed_reference"] = compare_summaries(reference["ppo"]["report"], result["ppo"]["report"])
    result["original_seed_comparison"] = str(FLAT_REFERENCE / "comparison.json")
    write(output / "comparison.json", result)
    lines = ["# Flat targeted slip-weight pilot", "", "Same original actor, training seed 43, fresh critic/optimizer, "
             "20,480 steps; learner reward scale 0.01. Only slip weight changed by 50%.", "",
             "| Metric | Reference PPO | Targeted PPO | Matching PI |", "|---|---:|---:|---:|"]
    reports = [reference["ppo"]["report"], result["ppo"]["report"], result["pi"]["report"]]
    lines.append("| Physical arrivals | " + " | ".join(f"{round(r['success_rate']*24)}/24" for r in reports) + " |")
    for metric in ("time_seconds", "truth_path_rmse_m", "rms_vertical_acceleration_m_s2", "rms_wheel_slip"):
        lines.append("| " + metric + " | " + " | ".join(f"{r['metrics_all_episodes'][metric]['mean']:.6f}" for r in reports) + " |")
    lines += ["", f"Unchanged gates: `{json.dumps(result['gates'])}`. Qualifies: **{result['promote']}**.", "",
              "Same training seed controls one source of variation; one targeted run does not establish training-seed "
              "robustness. Returns from different reward weights are not directly comparable. No automatic Optuna, "
              "long training or extra cable is started.", ""]
    (output / "REPORT.md").write_text("\n".join(lines))
    save("complete", report=str(output / "REPORT.md"), gates=result["gates"])


def rough_run(output, save, prepare_only=False):
    import yaml
    from tune_rough_e1_v16 import bootstrap
    bootstrap()
    from run_rough_trial8_validation import Validation, route_readiness
    from run_rough_localized import longest_commanded_stall
    from nino_rl.tuning_trials import digest
    output.mkdir(parents=True, exist_ok=True)
    validator = Validation(output)
    override_path = ROOT / "src/nino_rl/config/rough_n1_alignment_override.yaml"
    original = yaml.safe_load((ROUGH_REFERENCE / "correction.yaml").read_text())
    config = rough_change(original, yaml.safe_load(override_path.read_text()))
    config.pop("training_reward_scale", None)
    validator.config = config
    paths = [Path(__file__), override_path, ROUGH_REFERENCE / "correction.yaml", ROUGH_REFERENCE / "route_pi_gate.json"]
    contract = dict(revision="rough_n1_alignment_v17_validation", controller_changes=override_path.read_text(),
        original_evidence=str(ROUGH_REFERENCE), physical_scoring="unchanged independent physical arrival and ordered gates",
        geometry="unchanged fixed original terrain and E1/N1/S1 routes",
        action_meanings="unchanged three-action wheel torque", estimator="unchanged frozen v16",
        gate=config["rough_curriculum"]["gate"], screening_seeds=[13000,13001,13002],
        confirmation_seeds=list(range(13100,13120)), training_updates=0,
        assets={str(p): digest(p) for p in paths}, config=config)
    path = output / "alignment_contract.json"
    if path.exists() and read(path) != contract:
        raise ValueError("Alignment validation contract changed; use a new output directory")
    write(path, contract)
    (output / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    verify_assets(contract["assets"])
    validator.check()
    if prepare_only:
        return
    results = {}

    def evaluate(route, seeds, label):
        verify_assets(contract["assets"])
        cfg = deepcopy(config)
        cfg["rough_runtime"]["stage_index"] = {"E1": 0, "N1": 1, "S1": 2}[route]
        save("rough_pi_" + route + "_" + label)
        evidence = validator.evaluate("route_pi/" + route + "/" + label, cfg,
            route=route, seeds=seeds, control_trace=True)
        gate = route_readiness(evidence["rows"], cfg, len(seeds))
        stalls = [longest_commanded_stall(Path(evidence["summary"]).parent / f"episode-{i:03d}/control_trace.csv")
                  for i in range(1, len(seeds)+1)]
        gate["longest_commanded_stall_seconds"] = max(stalls)
        gate["passed"] = gate["passed"] and max(stalls) <= 2.
        return dict(gate=gate, summary=evidence["summary"], report=evidence["report"])

    def report():
        passed = len(results) == 3 and all(item.get("confirmation", {}).get("gate", {}).get("passed", False)
                                         for item in results.values())
        write(output / "route_pi_gate.json", dict(passed=passed, routes=results))
        lines = ["# Rough N1 alignment validation", "", "Enabled the existing bounded S1 stop-and-align profile "
                 "for N1. Route geometry, localization and strict physical scoring remain unchanged. No RL updates.", "",
                 "| Route | Batch | Arrivals | Physical RMSE | Gate |", "|---|---|---:|---:|---|"]
        for route, batches in results.items():
            for label, evidence in batches.items():
                gate = evidence["gate"]
                lines.append(f"| {route} | {label} | {round(gate['physical_arrival_rate']*gate['episodes'])}/{gate['episodes']} | "
                             f"{gate['truth_path_rmse_m']:.6f} m | {gate['passed']} |")
        lines += ["", f"All three routes qualified: **{passed}**.", "",
                  "A passing PI screen is not an RL result. Controller change requires actor-only initialization with a "
                  "fresh critic/optimizer under this new contract before any future curriculum run. Old models/studies "
                  "remain preserved; no historical scores imported and no curriculum or Optuna started.", ""]
        (output / "REPORT.md").write_text("\n".join(lines))
        return passed

    try:
        results["N1"] = {"screen": evaluate("N1", [13000,13001,13002], "screen")}
        report()
        if not results["N1"]["screen"]["gate"]["passed"]:
            save("held_n1_alignment", reason="New N1 alignment failed strict physical readiness", report=str(output / "REPORT.md"))
            return
        for route in ("N1", "E1", "S1"):
            results.setdefault(route, {})["confirmation"] = evaluate(route, list(range(13100,13120)), "confirmation")
            report()
        passed = report()
        save("validated_for_curriculum" if passed else "held_route_pi", report=str(output / "REPORT.md"))
    finally:
        validator.processes.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", choices=("all", "flat", "rough"), default="all")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0] = [str(ROOT / "src/nino_rl"), str(Path(__file__).parent)]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = dict(pid=os.getpid(), started_utc=datetime.now(timezone.utc).isoformat(), course=args.course)

        def save(stage, **extra):
            state.update(stage=stage, updated_utc=datetime.now(timezone.utc).isoformat(), **extra)
            write(output / "status.json", state)
            print(stage, flush=True)

        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            if args.course == "all":
                from train_rough_curriculum import Processes
                processes = Processes(os.environ.copy())
                try:
                    # Independent processes keep the frozen rough imports out of flat.
                    for course in ("rough", "flat"):
                        save(course + ("_running" if args.run else "_preparing"))
                        command = [sys.executable, str(Path(__file__)), "--course", course, "--output", output / course]
                        if args.run:
                            command.append("--run")
                        processes.run(command, output / (course + ".log"))
                    save("complete" if args.run else "prepared")
                finally:
                    processes.close()
            elif args.course == "flat":
                if args.run:
                    flat_run(output, save)
                else:
                    prepare_flat(output)
                    save("prepared")
            else:
                rough_run(output, save, prepare_only=not args.run)
                if not args.run:
                    save("prepared")
        except KeyboardInterrupt:
            save("cancelled")
            raise
        except Exception as error:
            save("failed", error=str(error))
            raise


if __name__ == "__main__":
    main()
