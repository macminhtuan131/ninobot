#!/usr/bin/env python3
"""Contact/impact associations and paired repeatability; no training or reward edits."""
import csv
import json
from pathlib import Path
import sys
import numpy as np
import struct

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).parent))
from run_flat_contact_repeatability import OUTPUT as SOURCE
from train_rough_curriculum import complete_evaluation
from analyze_rough_reactive_authority import window_metrics
OUTPUT=ROOT/'docs/flat_contact_repeatability_2026-10-12'

def rows(path):
    with Path(path).open() as stream:return list(csv.DictReader(stream))

def contact_stats(contact,control,low,high):
    t=np.array([float(r['sim_time_s']) for r in control]);x=np.array([float(r['physical_x_m']) for r in control])
    selected={};impact=max((r for r in control if low<=float(r['physical_x_m'])<=high),key=lambda r:float(r['step_imu_energy']))
    end=float(impact['sim_time_s']);begin=end-float(impact['step_dt_s'])
    for r in contact:
        stamp=float(r['sim_time_s'])
        if not t[0]<=stamp<=t[-1]:continue
        pos=float(np.interp(stamp,t,x))
        if not low<=pos<=high:continue
        name=r['collision'].split('::')[-2]
        if 'base_footprint'==name:
            name='laser' if 'laser_collision' in r['collision'] else 'chassis'
        selected.setdefault(name,[]).append(r)
    stats={};impact_contacts={}
    for name,values in selected.items():
        stamps=sorted({float(r['sim_time_s']) for r in values})
        touched={float(r['sim_time_s']) for r in values if int(r['points'])>0}
        cable={float(r['sim_time_s']) for r in values if int(r['points'])>0 and 'training_cable_1' in r['other']}
        absent=[v for v in stamps if v not in touched];longest=run=0;last=None
        for v in absent:
            run=run+.002 if last is not None and v-last<=.00201 else .002
            longest=max(longest,run);last=v
        depth=max(float(r['max_depth_m']) for r in values)
        forces=[np.sqrt(sum(float(r[k])**2 for k in ('force_x_n','force_y_n','force_z_n'))) for r in values if int(r['wrench_points'])>0]
        angle=[]
        if 'bracket' in name:
            yaw=np.array([float(r['physical_yaw_rad']) for r in control]) if 'physical_yaw_rad' in control[0] else None
            for r in values:
                if yaw is not None:
                    a=float(r['yaw_rad'])-float(np.interp(float(r['sim_time_s']),t,yaw))
                    angle.append(float(np.arctan2(np.sin(a),np.cos(a))))
        stats[name]=dict(physics_samples=len(stamps),touch_fraction=len(touched)/len(stamps),
            second_cable_contact_samples=len(cable),longest_no_contact_seconds=longest,
            max_depth_m=depth,max_contact_force_norm_n=max(forces) if forces else None,
            wrench_data_available=bool(forces),
            caster_relative_yaw_min_deg=float(np.rad2deg(min(angle))) if angle else None,
            caster_relative_yaw_max_deg=float(np.rad2deg(max(angle))) if angle else None)
        local=[r for r in values if begin-1e-8<=float(r['sim_time_s'])<=end+1e-8 and int(r['points'])>0]
        impact_contacts[name]=dict(contact_samples=len({r['sim_time_s'] for r in local}),
            contacted=sorted({r['other'] for r in local}),max_depth_m=max((float(r['max_depth_m']) for r in local),default=0),
            max_force_norm_n=max((np.sqrt(sum(float(r[k])**2 for k in ('force_x_n','force_y_n','force_z_n')))
                for r in local if int(r['wrench_points'])>0),default=None))
    return dict(window=stats,strongest_action=dict(sim_end=end,x_m=float(impact['physical_x_m']),
        imu_energy=float(impact['step_imu_energy']),imu_peak_m_s2=float(impact['step_imu_peak_m_s2']),
        scale=float(impact['speed_scale']),contacts=impact_contacts))

