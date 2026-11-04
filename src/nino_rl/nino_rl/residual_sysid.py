"""Descriptive command-to-wheel identification; no body/slip calibration claim.

CSV time is an explicitly declared common receipt clock. Combined delay includes
transport and shaping; requested wheel equivalents are NOT target telemetry.
Entire sessions are held out. This tool never updates controller parameters.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

COLUMNS=('session_id','time_s','final_v_m_s','final_yaw_rad_s','wheel_l_rad_s','wheel_r_rad_s')


def read_dataset(csv_path,metadata_path):
    metadata=json.loads(Path(metadata_path).read_text())
    required=dict(time_s='s',final_v_m_s='m/s',final_yaw_rad_s='rad/s',wheel_l_rad_s='rad/s',wheel_r_rad_s='rad/s')
    if metadata.get('units')!=required:raise ValueError('Explicit SI units required; use sysid template')
    if metadata.get('time_basis')!='common_receipt_clock' or not metadata.get('alignment_note'):
        raise ValueError('Declare receipt clock/alignment limitations, not fabricated actuator stamps')
    if not metadata.get('provenance') or not metadata.get('conditions_note'):
        raise ValueError('Source bag/provenance and floor/load/caster conditions required')
    groups={}
    with Path(csv_path).open(newline='') as f:
        reader=csv.DictReader(f)
        if not set(COLUMNS).issubset(reader.fieldnames or []):raise ValueError('Missing CSV fields: '+str(COLUMNS))
        for row in reader:
            session=row['session_id'].strip()
            values=[float(row[c]) for c in COLUMNS[1:]]
            if not session or not np.all(np.isfinite(values)):raise ValueError('Missing/invalid sample; retain source as incomplete')
            groups.setdefault(session,[]).append(values)
    data={name:np.asarray(rows,dtype=float) for name,rows in groups.items()}
    for name,rows in data.items():
        if len(rows)<20 or rows[-1,0]-rows[0,0]<1.5 or np.any(np.diff(rows[:,0])<=0):raise ValueError('Insufficient/nonmonotonic session '+name)
    if len(data)<3:raise ValueError('Need >=3 complete sessions for whole-session fit/holdout; current data may remain unknown')
    hold=metadata.get('held_out_sessions')
    if not isinstance(hold,list) or not hold or set(hold)-data.keys() or len(hold)>=len(data):
        raise ValueError('Predeclare nonempty held-out whole sessions; do not choose by fit result')
    geometry=metadata.get('nominal_geometry',{})
    if set(geometry)!=set(('radius_l','radius_r','separation')) or any(not np.isfinite(v) or v<=0 for v in geometry.values()):
        raise ValueError('Explicit nominal geometry required')
    return data,metadata


def response(rows,wheel,geometry,delay,tau):
    t=rows[:,0];linear=rows[:,1]+(-1 if wheel==0 else 1)*geometry['separation']*rows[:,2]/2
    u=linear/geometry['radius_l' if wheel==0 else 'radius_r']
    idx=np.searchsorted(t,t-delay,side='right')-1
    delayed=np.where(idx>=0,u[np.maximum(idx,0)],0.)
    output=np.zeros(len(t))
    # Zero-state forcing. The initial measured state is added separately below
    # so fitting gain does not scale the initial state too.
    for i in range(1,len(t)):
        a=np.exp(-(t[i]-t[i-1])/tau);output[i]=a*output[i-1]+(1-a)*delayed[i-1]
    return output


def fit(data,metadata):
    train={k:v for k,v in data.items() if k not in metadata['held_out_sessions']}
    hold={k:v for k,v in data.items() if k in metadata['held_out_sessions']};geometry=metadata['nominal_geometry']
    for name,rows in data.items():
        if np.max(np.diff(rows[:,0]))>.15:raise ValueError('Source gap >150 ms in '+name+'; declare a different measurement protocol separately')
        if np.ptp(rows[:,1])<.01:raise ValueError('Insufficient command excitation: '+name)
    models=[]
    for wheel in (0,1):
        best=None
        for delay in np.linspace(0.,.30,16):
            for tau in np.geomspace(.02,1.,30):
                predictions=[];ys=[]
                for rows in train.values():
                    mask=rows[:,0]-rows[0,0]>=1.;predictions.extend(response(rows,wheel,geometry,delay,tau)[mask])
                    initial=rows[0,3+wheel]*np.exp(-(rows[:,0]-rows[0,0])/tau)
                    ys.extend((rows[:,3+wheel]-initial)[mask])
                x=np.asarray(predictions);y=np.asarray(ys)
                if len(x)<10 or x@x<1e-8:continue
                gain=float(x@y/(x@x));error=float(np.mean((gain*x-y)**2))
                if gain>0 and (best is None or error<best['fit_mse_rad_s2']):best=dict(combined_delay_s=float(delay),time_constant_s=float(tau),gain=gain,fit_mse_rad_s2=error)
        if best is None:raise ValueError('Unidentifiable wheel response')
        held=[]
        for name,rows in hold.items():
            mask=rows[:,0]-rows[0,0]>=1.;pred=best['gain']*response(rows,wheel,geometry,best['combined_delay_s'],best['time_constant_s'])
            pred+=rows[0,3+wheel]*np.exp(-(rows[:,0]-rows[0,0])/best['time_constant_s'])
            held.append(dict(session_id=name,rmse_rad_s=float(np.sqrt(np.mean((pred[mask]-rows[mask,3+wheel])**2)))))
        best.update(wheel='left' if wheel==0 else 'right',held_out=held,
            boundary_optimum=best['combined_delay_s'] in (0.,.3) or best['time_constant_s'] in (.02,1.))
        models.append(best)
    return dict(scope='command-to-wheel combined response; not actuator-target readback, body response or slip',
        models=models,fit_sessions=list(train),held_out_sessions=list(hold),
        uncertainty='descriptive fit only; no independent-repeat CI or hardware release threshold accepted',
        calibration_status='candidate_unknown_until_protocol_review',controller_parameters_changed=False,
        geometry_status='nominal_not_effective_rolling_calibration',time_basis=metadata['time_basis'])


def register(root,csv_path,metadata_path):
    # Registration preserves the exact input and does not run identification.
    from .residual_workflow import save
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    data,meta=read_dataset(csv_path,metadata_path)
    save(root/'registration.json',dict(csv=str(Path(csv_path).resolve()),metadata=str(Path(metadata_path).resolve()),
        sha256={k:hashlib.sha256(Path(p).read_bytes()).hexdigest() for k,p in [('csv',csv_path),('metadata',metadata_path)]},sessions=list(data)))


def analyze_registered_data(root,out):
    from .residual_workflow import save
    reg=json.loads((Path(root)/'registration.json').read_text())
    for key in ('csv','metadata'):
        p=Path(reg[key])
        if hashlib.sha256(p.read_bytes()).hexdigest()!=reg['sha256'][key]:raise ValueError('Registered data changed; retain and register a new input')
        shutil.copy2(p,out/('source.csv' if key=='csv' else 'source_metadata.json'))
    data,metadata=read_dataset(out/'source.csv',out/'source_metadata.json');result=fit(data,metadata)
    save(out/'sysid_result.json',result);return result
