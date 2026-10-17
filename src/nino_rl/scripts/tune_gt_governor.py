#!/usr/bin/env python3
"""Bounded six-point classical-governor study; GT-timestamp objective, no RL."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import optuna
import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from nino_rl.core import load_config
from nino_rl.slip_reporting import integrate
from nino_control.governor_core import GovernorSettings,GovernorFrame,ReactiveGovernor
from audit_gt_timestamp_slip import gt_timestamp_series
from audit_governor_phase_slip import load
from run_frozen_governor_confirmation import make_world,analyze_batch

CANDIDATES=[dict(target_scale=t,maximum_hold_seconds=h) for t,h in
            [(.9,1.),(.9,.8),(.9,1.2),(.95,.8),(.95,1.),(.95,1.2)]]
DEV=[dict(id="d0",x_m=2.7,angle_deg=-8,seeds=[77000]),
     dict(id="d1",x_m=3.1,angle_deg=8,seeds=[77001])]
VALIDATION=[dict(id=f"v{i}",x_m=x,angle_deg=a,seeds=[77100+2*i,77101+2*i])
            for i,(x,a) in enumerate([(2.35,-12),(2.85,12),(3.35,-6),(3.65,6)])]


def write_json(path,value):
    def clean(v):
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        if isinstance(v,list):return [clean(x) for x in v]
        return v.item() if isinstance(v,np.generic) else v
    path.write_text(json.dumps(clean(value),indent=2,allow_nan=False)+"\n")


def actual_holds(controls):
    bouts=[];active=None
    for row in controls:
        t=float(row["governor_input_time_s"])
        if row["governor_phase"]=="HOLD":
            if active is None:active=dict(start_s=t,minimum_scale=1.)
            active["minimum_scale"]=min(active["minimum_scale"],float(row["governor_scale"]))
        elif active is not None:
            active.update(end_s=t,commanded_hold_seconds=t-active["start_s"],
                exit_hold_timer_s=float(row["governor_hold_seconds"]),
                quiet_seconds_at_exit=float(row["governor_quiet_seconds"]),censored=False)
            bouts.append(active);active=None
    if active is not None:
        active.update(end_s=None,commanded_hold_seconds=None,censored=True);bouts.append(active)
    return bouts


def execution_preflight(base):
    reports=[]
    for params in CANDIDATES:
        settings={**base["governor"]["parameters"],**params,"profile":"reactive"}
        governor=ReactiveGovernor(GovernorSettings(**settings))
        # A sustained, finite motion disturbance tests timeout authority, not quality.
        frame=GovernorFrame(0.,1.,6.4,6.4,6.4,6.4,.4)
        trace=[]
        for i in range(40):
            result=governor.update(frame,.1,.4)
            trace.append(dict(governor_input_time_s=i*.1,governor_phase=result["phase"],
                governor_scale=result["scale"],governor_hold_seconds=result["hold_seconds"],
                governor_quiet_seconds=result["quiet_seconds"]))
        holds=actual_holds(trace)
        if len(holds)!=1 or holds[0]["censored"] or abs(holds[0]["minimum_scale"]-params["target_scale"])>1e-8:
            raise ValueError("Candidate cannot execute bounded holding/recovery")
        reports.append(dict(parameters=params,synthetic_hold=holds[0]))
    for target in (.9,.95):
        durations=[r["synthetic_hold"]["commanded_hold_seconds"] for r in reports if r["parameters"]["target_scale"]==target]
        if len({round(x,6) for x in durations})!=3:
            raise ValueError("Search contains indistinguishable executed hold durations")
    return reports


def score(rows):
    """A fixed cost; known physical failure is retained, missing comparison is FAIL."""
    terms=[];failures=[];references=[];actors=[]
    for seed in sorted({r["seed"] for r in rows}):
        arms={r["profile"]:r for r in rows if r["seed"]==seed}
        if set(arms)!={"full","reactive"}:raise ValueError("Missing paired arm")
        ref,actor=arms["full"],arms["reactive"]
        if not ref.get("complete") or not ref.get("physical_pass"):
            raise ValueError("PI reference failed/unavailable; comparison is not a score")
        if actor.get("physical_success") is False or (actor.get("complete") and actor.get("physical_pass") is False):
            failures.append(seed);continue
        for r in (ref,actor):
            if not r.get("complete") or not r.get("physical_pass") or not r.get("available"):
                raise ValueError("Incomplete native outcome; never substitute zero")
            if not r.get("native_replay",{}).get("matches_native") or not r.get("timestamps",{}).get("passed"):
                raise ValueError("Native replay/timestamp reporting failed")
            if not all(r.get("gt_native",{}).get(w,{}).get("available") for w in ("whole_route","crossing")):
                raise ValueError("Insufficient GT-time coverage")
        t=actor["time_s"]/ref["time_s"]
        cross=actor["gt_native"]["crossing"]["slip_square_per_m"]/ref["gt_native"]["crossing"]["slip_square_per_m"]
        path=actor["physical_rmse_m"]/ref["physical_rmse_m"]
        terms.append(dict(seed=seed,time_ratio=t,crossing_slip_ratio=cross,path_ratio=path,
                          cost=.5*(t+cross)+max(0.,path-1.05)))
        references.append(ref);actors.append(actor)
    if failures:return dict(value=100.+10*len(failures),feasible=False,physical_failures=failures,eligible=False,terms=terms)
    if not terms:raise ValueError("No available paired costs")
    def ratio(key,window=None):
        def val(r):return r["gt_native"][window][key] if window else r[key]
        return float(np.mean([val(r) for r in actors])/np.mean([val(r) for r in references]))
    guards=dict(tracking=ratio("physical_rmse_m")<=1.05,time=ratio("time_s")<=1.05,
                whole_slip=ratio("rms","whole_route")<=1.05)
    value=float(np.mean([term["cost"] for term in terms]))
    return dict(value=value,feasible=True,physical_failures=[],guards=guards,
                eligible=value<1. and all(guards.values()),terms=terms,
                mean_ratios=dict(time=ratio("time_s"),path=ratio("physical_rmse_m"),
                    whole_slip=ratio("rms","whole_route"),crossing_slip=ratio("slip_square_per_m","crossing")))


def run_scenarios(folder,base,params,scenarios,domain,order_seed,parallel=False):
    folder.mkdir(exist_ok=False)
    config=deepcopy(base);config["governor"]["parameters"].update(profile="reactive",**params)
    config["research_map"].update(revision="gt_timestamp_classical_tune_v2",training_allowed=False,optuna_allowed=True)
    path=folder/"config.yaml";path.write_text(yaml.safe_dump(config,sort_keys=False))
    write_json(folder/"protocol_before_results.json",dict(scenarios=scenarios,parameters=params,
               same_cruise_m_s=.4,gt_timestamp_objective=True,world_geometry_analysis_only=True))
    (folder/"confirmation").mkdir()
    def one(item):
        i,s=item;stage=folder/"confirmation"/s["id"];stage.mkdir()
        make_world(stage/"scenario.sdf",s)
        env=os.environ.copy();d=domain+i if parallel else domain
        env.update(ROS_DOMAIN_ID=str(d),NINO_ROS_DOMAIN_ID=str(d),ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",GZ_PARTITION=f"nino_gt_tune_{d}")
        cmd=[sys.executable,str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),
            "--variant","cable_box_capsule","--config",str(path),"--profiles","full","reactive",
            "--full-reference-speed",".4","--seeds",*map(str,s["seeds"]),"--shuffle-order","--order-seed",str(order_seed+i),
            "--world",str(stage/"scenario.sdf"),"--output",str(stage/"screen")]
        with (stage/"run.log").open("w") as log:
            p=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        print("BLOCK",folder.name,s["id"],"exit",p.returncode,flush=True)
        if p.returncode:raise RuntimeError(f"Scenario runner failed:{stage}")
    if parallel:
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(one,enumerate(scenarios)))
    else:
        for item in enumerate(scenarios):one(item)
    analyze_batch(folder)
    rows=json.loads((folder/"confirmation_episodes.json").read_text())
    for r in rows:
        try:
            case=Path(r["case"]);evaluation=next(case.glob("evaluation/*/summary.json")).parent
            logger=next(case.glob("contact/*/metadata.json")).parent
            data=load(case,dict(evaluation=str(evaluation),logger=str(logger),seed=r["seed"],profile=r["profile"],
                first_contact={"time_s":r["first_contact_s"]},postcontact_until_clearance={"end_time_s":r["clearance_s"]}))
            signal=gt_timestamp_series(data)
            r["gt_native"]={"whole_route":integrate(signal,data["start"],data["end"]),
                "crossing":integrate(signal,r["first_contact_s"]+.05,r["clearance_s"])}
            r["executed_holds"]=actual_holds(data["controls"])
        except (OSError,KeyError,ValueError,TypeError,StopIteration) as error:
            r["gt_analysis_error"]=f"{type(error).__name__}:{error}"
    write_json(folder/"episodes_gt_native.json",rows)
    result=score(rows);write_json(folder/"score.json",result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    base=load_config(ROOT/"docs/classical_governor_crossing_tune_2026-10-16/selected_candidate.yaml")
    base["navigation"]["straight_speed_m_s"]=.4
    base["governor"]["parameters"]["minimum_hold_seconds"]=.8
    preflight=execution_preflight(base);write_json(root/"execution_preflight.json",preflight)
    diagnostic=[]
    for path in sorted((ROOT/"rl_runs/governor_frozen_confirmation_2026-10-16/confirmation").glob("s*/screen/*reactive/evaluation/*/episode-*/control_trace.csv")):
        rows=list(csv.DictReader(path.open()));holds=[r for r in rows if r["governor_phase"]=="HOLD"]
        diagnostic.append(dict(trace=str(path),max_quiet_during_hold=max(float(r["governor_quiet_seconds"]) for r in holds),holds=actual_holds(rows)))
    write_json(root/"minimum_hold_diagnostic.json",diagnostic)
    contract=dict(schema="classical_gt_timestamp_target_maxhold_v2",candidates=CANDIDATES,
        corrected_search="minimum_hold was nonbinding on8 diagnostic traces(quiet=0); search effective maximum_hold instead; minimum_hold fixed0.8",
        development=DEV,validation_reserved=VALIDATION,max_development_episodes=24,max_validation_episodes=16,max_total_episodes=40,
        objective="mean_pair[0.5*(time_g/time_PI+GT_crossing_slip2_per_m_g/PI)+max(0,physical_RMSE_g/PI-1.05)]",
        failure="known candidate physical failure100+10*n; failed/missing PI or missing candidate measurement -> trial FAIL, never zero",
        eligibility="All arrival/2s-stop/reporting; cost<1; mean time/path/GTwholeRMS<=1.05*PI. Same rule for reserved validation.",
        selection="six fixed enqueued points only; freeze minimum-cost eligible development candidate before reserved validation. If none, stop at24. No retry or extension.",
        metric="original GT header timestamps with joint interpolation<=10ms; native unchanged; GT still50Hz, no true slip/impact claim",
        baseline_cruise_m_s=.4,candidate_cruise_m_s=.4,impact_optimized=False,
        source_base_config=base,development_parallel_domains=list(range(94,100)),validation_domains=list(range(90,94)),
        no_historical_scores_imported=True,no_training=True,no_default_promotion=True,
        qualification="Exploratory6-point grid managed by Optuna, n=2 dev blocks/trial; not Bayesian convergence, causal snapshot restoration, hardware validation or general optimum")
    write_json(root/"contract_before_results.json",contract)
    (root/"runner_snapshot.py").write_bytes(Path(__file__).read_bytes())
    study=optuna.create_study(study_name="nino_gt_target_maxhold_v2",storage="sqlite:///"+str(root/"study.sqlite3"),
        direction="minimize",sampler=optuna.samplers.RandomSampler(seed=77050),load_if_exists=False)
    study.set_user_attr("contract_sha256",hashlib.sha256((root/"contract_before_results.json").read_bytes()).hexdigest())
    for params in CANDIDATES:study.enqueue_trial(params)
    jobs=[]
    for i in range(6):
        trial=study.ask()
        params=dict(target_scale=trial.suggest_categorical("target_scale",[.9,.95]),
                    maximum_hold_seconds=trial.suggest_categorical("maximum_hold_seconds",[.8,1.,1.2]))
        jobs.append((trial,params,i))
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending={pool.submit(run_scenarios,root/f"trial_{t.number:03d}",base,p,DEV,94+i,77050+10*i):(t,p) for t,p,i in jobs}
        for future in as_completed(pending):
            trial,params=pending[future]
            try:
                result=future.result();trial.set_user_attr("eligible",result["eligible"]);trial.set_user_attr("feasible",result["feasible"])
                study.tell(trial,result["value"]);print("TRIAL END",trial.number,result,flush=True)
            except Exception as error:
                trial.set_user_attr("error",f"{type(error).__name__}:{error}")
                study.tell(trial,state=optuna.trial.TrialState.FAIL);print("TRIAL FAIL",trial.number,repr(error),flush=True)
    eligible=[t for t in study.trials if t.state==optuna.trial.TrialState.COMPLETE and t.user_attrs.get("eligible")]
    if not eligible:
        decision=dict(status="no_eligible_development_candidate_stop",validation_started=False,parameters_promoted=False)
    else:
        best=min(eligible,key=lambda t:t.value)
        selection=dict(trial=best.number,parameters=best.params,development_cost=best.value,validation_scenarios=VALIDATION,parameters_frozen=True)
        write_json(root/"selection_before_validation.json",selection)
        try:
            result=run_scenarios(root/"validation",base,best.params,VALIDATION,90,77150,parallel=True)
            decision=dict(status="validation_complete",selection=selection,validation_started=True,validation_score=result,
                          validation_pass=result["eligible"],parameters_promoted=False)
        except Exception as error:
            decision=dict(status="validation_unavailable_no_retry",selection=selection,validation_started=True,
                validation_pass=None,error=f"{type(error).__name__}:{error}",parameters_promoted=False)
    decision.update(training_started=False,predictor_started=False,extra_trials=False)
    write_json(root/"decision.json",decision);print("DECISION",decision,flush=True)


if __name__=="__main__":main()
