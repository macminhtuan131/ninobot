"""E2 single-slot coordinator. Offline qualification never allocates physics.

run-next needs a separately allocated release, pinned qualification and reviewed
previous slot. Failure consumes the claimed slot and closes the ledger. No retry.
"""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import time
import traceback
import xml.etree.ElementTree as ET

import numpy as np
from . import obstacle_authority_draft as draft
from . import obstacle_authority_runtime as context
from .obstacle_authority_metrics import assess
from .residual_workflow import save, json_value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def append(path, row):
    with Path(path).open("a") as stream:
        stream.write(json.dumps(row, default=json_value, allow_nan=False) + "\n")
        stream.flush()


def installation_parity():
    pairs = []
    for name in ("obstacle_authority_draft", "obstacle_authority_runtime",
                 "obstacle_authority_runner", "obstacle_authority_metrics"):
        source = draft.ROOT / "src/nino_rl/nino_rl" / (name + ".py")
        installed = list((draft.ROOT / "install/nino_rl/lib").glob("python*/site-packages/nino_rl/" + name + ".py"))
        if len(installed) != 1 or sha(source) != sha(installed[0]):
            raise ValueError("E2 source/install mismatch: " + name)
        pairs.append(dict(source=str(source), installed=str(installed[0]), sha256=sha(source)))
    return pairs


def verify_world(path):
    world = ET.parse(path).getroot().find("world")
    if {m.get("name") for m in world.findall("model")} != {"enclosed_hall", "controlled_box_floor", "cable_bumps"}:
        raise ValueError("E2 fixed world contains undeclared models")
    collision = world.find("model[@name='cable_bumps']/link/collision[@name='C1_collision']")
    if (collision is None or [float(v) for v in collision.findtext("pose").split()] != [0.65, 0, 0.003, 1.57079632679, 0, 0]
            or float(collision.findtext("geometry/cylinder/radius")) != .003
            or float(world.findtext("model[@name='controlled_box_floor']/link/collision/surface/friction/ode/mu")) != 1.):
        raise ValueError("E2 nominal world geometry/friction mismatch")
    return dict(path=str(path), sha256=sha(path), scenario="box_c1_6mm", randomized=False)


def require_test_report(path):
    path = Path(path).expanduser().resolve()
    tree = ET.parse(path).getroot()
    suites = list(tree.iter("testsuite"))
    if not suites or any(int(s.get(k, "0")) for s in suites for k in ("errors", "failures", "skipped")):
        raise ValueError("E2 software test gate not passed")
    classes = {r.get("classname", "").split(".")[-1] for r in tree.iter("testcase")}
    if not {"test_obstacle_authority_runtime", "test_obstacle_authority_runner"} <= classes:
        raise ValueError("E2 runtime/fault injection test coverage missing")
    return dict(path=str(path), sha256=sha(path), tests=sum(int(s.get("tests", "0")) for s in suites))


