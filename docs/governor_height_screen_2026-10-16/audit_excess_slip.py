"""One saved-case audit: 6mm/77311. No controller or score mutation."""
import csv
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
from nino_rl.slip_reporting import integrate
import numpy as np

out=Path(__file__).resolve().parent
rows=json.loads((out/"episodes.json").read_text())
arms={r["profile"]:r for r in rows if r["seed"]==77311 and r["height_m"]==.006}
controls=list(csv.DictReader(next(Path(arms["reactive"]["case"]).glob("evaluation/*/episode-*/control_trace.csv")).open()))
tc=arms["reactive"]["first_contact_s"]
begin=next(float(c["governor_input_time_s"]) for c in controls if float(c["governor_scale"])<.999)-tc
hold=next(float(c["governor_input_time_s"]) for c in controls if float(c["governor_scale"])<=.900001)-tc
recover=next(float(c["governor_input_time_s"]) for c in controls if c["governor_phase"]=="RECOVER")-tc
cruise=next(float(c["governor_input_time_s"]) for c in controls if float(c["governor_input_time_s"])>tc+recover and c["governor_phase"]=="CRUISE")-tc
common_end=min(r["clearance_s"]-r["first_contact_s"] for r in arms.values())
cuts=[.05,begin,hold,recover,cruise,common_end]
assert all(b>a for a,b in zip(cuts,cuts[1:]))
labels=["before_reduced_command","braking_command","holding_command","recovery_command","post_recovery_crossing"]
phases={}
conservation={}
for arm,row in arms.items():
    case=Path(row["case"])
    evaluation=next(case.glob("evaluation/*/summary.json")).parent
    logger=next(case.glob("contact/*/metadata.json")).parent
    data=load(case,dict(evaluation=str(evaluation),logger=str(logger),seed=77311,profile=arm))
    signal=gt_timestamp_series(data)
    drive=list(csv.DictReader(next(evaluation.glob("episode-*/drive_trace.csv")).open()))
    origin=row["first_contact_s"]
    phases[arm]={}
    for name,a,b in zip(labels,cuts,cuts[1:]):
        metric=integrate(signal,origin+a,origin+b)
        selected=[c for c in drive if origin+a<=float(c["sim_time_s"])<=origin+b]
        metric["drive_samples"]=len(selected)
        metric["mean_executed_reference_m_s"]=float(np.mean([float(c["executed_linear_m_s"]) for c in selected])) if selected else None
        metric["mean_abs_wheel_target_error_m_s"]=float(np.mean([
            .0625*abs(float(c[s+"_actual_rad_s"])-float(c[s+"_target_rad_s"]))
            for c in selected for s in ("left","right")])) if selected else None
        phases[arm][name]=metric
    total=integrate(signal,origin+cuts[0],origin+cuts[-1])
    summed=sum(m["slip_square_integral_s"] for m in phases[arm].values())
    conservation[arm]=dict(common_window=total,phase_sum_s=summed,
                           matches=bool(np.isclose(summed,total["slip_square_integral_s"],atol=1e-12,rtol=0)))
    assert conservation[arm]["matches"]
excess={name:phases["reactive"][name]["slip_square_integral_s"]-phases["full"][name]["slip_square_integral_s"] for name in labels}
result=dict(seed=77311,height_mm=6,common_contact_relative_boundaries_s=cuts,
    qualification="Phase boundaries from the recorded governor; PI translated by own first contact. "
                  "Common end is earlier clearance (not replacing either original crossing score). Native GT stamps retained. "
                  "Contact/reset states differ; phase co-occurrence is not proof of causation.",
    phases=phases,excess_governor_minus_pi_integral_s=excess,conservation=conservation)
with (out/"excess_slip_phase_audit.json").open("x") as stream:
    json.dump(result,stream,indent=2,allow_nan=False);stream.write("\n")
print(json.dumps(dict(excess=excess,conservation=conservation),indent=2))
