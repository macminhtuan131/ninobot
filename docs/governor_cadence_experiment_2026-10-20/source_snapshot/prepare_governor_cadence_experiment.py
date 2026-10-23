#!/usr/bin/env python3
"""Prepare the isolated 12-attempt cadence experiment. No launch mode.

The separate executor needs an explicit, hashed execution release. Preparation
does not confirm proposed application thresholds or consume a simulation slot.
"""
import argparse
from collections import Counter
from copy import deepcopy
from itertools import permutations, combinations
import json
from pathlib import Path
import random
import shutil
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/"src/nino_rl"), str(ROOT/"src/nino_control")]
from prepare_governor_h2_protocol import sha, write
from nino_rl.governor_cadence import validate_settings

PARENT = ROOT/"docs/governor_descriptive_survey_2026-10-18"
ARMS = ("full", "reactive_100ms", "reactive_20ms")
SEEDS = (77600, 77601)
REVISIONS = {"src/nino_control/nino_control/governor_core.py", "src/nino_rl/nino_rl/ros_env.py",
             "src/nino_rl/nino_rl/evaluation.py"}
CADENCE = dict(enabled=True, update_seconds=.02, imu_window_seconds=.1,
               target_acceleration_window_seconds=.1, scoring_seconds=.1)


def schedule():
    rng = random.Random(20261020)
    candidates = list(combinations(list(permutations(ARMS)), 4))
    rng.shuffle(candidates)
    orders = next(group for group in candidates if all(
        max(sum(order[pos] == arm for order in group) for pos in range(3))
        - min(sum(order[pos] == arm for order in group) for pos in range(3)) <= 1 for arm in ARMS))
    orders = list(orders); rng.shuffle(orders)
    jobs = []
    for repeat in (1, 2):
        seeds = list(SEEDS); rng.shuffle(seeds)
        for seed in seeds:
            for position, arm in enumerate(orders.pop(), 1):
                jobs.append(dict(attempt=len(jobs)+1, seed=seed, repeat=repeat,
                    triad_id=f"seed_{seed}_repeat_{repeat}", position=position, arm=arm,
                    profile="full" if arm == "full" else "reactive", cold_start=True))
    validate_schedule(jobs)
    return jobs


def validate_schedule(jobs):
    if len(jobs) != 12 or [j["attempt"] for j in jobs] != list(range(1,13)):
        raise ValueError("Exactly12 ordered attempts, no smoke/replacement slots")
    if Counter((j["seed"],j["arm"]) for j in jobs) != Counter({(s,a):2 for s in SEEDS for a in ARMS}):
        raise ValueError("Unbalanced seed/arm counts")
    for s in SEEDS:
        for repeat in (1,2):
            triad = [j for j in jobs if (j["seed"],j["repeat"]) == (s,repeat)]
            if (len(triad) != 3 or {j["arm"] for j in triad} != set(ARMS)
                    or [j["position"] for j in triad] != [1,2,3]
                    or triad[-1]["attempt"]-triad[0]["attempt"] != 2
                    or any(not j["cold_start"] or j["triad_id"] != f"seed_{s}_repeat_{repeat}" for j in triad)):
                raise ValueError("Each adjacent triad must retain all3 assigned controllers")
    for arm in ARMS:
        n = [sum(j["arm"] == arm and j["position"] == pos for j in jobs) for pos in (1,2,3)]
        if max(n)-min(n) > 1:
            raise ValueError("Position balance must be as close as possible within12 slots")


def configs():
    ref = yaml.safe_load((PARENT/"inputs/reactive.yaml").read_text())
    ref["governor"]["world_chunk_seconds"] = .02  # same batching in all three arms
    result = {arm: deepcopy(ref) for arm in ARMS}
    result["full"]["governor"]["parameters"]["profile"] = "full"
    result["reactive_20ms"]["governor"]["cadence_experiment"] = deepcopy(CADENCE)
    for arm, config in result.items():
        if config["control_hz"] != 10. or config["policy_v2"]["simulation_physics_step_seconds"] != .001:
            raise ValueError("Keep original environment and physics timesteps")
        if arm == "reactive_20ms":
            validate_settings(dict(config,evaluation_baseline=True))
    return result


def dependencies():
    from run_governor_h2_replication import execution_dependencies
    return execution_dependencies()


