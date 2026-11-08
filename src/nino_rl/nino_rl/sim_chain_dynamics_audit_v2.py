"""Query-aware raw audit: ambiguous payloads stay unknown, never selected/filled.

V1's failure and sources remain unchanged. V2 reuses its numerical diagnostics,
but records conflicts outside a query and refuses metrics for incomplete queries.
No controller or plant changes; this is an offline reader correction only.
"""
import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,math,platform
from pathlib import Path
import numpy as np
from . import sim_chain_dynamics_audit as v1

ID='nino_sim_chain_dynamics_audit_v2_2026_11_07'
read,save,sha,jsonrows,rms=v1.read,v1.save,v1.sha,v1.jsonrows,v1.rms


def fingerprint():
    base=v1.repo()/'src/nino_rl'
    names=['nino_rl/sim_chain_dynamics_audit_v2.py','test/test_sim_chain_dynamics_audit_v2.py']
    return hashlib.sha256(json.dumps(dict(parent=v1.fingerprint(),files={n:sha(base/n) for n in names}),sort_keys=True).encode()).hexdigest()


def source():
    upstream,held=v1.source()
    failed=Path.home()/'nino_research/sim_chain_dynamics_audit_v1/analysis_2026_11_07'
    f=read(failed/'failure.json')
    if f['error']!="ValueError('Conflicting raw payload at one source stamp: wheel')" or (failed/'manifest.json').exists():
        raise ValueError('V1 failure provenance changed')
    return upstream,held,failed


def align_raw(records,epoch,start,end,maximum_age_s=.04):
    channels={n:{} for n in ('truth','wheel','drive','gain_map')};duplicates=Counter()
    for row in records:
        name=row['channel']
        if name not in channels:continue
        if not math.isfinite(row['stamp_s']):raise ValueError('Nonfinite raw clock')
        stamp=round(row['stamp_s']*1e9);variants=channels[name].setdefault(stamp,[])
        if variants:duplicates[name]+=1
        if not any(v['values']==row['values'] for v in variants):variants.append(row)
    times={n:sorted(v) for n,v in channels.items()};rows=[];unsupported=[]
    conflicts=[dict(channel=n,source_stamp_ns=t,task_s=t*1e-9-epoch,
        payload_variants=[v['values'] for v in versions],
        within_query_support=start-maximum_age_s-1e-9<=t*1e-9-epoch<=end+1e-9)
        for n,groups in channels.items() for t,versions in groups.items() if len(versions)>1]
    eligible=0
    for stamp in times['truth']:
        t=stamp*1e-9-epoch
        if not start-1e-9<=t<=end+1e-9:continue
        eligible+=1;selected={};ages={};reasons=[]
        if len(channels['truth'][stamp])!=1:reasons.append('ambiguous_truth')
        else:selected['truth']=channels['truth'][stamp][0]
        for name in ('wheel','drive'):
            i=bisect_right(times[name],stamp)-1
            if i<0:reasons.append('missing_'+name);continue
            ns=times[name][i];ages[name]=(stamp-ns)*1e-9
            if stamp-ns>round(maximum_age_s*1e9):reasons.append('stale_'+name)
            elif len(channels[name][ns])!=1:reasons.append('ambiguous_'+name)
            else:selected[name]=channels[name][ns][0]
        if 'drive' in selected:
            ns=round(selected['drive']['stamp_s']*1e9);gain=channels['gain_map'].get(ns,[])
            if len(gain)!=1:reasons.append('missing_or_ambiguous_gain_map')
            else:selected['gain']=gain[0]
        if reasons:
            unsupported.append(dict(truth_source_ns=stamp,task_s=t,reasons=reasons,ages_s=ages));continue
        rows.append(dict(task_s=t,truth=selected['truth']['values'],wheel=selected['wheel']['values'],
            drive=selected['drive']['values'],gain=selected['gain']['values'],source_ages_s=ages))
    return dict(rows=rows,eligible_samples=eligible,unsupported=unsupported,
        query_complete=bool(eligible and not unsupported),conflicts=conflicts,
        duplicate_counts=dict(duplicates),no_payload_selected_from_ambiguous_stamps=True)