def main():
    OUTPUT.mkdir(parents=True,exist_ok=True);contract=json.loads((SOURCE/'contract.json').read_text())
    groups={};completed=0
    for repeat in range(1,4):
        for label in contract['profiles']:
            directory=SOURCE/f'repeat_{repeat}'/label;batch=complete_evaluation(directory,2)
            if batch is None:continue
            episode_rows,summary=batch
            summary_path=next(directory.glob('*/summary.json'));run=summary_path.parent
            contact=rows(directory/'contacts.csv');data={}
            for episode in episode_rows:
                seed=int(episode['seed']);control=rows(run/f"episode-{int(episode['episode']):03d}/control_trace.csv")
                window=window_metrics(control,[[4.1,4.8]])
                contact_report=contact_stats(contact,control,4.1,4.8)
                impact=contact_report['strongest_action'];end=impact['sim_end'];start=end-.1
                drive=rows(run/f"episode-{int(episode['episode']):03d}/drive_trace.csv")
                local=[r for r in drive if start-1e-8<=float(r['sim_time_s'])<=end+1e-8]
                if not local:raise ValueError('No motor response during recorded impact')
                contact_report['strongest_action']['motor_response']=dict(
                    samples=len(local),requested_linear_mean_m_s=float(np.mean([float(r['requested_linear_m_s']) for r in local])),
                    executed_linear_mean_m_s=float(np.mean([float(r['executed_linear_m_s']) for r in local])),
                    max_abs_applied_torque_nm=max(abs(float(r[k])) for r in local for k in ('left_applied_nm','right_applied_nm')),
                    wheel_tracking_rmse_rad_s=float(np.sqrt(np.mean([.5*sum((float(r[side+'_actual_rad_s'])-float(r[side+'_target_rad_s']))**2
                        for side in ('left','right')) for r in local]))))
                physical=rows(run/f"episode-{int(episode['episode']):03d}/ground_truth/actual.csv")
                path_x=np.array([float(r['x_m']) for r in physical]);path_y=np.array([float(r['y_m']) for r in physical])
                path_t=np.array([float(r['time_s']) for r in physical]);weights=np.zeros(len(path_t))
                weights[:-1]+=.5*np.diff(path_t);weights[1:]+=.5*np.diff(path_t)
                # Fixed flat reference is y=0; these are region lateral-error diagnostics,
                # not a replacement for the unchanged full physical path metric.
                regions={'before_braking':path_x<3.9,'second_crossing':(path_x>=3.9)&(path_x<=4.8),'after_crossing':path_x>4.8}
                lateral_regions={k:dict(time_s=float(weights[m].sum()),
                    lateral_rmse_m=float(np.sqrt(np.sum(path_y[m]**2*weights[m])/weights[m].sum())))
                    for k,m in regions.items() if weights[m].sum()>0}
                data[seed]=dict(episode={k:float(episode[k]) for k in ('time_seconds','truth_path_rmse_m',
                    'rms_vertical_acceleration_m_s2','rms_wheel_slip','truth_endpoint_error_m')},
                    arrival=str(episode['success']).lower() in ('true','1','1.0'),window=window,
                    contacts=contact_report,
                    physical_lateral_regions=lateral_regions,
                    first_cable=window_metrics(control,[[2.1,2.8]]))
            groups[f'{repeat}/{label}']=data;completed+=1
    paired=[]
    for repeat in range(1,4):
        if any(f'{repeat}/{k}' not in groups for k in contract['profiles']):continue
        for seed in contract['seeds']:
            for label in ('old_460','new_455'):
                a=groups[f'{repeat}/{label}'][seed];b=groups[f'{repeat}/matched'][seed];full=groups[f'{repeat}/full'][seed]
                ratios={k:a['window'][k]/b['window'][k] for k in ('vibration_energy_per_m','slip_energy_per_m')}
                global_ratios={k:a['episode'][k]/full['episode'][k] for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')}
                duration=abs(a['episode']['time_seconds']/b['episode']['time_seconds']-1)
                local=min(ratios.values())<=.9 and max(ratios.values())<=1
                quality=min(global_ratios.values())<=.9 and max(global_ratios.values())<=1
                paired.append(dict(repeat=repeat,seed=seed,profile=label,window_ratios_to_matched=ratios,
                    global_ratios_to_full=global_ratios,duration_match_error=duration,
                    pair_passed=bool(a['arrival'] and b['arrival'] and full['arrival'] and local and quality and duration<=.03
                        and a['episode']['time_seconds']<=18.5
                        and a['episode']['truth_path_rmse_m']<=1.05*full['episode']['truth_path_rmse_m'])))
    table={};repeat_gates=[]
    for label in contract['profiles']:
        values=[groups[f'{r}/{label}'][seed] for r in range(1,4) if f'{r}/{label}' in groups for seed in contract['seeds']]
        if not values:continue
        table[label]=dict(episodes=len(values),arrivals=sum(v['arrival'] for v in values),
            means={k:float(np.mean([v['episode'][k] for v in values])) for k in values[0]['episode']},
            window_means={k:float(np.mean([v['window'][k] for v in values])) for k in ('vibration_energy_per_m','slip_energy_per_m')},
            window_vibration_energy_range=[min(v['window']['imu_energy'] for v in values),max(v['window']['imu_energy'] for v in values)])
    for repeat in range(1,4):
        if any(f'{repeat}/{k}' not in groups for k in contract['profiles']):continue
        mean=lambda label,section,key:float(np.mean([groups[f'{repeat}/{label}'][s][section][key] for s in contract['seeds']]))
        for label in ('old_460','new_455'):
            window_ratios={k:mean(label,'window',k)/mean('matched','window',k)
                for k in ('vibration_energy_per_m','slip_energy_per_m')}
            quality_ratios={k:mean(label,'episode',k)/mean('full','episode',k)
                for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')}
            matching=abs(mean(label,'episode','time_seconds')/mean('matched','episode','time_seconds')-1)
            physical=all(groups[f'{repeat}/{p}'][s]['arrival'] and groups[f'{repeat}/{p}'][s]['episode']['truth_endpoint_error_m']<=.20+1e-6
                for p in (label,'full','matched') for s in contract['seeds'])
            gate=dict(repeat=repeat,profile=label,physical=physical,completion=mean(label,'episode','time_seconds')<=18.5,
                tracking=mean(label,'episode','truth_path_rmse_m')<=1.05*mean('full','episode','truth_path_rmse_m'),
                quality=min(quality_ratios.values())<=.9 and max(quality_ratios.values())<=1,
                window_benefit=min(window_ratios.values())<=.9 and max(window_ratios.values())<=1,
                duration_match=matching<=.03,window_ratios=window_ratios,quality_ratios=quality_ratios,matching_error=matching)
            gate['passed']=all(gate[k] for k in ('physical','completion','tracking','quality','window_benefit','duration_match'))
            repeat_gates.append(gate)
    mesh=ROOT/'src/nino_description/meshes/caster_bracket_front1.STL';binary=mesh.read_bytes()
    count=struct.unpack_from('<I',binary,80)[0]
    if len(binary)!=84+count*50:raise ValueError('Unexpected caster mesh format')
    vertices=np.array([xyz for i in range(count) for xyz in np.array(struct.unpack_from('<9f',binary,84+50*i+12)).reshape(3,3)])
    from prepare_rough_foundations import digest
    geometry=dict(mesh=str(mesh),mesh_sha256=digest(mesh),local_min_m=vertices.min(0).tolist(),local_max_m=vertices.max(0).tolist(),
        nominal_swivel_z_m=.041,nominal_lowest_fork_z_m=float(.041+vertices[:,2].min()),
        caster_radius_m=.016,second_cable_radius_m=.010,second_cable_top_m=.020,
        qualification='Nominal level pose; dynamic clearance changes with pitch, lift and swivel. Not a real robot measurement.')
    result=dict(complete=completed==12,completed_batches=completed,contract=str(SOURCE/'contract.json'),
        geometry=geometry,
        groups=groups,paired=paired,table=table,training_started=False,optuna_held=True,
        repeat_gates=repeat_gates,
        reproducible_local_crossing_benefit={label:completed==12 and all(p['physical'] and p['window_benefit'] and p['duration_match']
            for p in repeat_gates if p['profile']==label) for label in ('old_460','new_455')},
        all_repeat_promotion_gates_passed={label:completed==12 and all(p['passed'] for p in repeat_gates if p['profile']==label)
            for label in ('old_460','new_455')},
        limitations=['Three repeats of two scenarios do not estimate unseen-course generalization.',
            'Contact logging is a common additional instrumentation condition in all repeats.',
            'Temporal overlap with contact is association, not proof of causal mechanism.',
            'Wrench magnitudes are raw solver contact outputs, not calibrated physical force measurements.',
            'Original 24-arrival promotion requirement remains; these six repeated runs are only a repeatability screen.'])
    (OUTPUT/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    if result['complete']:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
        for ax,metric,title in zip(axes,('vibration_energy_per_m','slip_energy_per_m'),('Vibration energy per metre','Slip energy per metre')):
            for profile,offset,marker in [('old_460',-.12,'o'),('new_455',.12,'s')]:
                for seed,color in [(65001,'#3167b1'),(65004,'#cf6329')]:
                    values=[v for v in paired if v['profile']==profile and v['seed']==seed]
                    ax.plot([v['repeat']+offset for v in values],[v['window_ratios_to_matched'][metric] for v in values],
                        marker=marker,color=color,alpha=.8,label=f'{profile}, seed {seed}')
            ax.axhline(1,color='black',lw=1);ax.axhline(.9,color='gray',ls='--',lw=1)
            ax.set(xticks=[1,2,3],xlabel='Fresh simulator repetition',ylabel='Ratio to time-matched PI',title=title,yscale='log')
            ax.grid(alpha=.2)
        axes[0].legend(fontsize=8);fig.suptitle('Average benefit hides scenario-specific contact variation')
        fig.savefig(OUTPUT/'paired_crossing_ratios.png',dpi=160);plt.close(fig)
    lines=['# Flat cable contact and impact repeatability','',
        'Seeds 65001/65004, three fresh simulator starts per profile; seed order alternates. '
        'No PPO pilot or Optuna started. Robot contacts logged at 2 ms physics resolution.','',
        '| Profile | Arrival | Time s | Physical RMSE m | Vibration RMS | Slip RMS | Cable-window energy/m | Cable-window energy range |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for label,data in table.items():
        m=data['means'];w=data['window_means'];low,high=data['window_vibration_energy_range']
        lines.append(f"| {label} | {data['arrivals']}/{data['episodes']} | {m['time_seconds']:.2f} | {m['truth_path_rmse_m']:.4f} | {m['rms_vertical_acceleration_m_s2']:.3f} | {m['rms_wheel_slip']:.3f} | {w['vibration_energy_per_m']:.2f} | {low:.2f}–{high:.2f} |")
    lines+=['','Reproducible local crossing benefit: `'+json.dumps(result['reproducible_local_crossing_benefit'])+'`.',
        'All repeat promotion gates: `'+json.dumps(result['all_repeat_promotion_gates_passed'])+'`.','',
        'Local benefit above refers to two-seed batch means in each repetition, not every individual scenario. '
        'Individual worsening remains in paired results; no flat pilot is qualified.','',
        '![Scenario-specific crossing ratios](paired_crossing_ratios.png)','',
        '## Largest second-cable impact action in each repeat','',
        '| Repeat/profile | Seed | x m | Scale | Action energy | Chassis contact | Caster brackets | Drive wheels |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for group,seeds in groups.items():
        for seed,v in seeds.items():
            action=v['contacts']['strongest_action'];cs=action['contacts']
            has=lambda name:any('training_cable_1' in other for k,c in cs.items() if name in k for other in c['contacted'])
            drive=any('training_cable_1' in other for k,c in cs.items()
                if k in ('left_wheel_link','right_wheel_link') for other in c['contacted'])
            lines.append(f"| {group} | {seed} | {action['x_m']:.3f} | {action['scale']:.3f} | {action['imu_energy']:.2f} | {has('chassis')} | {has('bracket')} | {drive} |")
    lines+=['','## Geometry and interpretation','',
        f"- Nominal fork clearance: {1000*geometry['nominal_lowest_fork_z_m']:.2f} mm. Caster radius: 16 mm. Second cable top: 20 mm.",
        '- Bracket contact is geometrically plausible during a crossing; do not assume every spike is a reward or speed-recovery defect.',
        '- Contact depth and wrench are solver outputs. Deep caster/cable penetration and wheel contact gaps warrant numerical contact convergence checks before treating vibration changes as reliable control gains.',
        '- First-cable data are also saved: full and both schedules request full speed there. Their variation cannot be attributed to later braking.',
        '', 'Details: analysis.json includes contact gaps, penetration, solver wrench magnitudes, caster orientation and motor response during the strongest impact.','',
        *result['limitations'],'']
    (OUTPUT/'REPORT.md').write_text('\n'.join(lines));print(json.dumps(table,indent=2));print('Completed batches',completed)

if __name__=='__main__':main()