def validate(bundle):
    p = json.loads((bundle/"protocol.json").read_text())
    m = json.loads((bundle/"prepared_manifest.json").read_text())
    if sha(bundle/"protocol.json") != m["protocol_sha256"]:
        raise ValueError("Protocol drift; create an explicit new contract")
    validate_schedule(p["schedule"])
    for name,h in p["bundle_sha256"].items():
        if not (bundle/name).is_file() or sha(bundle/name) != h:
            raise ValueError("Frozen input drift: "+name)
    if dependencies() != p["execution_dependency_sha256"]:
        raise ValueError("Runtime/source dependency drift")
    expected = configs()
    for arm in ARMS:
        if yaml.safe_load((bundle/f"inputs/{arm}.yaml").read_text()) != expected[arm]:
            raise ValueError("Arm-specific change outside cadence hypothesis")
        if json.loads((bundle/f"arm_views/{arm}/protocol.json").read_text())["fixed"] != p["fixed"]:
            raise ValueError("Collector view differs from the experiment's fixed contract")
    if p["budget"]["maximum_attempts"] != 12 or p["thresholds_applied"] or p["H2_decision"] != "not_assessed":
        raise ValueError("Budget/application contract changed")
    return dict(prepared=True, maximum_attempts=12, execution_authorized=False,
                simulator_started=False, physical_integration_validated=False,
                protocol_sha256=m["protocol_sha256"], application_thresholds="proposal_only")


