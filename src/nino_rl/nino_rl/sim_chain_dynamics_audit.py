"""Read-only diagnosis of nine sealed simulation trajectories. No plant calls."""
import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,math,platform
from pathlib import Path
import numpy as np

SOURCE_SHA='3865c03c6881502ac81544c9908a339bd62eb10afe529274da589c153d9e6ebd'
HELD_SHA='414a468cc0dbf885a7aa70be5999ecf9a44a04ca44fa82bdfa37894fad6e6623'
ID='nino_sim_chain_dynamics_audit_v1_2026_11_07'


def repo():return Path(__file__).resolve().parents[3]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def jsonrows(p):
    with Path(p).open() as stream:
        for line in stream:yield json.loads(line)


def specification():
    p=read(repo()/'src/nino_rl/config/sim_chain_dynamics_audit_v1.json')
    if (p['id'],p['source_cells'],p['source_rows_per_cell'],p['plateau_start_s'],p['fit_end_s'],
            p['plateau_end_s'],p['maximum_source_age_s'],p['constant_target_tolerance_m_s'],
            p['relaxation_tau_grid_s'],p['profile_sse_relative_band'],p['release'])!=(
            ID,9,140,3.,5.4,7.4,.04,1e-6,dict(minimum=.1,maximum=10.,count=81),.05,
            dict(physics_authorized=False,training_authorized=False,hardware_authorized=False)):
        raise ValueError('Changed diagnostic requires a new specification')
    return p


def fingerprint():
    base=repo()/'src/nino_rl'
    files=['nino_rl/sim_chain_dynamics_audit.py','config/sim_chain_dynamics_audit_v1.json',
        'test/test_sim_chain_dynamics_audit.py']
    return hashlib.sha256(json.dumps({n:sha(base/n) for n in files},sort_keys=True).encode()).hexdigest()


def source():
    from .gain_baseline_qualification import validated_latest,ROOT_NAME
    from .held_gain_preflight import verified_report
    upstream=validated_latest(Path.home()/'nino_research'/ROOT_NAME,check_runtime=False)
    held=Path.home()/'nino_research/sim_held_gain_offline_v1/qualification_2026_11_07'
    verified_report(held)
    if sha(upstream/'manifest.json')!=SOURCE_SHA or sha(held/'manifest.json')!=HELD_SHA:
        raise ValueError('Unexpected frozen input for dynamics audit')
    return upstream,held


def rms(values):return float(np.sqrt(np.mean(np.square(values))))


def native_components(row,radius):
    d=row['drive_diagnostics'];n=row['task']['nominal_shaped_body'][0]
    u=row['final_ros_reference'][0];effective=row['effective_drive_reference'][0]
    target=radius*(d['left_target_rad_s']+d['right_target_rad_s'])/2
    encoder=radius*(d['left_actual_rad_s']+d['right_actual_rad_s'])/2
    body=row['body_speed_m_s']
    parts=dict(reference_minus_nominal=u-n,gain_map=effective-u,
        target_minus_effective=target-effective,encoder_minus_target=encoder-target,
        body_minus_encoder=body-encoder)
    total=body-n
    if not all(math.isfinite(v) for v in [*parts.values(),total,row['task']['velocity_error_m_s']]):
        raise ValueError('Nonfinite native decomposition')
    if abs(sum(parts.values())-total)>1e-12 or abs(total-row['task']['velocity_error_m_s'])>1e-12:
        raise ValueError('Native decomposition does not reproduce unchanged task error')
    return dict(parts,total=total,target=target,encoder=encoder,body=body,
        drive_source_s=d['sim_time_s'],truth_source_s=row['sensor_clock_s']-row['source_lags_s']['truth'])


def indexed_channels(records):
    selected={n:{} for n in ('truth','wheel','drive','gain_map')};duplicates=Counter()
    for row in records:
        channel=row['channel']
        if channel not in selected:continue
        stamp=row['stamp_s']
        if not math.isfinite(stamp):raise ValueError('Nonfinite raw timestamp')
        ns=round(stamp*1e9);target=selected[channel]
        if ns in target:
            duplicates[channel]+=1
            if target[ns]['values']!=row['values']:
                raise ValueError('Conflicting raw payload at one source stamp: '+channel)
        else:target[ns]=row
    return selected,dict(duplicates)


