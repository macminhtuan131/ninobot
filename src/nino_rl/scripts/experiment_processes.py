"""Owned-process and evaluation utilities shared by flat simulation tools."""
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[3]


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
                    or "experiment_processes.py" in command)
        same = (env.get(b"ROS_DOMAIN_ID") == str(domain).encode()
                or env.get(b"NINO_ROS_DOMAIN_ID") == str(domain).encode()
                or env.get(b"GZ_PARTITION") == partition.encode())
        if relevant and same:
            raise RuntimeError(f"Domain {domain}/partition {partition} already has PID {entry.name}. "
                               "Stop that simulation session in its own terminal before starting this runner.")



class Processes:
    def __init__(self, env, pi_integrator_profile="legacy"):
        self.env, self.children, self.world = env, [], None
        if pi_integrator_profile not in ("legacy", "conditional_v1"):
            raise ValueError("Unknown PI integrator profile")
        self.pi_integrator_profile = pi_integrator_profile

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
        source = Path(world)
        if not source.is_file():
            source = ROOT / 'src/nino_description/worlds' / source.name
        world_name = ET.parse(source).getroot().find('world').get('name')
        self.world = self.start([
            "ros2", "launch", "nino_rl", "training_sim.launch.py",
            f"world:={world}", f"world_name:={world_name}",
            f"headless:={str(not gui).lower()}",
            f"pi_integrator_profile:={self.pi_integrator_profile}",
        ], directory / "gazebo.log")
        self.run(["ros2", "run", "nino_rl", "wait_for_sim"],
                 directory / "readiness.log", timeout=90)

