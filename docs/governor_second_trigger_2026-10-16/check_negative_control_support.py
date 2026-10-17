"""Validate all GT/joint interpolation support precedes earliest intervention."""
from pathlib import Path
import bisect
import json
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from audit_governor_second_trigger import read_case,write

out=Path(__file__).resolve().parent
rows=[r for r in json.loads((ROOT/"rl_runs/governor_brake_delay_2026-10-16/episodes.json").read_text()) if r["seed"]==77320]
result={}
for row in rows:
    case=read_case(row)
    s=case["signal"]
    t=s["time"]-case["tc"]
    result[row["arm"]]={}
    for end in (.05,.076):
        lo=max(0,bisect.bisect_right(t,0.)-1)
        hi=min(len(t)-1,bisect.bisect_left(t,end))
        last_gt=float(t[hi])
        last_joint=float(np.nanmax(s["joint_support_stamps"][lo:hi+1])-case["tc"])
        result[row["arm"]][str(end)]=dict(latest_GT_support_relative_s=last_gt,
            latest_joint_support_relative_s=last_joint,
            all_support_before_earliest_brake=last_gt<.076-1e-9 and last_joint<.076-1e-9,
            qualification="Boundary-clipped quadrature can use next GT sample; do not claim a causal pre-action negative control if support crosses the first reduced-command boundary.")
write(out/"negative_control_support.json",result)
assert all(v["0.05"]["all_support_before_earliest_brake"] for v in result.values())
print(json.dumps(result,indent=2))