def align_raw(records,epoch,start,end,maximum_age_s=.04):
    channels,duplicates=indexed_channels(records)
    times={n:sorted(v) for n,v in channels.items()};rows=[];unsupported=[]
    for ns in times['truth']:
        elapsed=ns*1e-9-epoch
        if not start-1e-9<=elapsed<=end+1e-9:continue
        support={};ages={}
        for name in ('wheel','drive'):
            idx=bisect_right(times[name],ns)-1
            if idx<0:
                support[name]=None;continue
            stamp=times[name][idx];ages[name]=(ns-stamp)*1e-9
            support[name]=channels[name][stamp]
            if ns-stamp>round(maximum_age_s*1e9):support[name]=None
        if any(support.get(n) is None for n in ('wheel','drive')):
            unsupported.append(dict(truth_source_ns=ns,ages_s=ages));continue
        drive=support['drive'];dns=round(drive['stamp_s']*1e9)
        gain=channels['gain_map'].get(dns)
        if gain is None:
            unsupported.append(dict(truth_source_ns=ns,error='gain_drive_stamp_unmatched'));continue
        rows.append(dict(task_s=elapsed,truth=channels['truth'][ns]['values'],
            wheel=support['wheel']['values'],drive=drive['values'],gain=gain['values'],
            source_ages_s=ages,truth_source_ns=ns))
    if unsupported or not rows:
        raise ValueError('Raw diagnostic support incomplete; retain data, do not fill: '+str(unsupported[:3]))
    return rows,duplicates


def recovery_fit(times,target,encoder,p):
    t,u,y=(np.asarray(v,dtype=float) for v in (times,target,encoder))
    if t.ndim!=1 or not (t.shape==u.shape==y.shape) or len(t)<20 or not np.isfinite(np.r_[t,u,y]).all():
        raise ValueError('Finite aligned plateau arrays required')
    if np.any(np.diff(t)<=0):raise ValueError('Ordered unique plateau time required')
    if np.ptp(u)>p['constant_target_tolerance_m_s']:
        return dict(eligible=False,reason='target_not_constant_no_static_plateau_fit')
    train=t<=p['fit_end_s']+1e-9;test=~train
    if train.sum()<10 or test.sum()<10:raise ValueError('Both time blocks required')
    gap=y-u;origin=p['plateau_start_s'];grid=p['relaxation_tau_grid_s']
    taus=np.geomspace(grid['minimum'],grid['maximum'],grid['count'])
    result={}
    for name,offset in [('exponential_zero_asymptote',False),('exponential_free_asymptote',True)]:
        fits=[]
        for tau in taus:
            z=np.exp(-(t-origin)/tau)
            X=np.column_stack([z,np.ones(len(t))]) if offset else z[:,None]
            coef=np.linalg.lstsq(X[train],gap[train],rcond=None)[0]
            prediction=X@coef
            fits.append((float(np.sum((prediction[train]-gap[train])**2)),float(tau),coef,prediction))
        idx=int(np.argmin([r[0] for r in fits]));sse,tau,coef,prediction=fits[idx]
        band=[r[1] for r in fits if r[0]<=sse*(1+p['profile_sse_relative_band'])+1e-20]
        result[name]=dict(tau_best_s=tau,amplitude_m_s=float(coef[0]),
            asymptotic_gap_m_s=float(coef[1]) if offset else 0.,train_rmse_m_s=rms(prediction[train]-gap[train]),
            later_block_rmse_m_s=rms(prediction[test]-gap[test]),
            sse_profile_tau_band_s=[min(band),max(band)],profile_band_is_confidence_interval=False,
            tau_grid_boundary=idx in (0,len(taus)-1))
    bias=float(np.mean(gap[train]));static_gain=float(np.dot(u[train],y[train])/np.dot(u[train],u[train]))
    rank=int(np.linalg.matrix_rank(np.column_stack([u,np.ones(len(u))])))
    result.update(eligible=True,fit_samples=int(train.sum()),later_samples=int(test.sum()),
        constant_gap_fit_m_s=bias,constant_gap_later_rmse_m_s=rms(gap[test]-bias),
        static_gain_fit=static_gain,static_gain_later_rmse_m_s=rms(y[test]-static_gain*u[test]),
        affine_gain_bias_design_rank=rank,affine_gain_bias_identified=rank==2,
        rank_is_sufficient_for_physical_identification=False,
        within_run_time_block_not_independent_validation=True,physical_deadtime_identified=False)
    return result


