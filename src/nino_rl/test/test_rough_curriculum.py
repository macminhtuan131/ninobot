"""Curriculum evidence, isolation, interruption recovery and monitor regression."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import os
import subprocess
import time
import zipfile

import numpy as np
import pytest

PACKAGE = Path(__file__).parents[1]
sys.path.insert(0, str(PACKAGE))
from nino_rl.core import load_config
from nino_rl.rough_curriculum import (choose_variant, curriculum_stage,
                                     evaluation_gate, load_bank, runtime_config)
from nino_rl.routes import RouteSet
from nino_rl.training_contract import training_contract, validate_resume

CONFIG = load_config(PACKAGE / "config/rough_route_curriculum.yaml")


def script(name):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = script("train_rough_curriculum")
MONITOR = script("laya_training_monitor")


def variant(identifier="original", level=0, split="original"):
    return dict(id=identifier, level=level, seed=level + 100, split=split, world="test.sdf")


def rows(route="E1", successes=20, count=20):
    return [dict(route_id=route, success=i < successes, termination="success" if i < successes else "off_path",
                 truth_path_rmse_m=.1, truth_endpoint_error_m=.1 if i < successes else 1.,
                 route_gates_passed=8, route_gates_total=8) for i in range(count)]


def test_inheritance_and_cycle(tmp_path):
    assert CONFIG["ppo"] == load_config(PACKAGE / "config/combined_rough_section.yaml")["ppo"]
    (tmp_path / "base.yaml").write_text("outer: {keep: 1, change: 2}\nlist: [1, 2]\n")
    (tmp_path / "child.yaml").write_text("extends: base.yaml\nouter: {change: 3}\nlist: [4]\n")
    assert load_config(tmp_path / "child.yaml") == dict(outer=dict(keep=1, change=3), list=[4])
    (tmp_path / "base.yaml").write_text("extends: child.yaml\n")
    with pytest.raises(ValueError, match="cycle"):
        load_config(tmp_path / "child.yaml")


@pytest.mark.parametrize("index,count", [(0, 1), (1, 3), (2, 5), (3, 7), (4, 8), (5, 8), (6, 8), (7, 8)])
def test_route_curriculum_retains_previous_goals(index, count):
    cfg = runtime_config(CONFIG, index, variant(), "bank")
    routes = RouteSet(cfg)
    rng = np.random.default_rng(42)
    chosen = {routes.select(rng, i)["id"] for i in range(count)}
    assert chosen == set(curriculum_stage(cfg)["route_ids"])
    assert len(chosen) == count
    assert "E1" in chosen
    if index:
        assert set(CONFIG["rough_curriculum"]["stages"][index-1]["route_ids"]) <= chosen
    if index == 0:
        with pytest.raises(ValueError, match="Unknown route"):
            routes.select(rng, 1, "N1")


def test_pooled_success_cannot_hide_a_bad_route():
    evidence = rows("E1", 20) + rows("N1", 11) + rows("S1", 20)
    assert np.mean([row["success"] for row in evidence]) > .8
    gate = evaluation_gate(evidence, ["E1", "N1", "S1"], CONFIG)
    assert not gate["passed"]
    assert gate["per_route"]["E1"]["passed"]
    assert not gate["per_route"]["N1"]["passed"]


@pytest.mark.parametrize("condition", ["too_few", "rollover", "high_rmse", "odometry_false_goal", "gate_shortcut"])
def test_stage_rejects_unsafe_or_insufficient_evidence(condition):
    evidence = rows(successes=16)
    assert evaluation_gate(evidence, ["E1"], CONFIG)["passed"]
    if condition == "too_few":
        evidence = evidence[:19]
    elif condition == "rollover":
        evidence[-1]["termination"] = evidence[-2]["termination"] = "rollover"
    elif condition == "high_rmse":
        for row in evidence:
            row["truth_path_rmse_m"] = .3
    elif condition == "odometry_false_goal":
        evidence[0]["truth_endpoint_error_m"] = .4
    elif condition == "gate_shortcut":
        evidence[0]["route_gates_passed"] = 0
    assert not evaluation_gate(evidence, ["E1"], CONFIG)["passed"]


def test_csv_boolean_evidence_and_nonfinite_rejection():
    evidence = rows()
    for row in evidence:
        row["success"] = str(row["success"])
    assert evaluation_gate(evidence, ["E1"], CONFIG)["passed"]
    evidence[0]["truth_path_rmse_m"] = "nan"
    with pytest.raises(ValueError, match="Non-finite"):
        evaluation_gate(evidence, ["E1"], CONFIG)


def test_only_training_variants_are_sampled():
    manifest = dict(variants=[variant(), variant("train", 1, "train"),
                              variant("validation", 1, "validation"), variant("test", 1, "test")])
    stage = deepcopy(CONFIG["rough_curriculum"]["stages"][5])
    rng = np.random.default_rng(42)
    sampled = [choose_variant(manifest, stage, rng)["id"] for _ in range(2000)]
    assert set(sampled) == {"original", "train"}
    assert .26 < sampled.count("train") / len(sampled) < .34
    stage["terrain_level"] = 0
    assert choose_variant(manifest, stage, rng)["id"] == "original"


def test_resume_preserves_declared_task_and_rejects_changed_bank_reward():
    first = runtime_config(CONFIG, 0, variant(), "immutable-bank")
    later = runtime_config(CONFIG, 7, variant("R3_train", 3, "train"), "immutable-bank")
    model = SimpleNamespace(nino_training_contract=training_contract(first))
    validate_resume(model, later)
    for change in ("bank", "reward"):
        invalid = deepcopy(later)
        if change == "bank":
            invalid["rough_runtime"]["bank_digest"] = "different-bank"
        else:
            invalid["reward_v2"]["goal_bonus"] = 12345
        with pytest.raises(ValueError, match="contract differs"):
            validate_resume(model, invalid)
    flat = load_config(PACKAGE / "config/combined_flat_section.yaml")
    assert training_contract(flat)["revision"] == 30
    assert "rough_bank_digest" not in training_contract(flat)


def zip_checkpoint(path, steps):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data", json.dumps(dict(num_timesteps=steps)))
        for name in ("policy.pth", "policy.optimizer.pth", "pytorch_variables.pth"):
            archive.writestr(name, b"fixture")


def test_power_loss_falls_back_to_intact_checkpoint(tmp_path):
    valid = tmp_path / "a" / "nino_ppo_interrupted.zip"
    zip_checkpoint(valid, 12345)
    corrupt = tmp_path / "b" / "nino_ppo_final.zip"
    corrupt.parent.mkdir()
    corrupt.write_bytes(b"partial ZIP from power loss")
    assert RUNNER.newest_checkpoint(tmp_path) == valid
    state_path = tmp_path / "curriculum_state.json"
    RUNNER.save_json(state_path, dict(stage_index=2))
    assert json.loads(state_path.read_text())["stage_index"] == 2
    assert not state_path.with_suffix(".json.tmp").exists()


def make_runner(tmp_path):
    args = SimpleNamespace(output=tmp_path, bank=tmp_path / "manifest.json", domain=78,
                           device="cpu", gui=False, test_episodes_per_route=10)
    state = dict(stage_index=0, block_index=0, training_steps=20000, latest_checkpoint="fake.zip",
                 active_block={}, history=[], status="evaluation")
    runner = RUNNER.CurriculumRunner(args, CONFIG, dict(variants=[variant()]), "bank", state)
    return runner


def test_transition_uses_complete_frozen_evaluation_not_training_success(tmp_path, monkeypatch):
    runner = make_runner(tmp_path)
    block = dict(directory="blocks/block_0000", stage_index=0)
    monkeypatch.setattr(RUNNER, "compare_summaries", lambda *_: {"success_delta": 0.})
    runner.evaluate = lambda *_, **__: (rows(successes=0), {})
    runner.qualify(block)
    assert runner.state["stage_index"] == 0
    assert runner.state["status"] == "stage_held"
    runner.evaluate = lambda *_, **__: (rows(successes=20), {})
    runner.qualify(dict(directory="blocks/block_0001", stage_index=0))
    assert runner.state["stage_index"] == 1
    assert len(runner.state["history"]) == 1


def test_random_stage_must_pass_original_and_reserved_validation(tmp_path, monkeypatch):
    runner = make_runner(tmp_path)
    runner.state["stage_index"] = 5
    runner.manifest["variants"].append(variant("R1_validation", 1, "validation"))
    monkeypatch.setattr(RUNNER, "compare_summaries", lambda *_: {})
    def evaluate(_directory, map_variant, *_args, **kwargs):
        successes = 20 if map_variant["id"] == "original" else 0
        return [row for route in CONFIG["rough_curriculum"]["stages"][5]["route_ids"]
                for row in rows(route, successes)], {}
    runner.evaluate = evaluate
    runner.qualify(dict(directory="blocks/block_0000", stage_index=5))
    assert runner.state["stage_index"] == 5
    assert not runner.state["last_evaluation"]["passed"]


def test_resume_recovers_stage_and_steps_within_same_block(tmp_path):
    runner = make_runner(tmp_path)
    checkpoint = tmp_path / "blocks/block_0000/train/stamp/nino_ppo_interrupted.zip"
    zip_checkpoint(checkpoint, 27333)
    runner.state.update(stage_index=2, active_block=dict(directory="blocks/block_0000",
                         stage_index=2, phase="training", target_steps=40000))
    runner.recover()
    assert runner.state["stage_index"] == 2
    assert runner.state["training_steps"] == 27333
    assert runner.state["active_block"]["target_steps"] == 40000
    assert Path(runner.state["latest_checkpoint"]) == checkpoint


def test_laya_aggregates_training_blocks_and_never_evaluation(tmp_path):
    training = tmp_path / "blocks/block_0000/train/stamp/episodes.jsonl"
    training.parent.mkdir(parents=True)
    training.write_text(json.dumps(dict(route_id="E1", success=True, rough_curriculum_stage=0)) + "\n")
    second = tmp_path / "blocks/block_0001/train/stamp/episodes.jsonl"
    second.parent.mkdir(parents=True)
    second.write_text(json.dumps(dict(route_id="N1", success=False, rough_curriculum_stage=1)) + "\n")
    evaluation = tmp_path / "blocks/block_0001/evaluation/stamp/episodes.jsonl"
    evaluation.parent.mkdir(parents=True)
    evaluation.write_text('{"success": true}\n')
    paths, episodes = MONITOR.monitored_episodes(tmp_path)
    assert len(paths) == len(episodes) == 2
    report = MONITOR.report(episodes, 100)
    assert report["current"]["success_rate"] == 0.
    assert set(report["current"]["per_route"]) == {"N1"}
    assert MONITOR.report(episodes, 100, active_stage=2)["current"]["episodes"] == 0


def test_laya_reads_evaluation_booleans_and_ignores_partial_csv_row(tmp_path):
    path = tmp_path / "stamp/episodes.csv"
    path.parent.mkdir()
    path.write_text(
        "episode,seed,controller,route_id,success,termination,truth_path_rmse_m\n"
        "1,10000,ppo,E1,True,success,0.1\n"
        "2,10001,ppo,E1,False,timeout,0.2\n"
        "3,10002,ppo,E1,True,succ")
    paths, episodes = MONITOR.monitored_episodes(tmp_path)
    assert paths == [path]
    assert [row["success"] for row in episodes] == [True, False]
    assert episodes[-1]["seed"] == 10001
    current = MONITOR.report(episodes, 20)["current"]
    assert current["success_rate"] == .5
    assert current["truth_path_rmse_m"] == .15
    assert current["termination_counts"] == {"success": 1, "timeout": 1}


def test_laya_selects_latest_evaluation_without_mixing_runs(tmp_path):
    header = "episode,success,termination\n"
    old = tmp_path / "old/episodes.csv"
    latest = tmp_path / "latest/episodes.csv"
    for path in (old, latest):
        path.parent.mkdir()
    old.write_text(header + "1,True,success\n")
    latest.write_text(header + "1,False,timeout\n")
    os.utime(old, (10, 10))
    os.utime(latest, (20, 20))
    paths, episodes = MONITOR.monitored_episodes(tmp_path)
    assert paths == [latest]
    assert len(episodes) == 1 and episodes[0]["success"] is False


def test_owned_process_interrupt_saves_without_stopping_other_session(tmp_path):
    processes = RUNNER.Processes(os.environ.copy())
    ready, saved = tmp_path / "ready", tmp_path / "saved"
    code = ("import signal,time,pathlib,sys; "
            f"signal.signal(signal.SIGINT, lambda *_: (pathlib.Path({str(saved)!r}).write_text('saved'), sys.exit(0))); "
            f"pathlib.Path({str(ready)!r}).write_text('ready'); time.sleep(60)")
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        child = processes.start([sys.executable, "-c", code], tmp_path / "process.log")
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert ready.exists()
        processes.close()
        assert child.poll() == 0
        assert saved.read_text() == "saved"
        assert other.poll() is None
    finally:
        processes.close()
        other.terminate()
        other.wait(timeout=5)


def test_domain_isolation_detects_only_the_requested_domain():
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID="231", NINO_ROS_DOMAIN_ID="231", GZ_PARTITION="curriculum_test_231")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "gz sim"], env=env)
    try:
        with pytest.raises(RuntimeError, match=str(child.pid)):
            RUNNER.assert_isolated(231, "curriculum_test_231")
        RUNNER.assert_isolated(232, "curriculum_test_232")
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_generated_bank_geometry_provenance_and_split_isolation():
    bank_path = PACKAGE.parents[1] / "rl_runs/rough_terrain_bank_v1/manifest.json"
    if not bank_path.exists():
        pytest.skip("Generate the terrain bank to run artifact verification")
    import xml.etree.ElementTree as ET
    manifest, digest = load_bank(bank_path, verify_files=True)
    assert len(digest) == 64
    assert len(manifest["variants"]) == 19
    normals = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    for item in manifest["variants"]:
        world = ET.parse(bank_path.parent / item["world"])
        ground = world.find("world/model[@name='rough_approach_ground']/link")
        uri = (bank_path.parent / item["mesh"]).resolve().as_uri()
        assert ground.find("visual/geometry/mesh/uri").text == uri
        assert ground.find("collision/geometry/mesh/uri").text == uri
        mesh = np.fromfile(bank_path.parent / item["mesh"], dtype=normals, offset=84)
        assert np.isfinite(mesh["vertices"]).all()
        assert (mesh["normal"][:, 2] > 0).all()
        assert abs(mesh["vertices"][..., 2]).max() <= .33
        # The mesh seam at +/-5.2m is genuinely flat in the saved artifact.
        vertices = mesh["vertices"].reshape(-1, 3)
        assert np.max(abs(vertices[np.isclose(abs(vertices[:, 1]), 5.2), 2])) < 1e-6
        assert min(entry["height_span_m"] for entry in item["route_exposure"].values()) >= .03
