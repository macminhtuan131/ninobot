#!/usr/bin/env python3
"""Compare saved Full PI runs across cylinder/capsule collision primitives."""
import argparse
import csv
import json
from pathlib import Path

from audit_single_cable_screen import analyze
from audit_cable_contact_geometry import analyze as geometry
from summarize_contact_oracle_h2 import native_status


def compare(cylinder, capsule, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rows=[];details=[]
    for primitive,root in (("cylinder",Path(cylinder)),("capsule",Path(capsule))):
        for case in sorted(root.glob("seed_*_full")):
            seed=int(case.name.split("_")[1])
            try:
                data=analyze(case); shape=geometry(case)
                native=data.get("outcome") or {}
                audit=json.loads((case/"audit.json").read_text())
                meta=json.loads((Path(data["logger"])/"metadata.json").read_text())
                world=json.loads((Path(data["logger"])/"world_metadata.json").read_text())
                contact=data.get("postcontact_until_clearance",{})
                point_peak=max((v.get("peak_abs_force_z_N") or 0. for v in audit["contact_messages"].values()),default=None)
                def numeric(key):return float(native[key]) if native.get(key) not in (None,"") else None
                rows.append(dict(seed=seed,primitive=primitive,case=str(case),complete=data.get("complete"),
                    physical_success=(native.get("success")=="True") if native else None,
                    stop_settled=audit.get("post_arrival_stop",{}).get("settled"),
                    positive_contact_available=data.get("available"),
                    contact_components=";".join(sorted(data.get("first_contact_by_component_s",{}))),
                    approach_m_s=data.get("approach_body_speed_m_s"),time_s=numeric("time_seconds"),
                    truth_rmse_m=numeric("truth_path_rmse_m"),endpoint_m=numeric("truth_endpoint_error_m"),
                    whole_vertical_rms=numeric("rms_vertical_acceleration_m_s2"),
                    whole_vertical_peak=numeric("peak_vertical_acceleration_m_s2"),
                    whole_slip_rms=numeric("rms_wheel_slip"),
                    post_vertical_rms=contact.get("acceleration",{}).get("rms"),
                    post_vertical_peak=contact.get("acceleration",{}).get("peak"),
                    post_slip_energy_per_m=contact.get("slip_energy_per_m"),
                    distant_contact_points=shape.get("distant_positive_points"),
                    maximum_contact_distance_m=shape.get("maximum_horizontal_distance_m",{}).get("cable"),
                    largest_reported_point_force_z_N=point_peak,
                    robot_sha256=meta.get("robot_description_sha256"),core_sha256=meta.get("governor_core_sha256"),
                    world_sha256=meta.get("world_sha256"),
                    parent_world_sha256=world.get("cable_collision_control",{}).get("parent_world_sha256")))
                details.append(dict(primitive=primitive,seed=seed,contact=data,geometry=shape))
            except Exception as error:
                rows.append(dict(seed=seed,primitive=primitive,case=str(case),**native_status(case),
                    reason=f"{type(error).__name__}: {error}"))
    requested=json.loads((Path(cylinder)/"plan.json").read_text())["seeds"]
    result=dict(episodes=rows,details=details,requested_seeds=requested,
        complete=(len(rows)==2*len(requested) and all(r.get("complete") is True for r in rows) and
            all({r["seed"] for r in rows if r["primitive"]==p}==set(requested) for p in ("cylinder","capsule"))),
        qualification="One local-geometry collision control with paired cold starts, not a hardware validation or learned-controller result",
        all_native_arrivals_and_stops=bool(rows) and all(r.get("physical_success") is True and r.get("stop_settled") is True for r in rows),
        all_contacts_available=bool(rows) and all(r.get("positive_contact_available") is True for r in rows),
        same_robot=len({r.get("robot_sha256") for r in rows})==1,
        same_core=len({r.get("core_sha256") for r in rows})==1,
        capsule_parent_matches_cylinder=all(r.get("parent_world_sha256") in
            {v.get("world_sha256") for v in rows if v["primitive"]=="cylinder"}
            for r in rows if r["primitive"]=="capsule"),
        controller_changed=False,training_started=False,optuna_started=False)
    (output/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (output/"comparison.csv").open("w") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    print("Saved",output/"result.json")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cylinder",type=Path,required=True)
    parser.add_argument("--capsule",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    compare(args.cylinder,args.capsule,args.output)