def plateau(rows,params,p):
    radius=params['wheel_radius'];time=np.array([r['task_s'] for r in rows])
    target=np.array([radius*(r['drive']['left_target_rad_s']+r['drive']['right_target_rad_s'])/2 for r in rows])
    encoder=np.array([radius*sum(r['wheel'])/2 for r in rows]);body=np.array([r['truth']['speed'] for r in rows])
    integrals=[];errors=[];pis=[];clipped=False
    for row in rows:
        d=row['drive'];ii=[];ee=[];pp=[]
        for side in ('left','right'):
            e=d[side+'_target_rad_s']-d[side+'_actual_rad_s'];pi=d[side+'_pi_nm']
            if abs(pi)>=params['max_wheel_torque']-1e-9:clipped=True
            ii.append((pi-params['velocity_kp']*e)/params['velocity_ki']);ee.append(e);pp.append(pi)
        integrals.append(np.mean(ii));errors.append(np.mean(ee));pis.append(np.mean(pp))
    integrals,errors,pis=map(np.asarray,(integrals,errors,pis))
    integral_dt=float(np.sum(.5*(errors[:-1]+errors[1:])*np.diff(time)))
    half=(p['plateau_start_s']+p['plateau_end_s'])/2
    metrics=dict(raw_target_encoder_rmse_m_s=rms(encoder-target),raw_encoder_body_rmse_m_s=rms(body-encoder),
        raw_encoder_body_mean_m_s=float(np.mean(body-encoder)),
        raw_apparent_body_encoder_slope=float(np.dot(encoder,body)/np.dot(encoder,encoder)),
        apparent_slope_is_geometry_or_traction_calibration=False,
        target_error_early_mean_m_s=float(np.mean((encoder-target)[time<=half])),
        target_error_late_mean_m_s=float(np.mean((encoder-target)[time>half])),
        maximum_absolute_GT_yaw_rad=max(abs(r['truth']['pose'][3]) for r in rows),
        maximum_raw_source_age_s={n:max(r['source_ages_s'][n] for r in rows) for n in ('wheel','drive')},
        pi_algorithm_state_proxy=dict(valid=not clipped,
            evidence='inferred simulated PI algorithm state, not independently measured torque',
            inferred_integral_start_rad=float(integrals[0]),inferred_integral_end_rad=float(integrals[-1]),
            inferred_integral_delta_rad=float(integrals[-1]-integrals[0]),
            trapezoid_error_integral_rad=integral_dt,
            integration_residual_rad=float(integrals[-1]-integrals[0]-integral_dt),
            pi_effort_first_nm=float(pis[0]),pi_effort_last_nm=float(pis[-1]),
            proportional_to_integral_time_ratio_s=params['velocity_kp']/params['velocity_ki']))
    points=[dict(task_s=float(t),target_m_s=float(u),encoder_m_s=float(e),body_m_s=float(b),
        inferred_pi_integral_rad=float(i)) for t,u,e,b,i in zip(time,target,encoder,body,integrals)]
    return metrics,points,v1.recovery_fit(time,target,encoder,p)


def audit_cell(cell,p,validator=None):
    source_rows=list(jsonrows(cell/'trace.jsonl'));config=read(cell/'config.json');condition=config['condition']
    if len(source_rows)!=140 or [r['step'] for r in source_rows]!=list(range(140)):
        raise ValueError('Exactly140 sequential source rows required')
    rawdir=cell/'episodes/episode_0/backend/episode_0';params=read(rawdir/'drive_parameters.json')
    geometry=config['config']['nominal_geometry'];radius=params['wheel_radius']
    if geometry['radius_l']!=radius or geometry['radius_r']!=radius:raise ValueError('Geometry mismatch')
    if params['pi_integrator_profile']!='conditional_v1' or params['velocity_ki']<=0:raise ValueError('PI contract mismatch')
    epoch=source_rows[0]['sensor_clock_s']-source_rows[0]['task']['elapsed_s']
    if validator:
        for i,r in enumerate(source_rows):validator(r,source_rows[i-1] if i else None,epoch,condition['gain'])
    native=[v1.native_components(r,radius) for r in source_rows]
    primary=rms([r['total'] for r in native])
    if not math.isclose(primary,read(cell/'summary.json')['nominal_velocity_rmse_m_s'],rel_tol=1e-10,abs_tol=1e-12):
        raise ValueError('Primary changed')
    active=[x for x,r in zip(native,source_rows) if r['plan_projection']['window_open']]
    names=('reference_minus_nominal','gain_map','target_minus_effective','encoder_minus_target','body_minus_encoder')
    stats={n:dict(mean_m_s=float(np.mean([x[n] for x in active])),rms_m_s=rms([x[n] for x in active])) for n in names}
    query=align_raw(jsonrows(rawdir/'raw_samples.jsonl'),epoch,p['plateau_start_s'],p['plateau_end_s'],p['maximum_source_age_s'])
    report=dict(condition=condition,native_rows=140,primary_rmse_reproduced_m_s=primary,
        native_open_component_statistics=stats,additive_parts_are_not_independent_causal_contributions=True,
        maximum_native_truth_drive_stamp_skew_s=max(abs(r['truth_source_s']-r['drive_source_s']) for r in native),
        raw_query_complete=query['query_complete'],raw_query_eligible_samples=query['eligible_samples'],
        raw_query_supported_samples=len(query['rows']),raw_query_unsupported=query['unsupported'],
        raw_conflicts=query['conflicts'],raw_duplicate_counts=query['duplicate_counts'],
        raw_target_encoder_rmse_m_s=None,raw_encoder_body_rmse_m_s=None,
        pi_algorithm_state_proxy=None,relaxation_models=dict(eligible=False,reason='incomplete_raw_query_unknown'))
    points=[]
    if query['query_complete']:
        metrics,points,models=plateau(query['rows'],params,p);report.update(metrics)
        report['relaxation_models']=(models if condition['arm']!='Causal_gain_candidate' else dict(
            eligible=False,reason='causal_closed_loop_changing_reference_not_fitted'))
    return report,points


