#!/usr/bin/env python3
"""Prepare/validate a bounded H2 protocol; never starts ROS or a simulator."""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT/"rl_runs/governor_pi_repeatability_2026-10-17"
BLOCK_SEEDS = (77500, 77501)
ORDER_SEED = 20261017


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def make_schedule(order_seed=ORDER_SEED):
    """Four rounds; one adjacent pair per seed/round; two AB/two BA per seed."""
    rng = random.Random(order_seed)
    full_first = [True, True, False, False]
    rng.shuffle(full_first)
    schedule = []
    for repeat in range(1, 5):
        blocks = list(BLOCK_SEEDS)
        rng.shuffle(blocks)
        for seed in blocks:
            first = full_first[repeat-1] if seed == BLOCK_SEEDS[0] else not full_first[repeat-1]
            arms = ("full", "reactive") if first else ("reactive", "full")
            for position, profile in enumerate(arms, 1):
                schedule.append(dict(attempt=len(schedule)+1, round=repeat,
                    pair_id=f"seed_{seed}_repeat_{repeat}", seed=seed, repeat=repeat,
                    position_in_pair=position, profile=profile, cold_start=True))
    validate_schedule(schedule)
    return schedule


def validate_schedule(schedule):
    if len(schedule) != 16 or [r["attempt"] for r in schedule] != list(range(1, 17)):
        raise ValueError("Exactly sixteen ordered attempts required")
    counts = Counter((r["seed"], r["profile"]) for r in schedule)
    if counts != Counter({(s,p):4 for s in BLOCK_SEEDS for p in ("full","reactive")}):
        raise ValueError("Unbalanced block/arm counts")
    for seed in BLOCK_SEEDS:
        first = []
        for repeat in range(1,5):
            pair = [r for r in schedule if r["seed"] == seed and r["repeat"] == repeat]
            if len(pair) != 2 or {r["profile"] for r in pair} != {"full","reactive"}:
                raise ValueError("Each replicate must contain both arms")
            if pair[1]["attempt"] != pair[0]["attempt"]+1 or [r["position_in_pair"] for r in pair] != [1,2]:
                raise ValueError("Pair must remain adjacent")
            if any(r["round"] != repeat or not r["cold_start"] or r["pair_id"] != f"seed_{seed}_repeat_{repeat}" for r in pair):
                raise ValueError("Invalid round/pair/reset label")
            first.append(pair[0]["profile"])
        if Counter(first) != Counter(full=2,reactive=2):
            raise ValueError("Each seed requires two AB and two BA orders")
    for repeat in range(1,5):
        first=[r["profile"] for r in schedule if r["round"]==repeat and r["position_in_pair"]==1]
        if Counter(first) != Counter(full=1,reactive=1):
            raise ValueError("First-arm order must balance within each round")


def arm_config(base, profile):
    if profile not in ("full","reactive"):
        raise ValueError("Unknown arm")
    config=deepcopy(base)
    config["governor"]["parameters"]["profile"]=profile
    return config


def application_issues(application):
    issues=[]
    if application.get("primary_metric") not in ("postcontact_vertical_sample_rms_m_s2","postcontact_GT_slip_square_per_m"):
        issues.append("primary_metric_not_selected")
    for name in ("minimum_relative_improvement","maximum_added_route_seconds"):
        v=application.get(name)
        if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v):
            issues.append(name+"_not_fixed")
        elif (name=="minimum_relative_improvement" and not 0<v<1) or (name=="maximum_added_route_seconds" and v<0):
            issues.append(name+"_invalid")
    if application.get("requirement_origin") not in ("user_factory_requirement","user_accepted_engineering_assumption"):
        issues.append("application_requirement_origin_not_confirmed")
    return issues


