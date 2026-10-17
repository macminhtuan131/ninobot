from pathlib import Path
import csv,hashlib,json,struct,sys,xml.etree.ElementTree as ET
import numpy as np
ROOT=Path("/home/tuanmac/ninorobot")
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from analyze_governor_experiment import stamp
from nino_control.governor_core import quaternion_rpy

run=ROOT/"rl_runs/governor_frozen_repeats_2026-10-16"
rows=json.loads((run/"episodes.json").read_text())
mesh=ROOT/"src/nino_description/meshes/caster_bracket_front1.STL"
buf=mesh.read_bytes();n=struct.unpack_from("<I",buf,80)[0]
triangles=np.frombuffer(buf,offset=84,count=n,dtype=np.dtype([("normal","<f4",(3,)),("v","<f4",(3,3)),("attr","<u2")]))
vertices=triangles["v"].reshape(-1,3).astype(float)
def rotation(r,p,y):
    cr,sr,cp,sp,cy,sy=np.cos(r),np.sin(r),np.cos(p),np.sin(p),np.cos(y),np.sin(y)
    return np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
                     [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])
results=[]
for outcome in rows:
    case=Path(outcome["case"]);log=next(case.glob("contact/*/metadata.json")).parent
    events=[json.loads(s) for s in (log/"contact_events.jsonl").open()]
    tc=outcome["first_contact_s"]
    first=min((e for e in events if e["event"]=="begin" and e.get("named_positive_obstacle") and abs(e["time_s"]-tc)<.01),key=lambda e:e["time_s"])
    component=first["component"];side=component.rsplit("_",1)[-1]
    g,j,c=[],[],[]
    first_force=None;first_force_depth=None
    for line in (log/"samples.jsonl").open():
        row=json.loads(line);d=row["data"]
        if row["topic"] not in ("/ground_truth/odom","/joint_states","/nino/contact_lab/"+component):continue
        t=stamp(d)
        if not tc-.04<=t<=tc+.3:continue
        if row["topic"]=="/ground_truth/odom":g.append((t,d))
        elif row["topic"]=="/joint_states":j.append((t,d))
        else:
            for contact in d["contacts"]:
                if "cable_bumps" in contact["collision1"]["name"]+contact["collision2"]["name"]:
                    forces=[w["body_1_wrench"]["force"] for w in contact["wrenches"]]
                    item=dict(time_s=t,depths_m=contact["depths"],positions=contact["positions"],body_1_forces_N=forces)
                    loaded=any(np.linalg.norm([f[k] for k in ("x","y","z")])>1e-6 for f in forces)
                    loaded_depth=any(depth>0 and np.linalg.norm([f[k] for k in ("x","y","z")])>1e-6 for depth,f in zip(contact["depths"],forces))
                    if t>=tc and loaded and (first_force is None or t<first_force["time_s"]):first_force=item
                    if t>=tc and loaded_depth and (first_force_depth is None or t<first_force_depth["time_s"]):first_force_depth=item
                    if abs(t-tc)<.012:c.append(item)
    u=ET.parse(log/"robot_description.urdf").getroot()
    base=np.array(list(map(float,u.find("joint[@name='base_footprint_joint']/origin").get("xyz").split())))
    origin=np.array(list(map(float,u.find(f"joint[@name='caster_{side}_swivel_joint']/origin").get("xyz").split())))
    poses=[]
    for tg,gd in sorted(g,key=lambda z:abs(z[0]-tc))[:2]:
        tj,jd=min(j,key=lambda z:abs(z[0]-tg))
        angle=dict(zip(jd["name"],jd["position"]))[f"caster_{side}_swivel_joint"]
        pose=gd["pose"]["pose"];q=pose["orientation"];r,p,y=quaternion_rpy(tuple(q[k] for k in ("x","y","z","w")))
        position=np.array([pose["position"][k] for k in ("x","y","z")])
        world=(rotation(r,p,y)@((rotation(0,0,angle)@vertices.T).T+base+origin).T).T+position
        theta=np.deg2rad(8.);s=(world[:,0]-3.1)*np.cos(theta)+world[:,1]*np.sin(theta);z=world[:,2]-.011
        ds=max(float(s.min()),float(-s.max()),0.);dz=max(float(z.min()),float(-z.max()),0.)
        poses.append(dict(ground_stamp_s=tg,joint_stamp_s=tj,ground_age_relative_contact_s=tc-tg,
            model_position=pose["position"],roll_rad=r,pitch_rad=p,yaw_rad=y,swivel_rad=angle,
            radial_plane_interval_m=[float(s.min()),float(s.max())],height_relative_axis_interval_m=[float(z.min()),float(z.max())],
            conservative_mesh_bounds_gap_to_capsule_m=float(np.hypot(ds,dz)-.011)))
    results.append(dict(attempt=outcome["attempt"],profile=outcome["profile"],first_contact=first,
        adjacent_pose_geometry_checks=poses,first_contact_manifolds=c,
        first_nonzero_force_manifold=first_force,first_nonzero_force_and_positive_depth=first_force_depth,
        force_reference_delay_s=first_force["time_s"]-tc if first_force else None,
        qualification="Conservative bounding rectangle in cable radial plane; positive gap excludes intersection at those sampled poses, not at unsampled exact physics ticks. No force impulse inferred."))
output=dict(mesh_sha256=hashlib.sha256(buf).hexdigest(),mesh_bounds_m=[vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist()],
    nominal_bracket_lowest_z_m=float(.0625-.0215+vertices[:,2].min()),cable_top_z_m=.022,results=results)
(run/"bracket_first_contact_geometry.json").write_text(json.dumps(output,indent=2)+"\n")
for r in results:
    print(r["attempt"],[round(p["conservative_mesh_bounds_gap_to_capsule_m"],5) for p in r["adjacent_pose_geometry_checks"]],
          [(p["time_s"],p["depths_m"],p["body_1_forces_N"]) for p in r["first_contact_manifolds"][:2]])
