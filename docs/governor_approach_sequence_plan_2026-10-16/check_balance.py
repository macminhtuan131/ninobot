"""Prospective approach flags demonstrated offline; never filter old outcomes."""
import itertools
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src/nino_rl/scripts"))
from prepare_governor_contact_sequence import angle_delta

out=Path(__file__).resolve().parent
rows=json.loads((out/"historical_sequence_demonstration.json").read_text())
plan=json.loads((out/"protocol_before_future_runs.json").read_text())
limits=plan["prospective_diagnostic_limits"]
flags=[]
for r in rows:
    if not r["available"]:
        flags.append(dict(seed=r["seed"],arm=r["arm"],available=False));continue
    a=r["approach"]
    bounds={k:max(abs(a[k]["minimum"]),abs(a[k]["maximum"])) for k in ("y","yaw","roll","pitch")}
    check=dict(speed=a["v"]["minimum"]>=.39 and a["v"]["maximum"]<=.41,
        lateral=bounds["y"]<=.01,yaw=bounds["yaw"]<=math.radians(2.),
        tilt=max(bounds["roll"],bounds["pitch"])<=math.radians(2.),coverage=a["coverage_fraction"]>=.98)
    flags.append(dict(seed=r["seed"],arm=r["arm"],available=True,checks=check,
        coarse_approach_pass=all(check.values()),post_reset_quiet_release_verified=False,
        qualification="Flags only, no historical row excluded or promoted; contact/physics equality not implied."))
pairs=[]
for seed in sorted({r["seed"] for r in rows}):
    for a,b in itertools.combinations([r for r in rows if r["seed"]==seed],2):
        if not a["available"] or not b["available"]:continue
        aa,bb=a["approach"],b["approach"]
        dv=abs(aa["v"]["median"]-bb["v"]["median"])
        dy=abs(aa["y"]["median"]-bb["y"]["median"])
        da=abs(angle_delta(aa["yaw"]["median"],bb["yaw"]["median"]))
        pairs.append(dict(seed=seed,arms=[a["arm"],b["arm"]],median_speed_difference_m_s=dv,
            median_lateral_difference_m=dy,wrapped_median_yaw_difference_deg=math.degrees(da),
            coarse_pair_balance_pass=dv<=.005 and dy<=.005 and da<=math.radians(1.),
            caster_support_classes={r["arm"]:{s:z["load_class"] for s,z in r["approach"]["caster"].items()} for r in (a,b)},
            interpretation="Precontact covariates only; first-impact quality is NOT a matching/exclusion criterion."))
result=dict(flags=flags,pairs=pairs,limits_origin=limits["origin"],
    conclusion="Coarse approach balance cannot establish identical contact state or eliminate reset variance. StageA PI-only repeatability remains necessary before intervention selection.",
    excluded_rows=0,new_simulation_episodes=0)
(out/"approach_balance_demonstration.json").write_text(json.dumps(result,indent=2)+"\n")
print("Coarse approach passes:",sum(r.get("coarse_approach_pass",False) for r in flags),"/",len(flags))
print("Coarse pair passes:",sum(r["coarse_pair_balance_pass"] for r in pairs),"/",len(pairs))
