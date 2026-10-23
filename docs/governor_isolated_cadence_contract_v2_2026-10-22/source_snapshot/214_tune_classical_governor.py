#!/usr/bin/env python3
"""Bounded three-candidate Optuna screen for crossing time/slip, not peak impact."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import optuna
import yaml

from nino_rl.core import load_config
from summarize_contact_oracle_h2 import summarize

ROOT=Path(__file__).resolve().parents[3]
CANDIDATES=[dict(target_scale=.85,maximum_hold_seconds=2.5),
            dict(target_scale=.90,maximum_hold_seconds=1.),
            dict(target_scale=.95,maximum_hold_seconds=.8)]
DEVELOPMENT=[76600,76601]
VALIDATION=[76700,76701,76702]


def score(report,candidate="reactive"):
    """Fixed paired objective. Native arrival/stop gates dominate selection."""
    terms=[];failures=0
    seeds=sorted({r["seed"] for r in report["episodes"]})
    for seed in seeds:
        rows={r["profile"]:r for r in report["episodes"] if r["seed"]==seed}
        if any(p not in rows or not rows[p].get("complete")
               for p in ("full",candidate)):
            raise ValueError("Infrastructure/analysis incomplete; do not assign a physical score")
        ref,actor=rows["full"],rows[candidate]
        if not ref.get("physical_success") or not ref.get("stop_settled") or not ref.get("available"):
            raise ValueError("PI reference failed physical gate; trial comparison unavailable")
        if actor.get("physical_success") is False or actor.get("stop_settled") is False:
            failures+=1
            continue
        if not actor.get("physical_success") or not actor.get("stop_settled") or not actor.get("available"):
            raise ValueError("Candidate measurement unavailable; not a physical failure")
        keys=("time_s","postcontact_slip_energy_per_m","truth_rmse_m")
        if any(actor.get(k) is None or ref.get(k) is None or ref[k]<=0 for k in keys):
            raise ValueError("Missing/nonpositive reference metric; no zero substitution")
        terms.append(.5*(actor["time_s"]/ref["time_s"]+
            actor["postcontact_slip_energy_per_m"]/ref["postcontact_slip_energy_per_m"])
            +max(0.,actor["truth_rmse_m"]/ref["truth_rmse_m"]-1.05))
    return dict(value=(100.+10*failures if failures else sum(terms)/len(terms)),
        feasible=failures==0,physical_failures=failures,paired_costs=terms)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    base=load_config(ROOT/"src/nino_rl/config/factory_floor_governor_time_comparison.yaml")
    base["research_map"].update(revision="classical_governor_crossing_tune_v1_2026_10_16",
        stage="crossing_time_slip_screen_not_impact_optimization")
    base["governor"]["parameters"].update(profile="reactive",target_scale=.85)
    manifest=dict(contract="classical_crossing_time_slip_v1",candidates=CANDIDATES,
        development_seeds=DEVELOPMENT,validation_seeds=VALIDATION,max_episodes=18,
        objective="mean[0.5*(time/paired_PI_time+slip2_per_m/paired_PI_slip2_per_m)+max(0,path_RMSE/PI_RMSE-1.05)]; physical failure=100+10*n; missing/failed PI comparison=FAIL",
        reference_speed_m_s=.388,pi_objective=1.,impact_rms_or_peak_optimized=False,
        validation_condition="best feasible development value<1; freeze parameters before validation; otherwise stop",
        validation_pass="all arrival/2s stop, objective<1, mean path RMSE<=1.05*paired PI; only crossing-feasibility screen, never impact/deployment promotion",
        automatic_extra_trials=False,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__),ROOT/"src/nino_control/nino_control/governor_core.py",
                      ROOT/"src/nino_control/nino_control/effort_drive.py",ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py",
                      ROOT/"src/nino_rl/nino_rl/governor_logger.py",
                      ROOT/"src/nino_description/worlds/factory_floor_cable_box_capsule_contact_lab.sdf")},
        base_resolved_config=base)
    (out/"contract.json").write_text(json.dumps(manifest,indent=2)+"\n")
    study=optuna.create_study(study_name="nino_classical_crossing_v1",direction="minimize",
        storage="sqlite:///"+str(out/"study.sqlite3"),load_if_exists=False,
        sampler=optuna.samplers.RandomSampler(seed=76650))
    study.set_user_attr("contract_sha256",hashlib.sha256((out/"contract.json").read_bytes()).hexdigest())
    for params in CANDIDATES:study.enqueue_trial(params)

    def run(params,folder,seeds,order_seed):
        folder.mkdir()
        config=load_config(ROOT/"src/nino_rl/config/factory_floor_governor_time_comparison.yaml")
        config["research_map"]=base["research_map"]
        config["governor"]["parameters"].update(profile="reactive",**params)
        path=folder/"config.yaml";path.write_text(yaml.safe_dump(config,sort_keys=False))
        command=[sys.executable,str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),
            "--variant","cable_box_capsule","--config",str(path),"--profiles","full","reactive",
            "--full-reference-speed","0.388","--seeds",*[str(s) for s in seeds],
            "--shuffle-order","--order-seed",str(order_seed),"--output",str(folder/"screen")]
        with (folder/"run.log").open("w") as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
        summarize(folder/"screen",folder/"analysis")
        report=json.loads((folder/"analysis/result.json").read_text())
        result=score(report);(folder/"score.json").write_text(json.dumps(result,indent=2)+"\n")
        return report,result

    for index in range(len(CANDIDATES)):
        trial=study.ask()
        params=dict(target_scale=trial.suggest_categorical("target_scale",[.85,.9,.95]),
                    maximum_hold_seconds=trial.suggest_categorical("maximum_hold_seconds",[.8,1.,2.5]))
        print("START trial",trial.number,params,flush=True)
        try:
            _,result=run(params,out/f"trial_{trial.number:03d}",DEVELOPMENT,76650+index)
            trial.set_user_attr("feasible",result["feasible"])
            study.tell(trial,result["value"])
            print("END trial",trial.number,result,flush=True)
        except KeyboardInterrupt:
            study.tell(trial,state=optuna.trial.TrialState.FAIL);raise
        except Exception as error:
            trial.set_user_attr("error",str(error));study.tell(trial,state=optuna.trial.TrialState.FAIL)
            print("FAILED trial",trial.number,repr(error),flush=True)
    eligible=[t for t in study.trials if t.state==optuna.trial.TrialState.COMPLETE and t.user_attrs.get("feasible")]
    if not eligible or min(t.value for t in eligible)>=1.:
        decision=dict(status="no_candidate_better_on_development_stop",validation_started=False)
    else:
        best=min(eligible,key=lambda t:t.value)
        selection=dict(trial=best.number,parameters=best.params,development_value=best.value,
            validation_seeds=VALIDATION,parameters_frozen=True)
        (out/"selection_before_validation.json").write_text(json.dumps(selection,indent=2)+"\n")
        report,result=run(best.params,out/"validation",VALIDATION,76750)
        groups=report["groups"]
        path_ok=groups["reactive"]["metrics"]["truth_rmse_m"]["mean"]<=1.05*groups["full"]["metrics"]["truth_rmse_m"]["mean"]
        decision=dict(status="validation_complete",**selection,validation_started=True,
            validation_score=result,tracking_gate=path_ok,
            crossing_screen_pass=result["feasible"] and result["value"]<1. and path_ok,
            impact_benefit_proven=False,deployment_promoted=False,predictor_or_ppo_started=False)
    (out/"decision.json").write_text(json.dumps(decision,indent=2)+"\n")
    print("DECISION",json.dumps(decision),flush=True)


if __name__=="__main__":main()