def audit_cell(cell,p,validator=None):
    rows=list(jsonrows(cell/'trace.jsonl'));config=read(cell/'config.json');condition=config['condition']
    if len(rows)!=140 or [r['step'] for r in rows]!=list(range(140)):raise ValueError('Exactly140 sequential source rows required')
    rawdir=cell/'episodes/episode_0/backend/episode_0'
    params=read(rawdir/'drive_parameters.json')
    geometry=config['config']['nominal_geometry'];radius=params['wheel_radius']
    if geometry['radius_l']!=radius or geometry['radius_r']!=radius:
        raise ValueError('Declared nominal and simulated drive radii disagree')
    if params['pi_integrator_profile']!='conditional_v1' or params['velocity_ki']<=0:
        raise ValueError('PI reconstruction source contract differs')
    epoch=rows[0]['sensor_clock_s']-rows[0]['task']['elapsed_s']
    if validator is not None:
        for i,row in enumerate(rows):validator(row,rows[i-1] if i else None,epoch,condition['gain'])
    components=[native_components(r,radius) for r in rows]
    primary=rms([x['total'] for x in components]);original=read(cell/'summary.json')['nominal_velocity_rmse_m_s']
    if not math.isclose(primary,original,rel_tol=1e-10,abs_tol=1e-12):raise ValueError('Changed native primary')
    active=[c for c,r in zip(components,rows) if r['plan_projection']['window_open']]
    names=('reference_minus_nominal','gain_map','target_minus_effective','encoder_minus_target','body_minus_encoder')
    decomp={name:dict(mean_m_s=float(np.mean([x[name] for x in active])),
        rms_m_s=rms([x[name] for x in active])) for name in names}
    aligned,duplicates=align_raw(jsonrows(rawdir/'raw_samples.jsonl'),epoch,
        p['plateau_start_s'],p['plateau_end_s'],p['maximum_source_age_s'])
    time=np.array([r['task_s'] for r in aligned]);target=np.array([
        radius*(r['drive']['left_target_rad_s']+r['drive']['right_target_rad_s'])/2 for r in aligned])
    enc=np.array([radius*sum(r['wheel'])/2 for r in aligned]);body=np.array([r['truth']['speed'] for r in aligned])
    integral=[];errors=[];pi=[];clipped=False
    for row in aligned:
        d=row['drive'];iside=[];eside=[];pside=[]
        for side in ('left','right'):
            error=d[side+'_target_rad_s']-d[side+'_actual_rad_s'];effort=d[side+'_pi_nm']
            if abs(effort)>=params['max_wheel_torque']-1e-9:clipped=True
            eside.append(error);pside.append(effort)
            iside.append((effort-params['velocity_kp']*error)/params['velocity_ki'])
        integral.append(np.mean(iside));errors.append(np.mean(eside));pi.append(np.mean(pside))
    integral,errors,pi=map(np.asarray,(integral,errors,pi))
    predicted_delta=float(np.sum(.5*(errors[1:]+errors[:-1])*np.diff(time)))
    proxy=dict(valid=not clipped,evidence='inferred simulated PI algorithm state, not independently measured torque',
        inferred_integral_start_rad=float(integral[0]),inferred_integral_end_rad=float(integral[-1]),
        inferred_integral_delta_rad=float(integral[-1]-integral[0]),
        trapezoid_error_integral_rad=predicted_delta,
        integration_residual_rad=float(integral[-1]-integral[0]-predicted_delta),
        pi_effort_first_nm=float(pi[0]),pi_effort_last_nm=float(pi[-1]),
        proportional_to_integral_time_ratio_s=params['velocity_kp']/params['velocity_ki'])
    fits=recovery_fit(time,target,enc,p) if condition['arm']!='Causal_gain_candidate' else dict(
        eligible=False,reason='causal_closed_loop_changing_reference_not_fitted')
    half=(p['plateau_start_s']+p['plateau_end_s'])/2
    report=dict(condition=condition,native_rows=140,primary_rmse_reproduced_m_s=primary,
        native_open_component_statistics=decomp,additive_parts_are_not_independent_causal_contributions=True,
        maximum_native_truth_drive_stamp_skew_s=max(abs(x['truth_source_s']-x['drive_source_s']) for x in components),
        raw_plateau_samples=len(aligned),raw_duplicate_counts=duplicates,
        maximum_raw_source_age_s={n:max(r['source_ages_s'][n] for r in aligned) for n in ('wheel','drive')},
        raw_target_encoder_rmse_m_s=rms(enc-target),raw_encoder_body_rmse_m_s=rms(body-enc),
        raw_encoder_body_mean_m_s=float(np.mean(body-enc)),
        raw_apparent_body_encoder_slope=float(np.dot(enc,body)/np.dot(enc,enc)),
        apparent_slope_is_geometry_or_traction_calibration=False,
        target_error_early_mean_m_s=float(np.mean((enc-target)[time<=half])),
        target_error_late_mean_m_s=float(np.mean((enc-target)[time>half])),
        maximum_absolute_GT_yaw_rad=max(abs(r['truth']['pose'][3]) for r in aligned),
        pi_algorithm_state_proxy=proxy,relaxation_models=fits,
        clock='GT source headers, preceding drive and wheel sources; no interpolation or receipt-time alignment')
    points=[dict(task_s=float(t),target_m_s=float(u),encoder_m_s=float(v),body_m_s=float(b),
        inferred_pi_integral_rad=float(it)) for t,u,v,b,it in zip(time,target,enc,body,integral)]
    return report,points


