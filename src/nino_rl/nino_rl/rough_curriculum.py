"""Evaluation-gated rough routes and bounded terrain-bank curriculum."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np


def curriculum_stage(config):
    curriculum = config.get("rough_curriculum", {})
    if not curriculum.get("enabled", False):
        return None
    stages = curriculum["stages"]
    ids = {route["id"] for route in config["routes"]["definitions"]}
    previous = set()
    for stage in stages:
        active = set(stage["route_ids"])
        if (not active or len(active) != len(stage["route_ids"]) or not active <= ids
                or not previous <= active or stage["terrain_level"] not in (0, 1, 2, 3)
                or not 0. <= float(stage["variant_probability"]) <= 1.):
            raise ValueError("Invalid cumulative rough curriculum stages")
        previous = active
    index = int(config.get("rough_runtime", {}).get("stage_index", 0))
    if not 0 <= index < len(stages):
        raise ValueError("rough_runtime.stage_index is outside the curriculum")
    return stages[index]


def runtime_config(config, stage_index, variant, bank_digest):
    result = deepcopy(config)
    result["rough_runtime"] = {"stage_index": int(stage_index),
                               "terrain_variant_id": variant["id"],
                               "terrain_level": variant["level"],
                               "terrain_seed": variant.get("seed"),
                               "bank_digest": bank_digest}
    curriculum_stage(result)
    return result


def manifest_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def load_bank(path, verify_files=False):
    path = Path(path).expanduser().resolve()
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported rough terrain bank schema")
    seeds = {split: set() for split in ("train", "validation", "test")}
    ids = set()
    for variant in manifest["variants"]:
        if variant["id"] in ids or variant["split"] not in (*seeds, "original"):
            raise ValueError("Invalid/duplicate terrain bank entry")
        ids.add(variant["id"])
        if variant["split"] in seeds:
            seeds[variant["split"]].add(variant["seed"])
        for key in ("world", "mesh"):
            artifact = (path.parent / variant[key]).resolve()
            if not artifact.is_file():
                raise ValueError(f"Missing terrain-bank artifact: {artifact}")
            if verify_files and hashlib.sha256(artifact.read_bytes()).hexdigest() != variant[key + "_sha256"]:
                raise ValueError(f"Terrain bank was modified: {artifact}")
        if (variant["level"] not in (0, 1, 2, 3)
                or not np.isfinite([variant["max_grade"], variant["max_abs_height_m"]]).all()
                or variant["max_grade"] > .60 or variant["max_abs_height_m"] > .33):
            raise ValueError("Terrain-bank variant exceeds slope/height bounds")
        if verify_files:
            world = ET.parse(path.parent / variant["world"])
            ground = world.find("world/model[@name='rough_approach_ground']/link")
            expected_uri = (path.parent / variant["mesh"]).resolve().as_uri()
            if ground is None or any(ground.find(f"{kind}/geometry/mesh/uri").text != expected_uri
                                     for kind in ("visual", "collision")):
                raise ValueError("Terrain-bank world must use its exact mesh for visual and collision; do not relocate the bank")
    if any(seeds[a] & seeds[b] for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))):
        raise ValueError("Train, validation and test terrain seeds must be disjoint")
    if "original" not in ids:
        raise ValueError("Terrain bank needs its fixed original map")
    return manifest, manifest_digest(manifest)


def choose_variant(manifest, stage, rng):
    if stage["terrain_level"] == 0 or rng.random() >= stage["variant_probability"]:
        return next(item for item in manifest["variants"] if item["id"] == "original")
    candidates = [item for item in manifest["variants"] if item["split"] == "train"
                  and item["level"] == stage["terrain_level"]]
    if not candidates:
        raise ValueError("No training terrain variants for the active level")
    return candidates[int(rng.integers(len(candidates)))]


def evaluation_gate(rows, active_ids, config):
    """Every active route must pass, including previously introduced routes."""
    settings = config["rough_curriculum"]["gate"]
    minimum = int(settings["episodes_per_route"])
    if not active_ids or minimum < 1:
        raise ValueError("Evaluation needs active routes and a positive episode count")
    def success(row):
        value = row["success"]
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return float(value.lower() == "true")
        value = float(value)
        if value not in (0., 1.):
            raise ValueError("Evaluation success must be binary")
        return value
    result = {"passed": True, "per_route": {}}
    for route_id in active_ids:
        selected = [row for row in rows if row.get("route_id") == route_id]
        def numeric(key):
            values = [float(row[key]) for row in selected]
            if not np.isfinite(values).all():
                raise ValueError(f"Non-finite evaluation evidence: {route_id}/{key}")
            return values
        successes = [success(row) for row in selected]
        rate = float(np.mean(successes)) if selected else 0.
        rollovers = sum(row["termination"] == "rollover" for row in selected) / max(1, len(selected))
        error = float(np.mean(numeric("truth_path_rmse_m"))) if selected else None
        physical_success = all(
            not success(row) or
            (float(row["truth_endpoint_error_m"]) <= config["goal_tolerance_m"] + 1e-6
             and int(float(row["route_gates_passed"])) == int(float(row["route_gates_total"])))
            for row in selected)
        passed = (len(selected) >= minimum and rate >= settings["success_rate"]
                  and rollovers <= settings["max_rollover_rate"]
                  and error is not None and error <= settings["max_truth_path_rmse_m"]
                  and physical_success)
        result["per_route"][route_id] = dict(episodes=len(selected), success_rate=rate,
            rollover_rate=rollovers, truth_path_rmse_m=error,
            physical_success_consistent=physical_success, passed=bool(passed))
        result["passed"] = result["passed"] and bool(passed)
    return result
