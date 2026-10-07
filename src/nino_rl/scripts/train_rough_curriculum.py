#!/usr/bin/env python3
"""Own a rough Gazebo session, train route stages, evaluate and resume safely.

Map changes happen between blocks, never underneath a driving robot. Laya is
an independent advisory monitor; only complete numerical evaluations advance
this curriculum. This supervisor never stops another terminal's processes.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import zipfile

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/nino_rl"))
from nino_rl.core import load_config
from nino_rl.rough_curriculum import (choose_variant, curriculum_stage,
                                     evaluation_gate, load_bank, runtime_config)
from nino_rl.evaluation import compare_summaries


def save_json(path, value):
    """Replace durable state atomically, including after an unexpected shutdown."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def checkpoint_steps(path):
    with zipfile.ZipFile(path) as archive:
        if not {"data", "policy.pth", "policy.optimizer.pth", "pytorch_variables.pth"} <= set(archive.namelist()):
            raise ValueError(f"Incomplete PPO archive: {path}")
        if archive.testzip() is not None:
            raise ValueError(f"Corrupt checkpoint: {path}")
        return int(json.loads(archive.read("data"))["num_timesteps"])


def newest_checkpoint(parent):
    """Ignore a partial ZIP from power loss; retain an earlier intact save."""
    candidates = []
    for path in Path(parent).glob("**/nino_ppo*.zip"):
        try:
            candidates.append((checkpoint_steps(path), path.stat().st_mtime_ns, path))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, EOFError):
            continue
    return max(candidates)[2] if candidates else None