def validate_bundle(directory):
    manifest=json.loads((directory/"prepared_manifest.json").read_text())
    if sha(directory/"protocol.json") != manifest["protocol_sha256"]:
        raise ValueError("Prepared protocol changed; create an explicit new revision")
    protocol=json.loads((directory/"protocol.json").read_text())
    validate_schedule(protocol["schedule"])
    for name,h in protocol["frozen_bundle_sha256"].items():
        p=directory/name
        if not p.is_file() or sha(p)!=h:
            raise ValueError("Frozen bundle changed: "+name)
    changed=[p for p,h in protocol["workspace_reference_sha256"].items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    if changed:
        raise ValueError("Workspace contract changed: "+str(changed))
    base=yaml.safe_load((directory/"inputs/base_config.yaml").read_text())
    for profile in ("full","reactive"):
        actual=yaml.safe_load((directory/f"inputs/{profile}.yaml").read_text())
        if actual!=arm_config(base,profile):
            raise ValueError("Unapproved arm-specific change")
    app=json.loads((directory/"application_requirements.json").read_text())
    pending=application_issues(app)
    # Completing the application form cannot silently authorize a launch.
    return dict(structure_valid=True, frozen_files_verified=len(protocol["frozen_bundle_sha256"]),
        workspace_references_verified=len(protocol["workspace_reference_sha256"]),
        maximum_attempts=16, pending_application_fields=pending,
        budget_released=False, execution_authorized=False,
        run_allowed=False, simulator_started=False,
        next_step="Fix application values, seal their hash before results, and review/release this concrete budget separately. This tool has no execution mode.")


def prepare(output):
    baseline=json.loads((REFERENCE/"protocol_before_results.json").read_text())
    sources={Path(p):h for p,h in baseline["source_sha256"].items()}
    for p,h in sources.items():
        if sha(p)!=h:
            raise ValueError("PI-batch source drift: "+str(p))
    config=REFERENCE/"config.yaml"
    world=REFERENCE/"attempt_01/confirmation/height/scenario.sdf"
    metadata=world.with_suffix(".json")
    robot=next((REFERENCE/"attempt_01").rglob("robot_description.urdf"))
    expected={config:"74a7c9a56eb964727df71998090c1509760aaaf0a9c539a419baff9cabb41235",
        world:"8b1fc28bae7254c877cd53a4038924f567f674f0da43a04f200d429a5a26b4fd",
        robot:"6e74ef55720b5878ddca1c60fe6a7b4e5d82b7a68aa4934d2d1a026451c4878b"}
    for p,h in expected.items():
        if sha(p)!=h:
            raise ValueError("Reference changed: "+str(p))
    base=yaml.safe_load(config.read_text())
    gp=base["governor"]["parameters"]
    assert gp["trigger_to_brake_delay_seconds"]==0 and gp["target_scale"]==.9
    assert base["reset_standstill_gate"]["enabled"] and base["navigation"]["straight_speed_m_s"]==.4
    cable=ET.parse(world).getroot().find("world/model[@name='cable_bumps']/link/collision/geometry/capsule")
    assert float(cable.findtext("radius"))==.003
    output.mkdir(parents=True,exist_ok=False)
    (output/"inputs").mkdir();(output/"source_snapshot").mkdir()
    for source,name in ((config,"base_config.yaml"),(world,"scenario.sdf"),(metadata,"scenario.json"),(robot,"reference_robot.urdf")):
        shutil.copy2(source,output/"inputs"/name)
        sources[source]=sha(source)
    for profile in ("full","reactive"):
        (output/f"inputs/{profile}.yaml").write_text(yaml.safe_dump(arm_config(base,profile),sort_keys=False))
    extras=[ROOT/"src/nino_rl/scripts"/n for n in ("audit_gt_timestamp_slip.py","audit_governor_phase_slip.py",
        "run_governor_frozen_repeats.py","run_frozen_governor_confirmation.py")]
    extras += [ROOT/"src/nino_rl/nino_rl"/n for n in ("governor_logger.py","core.py")]
    extras += [ROOT/"src/nino_description/urdf/nino.urdf.xacro",Path(__file__).resolve()]
    for p in extras:
        sources[p]=sha(p)
    for index,p in enumerate(sorted(sources)):
        shutil.copy2(p,output/"source_snapshot"/f"{index:02d}_{p.name}")
    application=dict(status="pending_user_requirement_no_launch",primary_metric=None,
        minimum_relative_improvement=None,maximum_added_route_seconds=None,requirement_origin=None,
        units=dict(minimum_relative_improvement="fraction, e.g. 0.10 means 10%, not a recommended threshold",
                   maximum_added_route_seconds="simulation seconds per E1 route; not startup/reset wait"),
        secondary_quality_rule="No increase in the other postcontact metric or whole-route vibration/slip; if a noninferiority margin is needed, explicitly revise and seal it before any run.")
    write(output/"application_requirements.json",application)
    schedule=make_schedule()
    with (output/"run_order.csv").open("w") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(schedule[0]));writer.writeheader();writer.writerows(schedule)
    bundle={str(p.relative_to(output)):sha(p) for d in (output/"inputs",output/"source_snapshot") for p in d.iterdir()}
    bundle["run_order.csv"]=sha(output/"run_order.csv")
    protocol=dict(contract="H2_replicated_frozen_reactive_v1_2026_10_17",status="prepared_not_funded_not_run",
        purpose="Screen H2 for one fixed 6mm rigid cable-like obstacle at 0.4m/s. Not H1/H3 or sim-to-real.",
        budget=dict(maximum_attempts=16,blocks=2,arms=2,replicates_per_cell=4,maximum_pairs=8,
                    released=False,retries=0,replacements=0,automatic_extension=False),
        randomization=dict(seed=ORDER_SEED,algorithm="Python random.Random; four rounds, paired adjacent arms; opposite first arms across seeds per round and two AB/two BA per seed",locked_csv="run_order.csv"),
        schedule=schedule,block_interpretation="New seed labels 77500/77501 on the SAME fixed geometry, not two independent obstacle scenarios or identical-state branches",
        fixed=dict(route="E1",start=[0.,0.,0.],goal=[6.45,0.,0.],cruise_m_s=.4,physics_step_s=.001,control_interval_s=.1,
            IMU_period_s=.02,floor="10x7x0.1m box, top z=0",obstacle="rigid capsule, diameter6mm, cylindrical section4m, x3.1m, yaw+8deg",
            effective_geometry_source="inputs/scenario.sdf, not inherited metadata/config tags",robot_expected_sha256=expected[robot],
            PI=base["drive_controller"]["parameters"],governor_parameters=gp,
            randomization_disabled=["geometry","adaptive items","terrain/curriculum","dynamics domain randomization"],
            only_between_arm_configuration_delta="governor.parameters.profile: full versus reactive",
            note="Inherited config/metadata contain legacy radius/mesh tags. Preserve bytes; effective collision is verified SDF. PPO/reward fields are inert in this baseline evaluation."),
        initialization=dict(cold_start_each_attempt=True,owned_simulator_sequential=True,post_reset_quiet_s=.5,maximum_gate_wait_sim_s=5.,
            body_and_driven_wheel_speed_limit_m_s=.01,yaw_rate_limit_rad_s=.03,gate_wait_outside_native_episode_time=True,
            post_arrival_observe_sim_s=2.,same_snapshot_claim=False,control_trace_required=True,command_ownership="one inline evaluation governor; no second ROS speed governor"),
        outcome_windows=dict(primary="first recorded positive-obstacle manifold +0.05s to +3.0s; fixed for both arms; not guaranteed to remove entire first-impact tail",
            whole_route="unchanged first control input through final action end",legacy_crossing="unchanged +50ms to existing clearance plane",
            contact_sequence="existing max(clearance,last closed manifold end+0.2s)",
            recovery="existing concurrent CRUISE scale>=0.98, executed v>=0.392m/s, body v>=0.95 precontact median sustained0.3s after contact end",
            negative_control="precontact approach and first50ms only when every GT/joint interpolation support precedes the first reduced executed command; otherwise mark contaminated/unavailable, never use it as a causal negative control"),
        measurement=dict(native="Keep replay and native scores unchanged, separate namespace",
            vertical="Unfiltered original IMU header-time samples; sample RMS and peak; raw values retained; existing signal_stats coverage>=0.98",
            slip="gt_timestamp_series + integrate at original GT stamps; interpolate joints only, maxgap10.001ms, no extrapolation; same ratio clipping/denominator; slip_square_per_m units s/m, not joules",
            required=["arrival","stall/timeout/failure","physical path RMSE","native route time","post-arrival2s stop","whole-route and postcontact vibration/slip","full contact/recovery sequence","approach/caster diagnostics","executed command/targets/raw joints/body response","timestamp ages/skew/coverage"],
            sensitivity="Retain original-GT slip plus existing20ms grid and+10ms shifted grid on same windows. Require same direction for primary slip effect; report all. No downsampling IMU to10Hz for scoring, no favorable grid selection.",
            protection="No spike removal, no zero imputation, no changes to historical studies/models or parameter configuration"),
        causal_scope=dict(before_contact="All commands/governor events and approach pose/speed reported. Any precontact reduced command or failed predeclared approach caliper prevents a clean postcontact-H2 pass; retain attempt, do not exclude/replace.",
            calipers=dict(window_s=[-.3,-.05],speed_m_s=[.39,.41],abs_y_m=.01,abs_yaw_deg=2.,abs_roll_pitch_deg=2.,
                paired_median_speed_difference_m_s=.005,paired_median_y_difference_m=.005,paired_yaw_difference_deg=1.),
            authority="Report detector time, first reduced final executed command and wheel target, body/encoder response, and next loaded-contact times. H2 cannot pass without intervention preceding at least one subsequent loaded contact in each reactive episode; magnitude benefit requires randomized arm comparison, not a body-speed dip alone.",
            same_time_reference_not_in_budget="This two-arm screen only establishes local H2 including the cost of slowdown. No advantage beyond driving slower, tuned-reactive H3, generalization or factory readiness claim."),
        analysis=dict(unit="episode, not frames/contact points; eight chronological random-order pairs nested in two fixed seed blocks",
            estimand="For metric M, block benefit=1-mean(M_reactive,4)/mean(M_full,4); aggregate benefit=equal-weight mean of the two block benefits. Undefined PI denominator -> unavailable/inconclusive, no epsilon rescue.",
            timing="equal-block mean of paired governor-minus-PI route seconds; report every pair and each block",
            uncertainty="Prespecified paired bootstrap within each fixed seed: resample four intact pairs with replacement in each block,10000 replicates, rng20261018; percentile95% interval. No frame bootstrap or population-of-terrains inference; tiny-n coverage not guaranteed.",
            failures="Count all16 assigned positions and all attempted outcomes. Any unsuccessful physical arrival/stop means no promotion. Missing/censored quality remains null and denominators reported; no success-only aggregate used for decision.",
            early_stopping="No early benefit/futility check; hard-stop on readiness/timestamp/provenance/measurement integrity, rollover or invalid physical state; no retry/replacement. Ordinary timeout/stall/arrival miss retained and subsequent slots may proceed if infrastructure/physical validity intact. Early stop -> incomplete, never pass.",
            historical_data="77400/77401 and earlier trials are diagnostics only; no pooling into confirmation totals or selecting thresholds from outcomes"),
        decision=dict(application_file="application_requirements.json",application_values_must_be_sealed_before_first_attempt=True,
            pass_requirements=["all16 attempts complete, all8 arrivals/controller with2s stable stop, reporting/provenance/approach gates pass",
                "executed intervention has timing opportunity before subsequent loaded contact in every reactive episode",
                "both block primary improvements>=application minimum; aggregate primary lower95% bootstrap bound>=same minimum",
                "other postcontact quality metric and whole-route vibration/slip point estimates do not worsen in either block; complete-sequence primary benefit has same direction",
                "mean governor time<=18.5s and<=1.05xPI, mean physical path RMSE<=1.05xPI, each block; aggregate upper95% interval of added route seconds<=application allowed added seconds",
                "predeclared slip sensitivity does not reverse the direction of the selected primary slip conclusion"],
            pass_next="Review a small classical governor tuning budget on separate development seeds; no automatic execution or predictor/PPO release",
            not_pass="Stop this frozen intervention configuration/small-screen branch; distinguish observed harm from inconclusive uncertainty. No automatic extra episodes, delay search, penalty change or claim that H2 is globally false."),
        prerequisites=["application primary metric/minimum worthwhile improvement/allowed extra seconds and origin confirmed",
            "seal application file hash and protocol/references/order manifest before first attempt",
            "review/release max16 attempt budget explicitly; no implied release from completing the form",
            "implement/review a separate bounded executor preserving ordinary failures; existing four-attempt PI runner must not be reused as-is",
            "verify actual spawned world/robot and effective arm configuration hashes at launch"],
        execution=dict(authorized=False,simulator_started=False,runner_implemented=False,no_launch_command=True),
        frozen_bundle_sha256=bundle,workspace_reference_sha256={str(p.relative_to(ROOT)):h for p,h in sources.items()})
    write(output/"protocol.json",protocol)
    write(output/"prepared_manifest.json",dict(protocol_sha256=sha(output/"protocol.json"),
        initial_application_sha256=sha(output/"application_requirements.json"),
        application_sealed=False,execution_authorized=False,
        note="Initial application hash records the pending form, not approved thresholds. Seal final requirements separately before any run; no simulator execution in this tool."))
    write(output/"validation.json",validate_bundle(output))
    print(json.dumps(json.loads((output/"validation.json").read_text()),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output",type=Path);mode.add_argument("--validate",type=Path)
    args=parser.parse_args()
    if args.validate:
        print(json.dumps(validate_bundle(args.validate),indent=2))
    else:
        prepare(args.output)


if __name__=="__main__":
    main()
