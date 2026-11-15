"""Immutable input and reporting helpers shared by flat experiments."""
from copy import deepcopy
import csv
import struct
import numpy as np
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()



def immutable(path, data):
    data = data.encode() if isinstance(data,str) else data
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Foundation input changed; choose a new output: ' + str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)



def read(path):
    return json.loads(Path(path).read_text())



def verify(plan):
    for path, expected in plan['assets'].items():
        if digest(path) != expected:
            raise ValueError('Frozen reference input changed: ' + path)



def replace(code, anchor, replacement):
    if code.count(anchor) != 1:
        raise ValueError('Unexpected frozen insertion point: ' + anchor)
    return code.replace(anchor, replacement)



def flat_target(x, profile, matched_scale=1.):
    if profile == 'full':
        return 1.
    if profile == 'matched':
        return matched_scale
    if profile != 'schedule':
        raise ValueError('Unknown flat intervention')
    # Known second-cable position, estimated X only. First cable is unchanged.
    return .70 if 4.45-.55 <= x <= 4.45+.15 else 1.



def scripted_scale(env, previous):
    target = flat_target(env.ros.snapshot().x, os.environ['NINO_AUTHORITY_PROFILE'],
                        float(os.environ.get('NINO_MATCH_SCALE', '1')))
    delta = .4 * env.control_dt
    return min(previous+delta, max(previous-delta, target))



def flat_change(original, candidate):
    """Only slip weight may differ from the same-seed completed control."""
    expected = deepcopy(original)
    expected["reward_v2"]["slip_weight"] *= 1.5
    if candidate != expected:
        raise ValueError("Targeted flat pilot may only increase slip weight by 50%")
    if candidate["seed"] != 43 or candidate["training_reward_scale"] != 0.01:
        raise ValueError("Preserve seed 43 and measured learner reward units")
    return expected



def scaled_mesh(source, fraction):
    """Scale actual triangle elevations, recomputing normals; keep XY and topology."""
    import numpy as np
    data=Path(source).read_bytes()
    count=struct.unpack_from('<I',data,80)[0]
    if len(data) != 84+count*50:
        raise ValueError('Expected binary STL')
    dtype=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    triangles=np.frombuffer(data, dtype=dtype, offset=84).copy()
    triangles['vertices'][:,:,2] *= fraction
    v=triangles['vertices']
    normal=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0])
    length=np.linalg.norm(normal,axis=1)
    if (length==0).any():
        raise ValueError('Degenerate terrain triangle')
    triangles['normal']=normal/length[:,None]
    return (b'Nino foundation: 50 percent relief, same triangle collision/visual'.ljust(80,b'\0')+
            struct.pack('<I',count)+triangles.tobytes()), dict(triangles=count,
                height_range_m=[float(v[:,:,2].min()),float(v[:,:,2].max())],
                maximum_triangle_grade=float(np.linalg.norm(normal[:,:2],axis=1).__truediv__(np.abs(normal[:,2])).max()))



def traces(directory):
    found={}
    for path in Path(directory).glob('*/episode-*/control_trace.csv'):
        rows=list(csv.DictReader(path.open()))
        if not rows:raise ValueError('Empty trace: '+str(path))
        seed=int(rows[0]['seed'])
        if seed in found:raise ValueError('Ambiguous completed traces for seed '+str(seed))
        found[seed]=rows
    return found



def windows(rows,config):
    ranges=sorted((float(r['physical_x_m'])-config['before_m'],float(r['physical_x_m'])+config['after_m'])
        for r in rows if int(r['cue_triggered']))
    merged=[]
    for low,high in ranges:
        if merged and low<=merged[-1][1]:merged[-1][1]=max(high,merged[-1][1])
        else:merged.append([max(0.,low),high])
    return merged



