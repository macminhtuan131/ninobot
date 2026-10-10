#!/usr/bin/env python3
"""Compare completed rough PI diagnostics with independent physical metrics."""
import csv
import json
from pathlib import Path
import numpy as np

from run_rough_localized import EXPERIMENT, ROOT, verify


def latest(parent):
    for path in sorted(parent.glob('*/summary.json'), reverse=True):
        if json.loads(path.read_text()).get('complete'):
            with (path.parent/'episodes.csv').open() as stream:
                rows=list(csv.DictReader(stream))
            if len(rows)==3:
                return path,rows
    raise RuntimeError(f'No completed three-episode evaluation: {parent}')


def main():
    verify()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # Keep the earlier 2D qualification report intact.
    out=ROOT/'docs/rough_cloud_localization_2026-10-09'
    out.mkdir(exist_ok=True)
    fig,axes=plt.subplots(1,3,figsize=(13,5),layout='constrained')
    comparison={}
    lines=['# Rough PI qualification comparison','',
        '| Route | Original / corrected arrivals | Physical endpoint (m) | Physical path RMSE (m) | Pose disagreement (m) | Time (s) |',
        '|---|---:|---:|---:|---:|---:|']
    for ax,route in zip(axes,('E1','N1','S1')):
        original,old=latest(ROOT/'rl_runs/rough_turn_pi_candidate_20261009'/route)
        corrected,new=latest(EXPERIMENT/'pi'/route)
        def metrics(rows):
            return {'successes':sum(r['success'].lower()=='true' for r in rows),'episodes':len(rows),
                'maximum_motion_feedback_lag_s':max(float(r['max_motion_sensor_lag_seconds']) for r in rows),
                **{key:float(np.mean([float(r[key]) for r in rows])) for key in
                    ('truth_endpoint_error_m','truth_path_rmse_m','odom_truth_position_error_m',
                     'time_seconds','rms_wheel_slip','rms_vertical_acceleration_m_s2')}}
        a,b=metrics(old),metrics(new)
        comparison[route]={'original':a,'corrected':b,'original_summary':str(original),
            'corrected_summary':str(corrected)}
        pairs=[f'{a[key]:.3f} → {b[key]:.3f}' for key in
            ('truth_endpoint_error_m','truth_path_rmse_m','odom_truth_position_error_m','time_seconds')]
        lines.append(f'| {route} | {a["successes"]}/3 → {b["successes"]}/3 | '+ ' | '.join(pairs)+' |')
        for path,label,color in [(original,'Original PI','#c85645'),(corrected,'Corrected PI','#137a66')]:
            with (path.parent/'episode-001/control_trace.csv').open() as stream:
                trace=list(csv.DictReader(stream))
            ax.plot([float(r['physical_x_m']) for r in trace],[float(r['physical_y_m']) for r in trace],
                color=color,label=label+' physical',linewidth=2)
            ax.plot([float(r['estimated_x_m']) for r in trace],[float(r['estimated_y_m']) for r in trace],
                color=color,linestyle=':',label=label+' estimated',alpha=.65)
        goal=(10.5,0.) if route=='E1' else (2.5,6.2 if route=='N1' else -6.2)
        points=np.array([[0,0],goal] if route=='E1' else [[0,0],[2.5,0],goal])
        ax.plot(points[:,0],points[:,1],'k--',alpha=.4,label='Drawn reference')
        ax.add_patch(plt.Circle(goal,.2,color='#55a85f',fill=False))
        ax.set_title(route)
        ax.set(xlabel='X (m)',ylabel='Y (m)')
        ax.axis('equal');ax.grid(alpha=.2)
    slow_path,slow_rows=latest(EXPERIMENT/'slow_e1')
    comparison['E1_slow']={'corrected':metrics(slow_rows),'corrected_summary':str(slow_path),
                           'baseline_speed_scale':.65}
    def coverage(path):
        observations=accepted=0
        counts=[]
        for line in path.open():
            r=json.loads(line)
            if not 7.7 < r['pose'][0] < 8.6:
                continue
            observations+=1
            if r['fix'] is not None and np.linalg.norm(np.asarray(r['fix'])-r['pose'][:2])<=.30:
                accepted+=1
                counts.append(r['counts'])
        return {'source':str(path),'crest_x_interval_m':[7.7,8.6],
            'observations':observations,'accepted_fixes':accepted,
            'minimum_axis_rays':np.min(counts,axis=0).tolist() if counts else None}
    comparison['coverage']={
        'previous_ppo_2d':coverage(ROOT/'rl_runs/rough_wall_slip_v7/curriculum/blocks/block_0000/wall_observations.jsonl'),
        'cloud_qualification':coverage(
            EXPERIMENT/'slow_e1_logs/wall_observations.jsonl' if (EXPERIMENT/'slow_e1_logs/wall_observations.jsonl').exists()
            else EXPERIMENT/'qualification_logs/wall_observations.jsonl')}
    lines += ['', '## Slow E1 crest check', '',
        f'Physical arrivals: {comparison["E1_slow"]["corrected"]["successes"]}/3 at 65% speed.',
        f'Mean pose disagreement: {comparison["E1_slow"]["corrected"]["odom_truth_position_error_m"]:.4f} m.']
    lines += [f'Maximum motion-feedback lag: {comparison["E1_slow"]["corrected"]["maximum_motion_feedback_lag_s"]:.3f} s '
              '(unchanged limit: 0.040 s).', '',
        'Crest coverage observations are included in comparison.json. The prior PPO '
        'and current PI have different motion profiles; these counts diagnose '
        'observability and do not compare policy quality.']
    axes[0].legend(fontsize=7)
    fig.suptitle('Physical motion versus estimated motion — first matched seed per route')
    fig.savefig(out/'physical_comparison.png',dpi=150)
    plt.close(fig)
    (out/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    gate=json.loads((EXPERIMENT/'pi_gate.json').read_text()) if (EXPERIMENT/'pi_gate.json').exists() else None
    lines += ['',f'PI qualification gate: **{"passed" if gate and gate["passed"] else "not passed"}**.',
        '', 'Both localization and turn requests changed together. These small matched-seed diagnostics '
        'do not establish which change contributes more or prove reliability on unseen terrain. '
        'Physical scoring and ordered route gates are unchanged.', '',
        '![Physical and estimated paths](physical_comparison.png)', '', '[Measured values and source files](comparison.json)']
    (out/'README.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines[:8]))
    print(f'Saved {out}')


if __name__=='__main__':main()
