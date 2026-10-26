#!/usr/bin/env python3
"""Screen N1 early braking, preserving qualified E1/S1 references."""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "rl_runs/rough_n1_anticipation_v19"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--wait-for-flat-pid", type=int)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0] = [str(ROOT / "src/nino_rl"), str(Path(__file__).parent)]
    from tune_rough_e1_v16 import bootstrap
    original = bootstrap()
    import yaml
    from nino_rl.tuning_trials import digest
    from run_rough_trial8_validation import Validation, route_readiness, read, write
    from run_flat_seed_repeat import process_identity
    from run_rough_localized import longest_commanded_stall
    from rough_n1_anticipation_profile import configuration, patch_routes
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        validator = Validation(output)
        reference = ROOT / "rl_runs/rough_trial8_validation_v1/correction.yaml"
        config = configuration(yaml.safe_load(reference.read_text()))
        validator.config = config
        overlay = output / "python"
        original_code = (original / "python/nino_rl/rough_stall_recovery.py").read_text()
        start = original_code.index("def route_controller_config(")
        end = original_code.index("\n\nclass CornerAlignment:", start)
        replacement = ("def route_controller_config(config, route_id):\n"
                       "    from nino_rl.n1_anticipation_profile import route_controller_config as select\n"
                       "    return select(config, route_id)\n")
        if not overlay.exists():
            temporary = output / "python.preparing"
            if temporary.exists():
                shutil.rmtree(temporary)
            shutil.copytree(original / "python", temporary, ignore=shutil.ignore_patterns("__pycache__"))
            (temporary / "nino_rl/rough_stall_recovery.py").write_text(original_code[:start] + replacement + original_code[end:])
            shutil.copyfile(Path(__file__).with_name("rough_n1_anticipation_profile.py"), temporary / "nino_rl/n1_anticipation_profile.py")
            routes = temporary / "nino_rl/routes.py"
            routes.write_text(patch_routes(routes.read_text()))
            temporary.rename(overlay)
        for path in (overlay / "nino_rl").glob("*.py"):
            compile(path.read_text(), str(path), "exec")
            if path.name == "rough_stall_recovery.py":
                expected = (original_code[:start] + replacement + original_code[end:]).encode()
            elif path.name == "routes.py":
                expected = patch_routes((original / "python/nino_rl/routes.py").read_text()).encode()
            elif path.name == "n1_anticipation_profile.py":
                expected = Path(__file__).with_name("rough_n1_anticipation_profile.py").read_bytes()
            else:
                expected = (original / "python/nino_rl" / path.name).read_bytes()
            if path.read_bytes() != expected:
                raise ValueError("Continuous profile changed an undeclared package file: " + str(path))
        assets = {str(p): digest(p) for p in sorted((overlay / "nino_rl").glob("*.py"))}
        contract = dict(revision="n1_early_braking_v19", config=config, snapshot_assets=assets,
            workflow_assets={str(p): digest(p) for p in [Path(__file__), Path(__file__).with_name("rough_n1_anticipation_profile.py"), Path(__file__).with_name("encoder_history_transport.py"), reference]},
            physical_scoring="unchanged strict arrival, ordered gates, tracking, localization, tilt and stall",
            change="N1 brakes over 1.20m before corner, 0.30m lookahead and 0.06m/s turn cap; original E1/S1 unchanged; encoder history 100",
            failed_candidate_preserved=str(ROOT / "rl_runs/rough_n1_continuous_v18"),
            training_updates=0)
        path = output / "continuous_contract.json"
        if path.exists() and read(path) != contract:
            raise ValueError("Continuous-corner contract changed; use a new output directory")
        write(path, contract)
        # Validation.check reads this manifest to verify any overlay before launch.
        write(output / "correction_contract.json", dict(snapshot_assets=assets))
        (output / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
        state = dict(pid=os.getpid(), started_utc=datetime.now(timezone.utc).isoformat())

        def save(stage, **extra):
            state.update(stage=stage, updated_utc=datetime.now(timezone.utc).isoformat(), **extra)
            write(output / "status.json", state)
            print(stage, flush=True)

        def check():
            for group in (contract["snapshot_assets"], contract["workflow_assets"]):
                for path, expected in group.items():
                    if digest(path) != expected:
                        raise ValueError("Frozen continuous repair input changed: " + path)
            validator.check(overlay)

        check()
        if not args.run:
            save("prepared")
            return
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        results = {}

        def evaluate(route, seeds, label):
            check()
            cfg = deepcopy(config)
            cfg["rough_runtime"]["stage_index"] = {"E1": 0, "N1": 1, "S1": 2}[route]
            save("pi_" + route + "_" + label)
            evidence = validator.evaluate("route_pi/" + route + "/" + label, cfg, route=route,
                                          seeds=seeds, overlay=overlay, control_trace=True)
            gate = route_readiness(evidence["rows"], cfg, len(seeds))
            stalls = [longest_commanded_stall(Path(evidence["summary"]).parent / f"episode-{i:03d}/control_trace.csv")
                      for i in range(1, len(seeds)+1)]
            gate["longest_commanded_stall_seconds"] = max(stalls)
            gate["passed"] = gate["passed"] and max(stalls) <= 2.
            return dict(gate=gate, summary=evidence["summary"])

        def report():
            passed = len(results) == 3 and all(item.get("confirmation", {}).get("gate", {}).get("passed", False)
                                             for item in results.values())
            write(output / "route_pi_gate.json", dict(passed=passed, routes=results))
            lines = ["# Rough N1 early braking validation", "",
                     "N1 uses early braking over 1.20m, 0.30m pursuit lookahead and a 0.06m/s moving turn. "
                     "S1's existing alignment and E1 behaviour remain unchanged. Geometry and scoring unchanged. Encoder transport retains 100 samples; timing limits unchanged.", "",
                     "| Route | Batch | Arrivals | Physical RMSE | Pass |", "|---|---|---:|---:|---|"]
            for route, batches in results.items():
                for label, evidence in batches.items():
                    gate = evidence["gate"]
                    lines.append(f"| {route} | {label} | {round(gate['physical_arrival_rate']*gate['episodes'])}/{gate['episodes']} | "
                                 f"{gate['truth_path_rmse_m']:.6f}m | {gate['passed']} |")
            lines += ["", f"All routes qualified (screen alone cannot qualify): **{passed}**. No RL updates or automatic curriculum/Optuna.", "",
                      "Failed stop-and-align N1 candidate preserved separately. Any future changed-controller training "
                      "requires actor initialization with a fresh critic/optimizer and a new contract.", ""]
            (output / "REPORT.md").write_text("\n".join(lines))
            return passed

        try:
            identity = process_identity(args.wait_for_flat_pid) if args.wait_for_flat_pid else None
            if identity:
                if "recover_flat_targeted_pi.py" not in identity[0]:
                    raise ValueError("Wait PID is not the owned flat PI recovery")
                save("waiting_for_flat", waited_pid=args.wait_for_flat_pid)
                while process_identity(args.wait_for_flat_pid) == identity:
                    time.sleep(2)
            results["N1"] = {"screen": evaluate("N1", [13000,13001,13002], "screen")}
            report()
            if not results["N1"]["screen"]["gate"]["passed"]:
                save("held_n1_anticipation", report=str(output / "REPORT.md"))
                return
            save("screen_passed_pending_confirmation", report=str(output / "REPORT.md"))
        except KeyboardInterrupt:
            save("cancelled")
            raise
        except Exception as error:
            save("failed", error=str(error))
            raise
        finally:
            validator.processes.close()


if __name__ == "__main__":
    main()
