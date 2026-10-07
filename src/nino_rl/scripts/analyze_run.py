#!/usr/bin/env python3
"""Export raw TensorBoard trends and episode outcomes without UI smoothing."""
import argparse
from collections import Counter
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    event_dirs = sorted({p.parent for p in args.run.glob('tensorboard/**/events.out.tfevents*')})
    if len(event_dirs) != 1:
        parser.error('Expected one TensorBoard run directory')
    events = EventAccumulator(str(event_dirs[0]), size_guidance={'scalars':0}).Reload()
    rows = [json.loads(s) for s in (args.run/'episodes.jsonl').read_text().splitlines()]
    summary = {'run':str(args.run), 'episodes':len(rows),
               'terminations':dict(Counter(r['termination'] for r in rows)),
               'last_100_terminations':dict(Counter(r['termination'] for r in rows[-100:])),
               'reward_totals_mean':{}, 'by_termination':{}, 'scalars':{}}
    for key in rows[0]['reward_totals']:
        summary['reward_totals_mean'][key] = float(np.mean([r['reward_totals'][key] for r in rows]))
    for reason in summary['terminations']:
        group = [r for r in rows if r['termination']==reason]
        summary['by_termination'][reason] = {key:float(np.mean([r[key] for r in group]))
            for key in ('path_rmse_m','endpoint_distance_m','return','time_seconds','rms_vertical_acceleration_m_s2')}
    for tag in events.Tags()['scalars']:
        s = events.Scalars(tag)
        values = np.array([v.value for v in s])
        summary['scalars'][tag] = dict(count=len(s), first_step=s[0].step,last_step=s[-1].step,
            first_20_mean=float(values[:20].mean()), last_20_mean=float(values[-20:].mean()),
            last=float(values[-1]),minimum=float(values.min()),maximum=float(values.max()))
    (args.output/'training_analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    fig, axes = plt.subplots(3,2,figsize=(12,10),layout='constrained')
    charts = [
        ('episode/success','Success per logging interval','fraction'),
        ('episode/goal_missed_failure','Missed goal per logging interval','fraction'),
        ('episode/path_rmse_m','Path error (wheel odometry)','m'),
        ('episode/endpoint_distance_m','Endpoint distance (wheel odometry)','m'),
        ('episode/return','Episode return','reward'),
        ('episode/rms_vertical_acceleration_m_s2','Vertical acceleration RMS','m/s²')]
    for ax,(tag,title,unit) in zip(axes.flat,charts):
        s=events.Scalars(tag); x=np.array([v.step for v in s])/1000.; y=np.array([v.value for v in s])
        ax.plot(x,y,color='#8dabc0',alpha=.6,lw=1,label='raw interval mean')
        n=min(10,len(y)); ax.plot(x[n-1:],np.convolve(y,np.ones(n)/n,'valid'),color='#14577a',lw=2,label='10 interval mean')
        ax.set(title=title,xlabel='Cumulative steps (thousands)',ylabel=unit)
        ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle(f'{args.run.name}: final resumed segment, {len(rows):,} training episodes',fontsize=14)
    fig.savefig(args.output/'training_trends.png',dpi=160)
    plt.close(fig)
    print(json.dumps({k:summary[k] for k in ('episodes','terminations','last_100_terminations')},indent=2))


if __name__ == '__main__':
    main()