def prepare(output):
    old_manifest = json.loads((PARENT/"analysis/input_sha256.json").read_text())
    originals = {"src/nino_control/nino_control/governor_core.py":"06_governor_core.py",
                 "src/nino_rl/nino_rl/evaluation.py":"09_evaluation.py",
                 "src/nino_rl/nino_rl/ros_env.py":"12_ros_env.py"}
    revisions = {relative:dict(previous_sha256=sha(PARENT/"source_snapshot"/name),
                              previous_snapshot="source_snapshot/previous_"+name,
                              new_sha256=sha(ROOT/relative)) for relative,name in originals.items()}
    for path,h in old_manifest.items():
        f = Path(path)
        if sha(f) != h:
            relative = str(f.relative_to(ROOT))
            if relative not in REVISIONS:
                raise ValueError("Unexpected parent input change: "+relative)
            revisions[relative] = dict(previous_sha256=h, new_sha256=sha(f))
    output.mkdir(parents=True, exist_ok=False)
    (output/"inputs").mkdir(); (output/"source_snapshot").mkdir()
    cs = configs()
    for arm,config in cs.items():
        (output/f"inputs/{arm}.yaml").write_text(yaml.safe_dump(config,sort_keys=False))
    for name in ("scenario.sdf","scenario.json","reference_robot.urdf"):
        shutil.copy2(PARENT/"inputs"/name,output/"inputs"/name)
    old = json.loads((PARENT/"protocol.json").read_text())
    fixed = deepcopy(old["fixed"])
    fixed["only_between_arm_configuration_delta"] = "profile full/reactive and opt-in20ms governor cadence; common20ms world transactions in ALL arms; environment/scoring/follower remain100ms"
    fixed["common_lockstep_transaction_s"] = .02
    # Views let the existing single-episode cold-start collector read the
    # assigned config without changing its original full/reactive profile IDs.
    for arm in ARMS:
        view = output/"arm_views"/arm
        (view/"inputs").mkdir(parents=True)
        profile = "full" if arm == "full" else "reactive"
        shutil.copy2(output/f"inputs/{arm}.yaml",view/f"inputs/{profile}.yaml")
        for name in ("scenario.sdf","scenario.json"):
            shutil.copy2(output/"inputs"/name,view/"inputs"/name)
        write(view/"protocol.json", dict(fixed=fixed))
    for name in ("06_governor_core.py","09_evaluation.py","12_ros_env.py"):
        shutil.copy2(PARENT/"source_snapshot"/name,output/"source_snapshot"/("previous_"+name))
    for relative in sorted(REVISIONS | {"src/nino_rl/nino_rl/governor_cadence.py",
            "src/nino_rl/scripts/prepare_governor_cadence_experiment.py",
            "src/nino_rl/scripts/run_governor_cadence_experiment.py",
            "src/nino_rl/scripts/analyze_governor_cadence_experiment.py"}):
        shutil.copy2(ROOT/relative,output/"source_snapshot"/Path(relative).name)
    jobs = schedule()
    protocol = dict(contract="governor_cadence_100_vs20ms_v1_2026_10_20",status="prepared_no_simulation",
        hypothesis="Earlier sensor-based updates may change executed wheel/body response before subsequent impacts. Benefit unproven; fixed ramp/40ms confirmation can remove the expected timing advantage.",
        budget=dict(maximum_attempts=12, released=False, retries=0, replacements=0, extra_smoke=0,
                    cold_start_each_attempt=True, automatic_extension=False),
        schedule=jobs, fixed=fixed, initialization=old["initialization"],
        outcome_windows=old["outcome_windows"], measurement=old["measurement"],
        parent=dict(protocol_sha256=sha(PARENT/"protocol.json"), parent_data_not_overwritten=True,
                    authorized_source_revisions=revisions),
        update_cadence_s=dict(full=.1,reactive_100ms=.1,reactive_20ms=.02),
        scoring_s=.1, physics_s=.001, follower_s=.1, imu_window_s=.1, target_acceleration_window_s=.1,
        common_world_transaction_s=.02,
        ramp_per_second=.4, target_scale=.9, minimum_hold_seconds=.8, maximum_hold_seconds=1.,
        rearming="Unchanged: HOLD can retrigger and restart its timer;0.8-1.0s limits apply per trigger, not to a whole multi-trigger contact sequence. Log all event-count changes.",
        confirmation_seconds=.04, feature_semantics="Latest hardware state each decision; trailing100ms IMU. Target acceleration uses100ms decision-feedback history, not20ms. Same physical filter constant; discretization/time-quantization effects are part of cadence, no per-frame timer reinterpretation.",
        initialization_semantics="Match empty IMU summary at initial command. Target-acceleration history warmup <=100ms explicitly marked, before fixed800ms startup; never load pre-reset history.",
        fairness="Four triads, 4 observations per arm. Position counts1/1/2 per arm; exact3-position balance impossible with4 triads. Report order, seed blocks and individual repeats. Same seed is not same caster/contact state.",
        analysis=dict(primary_selection=None, contrasts=["reactive_20ms-reactive_100ms","reactive_100ms-full","reactive_20ms-full"],
            pairs="4 intact seed+repeat pairs per contrast,2 per block; never treat overlapping frames as independent trials",
            uncertainty="Paired bootstrap10000, RNG20261020, resample intact triads within each block; equal-weight blocks; descriptive intervals with no power/coverage guarantee",
            missing="All12 assigned attempts remain; retain failures/spikes/null. No zero fill, success-only averages or finite-only CI. Missing required pair makes its estimand/CI unavailable.",
            sampling="Original GT-header slip/joint interpolation, native replay and existing20ms/+10ms sensitivity retained; no favorable-grid selection",
            timing="Use full governor_update_trace.csv for20ms arm, not coarse100ms control_trace. Causal drive receipt/publication checks; distinguish command/target timing from body/joint response; preserve sensor age/support and whole contact sequence.",
            observed_body_response="Report precontact and contact-before-command differences, event-aligned body/wheel trajectories and causal snapshots before command/each subsequent loaded manifold. A contact-induced dip before command is not governor latency or benefit. No claimed identified actuator latency.",
            phase_windows="Retain route and tc+50ms..tc+3s outcomes, first50ms fixed diagnostic, crossing/whole-sequence/recovery. First50ms is NOT necessarily a negative control when20ms arm can act inside it. Pre-intervention comparison uses tc to earliest relative executed command of either arm; before both interventions. No global-x alignment.",
            metrics=["arrival","stall","stopping_2s","tracking","time","native_slip","GT_route_slip","postcontact_slip2_per_m","crossing_slip","whole_sequence_slip","vertical_RMS_peak","body_speed","wheel_targets_actual","torque_commands_limiter","contact_events"],
            stopping="Hard stop on setup/provenance/sensor/cadence/physics/cleanup fault; ordinary task failures retained with no replacement. At12 attempts stop. Mixed/uncertain findings remain inconclusive; no automatic next pilot."),
        integration_checks="First attempts are within12, no separate smoke. Exactly5 micro-decisions per100ms score interval in fast arm, none at endpoint100ms (next step owns it); same total100 physics steps. Native score/IMU accumulation once per100ms; full trace and native replay mandatory.",
        H2_decision="not_assessed", thresholds_applied=False, criteria_status="10percent/+0.5s remain proposals, not accepted",
        automatic_promotion=False, predictor=False, PPO=False, optuna=False, real_robot="on_hold",
        execution_dependency_sha256=dependencies(),
        bundle_sha256={str(p.relative_to(output)):sha(p) for p in output.rglob("*") if p.is_file()})
    write(output/"protocol.json",protocol)
    write(output/"prepared_manifest.json",dict(protocol_sha256=sha(output/"protocol.json"),
        execution_authorized=False, budget_released=False, simulation_attempts=0, thresholds_confirmed=False))
    return validate(output)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--output",type=Path)
    group.add_argument("--validate",type=Path)
    a = p.parse_args()
    print(json.dumps(prepare(a.output) if a.output else validate(a.validate),indent=2))