def complete_evaluation(parent, episodes):
    candidates = sorted(Path(parent).glob("*/summary.json"), reverse=True)
    for path in candidates:
        try:
            summary = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        if summary.get("complete") and summary.get("episodes") == episodes:
            with (path.parent / "episodes.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            if len(rows) == episodes:
                return rows, summary
    return None


def assert_isolated(domain, partition):
    """Fail instead of joining an existing simulator/trainer in this domain."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            env = dict(item.split(b"=", 1) for item in
                       (entry / "environ").read_bytes().split(b"\0") if b"=" in item)
        except (OSError, ValueError):
            continue
        relevant = ("gz sim" in command or "gz-sim" in command
                    or "ruby /usr/bin/gz" in command
                    or "/nino_rl/train" in command
                    or "ros2 launch nino_rl" in command
                    or "train_rough_curriculum.py" in command)
        same = (env.get(b"ROS_DOMAIN_ID") == str(domain).encode()
                or env.get(b"NINO_ROS_DOMAIN_ID") == str(domain).encode()
                or env.get(b"GZ_PARTITION") == partition.encode())
        if relevant and same:
            raise RuntimeError(f"Domain {domain}/partition {partition} already has PID {entry.name}. "
                               "Stop that rough session in its own terminal before starting this runner.")


class Processes:
    def __init__(self, env):
        self.env, self.children, self.world = env, [], None

    def start(self, command, log):
        log = Path(log)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as stream:
            stream.write("\nCOMMAND " + " ".join(map(str, command)) + "\n")
            stream.flush()
            child = subprocess.Popen(list(map(str, command)), cwd=ROOT, env=self.env,
                                     stdout=stream, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        self.children.append(child)
        return child

    def stop(self, child):
        if child is None:
            return
        # Signal the whole owned session, including any surviving grandchildren
        # if ros2 launch itself has already exited.
        for sig, timeout in ((signal.SIGINT, 20), (signal.SIGTERM, 8), (signal.SIGKILL, 3)):
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                break
            try:
                child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                continue
            # ros2 launch waits for its children. Other commands have none.
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(.2)
        if child in self.children:
            self.children.remove(child)

    def run(self, command, log, timeout=None):
        child = self.start(command, log)
        deadline = time.monotonic() + timeout if timeout else None
        try:
            while child.poll() is None:
                if self.world is not None and self.world.poll() is not None:
                    raise RuntimeError(f"Gazebo exited; inspect {Path(log).parent}/gazebo.log")
                if deadline and time.monotonic() > deadline:
                    raise TimeoutError(f"Command timed out; inspect {log}")
                time.sleep(.5)
            if child.returncode:
                raise RuntimeError(f"Command exited {child.returncode}; inspect {log}")
        finally:
            self.stop(child)

    def close(self):
        for child in self.children.copy()[::-1]:
            self.stop(child)
        self.world = None

    def launch(self, world, directory, gui):
        self.close()
        self.world = self.start([
            "ros2", "launch", "nino_rl", "training_sim.launch.py",
            f"world:={world}", "world_name:=combined_rough_section",
            f"headless:={str(not gui).lower()}",
        ], directory / "gazebo.log")
        self.run(["ros2", "run", "nino_rl", "wait_for_sim"],
                 directory / "readiness.log", timeout=90)


class CurriculumRunner:
    def __init__(self, args, config, manifest, digest, state):
        self.args, self.config, self.manifest, self.digest, self.state = args, config, manifest, digest, state
        self.output = args.output.resolve()
        self.bank_dir = args.bank.resolve().parent
        self.by_id = {item["id"]: item for item in manifest["variants"]}
        env = os.environ.copy()
        env.update(ROS_DOMAIN_ID=str(args.domain), NINO_ROS_DOMAIN_ID=str(args.domain),
                   ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST", GZ_PARTITION=f"nino_rough_{args.domain}")
        self.processes = Processes(env)

    def save(self):
        self.state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
        self.state["stage_name"] = self.config["rough_curriculum"]["stages"][self.state["stage_index"]]["name"]
        save_json(self.output / "curriculum_state.json", self.state)

    def config_file(self, directory, variant, stage_index):
        directory.mkdir(parents=True, exist_ok=True)
        cfg = runtime_config(self.config, stage_index, variant, self.digest)
        path = directory / "config.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        return path

    def evaluate(self, directory, variant, stage_index, episodes, baseline=False, seed=10000):
        cached = complete_evaluation(directory, episodes)
        if cached:
            return cached
        cfg = self.config_file(directory, variant, stage_index)
        self.processes.launch(self.bank_dir / variant["world"], directory, self.args.gui)
        command = ["ros2", "run", "nino_rl", "evaluate_baseline" if baseline else "evaluate",
                   "--config", cfg, "--episodes", episodes, "--seed", seed, "--output", directory]
        if not baseline:
            command += ["--model", self.state["latest_checkpoint"], "--device", self.args.device]
        self.processes.run(command, directory / "evaluation.log")
        self.processes.close()
        result = complete_evaluation(directory, episodes)
        if result is None:
            raise RuntimeError(f"Evaluation is incomplete: {directory}")
        return result

    def recover(self):
        block = self.state.get("active_block")
        if block:
            checkpoint = newest_checkpoint(self.output / block["directory"] / "train")
            if checkpoint:
                self.state["latest_checkpoint"] = str(checkpoint)
                self.state["training_steps"] = checkpoint_steps(checkpoint)
        if self.state["latest_checkpoint"]:
            # Never silently resume a corrupt/missing policy saved in the ledger.
            self.state["training_steps"] = checkpoint_steps(self.state["latest_checkpoint"])
        self.save()

    def train_block(self, block):
        directory = self.output / block["directory"]
        remaining = block["target_steps"] - self.state["training_steps"]
        if remaining > 0:
            variant = self.by_id[block["variant_id"]]
            cfg = self.config_file(directory, variant, block["stage_index"])
            self.processes.launch(self.bank_dir / variant["world"], directory, self.args.gui)
            command = ["ros2", "run", "nino_rl", "train", "--config", cfg,
                       "--device", self.args.device, "--timesteps", remaining,
                       "--checkpoint-every", self.args.checkpoint_every,
                       "--output", directory / "train", "--preflight-timeout", 60]
            if self.state["latest_checkpoint"]:
                command += ["--resume", self.state["latest_checkpoint"]]
            elif self.state.get("init_model"):
                command += ["--init-model", self.state["init_model"]]
            self.state["status"] = "training"
            self.save()
            self.processes.run(command, directory / "train.log")
            self.recover()
            if self.state["training_steps"] < block["target_steps"]:
                raise RuntimeError("Trainer stopped before finishing this block. Resume the runner.")
        self.processes.close()
        block["phase"] = "evaluation"
        self.state["status"] = "evaluation"
        self.save()

    def qualify(self, block):
        index = block["stage_index"]
        stage = self.config["rough_curriculum"]["stages"][index]
        episodes = len(stage["route_ids"]) * int(self.config["rough_curriculum"]["gate"]["episodes_per_route"])
        maps = [self.by_id["original"]]
        if stage["terrain_level"]:
            maps += [item for item in self.manifest["variants"] if item["split"] == "validation"
                     and item["level"] == stage["terrain_level"]]
            if len(maps) == 1:
                raise ValueError("Randomized stages require reserved validation maps")
        evidence = {"stage_index": index, "stage_name": stage["name"], "passed": True, "maps": {}}
        directory = self.output / block["directory"]
        for variant in maps:
            rows, summary = self.evaluate(directory / "evaluation" / variant["id"], variant, index, episodes)
            gate = evaluation_gate(rows, stage["route_ids"], self.config)
            baseline_dir = self.output / "baselines" / f"stage_{index}" / variant["id"]
            _, baseline = self.evaluate(baseline_dir, variant, index, episodes, baseline=True)
            gate["baseline_comparison"] = compare_summaries(baseline, summary)
            evidence["maps"][variant["id"]] = gate
            evidence["passed"] = evidence["passed"] and gate["passed"]
            self.state["last_evaluation"] = evidence
            self.save()
        save_json(directory / "gate.json", evidence)
        self.state["last_evaluation"] = evidence
        self.state["active_block"] = None
        self.state["block_index"] += 1
        if evidence["passed"]:
            self.state["history"].append(dict(stage_index=index, stage_name=stage["name"],
                training_steps=self.state["training_steps"], evidence=str(directory / "gate.json")))
            if index == len(self.config["rough_curriculum"]["stages"]) - 1:
                self.state["status"] = "curriculum_passed"
            else:
                self.state["stage_index"] += 1
                self.state["status"] = "stage_advanced"
        else:
            self.state["status"] = "stage_held"
        self.save()
        print(json.dumps({"status": self.state["status"], "stage": self.state["stage_name"],
                          "steps": self.state["training_steps"], "gate_passed": evidence["passed"]}), flush=True)

    def train(self):
        self.recover()
        while self.state["status"] != "curriculum_passed":
            block = self.state.get("active_block")
            if block is None:
                if self.state["training_steps"] >= self.args.timesteps:
                    self.state["status"] = "budget_reached"
                    self.save()
                    break
                index = self.state["stage_index"]
                stage = self.config["rough_curriculum"]["stages"][index]
                rng = np.random.default_rng(self.config["seed"] + self.state["block_index"])
                variant = choose_variant(self.manifest, stage, rng)
                block = dict(directory=f"blocks/block_{self.state['block_index']:04d}",
                             stage_index=index, variant_id=variant["id"], phase="training",
                             target_steps=min(self.args.timesteps,
                                              self.state["training_steps"] + self.args.block_steps))
                self.state["active_block"] = block
                self.save()
                print(f"Stage {stage['name']}, map {variant['id']}, block target {block['target_steps']}. "
                      f"Live log: {self.output / block['directory'] / 'train.log'}", flush=True)
            if block["phase"] == "training":
                self.train_block(block)
            self.qualify(block)

    def test(self):
        self.recover()
        if not self.state["latest_checkpoint"]:
            raise ValueError("No trained checkpoint available for frozen testing")
        index = len(self.config["rough_curriculum"]["stages"]) - 1
        stage = self.config["rough_curriculum"]["stages"][index]
        episodes = len(stage["route_ids"]) * self.args.test_episodes_per_route
        checkpoint_hash = hashlib.sha256(Path(self.state["latest_checkpoint"]).read_bytes()).hexdigest()
        directory = self.output / "held_out_tests" / checkpoint_hash[:16]
        report = {"checkpoint": self.state["latest_checkpoint"], "checkpoint_sha256": checkpoint_hash,
                  "weight_updates": False, "episodes_per_route_per_map": self.args.test_episodes_per_route,
                  "maps": {}}
        for variant in self.manifest["variants"]:
            if variant["split"] == "test":
                _, summary = self.evaluate(directory / variant["id"], variant, index, episodes, seed=90000)
                report["maps"][variant["id"]] = summary
                save_json(directory / "report.json", report)
        if hashlib.sha256(Path(self.state["latest_checkpoint"]).read_bytes()).hexdigest() != checkpoint_hash:
            raise RuntimeError("Checkpoint changed during frozen evaluation")
        print(f"Frozen unseen-map report: {directory / 'report.json'}", flush=True)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "src/nino_rl/config/rough_route_curriculum.yaml")
    parser.add_argument("--bank", type=Path, default=ROOT / "rl_runs/rough_terrain_bank_v1/manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "rl_runs/rough_curriculum_v1")
    parser.add_argument("--timesteps", type=int, default=500000, help="Total cumulative training budget, including saved steps")
    parser.add_argument("--block-steps", type=int, default=20000)
    parser.add_argument("--checkpoint-every", type=int, default=10000)
    parser.add_argument("--test-episodes-per-route", type=int, default=10)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--domain", type=int, default=78)
    parser.add_argument("--gui", action="store_true", help="Show the runner's Gazebo window")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--init-model", type=Path, help="Optional compatible actor transfer for a fresh run")
    parser.add_argument("--test-only", action="store_true", help="Frozen policy on reserved test maps; requires --resume")
    parser.add_argument("--plan", action="store_true", help="Validate artifacts and show stages without launching anything")
    args = parser.parse_args()
    if min(args.timesteps, args.block_steps, args.checkpoint_every, args.test_episodes_per_route) < 1:
        parser.error("Step budgets and episode counts must be positive")
    if args.resume and args.init_model or args.test_only and not args.resume:
        parser.error("--init-model is fresh-run only; --test-only requires --resume")
    if not 0 <= args.domain <= 232:
        parser.error("ROS domain must be between 0 and 232")
    return args


def main():
    args = arguments()
    config = load_config(args.config)
    if curriculum_stage(config) is None:
        raise ValueError("This runner needs rough_curriculum.enabled")
    manifest, digest = load_bank(args.bank, verify_files=True)
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    if args.plan:
        print(json.dumps({"bank_digest": digest, "variants": len(manifest["variants"]),
                          "domain": args.domain, "stages": config["rough_curriculum"]["stages"],
                          "gate": config["rough_curriculum"]["gate"], "total_step_budget": args.timesteps}, indent=2))
        return
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".runner.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another curriculum runner owns this output directory")
        path = output / "curriculum_state.json"
        if args.resume:
            state = json.loads(path.read_text())
            if state["config_hash"] != config_hash or state["bank_digest"] != digest:
                raise ValueError("Config or terrain bank changed; start a new output directory")
            if args.timesteps < state["target_steps"] and not args.test_only:
                raise ValueError("Do not reduce a saved training budget; --timesteps is cumulative")
            state["target_steps"] = max(args.timesteps, state["target_steps"])
        else:
            if path.exists() or any((output / "blocks").glob("*")):
                raise ValueError("This output already has progress. Use --resume or a new directory")
            state = dict(schema_version=1, config_hash=config_hash, bank_digest=digest,
                         init_model=str(args.init_model.resolve()) if args.init_model else None,
                         stage_index=0, block_index=0, latest_checkpoint=None, training_steps=0,
                         target_steps=args.timesteps, status="ready", active_block=None,
                         last_evaluation=None, history=[])
            (output / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
        assert_isolated(args.domain, f"nino_rough_{args.domain}")
        runner = CurriculumRunner(args, config, manifest, digest, state)
        runner.save()
        original_status = state["status"]
        # Treat terminal Ctrl+C and graceful service termination identically.
        def interrupted(_signal, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        try:
            runner.test() if args.test_only else runner.train()
        except KeyboardInterrupt:
            # Close the trainer FIRST, giving it time to save interrupted.zip.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            runner.processes.close()
            runner.recover()
            runner.state["status"] = original_status if args.test_only else "paused"
            runner.save()
            print("Saved stage and checkpoint; add --resume to the same command.")
            return 130
        except Exception:
            runner.processes.close()
            runner.recover()
            runner.state["status"] = original_status if args.test_only else "error"
            runner.save()
            raise
        finally:
            runner.processes.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
