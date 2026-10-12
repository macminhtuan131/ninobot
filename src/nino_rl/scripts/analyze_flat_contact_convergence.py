#!/usr/bin/env python3
"""Separate reset, tracking and contact timestep effects in sixteen episodes."""
import argparse,csv,json
from pathlib import Path
import numpy as np
from train_rough_curriculum import complete_evaluation
from analyze_rough_reactive_authority import window_metrics
ROOT=Path(__file__).resolve().parents[3]

def rows(path):
    with Path(path).open() as stream:return list(csv.DictReader(stream))

def rms(values):return float(np.sqrt(np.mean(np.square(values))))

def episode_data(directory,episode,dt,contract):
    run=next(p.parent for p in directory.glob('*/summary.json') if json.loads(p.read_text()).get('complete'))
    folder=run/f"episode-{int(episode['episode']):03d}"
    control=rows(folder/'control_trace.csv');physical=rows(folder/'ground_truth/actual.csv')
    t=np.array([float(r['time_s']) for r in physical]);x=np.array([float(r['x_m']) for r in physical]);y=np.array([float(r['y_m']) for r in physical])
    w=np.zeros(len(t));w[:-1]+=.5*np.diff(t);w[1:]+=.5*np.diff(t)
    regions={'before_braking':x<3.9,'crossing':(x>=3.9)&(x<=4.8),'after_crossing':x>4.8}
    tracking={k:dict(lateral_rmse_m=float(np.sqrt(np.sum(w[m]*y[m]**2)/np.sum(w[m]))),duration_s=float(w[m].sum()))
        for k,m in regions.items() if w[m].sum()>0}
    origin=float(episode['clock_origin_sim_s']);joint={}
    for r in rows(directory/'joints.csv'):
        stamp=float(r['sim_time_s'])
        # Last .10s before actual first action, not the earlier spawn pause.
        if origin-contract['reset_window_s']-1e-8<=stamp<=origin+1e-8:
            joint.setdefault(r['joint'].split('::')[-1],[]).append(r)
    reset={}
    for name,rs in joint.items():
        last=max(rs,key=lambda r:float(r['sim_time_s']));v=[float(r['velocity_rad_s']) for r in rs]
        reset[name]=dict(angle_rad=float(last['position_rad']),last_velocity_rad_s=float(last['velocity_rad_s']),
            maximum_abs_velocity_rad_s=max(map(abs,v)),samples=len(rs),
            stationary=max(map(abs,v))<=contract['reset_stationary_threshold_rad_s'])
    if not any('swivel' in k for k in reset):raise ValueError('No actual caster swivel readback at reset')
    ct=np.array([float(r['sim_time_s']) for r in control]);cx=np.array([float(r['physical_x_m']) for r in control])
    contacts={}
    for r in rows(directory/'contacts.csv'):
        stamp=float(r['sim_time_s'])
        if not ct[0]<=stamp<=ct[-1] or not 4.1<=np.interp(stamp,ct,cx)<=4.8:continue
        if 'training_cable_1' not in r['other'] or int(r['points'])==0:continue
        name=r['collision'].split('::')[-2];contacts.setdefault(name,[]).append(r)
    contact_stats={}
    for name,rs in contacts.items():
        contact_stats[name]=dict(contact_duration_s=len({r['sim_time_s'] for r in rs})*dt,
            maximum_penetration_m=max(float(r['max_depth_m']) for r in rs),
            maximum_solver_force_n=max((np.linalg.norm([float(r[k]) for k in ('force_x_n','force_y_n','force_z_n')])
                for r in rs if int(r['wrench_points'])>0),default=None))
    drive=rows(folder/'drive_trace.csv');motor={}
    for region,lo,hi in [('before_braking',0.,3.9),('crossing',3.9,4.8),('after_crossing',4.8,10.)]:
        rs=[r for r in drive if ct[0]<=float(r['sim_time_s'])<=ct[-1] and lo<=np.interp(float(r['sim_time_s']),ct,cx)<=hi]
        if rs:motor[region]=dict(wheel_tracking_rmse_rad_s=rms([float(r[s+'_actual_rad_s'])-float(r[s+'_target_rad_s']) for r in rs for s in ('left','right')]),
            mean_executed_speed_m_s=float(np.mean([float(r['executed_linear_m_s']) for r in rs])),
            maximum_abs_torque_nm=max(abs(float(r[s+'_applied_nm'])) for r in rs for s in ('left','right')))
    episode_metrics={k:float(episode[k]) for k in ('time_seconds','truth_path_rmse_m','rms_vertical_acceleration_m_s2','rms_wheel_slip','truth_endpoint_error_m')}
    caster_angles_valid=all(abs(v['angle_rad'])<=contract.get('reset_swivel_angle_tolerance_rad',.001)
        for name,v in reset.items() if 'swivel' in name)
    return dict(seed=int(episode['seed']),arrival=episode['success'] in ('True','1','1.0'),episode=episode_metrics,
        reset_joints=reset,reset_stationary=all(v['stationary'] for v in reset.values()),
        caster_reset_angles_valid=caster_angles_valid,
        tracking_regions=tracking,motor_regions=motor,second_cable_contacts=contact_stats,
        crossing=window_metrics(control,[[4.1,4.8]]),first_cable=window_metrics(control,[[2.1,2.8]]))

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'rl_runs/flat_contact_convergence_v3');args=p.parse_args()
    output=args.output;contract=json.loads((output/'contract.json').read_text());groups={}
    for repeat in (1,2):
        for label,profile in contract['profiles'].items():
            for control in ('full','schedule'):
                directory=output/f'repeat_{repeat}'/label/control
                if 'cold_start' in contract:
                    values={}
                    for seed in contract['seeds']:
                        folder=directory/f'seed_{seed}';batch=complete_evaluation(folder,1)
                        if batch is None:raise ValueError('Incomplete batch '+str(folder))
                        values[seed]=episode_data(folder,batch[0][0],profile['step_seconds'],contract)
                    groups[f'{repeat}/{label}/{control}']=values
                else:
                    batch=complete_evaluation(directory,2)
                    if batch is None:raise ValueError('Incomplete batch '+str(directory))
                    groups[f'{repeat}/{label}/{control}']={int(e['seed']):episode_data(directory,e,profile['step_seconds'],contract) for e in batch[0]}
    metrics=('vibration_energy_per_m','slip_energy_per_m');gates=[];summary={};step_pairs=[]
    for label in contract['profiles']:
        for control in ('full','schedule'):
            rs=[groups[f'{repeat}/{label}/{control}'][seed] for repeat in (1,2) for seed in contract['seeds']]
            summary[f'{label}/{control}']=dict(episodes=4,arrivals=sum(r['arrival'] for r in rs),
                means={k:float(np.mean([r['episode'][k] for r in rs])) for k in rs[0]['episode']},
                window_means={k:float(np.mean([r['crossing'][k] for r in rs])) for k in metrics},
                stationary_resets=sum(r['reset_stationary'] for r in rs))
        for repeat in (1,2):
            rs=[groups[f'{repeat}/{label}/schedule'][seed] for seed in contract['seeds']]
            full=[groups[f'{repeat}/{label}/full'][seed] for seed in contract['seeds']]
            ratio=lambda section,k:float(np.mean([r[section][k] for r in rs])/np.mean([r[section][k] for r in full]))
            window={k:ratio('crossing',k) for k in metrics}
            quality={k:ratio('episode',k) for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')}
            tracking=ratio('episode','truth_path_rmse_m')
            gate=dict(step=label,repeat=repeat,physical=all(r['arrival'] and r['episode']['truth_endpoint_error_m']<=.2+1e-6 for r in rs+full),
                reset_stationary=all(r['reset_stationary'] and r['caster_reset_angles_valid'] for r in rs+full),
                timing=float(np.mean([r['episode']['time_seconds'] for r in rs]))<=18.5,
                tracking=tracking<=1.05,tracking_ratio=tracking,
                local_quality=min(window.values())<=.9 and max(window.values())<=1.,window_ratios=window,
                global_quality=min(quality.values())<=.9 and max(quality.values())<=1.,global_ratios=quality)
            gate['passed']=all(gate[k] for k in ('physical','reset_stationary','timing','tracking','local_quality','global_quality'));gates.append(gate)
    for repeat in (1,2):
        for control in ('full','schedule'):
            for seed in contract['seeds']:
                a=groups[f'{repeat}/1ms/{control}'][seed];b=groups[f'{repeat}/2ms/{control}'][seed]
                relative={k:a['crossing'][k]/max(b['crossing'][k],1e-12)-1 for k in metrics}
                rmse=a['episode']['truth_path_rmse_m']-b['episode']['truth_path_rmse_m']
                depth=lambda r:max((v['maximum_penetration_m'] for v in r['second_cable_contacts'].values()),default=0.)
                delta_depth=depth(a)-depth(b)
                step_pairs.append(dict(repeat=repeat,control=control,seed=seed,relative_crossing_change=relative,
                    tracking_delta_m=rmse,maximum_penetration_delta_m=delta_depth,
                    material_change=any(abs(v)>=.1 for v in relative.values()) or abs(rmse)>=.005 or abs(delta_depth)>=.001))
    # Treat material differences as a reason for investigation, not proof of convergence.
    # Pair/repetition variation is visible below. Two timesteps cannot prove a limit.
    material=any(r['material_change'] for r in step_pairs)
    passed=all(g['passed'] for g in gates) and not material
    result=dict(complete=True,episodes=16,groups=groups,table=summary,gates=gates,step_pairs=step_pairs,
        material_step_dependence=material,screening_gates_passed=passed,flat_ppo_started=False,optuna_held=True,
        qualification=contract['qualification'],next_step='Inspect reset and contact numerics before learning' if material else
            'Independent 24-seed time-matched confirmation before pilot promotion',
        limitations=['Material flags are sensitivity screens, not causal timestep attribution.',
            'Two repeated seeds cannot establish numerical convergence or generalization.',
            'Full-speed PI is slower only under the schedule; these sixteen episodes do not include time-matched PI.',
            'Saved time-matched results at 2ms are not imported as 1ms reference evidence.'])
    (output/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    lines=['# Flat contact timestep and reset comparison','',
        'Original braking x=3.90 m, recovery x=4.60 m. Control .1 s, geometry unchanged. '
        'Seeds 65001/65004, two cold starts per controller/timestep: 16 episodes.','',
        '| Physics / profile | Arrival | Time s | Physical RMSE m | Vibration RMS | Slip RMS | Stationary resets |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for key,v in summary.items():
        m=v['means'];lines.append(f"| {key} | {v['arrivals']}/4 | {m['time_seconds']:.2f} | {m['truth_path_rmse_m']:.4f} | {m['rms_vertical_acceleration_m_s2']:.3f} | {m['rms_wheel_slip']:.3f} | {v['stationary_resets']}/4 |")
    lines+=['','Material sensitivity flag: '+str(material)+'. Screening gates all passed: '+str(passed)+'.',
        'Flat PPO has not started.','', '## Tracking by physical region','',
        '| Repeat / step / profile | Seed | Before braking RMSE m | Crossing RMSE m | After RMSE m |',
        '|---|---:|---:|---:|---:|']
    for key,rs in groups.items():
        for seed,r in rs.items():
            vals=[r['tracking_regions'].get(k,{}).get('lateral_rmse_m',float('nan')) for k in ('before_braking','crossing','after_crossing')]
            lines.append(f'| {key} | {seed} | '+ ' | '.join(f'{v:.4f}' for v in vals)+' |')
    lines+=['','## Evidence and interpretation','',
        'analysis.json includes initial caster angles, measured joint velocities in the last .10s before each first action, '
        'wheel response by region, cable contact duration/depth/solver forces, paired timestep differences and unchanged gates.',
        'Stationary threshold .05 rad/s was frozen before simulation; it is a reset diagnostic, not physical arrival scoring.',
        '',*result['limitations'],'']
    (output/'REPORT.md').write_text('\n'.join(lines));print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