def qualify(out, test_report):
    out = Path(out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    try:
        draft.load(); ident = context.identity(); tests = require_test_report(test_report)
        parity = context.neutral_parity()
        from .residual_sim_pilot import prepare_worlds
        (out / "worlds").mkdir()
        worlds = prepare_worlds(out / "worlds")
        world = verify_world(worlds["box_c1_6mm"])
        report = dict(status="offline_e2_runtime_qualified_not_Gazebo", identity=ident,
            protocol_sha256=sha(draft.PLAN_PATH), neutral_parity=parity,
            software_tests=tests,
            world=world,
            installation=installation_parity(), runtime_implemented=True,
            allocated_attempts=0, new_physics_steps=0, optimizer_updates=0, hardware_actions=0,
            scope="Synthetic wrapper/reference parity only; runtime/contact dynamics not validated")
        if context.identity() != ident:
            raise ValueError("E2 source changed during qualification")
        save(out / "qualification.json", report)
        save(out / "manifest.json", dict(status="completed", files={str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()}))
        return report
    except BaseException as exc:
        save(out / "failure.json", dict(error=repr(exc), new_physics_steps=0)); raise


def require_release(path, root):
    release = read(path); plan = draft.load()
    if (release.get("protocol_id") != draft.PROTOCOL_ID or release.get("runtime_id") != context.CONTEXT_ID
            or release.get("released") is not True or release.get("decision_rules_accepted") is not True
            or type(release.get("allocated_attempts")) is not int or not 1 <= release["allocated_attempts"] <= 12
            or release.get("allowed_slot_ids") != [r["id"] for r in plan["proposed_attempts"][:release["allocated_attempts"]]]
            or release.get("retries") != 0 or release.get("hardware_actions") != 0
            or release.get("optimizer_updates") != 0):
        raise ValueError("No E2 physics allocation; offline preparation cannot grant release")
    if Path(release["root"]).expanduser().resolve() != Path(root).expanduser().resolve():
        raise ValueError("E2 release is bound to another root")
    if release.get("protocol_sha256") != sha(draft.PLAN_PATH) or release.get("identity") != context.identity():
        raise ValueError("Released E2 source/protocol identity changed")
    qualification = Path(release["qualification"]).expanduser().resolve()
    if sha(qualification) != release["qualification_sha256"]:
        raise ValueError("E2 qualification changed")
    q = read(qualification)
    if q["status"] != "offline_e2_runtime_qualified_not_Gazebo" or q["identity"] != release["identity"]:
        raise ValueError("Current E2 software qualification missing")
    if require_test_report(q["software_tests"]["path"]) != q["software_tests"]:
        raise ValueError("E2 software evidence changed")
    manifest = read(qualification.parent / "manifest.json")
    if manifest["status"] != "completed" or manifest["files"][qualification.name] != sha(qualification):
        raise ValueError("E2 qualification manifest mismatch")
    for name, digest in manifest["files"].items():
        candidate = (qualification.parent / name).resolve()
        if not candidate.is_relative_to(qualification.parent) or sha(candidate) != digest:
            raise ValueError("E2 qualification evidence changed")
    return release


def next_slot(state, plan):
    if state.get("status") != "ready":
        raise ValueError("E2 stopped or awaiting explicit review; no slot may start")
    used = state["attempts"]
    if len(used) >= 12 or [r["slot"] for r in used] != plan["proposed_attempts"][:len(used)]:
        raise ValueError("E2 slots exhausted or ledger order changed")
    if used and used[-1].get("reviewed_summary_sha256") != used[-1].get("summary_sha256"):
        raise ValueError("Previous E2 slot has not been reviewed")
    if state["consumed_wall_s"] >= plan["proposed_budget"]["wall_seconds_batch"]:
        raise ValueError("E2 batch wall budget exhausted")
    return deepcopy(plan["proposed_attempts"][len(used)])


def preflight(root, plan):
    installation_parity()
    budget = plan["proposed_budget"]
    disk = shutil.disk_usage(root).free
    minimum = budget["estimated_raw_bytes"] + budget["estimated_metadata_margin_bytes"] + budget["free_space_reserve_bytes"]
    if disk < minimum:
        raise ValueError("E2 disk estimate+reserve not available")
    # All owned experiments share localhost domain129: refuse other active Sim engines.
    active = []
    for proc in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            if int(proc.parent.name) == os.getpid(): continue
            args = proc.read_bytes().decode(errors="replace").split("\0")
            if not args or not args[0]: continue
            name = Path(args[0]).name
            if ("gz-sim" in name or (name == "gz" and "sim" in args)
                    or any(a.startswith("nino_rl.common_training_studio") for a in args)):
                active.append(int(proc.parent.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError): pass
    if active:
        raise ValueError("Another simulation owns the environment: " + str(active))
    return dict(free_bytes=disk, required_estimate_and_reserve_bytes=minimum,
                disk_estimate_is_bound=False, no_other_simulation_detected=True)


def evaluate_attempt(out, slot, world):
    from . import residual_drive_readiness as ready, residual_common_td3 as frozen
    from .reliable_episode import EpisodeLifecycle
    from .pi_screen_contract import require_parameters
    c, g, task, condition = context.configuration(slot["stop_s"])
    lp = ready.parent.lifecycle_protocol(True)
    lp.update(protocol_id=context.CONTEXT_ID, training_episodes_per_seed_maximum=1)
    backend = EpisodeLifecycle(c, out / "episodes", world, g, task, condition, lp,
        backend_factory=lambda *args: context.OraclePiBackend(*args, allow_physics=True))
    ident = context.identity()
    env = context.environment(c, backend, task, condition, slot["level"], contract_identity=ident)
    rows, error = [], None
    save(out / "configuration.json", dict(config=c, task=task, guidance=g, condition=condition, slot=slot, identity=ident))
    try:
        _, reset = env.reset(seed=701 + slot["block"])
        save(out / "reset.json", reset)
        ready.require_ready(backend.view())
        epoch = backend.start_time
        for tick in range(140):
            ready.require_ready(backend.view())
            append(out / "control_attempts.jsonl", dict(tick=tick, declared_level=slot["level"]))
            _, reward, term, trunc, info = env.step(np.array([slot["level"]], np.float32))
            row = dict(step=tick, reward=reward, terminated=term, truncated=trunc, done=bool(term or trunc),
                       **info, episode_namespace=backend.namespace, qualification_condition=slot)
            append(out / "trace.jsonl", row)  # preserve failed rows BEFORE validation
            context.verify_transition(row, rows[-1] if rows else None, epoch, ident)
            rows.append(row)
            if term or trunc: break
    except BaseException as exc:
        error = exc
        save(out / "failure.json", dict(error=repr(exc), valid_rows=len(rows), traceback=traceback.format_exc()))
        raise
    finally:
        try: env.close()
        except BaseException as cleanup:
            save(out / "closure_failure.json", dict(error=repr(cleanup), original=repr(error))); raise
    target = backend.directory / backend.namespace
    require_parameters(read(next((target / "backend").glob("episode_*/pi_screen_parameters.json"))), .10)
    summary = frozen.baseline.summarize(rows, target)
    diagnostic = frozen.timing.timestamp_diagnostic(target, rows)
    metrics = assess(rows, sorted((target / "backend").glob("episode_*/raw_samples.jsonl")))
    if len(rows) != 140 or not summary["functional_proposal_pass"] or not diagnostic["valid"]:
        raise ValueError("E2 task/native replay/timestamp gate failed")
    summary.update(slot=slot, status="measurement_pass_pending_review", timestamp_diagnostic=diagnostic,
                   contact_metrics=metrics, comparison_pending=True, actor_loads=0, optimizer_updates=0,
                   hardware_actions=0, training_transitions=0, task_transitions=len(rows))
    save(out / "summary.json", summary)
    return summary


def run_next(root, release_path):
    root = Path(root).expanduser().resolve()
    release = require_release(release_path, root)  # reject before process/artifact allocation
    plan = draft.load(); root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = root / "ledger.json"
        state = read(state_path) if state_path.exists() else dict(status="ready", attempts=[], consumed_wall_s=0.0,
                                                                  release_sha256=sha(release_path))
        if state["release_sha256"] != sha(release_path):
            raise ValueError("Release changed; no slot refill or reuse")
        state['allocated_attempts'] = release['allocated_attempts']
        if len(state['attempts']) >= release['allocated_attempts']:
            raise ValueError('E2 allocated prefix exhausted; no unallocated next slot')
        slot = next_slot(state, plan)
        check = preflight(root, plan)  # readiness failures before claim consume no slot
        out = root / slot["id"]
        if out.exists(): raise ValueError("E2 slot artifact already exists; no overwrite")
        state["status"] = "running"
        claim = dict(slot=slot, status="claimed", started_monotonic_s=time.monotonic())
        state["attempts"].append(claim); save(state_path, state)
        def timeout(*_): raise TimeoutError("E2 attempt wall deadline reached; no retry")
        old = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(max(1, int(min(300, 3600-state["consumed_wall_s"]))))
        try:
            out.mkdir(); save(out / "preflight.json", check); save(out / "release.json", release)
            from .residual_sim_pilot import prepare_worlds
            (out / "worlds").mkdir()
            worlds = prepare_worlds(out / "worlds")
            save(out / "world_check.json", verify_world(worlds["box_c1_6mm"]))
            summary = evaluate_attempt(out, slot, worlds["box_c1_6mm"])
            if context.identity() != release["identity"]:
                raise ValueError("E2 source changed during slot")
            claim.update(status="measurement_pass", summary_sha256=sha(out / "summary.json"))
            state["status"] = "awaiting_review"
        except BaseException as exc:
            claim.update(status="failed", error=repr(exc)); state["status"] = "closed_failed"
            if out.is_dir(): save(out / "runner_failure.json", dict(error=repr(exc), traceback=traceback.format_exc()))
            raise
        finally:
            signal.alarm(0); signal.signal(signal.SIGALRM, old)
            duration = time.monotonic()-claim["started_monotonic_s"]
            claim["wall_s"] = duration; state["consumed_wall_s"] += duration
            save(state_path, state)
            if out.is_dir():
                save(out / "manifest.json", dict(status=claim["status"],
                    files={str(p.relative_to(out)):sha(p) for p in out.rglob("*") if p.is_file() and p != out / "manifest.json"}))
        return summary


def review_slot(root, expected_summary_sha256):
    root = Path(root).expanduser().resolve()
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = read(root / "ledger.json")
        if state["status"] != "awaiting_review": raise ValueError("No E2 slot awaiting review")
        claim = state["attempts"][-1]; path = root / claim["slot"]["id"] / "summary.json"
        manifest = read(path.parent / "manifest.json")
        if manifest["status"] != "measurement_pass": raise ValueError("E2 closure/manifest did not pass")
        for name, digest in manifest["files"].items():
            if sha(path.parent / name) != digest: raise ValueError("E2 slot data changed")
        if sha(path) != expected_summary_sha256 or sha(path) != claim["summary_sha256"]:
            raise ValueError("Reviewed E2 summary hash mismatch")
        result = read(path)
        if result["status"] != "measurement_pass_pending_review": raise ValueError("E2 measurement not passed")
        claim["reviewed_summary_sha256"] = expected_summary_sha256
        limit = state.get('allocated_attempts', 12)
        state["status"] = ("ready" if len(state["attempts"]) < limit else
                           "completed_pending_comparison" if limit == 12 else "allocation_exhausted")
        save(root / "ledger.json", state)
        return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    q = sub.add_parser("qualify"); q.add_argument("--output", required=True); q.add_argument("--test-report", required=True)
    run = sub.add_parser("run-next"); run.add_argument("--root", required=True); run.add_argument("--release", required=True)
    review = sub.add_parser("review"); review.add_argument("--root", required=True); review.add_argument("--summary-sha256", required=True)
    args = parser.parse_args(argv)
    result = qualify(args.output, args.test_report) if args.mode == "qualify" else (run_next(args.root, args.release)
              if args.mode == "run-next" else review_slot(args.root, args.summary_sha256))
    print(json.dumps(result, default=json_value, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__": main()