def window_metrics(rows,ranges):
    energy=duration=covered=slip=distance=0.;peak=0.;previous=0.
    for row in rows:
        position=float(row['physical_x_m']);low,high=sorted((previous,position));dx=high-low
        fraction=(sum(max(0.,min(high,b)-max(low,a)) for a,b in ranges)/dx
            if dx>1e-9 else float(any(a<=position<=b for a,b in ranges)))
        fraction=min(1.,fraction);dt=float(row['step_dt_s'])*fraction
        energy+=float(row['step_imu_energy'])*fraction
        covered+=float(row['step_imu_coverage_s'])*fraction
        slip+=float(row['step_slip_square'])*dt
        distance+=dx*fraction;duration+=dt
        if fraction>0:peak=max(peak,float(row['step_imu_peak_m_s2']))
        previous=position
    if min(duration,covered,distance)<=0:raise ValueError('No covered reference disturbance windows')
    return dict(vibration_rms=float(np.sqrt(energy/covered)),slip_rms=float(np.sqrt(slip/duration)),
        vibration_energy_per_m=energy/distance,slip_energy_per_m=slip/distance,
        imu_energy=energy,slip_energy=slip,coverage_s=covered,duration_s=duration,
        distance_m=distance,peak_acceleration_m_s2=peak)



def metrics(summary):
    return {k: summary['metrics_all_episodes'][k]['mean'] for k in
            ('time_seconds', 'truth_path_rmse_m', 'rms_vertical_acceleration_m_s2', 'rms_wheel_slip')}



def report(output, course, summaries, result):
    lines = ['# '+course.title()+' disturbance reference comparison', '',
             'Fixed seeds/config/geometry. No learning updates. Optuna held.', '',
             '| Controller | Arrivals | Time s | Physical RMSE m | Vibration RMS | Slip RMS |',
             '|---|---:|---:|---:|---:|---:|']
    for label, s in summaries.items():
        m = metrics(s)
        lines.append(f"| {label} | {round(s['success_rate']*s['episodes'])}/{s['episodes']} | "
                     + ' | '.join(f'{v:.6f}' for v in m.values())+' |')
    lines += ['', '```json', json.dumps(result, indent=2), '```', '',
              'Phase comparisons are associational. Five fixed-map seeds are a screen, not generalization.',
              'Physical thresholds are unchanged. A failure holds training; no additional schedule search.', '']
    (output / 'REPORT.md').write_text('\n'.join(lines))



def analyze_flat(output, plan, summaries, batches):
    from experiment_assets import traces, window_metrics
    from nino_rl.evaluation import compare_summaries
    from run_flat_seed_repeat import promotion_gates
    trace = {k: traces(output/k) for k in ('full','schedule','matched')}
    if any(sorted(v)!=plan['seeds'] for v in trace.values()): raise ValueError('Flat seeds differ')
    ranges = [plan['protocol']['window']]
    windows = {k:[window_metrics(trace[k][seed],ranges) for seed in plan['seeds']] for k in trace}
    ratios = {k:float(np.mean([r[k] for r in windows['schedule']])/
                      np.mean([r[k] for r in windows['matched']]))
              for k in ('vibration_energy_per_m','slip_energy_per_m')}
    pair = dict(pi=dict(report=summaries['full']), ppo=dict(report=summaries['schedule']),
                comparison=compare_summaries(summaries['full'],summaries['schedule']))
    physical = promotion_gates(pair,dict(promotion_gates=plan['protocol']['physical_gates']))
    error = abs(metrics(summaries['matched'])['time_seconds']-
                metrics(summaries['schedule'])['time_seconds'])/metrics(summaries['schedule'])['time_seconds']
    passes = bool(all(physical[k] for k in ('physical_arrival','completion','tracking','quality')) and
        all(s['success_rate']==1 for s in summaries.values()) and
        error<=plan['protocol']['max_duration_match_error'] and
        min(ratios.values())<=1-plan['protocol']['min_window_gain'] and
        max(ratios.values())<=plan['protocol']['max_other_window_ratio'])
    result = dict(authority_passed=passes, existing_flat_gates=physical,
        window_ratios_to_time_matched_pi=ratios, duration_match_relative_error=error,
        windows=windows, source='Known cable X + estimated pose; no physical pose used for action',
        next_step='Prepare one new-contract PPO pilot for the demonstrated crossing mechanism' if passes else
                  'Hold PPO: the single schedule failed the fixed arrival/time/tracking/quality gate',
        optuna_held=True)
    (output / 'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    report(output,'flat',summaries,{k:v for k,v in result.items() if k!='windows'})
    return result



def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)