def run(output):
    output=Path(output).expanduser().resolve();upstream,held,failed=source()
    if output.exists():raise ValueError('Diagnostic output exists; preserve it, no overwrite')
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in (upstream,held,failed)) or output.is_relative_to(v1.repo()/'src'):
        raise ValueError('Derived report must be outside sealed inputs and source')
    p=v1.specification();current=fingerprint();output.mkdir(parents=True,exist_ok=False)
    save(output/'specification.json',dict(p,id=ID,
        reader_correction='retain all conflicts; full-query metrics unknown if any ambiguous support; no selection or interpolation'))
    from . import gain_context
    identity=gain_context.identity()
    def validate(*args):return gain_context.verify_transition(*args,expected_identity=identity)
    pins={};reports=[]
    try:
        for i in range(9):
            cell=upstream/f'eval_{i:02d}';r,points=audit_cell(cell,p,validate);reports.append(r)
            save(output/f'chain_{i:02d}.json',points)
            for path in [cell/'trace.jsonl',cell/'config.json',cell/'summary.json',
                cell/'episodes/episode_0/backend/episode_0/raw_samples.jsonl',
                cell/'episodes/episode_0/backend/episode_0/drive_parameters.json']:
                pins[str(path)]=sha(path)
        if current!=fingerprint() or source()!=(upstream,held,failed):raise ValueError('Audit sources changed')
        result=dict(id=ID,status='completed_offline_diagnostic_with_unknown_queries',runs=reports,
            source_artifact=str(upstream),source_manifest_sha256=v1.SOURCE_SHA,
            held_artifact=str(held),held_manifest_sha256=v1.HELD_SHA,
            failed_v1_artifact=str(failed),failed_v1_failure_sha256=sha(failed/'failure.json'),
            source_inputs_sha256=pins,native_rows_checked=1260,
            raw_query_eligible_samples=sum(r['raw_query_eligible_samples'] for r in reports),
            raw_query_supported_samples=sum(r['raw_query_supported_samples'] for r in reports),
            complete_raw_query_cells=sum(r['raw_query_complete'] for r in reports),
            unknown_raw_query_cells=sum(not r['raw_query_complete'] for r in reports),
            raw_conflicting_stamps=sum(len(r['raw_conflicts']) for r in reports),
            controller_parameters_changed=False,primary_metric_changed=False,
            diagnostic_runtime=dict(python=platform.python_version(),numpy=np.__version__,numeric_dtype='float64'),
            new_gazebo_launches=0,new_training_transitions=0,actor_loads=0,optimizer_updates=0,hardware_actions=0,
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
    output=Path(output).resolve();mf=read(output/'manifest.json')
    if mf['status']!='completed' or mf['fingerprint']!=fingerprint():raise ValueError('Dynamics V2 sources/completion changed')
    for name,value in mf['files'].items():
        path=(output/name).resolve()
        if path.parent!=output or sha(path)!=value:raise ValueError('Dynamics V2 artifact changed')
    r=read(output/'diagnostic.json');upstream,held,failed=source()
    if (r['source_artifact']!=str(upstream) or r['held_artifact']!=str(held) or r['failed_v1_artifact']!=str(failed)
            or sha(failed/'failure.json')!=r['failed_v1_failure_sha256'] or any(r['release'].values())):
        raise ValueError('Dynamics V2 dependency/release changed')
    for name,value in r['source_inputs_sha256'].items():
        path=Path(name).resolve()
        if not path.is_relative_to(upstream) or sha(path)!=value:raise ValueError('Dynamics V2 input changed')
    return r


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    r=run(parser.parse_args().output)
    print(json.dumps(dict(status=r['status'],native_rows=r['native_rows_checked'],raw_complete_cells=r['complete_raw_query_cells'],
        raw_unknown_cells=r['unknown_raw_query_cells'],conflicts_retained=r['raw_conflicting_stamps'],physics=0,training=0),indent=2))


if __name__=='__main__':main()