def run(output):
    output=Path(output).expanduser().resolve();upstream,held=source()
    if output.exists():raise ValueError('Diagnostic output exists; preserve it, no overwrite')
    if (output.is_relative_to(upstream) or upstream.is_relative_to(output)
            or output.is_relative_to(held) or held.is_relative_to(output)
            or output.is_relative_to(repo()/'src')):
        raise ValueError('Derived report must be outside sealed inputs and source')
    p=specification();current=fingerprint();output.mkdir(parents=True,exist_ok=False)
    save(output/'specification.json',p)
    try:
        from . import gain_context
        identity=gain_context.identity()
        def validator(*args):return gain_context.verify_transition(*args,expected_identity=identity)
        results=[];pins={}
        for i in range(9):
            cell=upstream/f'eval_{i:02d}';report,points=audit_cell(cell,p,validator)
            results.append(report);save(output/f'chain_{i:02d}.json',points)
            for path in [cell/'trace.jsonl',cell/'config.json',cell/'summary.json',
                cell/'episodes/episode_0/backend/episode_0/raw_samples.jsonl',
                cell/'episodes/episode_0/backend/episode_0/drive_parameters.json']:
                pins[str(path)]=sha(path)
        if fingerprint()!=current or source()!=(upstream,held):raise ValueError('Diagnostic source changed')
        result=dict(id=ID,status='completed_offline_diagnostic_not_system_identification',runs=results,
            diagnostic_runtime=dict(python=platform.python_version(),numpy=np.__version__,
                numeric_dtype='float64',least_squares_rcond='numpy_default'),
            source_artifact=str(upstream),source_manifest_sha256=SOURCE_SHA,
            held_artifact=str(held),held_manifest_sha256=HELD_SHA,source_inputs_sha256=pins,
            native_rows_checked=1260,raw_plateau_samples=sum(r['raw_plateau_samples'] for r in results),
            new_gazebo_launches=0,new_training_transitions=0,actor_loads=0,optimizer_updates=0,
            hardware_actions=0,controller_parameters_changed=False,primary_metric_changed=False,
            parameter_identification_verified=False,physical_benefit_verified=False,
            release=dict(physics_authorized=False,training_authorized=False,hardware_authorized=False),
            real_data_cutoff='2026-11-02')
        save(output/'diagnostic.json',result)
        save(output/'manifest.json',dict(id=ID,fingerprint=current,status='completed',
            created_utc=datetime.now(timezone.utc).isoformat(),files={f.name:sha(f) for f in output.iterdir() if f.is_file()}))
        return result
    except BaseException as exc:
        save(output/'failure.json',dict(error=repr(exc),retain_no_retry=True,physics=0,training=0));raise


def verified_report(output):
    output=Path(output).resolve();m=read(output/'manifest.json')
    if m['fingerprint']!=fingerprint() or m['status']!='completed':raise ValueError('Dynamics audit source/completion changed')
    for name,value in m['files'].items():
        path=(output/name).resolve()
        if path.parent!=output or sha(path)!=value:raise ValueError('Dynamics diagnostic artifact changed')
    result=read(output/'diagnostic.json');upstream,held=source()
    if (result['source_artifact']!=str(upstream) or result['held_artifact']!=str(held)
            or result['source_manifest_sha256']!=SOURCE_SHA or result['held_manifest_sha256']!=HELD_SHA
            or any(result['release'].values())):raise ValueError('Diagnostic dependencies or release changed')
    for name,value in result['source_inputs_sha256'].items():
        path=Path(name).resolve()
        if not path.is_relative_to(upstream) or sha(path)!=value:raise ValueError('Diagnostic input changed')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();r=run(args.output)
    print(json.dumps(dict(status=r['status'],native_rows=r['native_rows_checked'],raw_samples=r['raw_plateau_samples'],physics=0,training=0),indent=2))


if __name__=='__main__':main()
