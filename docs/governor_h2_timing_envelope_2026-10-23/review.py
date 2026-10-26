#!/usr/bin/env python3
"""Summarize the completed offline audit; no new raw-data fitting or simulation."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
OUT=HERE/'results'
report_path=OUT/'report.json'
d=json.loads(report_path.read_text())


def enclosing_residual(episode, bracket):
    """Nonnegative slip gives bounds using enclosing prespecified cuts only."""
    lo,hi=bracket
    if lo is None or lo<0:
        return dict(available=False,reason='left_censored_or_before_contact')
    rows=episode['residual']
    before=[r for r in rows if r['cut_offset_s']<=lo+1e-9]
    after=[r for r in rows if r['cut_offset_s']>=hi-1e-9]
    if not before or not after:
        return dict(available=False,reason='outside_prespecified_cuts')
    a,b=before[-1],after[0]
    return dict(available=all(r['slip_fraction_remaining'] is not None for r in (a,b)),
        enclosing_cuts_s=[a['cut_offset_s'],b['cut_offset_s']],
        remaining_slip_fraction_bounds=[b['slip_fraction_remaining'],a['slip_fraction_remaining']],
        interpretation='Conditional on descriptive pair-divergence interval, not a causal response or preventable fraction')


summary={}
for arm in ('full','reactive'):
    es=[e for e in d['episodes'] if e['batch']=='survey' and e['arm']==arm]
    summary[arm]=[]
    for i in range(len(es[0]['residual'])):
        rs=[e['residual'][i] for e in es]
        summary[arm].append(dict(offset_s=rs[0]['cut_offset_s'],n=len(rs),
            slip_percent_min_median_max=np.percentile([r['slip_fraction_remaining']*100 for r in rs],[0,50,100]).tolist(),
            imu_squared_sample_percent_min_median_max=np.percentile(
                [r['imu_squared_sample_fraction_remaining']*100 for r in rs],[0,50,100]).tolist()))
conditional=[]
for pair in d['pairs']:
    if not pair['available']:
        continue
    candidate=next(e for e in d['episodes'] if e['id']==pair['ids'][0])
    for diag in pair['diagnostics']:
        if diag.get('onset'):
            conditional.append(dict(batch=pair['batch'],seed=pair['seed'],repeat=pair['repeat'],
                channel=diag['channel'],threshold_m_s=diag['threshold_m_s'],
                onset=diag['onset'],residual=enclosing_residual(candidate,diag['onset']['bracket_s'])))
result=dict(survey_residual_summary=summary,conditional_observed_divergence=conditional,
    evidence=dict(assigned_slots=len(d['assigned']),raw_runs_read=len(d['episodes']),
        survey_pairs=sum(p['available'] for p in d['pairs'] if p['batch']=='survey'),
        valid_descriptive_cadence_pairs=sum(p['available'] for p in d['pairs'] if p['batch']=='cadence'),
        original_survey_integrals_reproduced=sum(e.get('original_whole_slip_reproduced',False) for e in d['episodes'])),
    decision=dict(H2='unknown',same_obstacle_branch='not disproved, useful actual response not established',
        next='One new bounded v2 cadence screen is still informative about actual response and late vibration; no more audits of these unchanged traces',
        simulation_release=False,learning_and_tuning='on hold',
        scope='Rigid 6mm +8deg E1 scenario only; no generalization or real-robot conclusion'),
    source_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
    tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(OUT/'decision.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')

fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
for arm,color in [('full','#444444'),('reactive','#067f9d')]:
    es=[e for e in d['episodes'] if e['batch']=='survey' and e['arm']==arm]
    for ax,key in zip(axes,('slip_fraction_remaining','imu_squared_sample_fraction_remaining')):
        t=[r['cut_offset_s'] for r in es[0]['residual']]
        values=np.array([[r[key]*100 for r in e['residual']] for e in es])
        for v in values:
            ax.plot(t,v,color=color,alpha=.2,lw=.7)
        ax.plot(t,np.median(values,axis=0),color=color,lw=2,label=arm+' median (8 runs)')
        ax.set(xlabel='Seconds after own first manifold',ylabel='Observed contribution remaining (%)',
               xlim=(0,1),ylim=(0,102))
        ax.grid(alpha=.2)
axes[0].set_title('GT-header slip squared integral to +3s')
axes[1].set_title('Unfiltered IMU squared-sample sum to +3s')
axes[0].legend(fontsize=8)
fig.suptitle('Residual contribution is not a preventable fraction; original spikes retained',fontsize=11)
fig.savefig(OUT/'remaining_cost.png',dpi=160)
plt.close(fig)
print(json.dumps(result['evidence'],indent=2))
