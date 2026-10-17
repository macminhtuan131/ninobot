"""Compare every old decision field against the preserved pre-change source."""
from pathlib import Path
import json
import random
import runpy
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src/nino_control"))
from nino_control.governor_core import GovernorSettings,GovernorFrame,ReactiveGovernor

old=runpy.run_path(str(Path(__file__).parent/"implementation_before/governor_core.py"))
rng=random.Random(200)
checks=0
for profile in ("reactive","full","moderate","deep","pulse"):
    previous=old["ReactiveGovernor"](old["GovernorSettings"](profile=profile))
    current=ReactiveGovernor(GovernorSettings(profile=profile))
    for tick in range(2000):
        if tick%200==0:previous.reset();current.reset()
        values=dict(vertical_m_s2=rng.choice([0.,.2,5.]),body_rate_rad_s=rng.choice([0.,.1,.5]),
            left_velocity_rad_s=rng.choice([0.,4.8,6.4]),right_velocity_rad_s=6.4,
            left_target_rad_s=6.4,right_target_rad_s=6.4,executed_linear_m_s=.4)
        dt=rng.choice([.05,.1])
        requested=rng.choice([0.,-.1,.4,.4,.4,.4])
        fresh=tick%197!=196
        a=previous.update(old["GovernorFrame"](**values),dt,requested,fresh=fresh)
        b=current.update(GovernorFrame(**values),dt,requested,fresh=fresh)
        assert all(b[k]==v for k,v in a.items()),(profile,tick,a,b)
        checks+=1
result=dict(default_delay_seconds=0.,decisions_checked=checks,
    all_legacy_fields_identical=True,profiles=5,new_telemetry_fields_excluded=True)
(Path(__file__).parent/"zero_delay_regression.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
