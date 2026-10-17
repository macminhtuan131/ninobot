#!/usr/bin/env python3
"""Execute the locked eight-case height contrast, one cold start at a time."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from run_frozen_governor_confirmation import analyze_batch
from run_governor_frozen_repeats import enrich
from summarize_contact_oracle_h2 import native_status

PLAN=ROOT/"docs/matched_ramp_response_2026-10-16/next_height_screen_protocol.json"
PARENT=ROOT/"src/nino_description/worlds/factory_floor_cable_box_capsule_contact_lab.sdf"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")


def make_height_world(destination,height):
    if height not in (.006,.022):raise ValueError("Height outside locked protocol")
    tree=ET.parse(PARENT)
    cable=tree.getroot().find("world/model[@name='cable_bumps']/link")
    radius=height/2
    for kind in ("collision","visual"):
        node=cable.find(kind)
        values=node.find("pose").text.split()
        values[0],values[2],values[5]=str(3.1),str(radius),str(math.radians(8.))
        node.find("pose").text=" ".join(values)
        node.find("geometry/*/radius").text=str(radius)
    tree.write(destination,encoding="utf-8",xml_declaration=True)
    metadata=json.loads(PARENT.with_suffix(".json").read_text())
    metadata["cables"][0].update(x_m=3.1,radius_m=radius,angle_deg=8.)
    metadata["cable_collision_control"].update(radius_m=radius,total_capsule_length_m=4.+height,
        change="Declared height contrast: capsule/visual radius and center z; common x3.1/yaw8deg")
    metadata.update(revision="frozen_governor_height_mechanism_screen_v1",world_file=destination.name,
        world_sha256=sha(destination),parent_world_sha256=sha(PARENT),
        scenario=dict(height_m=height,x_m=3.1,angle_deg=8.),
        notes=["Solid-box floor, unchanged robot and contact materials.",
               "Only ridge radius/center height and common x/yaw differ from parent; rigid, not deformable cable.",
               "World SDF and this sidecar define scenario geometry; frozen config is the controller reference, not a radius override.",
               "CAD-based simulation, not hardware validation or selection of an easier working height."])
    write(destination.with_suffix(".json"),metadata)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--domain",type=int,default=105)
    args=p.parse_args()
    plan=json.loads(PLAN.read_text())
    assert len(plan["case_order"])==plan["maximum_attempts"]==8
    frozen=ROOT/plan["fixed"]["config_source"]
    assert sha(frozen)=="6ce2de78c09eb502e89ab6e81f614a2c0064a05bacc1995df5e421d58e5cb7f5"
    root=args.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    shutil.copy2(frozen,root/"config.yaml")
    shutil.copy2(PLAN,root/"prepared_protocol_snapshot.json")
    sources=[ROOT/"src/nino_rl/nino_rl"/n for n in ("ros_env.py","ros_interface.py","evaluation.py","slip_reporting.py")]
    sources += [ROOT/"src/nino_control/nino_control"/n for n in ("governor_core.py","effort_drive.py")]
    sources += [Path(__file__).resolve(),ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py",PARENT]
    guard={}
    for directory in (ROOT/"docs/governor_frozen_repeats_2026-10-16",ROOT/"docs/matched_ramp_response_2026-10-16",
                      ROOT/"docs/gt_governor_optuna_v2_2026-10-16",ROOT/"src/nino_control",ROOT/"src/nino_rl/config"):
        for path in directory.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:guard[str(path)]=sha(path)
    write(root/"preservation_before.json",guard)
    (root/"source_snapshot").mkdir()
    for index,source in enumerate(sources):
        shutil.copy2(source,root/"source_snapshot"/f"{index:02d}_{source.name}")
    write(root/"protocol_before_results.json",dict(prepared_protocol=plan,domain=args.domain,
        partition=f"nino_height_screen_{args.domain}",source_sha256={str(s):sha(s) for s in sources},
        fixed_config_sha256=sha(frozen),analysis="Same native scoring, GT-stamp slip; report both existing grid origins as sensitivity. No pooling with history or height selection."))
    environment=os.environ.copy()
    environment.update(ROS_DOMAIN_ID=str(args.domain),NINO_ROS_DOMAIN_ID=str(args.domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",GZ_PARTITION=f"nino_height_screen_{args.domain}")
    rows=[]
    stop=None
    for index,(seed,height,arm) in enumerate(plan["case_order"],1):
        block=root/f"attempt_{index:02d}"
        scenario=dict(id="height",x_m=3.1,angle_deg=8.,height_m=height,seeds=[seed])
        stage=block/"confirmation/height"
        stage.mkdir(parents=True)
        write(block/"protocol_before_results.json",dict(scenarios=[scenario]))
        make_height_world(stage/"scenario.sdf",height)
        command=[sys.executable,str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),
            "--variant","cable_box_capsule","--config",str(root/"config.yaml"),"--profiles",arm,
            "--seeds",str(seed),"--world",str(stage/"scenario.sdf"),"--output",str(stage/"screen")]
        if arm=="full":command += ["--full-reference-speed",".4"]
        print("START",index,"height_mm",height*1000,seed,arm,flush=True)
        row=dict(attempt=index,seed=seed,height_m=height,profile=arm,reporting_pass=False,
                 physical_pass=False,case=str(stage/"screen"/f"seed_{seed}_{arm}"))
        try:
            with (block/"run.log").open("w") as stream:
                execution=subprocess.run(command,cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT)
            row["runner_exit"]=execution.returncode
            if not (stage/"screen/summary.json").is_file():
                row.update(native_status(Path(row["case"])))
                raise RuntimeError("Attempt produced no screen summary; outcome remains unavailable")
            analyze_batch(block)
            analyzed=json.loads((block/"confirmation_episodes.json").read_text())
            if len(analyzed)!=1:raise RuntimeError("One attempt must produce exactly one retained row")
            row.update(analyzed[0])
            enrich(row)
            row["provenance_pass"]=row["provenance"]["robot_description_sha256"]==plan["fixed"]["robot_URDF_sha256"]
            row["provenance_pass"] &= all(row["provenance"].get(k) for k in ("effort_drive_sha256","control_timing_sha256","governor_core_sha256"))
        except Exception as error:
            row["analysis_error"]=f"{type(error).__name__}: {error}"
            row["reporting_pass"]=False
        rows.append(row)
        write(root/"episodes.json",rows)
        print("END",index,"physical",row.get("physical_pass"),"reporting",row.get("reporting_pass"),flush=True)
        if row.get("runner_exit")!=0 or not all(row.get(k) for k in ("physical_pass","reporting_pass","provenance_pass")):
            stop="reporting_physical_or_provenance_failure_no_retry"
            break
    changed=[name for name,digest in guard.items() if not Path(name).is_file() or sha(name)!=digest]
    write(root/"decision.json",dict(status=stop or "eight_attempts_complete_offline_mechanism_review_required",
        attempts=len(rows),unattempted=plan["case_order"][len(rows):],protected_files=len(guard),changed_protected=changed,
        source_changed=[str(s) for s in sources if sha(s)!=sha(root/"source_snapshot"/f"{sources.index(s):02d}_{s.name}")],
        physical_passes=sum(bool(r.get("physical_pass")) for r in rows),reporting_passes=sum(bool(r.get("reporting_pass")) for r in rows),
        hardware_validated=False,tuning_started=False,training_started=False,predictor_started=False,
        parameter_selection=False,height_selection=False,no_retry=True,extra_attempts=False))
    print((root/"decision.json").read_text(),flush=True)


if __name__=="__main__":main()
