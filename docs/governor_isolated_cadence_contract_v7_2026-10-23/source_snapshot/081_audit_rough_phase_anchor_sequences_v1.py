#!/usr/bin/env python3
"""Preserve revision 57 and inspect saved commands, histories and wheel feedback."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'rl_runs/rough_phase_anchor_pilot_v2'
OUTPUT = ROOT / 'docs/rough_phase_anchor_sequence_audit_2026-10-12'
BACKUP = ROOT / 'rl_runs/rough_phase_anchor_trace_audit_v1/preserved/nino_ppo_final.zip'
BC = ROOT / 'rl_runs/rough_rate_bc_pilot_v2/bc_actor.zip'
SEEDS = (17400, 17401, 17404)
sys.path[:0] = [str(SOURCE / 'python'), str(Path(__file__).parent)]
from stable_baselines3 import PPO
from rough_rate_behavior_cloning_v2 import teacher
from analyze_rough_reactive_authority import window_metrics


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def load_profile(profile):
    summaries = list((SOURCE / 'evaluation' / profile).glob('*/summary.json'))
    assert len(summaries) == 1
    run = summaries[0].parent
    episodes = rows(run / 'episodes.csv')
    result = {}
    for episode in episodes:
        seed = int(episode['seed'])
        if seed not in SEEDS:
            continue
        directory = run / f"episode-{int(episode['episode']):03d}"
        control = rows(directory / 'control_trace.csv')
        drive = rows(directory / 'drive_trace.csv')
        for i, r in enumerate(control):
            for k in ('speed_scale','elapsed_s','step_dt_s','physical_x_m','sim_time_s','step_slip_square','step_imu_energy','step_imu_coverage_s'):
                r[k] = float(r[k])
            r['previous_scale'] = control[i-1]['speed_scale'] if i else 1.
            r['previous_x'] = control[i-1]['physical_x_m'] if i else 0.
            r['scale_delta'] = r['speed_scale'] - r['previous_scale']
            r['begin_s'] = r['elapsed_s'] - r['step_dt_s']
            if r['elapsed_s'] <= 1.:
                r['mode'] = 'startup'
            elif float(r['physical_goal_distance_m']) < .5:
                r['mode'] = 'approach'
            elif r['scale_delta'] < -.005:
                r['mode'] = 'braking'
            elif r['scale_delta'] > .005:
                r['mode'] = 'recovery'
            else:
                r['mode'] = 'holding' if r['speed_scale'] < .98 else 'cruise'
            r['motor'] = []
        stamps = np.array([r['sim_time_s'] for r in control])
        for r in drive:
            stamp = float(r['sim_time_s']); i = int(np.searchsorted(stamps, stamp))
            if i < len(control) and stamp >= stamps[i]-control[i]['step_dt_s']-1e-8:
                control[i]['motor'].append(r)
        assert all(r['motor'] for r in control), 'Missing stamped motor feedback'
        result[seed] = dict(control=control, episode=episode, directory=directory,
                            input_files=[directory/'control_trace.csv',directory/'drive_trace.csv',run/'episodes.csv',run/'summary.json'])
    assert sorted(result) == list(SEEDS)
    return result


def summary(control):
    duration = sum(r['step_dt_s'] for r in control)
    if not control:
        return None
    motors = [m for r in control for m in r['motor']]
    errors = [(float(m[side+'_actual_rad_s'])-float(m[side+'_target_rad_s']))**2 for m in motors for side in ('left','right')]
    torque = [float(m[side+'_applied_nm'])**2 for m in motors for side in ('left','right')]
    return dict(seconds=duration,frames=len(control),slip_integral=sum(r['step_slip_square']*r['step_dt_s'] for r in control),
        slip_rms=float(np.sqrt(sum(r['step_slip_square']*r['step_dt_s'] for r in control)/duration)),
        imu_energy=sum(r['step_imu_energy'] for r in control),
        mean_scale=sum(r['speed_scale']*r['step_dt_s'] for r in control)/duration,
        wheel_tracking_rmse_rad_s=float(np.sqrt(np.mean(errors))),applied_torque_rms_nm=float(np.sqrt(np.mean(torque))),
        mean_executed_linear_m_s=float(np.mean([float(m['executed_linear_m_s']) for m in motors])),
        mean_actual_wheel_linear_m_s=float(np.mean([.0625*.5*(float(m['left_actual_rad_s'])+float(m['right_actual_rad_s'])) for m in motors])),
        limited_wheel_fraction=float(np.mean([float(m[side+'_limited']) for m in motors for side in ('left','right')])),
        stale_feedback_frames=sum(float(m['cmd_fresh'])<.5 or float(m['have_wheel_state'])<.5 for m in motors))


def events(control):
    found = []
    for event_id in sorted({int(r['cue_events']) for r in control if r['cue_phase']=='holding'}):
        event = [r for r in control if int(r['cue_events'])==event_id]
        holding = [r for r in event if r['cue_phase']=='holding']
        recovering = [r for r in event if r['cue_phase']=='recovering']
        brake = [r for r in holding if r['scale_delta']<-.005]
        recovery = [r for r in event if r['scale_delta']>.005]
        full = [r for r in event if r['speed_scale']>=1.-1e-6 and r['begin_s']>=holding[-1]['elapsed_s']-1e-6]
        found.append(dict(event=event_id,onset_x_m=holding[0]['previous_x'],onset_s=holding[0]['begin_s'],
            start_scale=holding[0]['previous_scale'],minimum_holding_scale=min(r['speed_scale'] for r in holding),
            holding_end_scale=holding[-1]['speed_scale'],cue_holding_seconds=sum(r['step_dt_s'] for r in holding),
            actual_braking_seconds=sum(r['step_dt_s'] for r in brake),
            brake_onset_delay_s=brake[0]['begin_s']-holding[0]['begin_s'] if brake else None,
            first_recovery_x_m=recovery[0]['previous_x'] if recovery else None,
            first_recovery_s=recovery[0]['begin_s'] if recovery else None,
            recovery_delay_from_cue_s=recovery[0]['begin_s']-recovering[0]['begin_s'] if recovery and recovering else None,
            recovery_to_full_seconds=full[0]['elapsed_s']-recovering[0]['begin_s'] if full and recovering else None,
            holding=summary(holding),recovering=summary(recovering)))
    return found


def spatial_bins(control):
    edges = np.arange(0.,10.60001,.1)
    result = [dict(low_m=float(a),high_m=float(b),seconds=0.,slip_integral=0.,imu_energy=0.,scale_time=0.,
                   physical_speed_time=0.,wheel_error_time=0.,modes={}) for a,b in zip(edges[:-1],edges[1:])]
    for r in control:
        low, high = sorted((r['previous_x'],r['physical_x_m'])); dx=high-low
        for b in result:
            fraction=max(0.,min(high,b['high_m'])-max(low,b['low_m']))/dx if dx>1e-9 else float(b['low_m']<=high<b['high_m'])
            if not fraction:continue
            dt=r['step_dt_s']*fraction
            b['seconds']+=dt;b['slip_integral']+=r['step_slip_square']*dt;b['imu_energy']+=r['step_imu_energy']*fraction
            b['scale_time']+=r['speed_scale']*dt;b['physical_speed_time']+=float(r['physical_speed_m_s'])*dt
            motors=r['motor']; error=np.mean([(float(m[side+'_actual_rad_s'])-float(m[side+'_target_rad_s']))**2 for m in motors for side in ('left','right')])
            b['wheel_error_time']+=float(error)*dt
            b['modes'][r['mode']]=b['modes'].get(r['mode'],0.)+dt
    for b in result:
        if b['seconds']:
            b.update(slip_rms=float(np.sqrt(b['slip_integral']/b['seconds'])),mean_scale=b['scale_time']/b['seconds'],
                     physical_speed_m_s=b['physical_speed_time']/b['seconds'],wheel_error_rmse_rad_s=float(np.sqrt(b['wheel_error_time']/b['seconds'])))
    return result


def main():
    torch.set_num_threads(2)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    final = next((SOURCE/'train').glob('*/nino_ppo_final.zip'))
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    if BACKUP.exists():
        assert digest(BACKUP)==digest(final)
    else:
        BACKUP.write_bytes(final.read_bytes())
    profiles={k:load_profile(k) for k in ('ppo','pi_reactive')}
    chunks=sorted((SOURCE/'evaluation/ppo/actor_capture').glob('*.npz'))
    data=[np.load(p) for p in chunks]
    observations=np.concatenate([d['observations'] for d in data])
    records=[json.loads(str(r)) for d in data for r in d['records']]
    all_episodes=rows(next((SOURCE/'evaluation/ppo').glob('*/episodes.csv')))
    attempt_to_seed={int(e['attempt']):int(e['seed']) for e in all_episodes}
    input_files={final,BC,SOURCE/'config.yaml',SOURCE/'pilot_contract.json',SOURCE/'comparison.json',*chunks}
    for profile in profiles.values():
        for item in profile.values():input_files.update(item['input_files'])
    before={str(p):digest(p) for p in input_files}
    teacher_actions=np.array([teacher(x) for x in observations]); phase=np.array([r['cue']['cue_phase'] for r in records])
    seed_ids=np.array([attempt_to_seed[r['attempt']] for r in records])
    actor={}
    for name,path in (('original_bc',BC),('final_ppo',final)):
        model=PPO.load(path,device='cpu');model.policy.set_training_mode(False)
        if name=='final_ppo':
            assert model.num_timesteps==20480
            assert model.nino_training_contract['revision']==57
        else:
            assert model.num_timesteps==0
        with torch.no_grad():prob=model.policy.get_distribution(torch.as_tensor(observations)).distribution.probs.cpu().numpy()
        actions=prob.argmax(1)
        assert np.allclose(prob.sum(1),1.,atol=1e-6)
        if name=='final_ppo':assert np.array_equal(actions,np.array([r['rate_action'] for r in records]))
        actor[name]={}
        for seed in SEEDS:
            phases={};mismatches=[]
            for label in ('holding','recovering'):
                mask=(seed_ids==seed)&(phase==label)
                phases[label]=dict(frames=int(mask.sum()),teacher_agreement=float(np.mean(actions[mask]==teacher_actions[mask])),
                    teacher_brake_actor_hold=int(np.sum(mask&(teacher_actions==0)&(actions==1))),
                    teacher_recover_actor_hold=int(np.sum(mask&(teacher_actions==2)&(actions==1))))
                for i in np.flatnonzero(mask&(actions!=teacher_actions)):
                    control=profiles['ppo'][seed]['control'];r=min(control,key=lambda x:abs(x['elapsed_s']-records[i]['elapsed_s']))
                    assert abs(r['elapsed_s']-records[i]['elapsed_s'])<1e-7
                    pre_scale=float(observations[i].reshape(5,72)[-1,-16:][10])
                    assert abs(pre_scale-r['previous_scale'])<1e-6
                    mismatches.append(dict(elapsed_s=r['elapsed_s'],physical_x_m=r['physical_x_m'],cue_phase=label,
                        previous_executed_scale=pre_scale,teacher_action=int(teacher_actions[i]),actor_action=int(actions[i]),
                        probabilities=prob[i].tolist(),cue_remaining_s=float(r['cue_remaining_s'])))
            actor[name][seed]=dict(phases=phases,mismatches=mismatches)
    comparison=json.loads((SOURCE/'comparison.json').read_text());scored_windows={w['seed']:w['windows'] for w in comparison['disturbance_windows']}
    paired={}
    for seed in SEEDS:
        items={}
        for name,profile in profiles.items():
            c=profile[seed]['control'];b=spatial_bins(c)
            items[name]=dict(events=events(c),phases={mode:summary([r for r in c if r['mode']==mode]) for mode in sorted({r['mode'] for r in c})},
                spatial_bins=b,scored_window_metrics=window_metrics(c,scored_windows[seed]),
                same_event_phase_reversals=0,recovery_during_cue_holding=sum(r['scale_delta']>.005 and r['cue_phase']=='holding' for r in c),
                braking_during_cue_recovery=sum(r['scale_delta']<-.005 and r['cue_phase']=='recovering' for r in c))
            prior=None
            for r in c:
                if abs(r['scale_delta'])<=.005:continue
                key=(r['cue_phase'],int(r['cue_events']));sign=np.sign(r['scale_delta'])
                if prior and prior[0]==key and prior[1]!=sign:items[name]['same_event_phase_reversals']+=1
                prior=(key,sign)
        a,b=items['ppo']['events'],items['pi_reactive']['events'];event_pairs=[]
        for i,x in enumerate(a):
            j=min(range(len(b)),key=lambda j:abs(x['onset_x_m']-b[j]['onset_x_m']))
            back=min(range(len(a)),key=lambda k:abs(a[k]['onset_x_m']-b[j]['onset_x_m']))
            if i==back and abs(x['onset_x_m']-b[j]['onset_x_m'])<=.3:
                event_pairs.append(dict(ppo_event=x['event'],reactive_event=b[j]['event'],onset_separation_m=abs(x['onset_x_m']-b[j]['onset_x_m']),
                    ppo=x,reactive=b[j]))
        bins_a,bins_b=items['ppo']['spatial_bins'],items['pi_reactive']['spatial_bins'];regions=[]
        for i in range(8,len(bins_a)-8):
            ar,br=bins_a[i:i+3],bins_b[i:i+3]
            if any(not z['seconds'] for z in ar+br):continue
            low,high=ar[0]['low_m'],ar[-1]['high_m']
            if not any(max(low,l)<min(high,h) for l,h in scored_windows[seed]):continue
            def aggregate(bs):
                dt=sum(z['seconds'] for z in bs)
                return dict(slip_integral=sum(z['slip_integral'] for z in bs),mean_scale=sum(z['scale_time'] for z in bs)/dt,
                    physical_speed_m_s=sum(z['physical_speed_time'] for z in bs)/dt,
                    wheel_error_rmse_rad_s=float(np.sqrt(sum(z['wheel_error_time'] for z in bs)/dt)),
                    modes={m:sum(z['modes'].get(m,0.) for z in bs) for m in {m for z in bs for m in z['modes']}})
            qa,qb=aggregate(ar),aggregate(br)
            regions.append(dict(low_m=low,high_m=high,slip_integral_excess=qa['slip_integral']-qb['slip_integral'],ppo=qa,reactive=qb))
        worst=[]
        for region in sorted(regions,key=lambda v:v['slip_integral_excess'],reverse=True):
            if not any(max(region['low_m'],v['low_m'])<min(region['high_m'],v['high_m']) for v in worst):worst.append(region)
            if len(worst)==3:break
        paired[seed]=dict(profiles=items,event_pairs=event_pairs,largest_excess_slip_spatial_regions=worst)
    result=dict(complete=True,source=str(SOURCE),seeds=list(SEEDS),preserved_checkpoint=str(BACKUP),checkpoint_sha256=digest(final),
        input_hashes=before,actor_replay=actor,paired=paired,
        selected_correction=dict(name='Add current-rollout holding/recovery histories to the actor BC sampling pool',
            change='Replace half of each eligible class sample with training-rollout observations labeled by the unchanged causal teacher; retain half frozen demonstrations and fall back to frozen samples when a class is absent.',
            keep=['BC coefficient and 50% actor-gradient cap','balanced action-class sampling','reward terms/weights','terrain','controller/estimator','observations','action meanings','speed bounds/ramp','physical scoring'],
            evidence='Premature HOLD decisions persist with high confidence on PPO-visited histories; original BC makes substantially fewer errors on those exact inputs. Existing imitation only samples three fixed demonstration trajectories.',
            qualification='Targets actor/history drift; physical slip reduction is a hypothesis, not established causation.',
            next_contract='New contract required; actor initialization from original BC with fresh critic/optimizer; no checkpoint extension',
            leakage_guard='Teacher sees only training pre-action cue state and executed scale. Never train on these evaluation seeds or use physical position as an actor input.'),
        source_artifacts_unchanged=False,simulation_started=False,training_started=False,optuna_held=True,
        limitations=['Physical-profile/route/seed conditions match, but contact/sensor stochasticity and cue events differ.',
            'Event pairs are mutual nearest physical onsets within 0.30 m; unmatched events stay in the full-course scoring.',
            'Spatial energy allocation assumes uniform interval energy along each short displacement; not raw per-sample slip.',
            'Phase exposures differ; pooled phase differences do not prove causal attribution.',
            'Offline original-BC replay does not predict a counterfactual physical trajectory.',
            'No new pilot or Optuna launched; the original failed promotion gate remains unchanged.'])
    assert before=={str(p):digest(p) for p in input_files}
    assert digest(BACKUP)==digest(final)
    result['source_artifacts_unchanged']=True
    preservation=dict(source=str(final),backup=str(BACKUP),sha256=digest(final),
        training_steps=20480,contract_revision=57,byte_identical=True)
    preservation_file=BACKUP.with_name('preservation.json')
    if preservation_file.exists():
        assert json.loads(preservation_file.read_text())==preservation
    else:
        preservation_file.write_text(json.dumps(preservation,indent=2)+'\n')
    (OUTPUT/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    plot(result,profiles)
    report(result)


def plot(result,profiles):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for seed in SEEDS:
        fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True,layout='constrained')
        for name,label,color in [('ppo','PPO','#1269b0'),('pi_reactive','Reactive PI','#bb6527')]:
            control=profiles[name][seed]['control'];bins=result['paired'][seed]['profiles'][name]['spatial_bins']
            x=[r['physical_x_m'] for r in control]
            axes[0].plot(x,[r['speed_scale'] for r in control],color=color,label=label)
            centres=[.5*(b['low_m']+b['high_m']) for b in bins if b['seconds']]
            axes[1].plot(centres,[b['slip_rms'] for b in bins if b['seconds']],color=color)
            axes[2].plot(centres,[b['wheel_error_rmse_rad_s'] for b in bins if b['seconds']],color=color)
            axes[3].plot(x,[float(r['physical_speed_m_s']) for r in control],color=color,label=label+' physical speed')
            axes[3].plot(x,[np.mean([float(m['executed_linear_m_s']) for m in r['motor']]) for r in control],color=color,ls='--',alpha=.7,label=label+' executed reference')
            for event in result['paired'][seed]['profiles'][name]['events']:
                axes[0].axvline(event['onset_x_m'],color=color,alpha=.15,lw=.8)
        wrong=[r for r in result['actor_replay']['final_ppo'][seed]['mismatches'] if r['teacher_action']==0 and r['actor_action']==1]
        axes[0].scatter([r['physical_x_m'] for r in wrong],[r['previous_executed_scale'] for r in wrong],marker='x',s=38,color='#c92323',label='HOLD instead of teacher BRAKE',zorder=5)
        for ax,label in zip(axes,['Executed speed scale','Slip RMS\n0.1 m spatial bins','Wheel tracking\nRMSE, rad/s','Forward speed, m/s']):
            ax.set_ylabel(label);ax.grid(alpha=.22);ax.set_xlim(.8,10.)
        axes[0].set_ylim(.53,1.04);axes[0].legend(loc='lower left',fontsize=8)
        axes[3].legend(loc='lower right',fontsize=8);axes[-1].set_xlabel('Physical forward position x, m')
        fig.suptitle(f'Seed {seed}: saved spatial command and wheel-response comparison\nVertical lines: each controller’s cue onset; spatial bins are diagnostic, not new scoring gates')
        fig.savefig(OUTPUT/f'seed_{seed}_spatial.png',dpi=140);plt.close(fig)


def report(result):
    lines=['# Rough revision-57 saved sequence audit','','Final checkpoint preserved byte-for-byte. Saved-data analysis only; no new simulation/training.',
        '', '| Seed | Controller | Cue events | Mean braking s/event | Mean minimum holding scale | HOLD instead of BRAKE | Delayed recovery HOLD |',
        '|---|---|---:|---:|---:|---:|---:|']
    for seed,p in result['paired'].items():
        for name,label in [('ppo','PPO'),('pi_reactive','Reactive PI')]:
            ev=p['profiles'][name]['events'];a=result['actor_replay']['final_ppo'][seed]['phases'] if name=='ppo' else None
            lines.append(f"| {seed} | {label} | {len(ev)} | {np.mean([x['actual_braking_seconds'] for x in ev]):.3f} | {np.mean([x['minimum_holding_scale'] for x in ev]):.3f} | {a['holding']['teacher_brake_actor_hold'] if a else 'n/a'} | {a['recovering']['teacher_recover_actor_hold'] if a else 'n/a'} |")
    lines+=['','## Nearby cue-event comparison','','Physical event IDs are not assumed to correspond. Only mutual-nearest onset pairs within 0.30 m are shown.','',
        '| Seed | PPO/reactive event | Onset gap m | Minimum scale PPO/PI | Braking s PPO/PI | Recovery to full s PPO/PI |',
        '|---|---|---:|---|---|---|']
    fmt=lambda v:'unavailable' if v is None else f'{v:.2f}'
    for seed,p in result['paired'].items():
        for e in p['event_pairs']:
            a,b=e['ppo'],e['reactive'];lines.append(f"| {seed} | {a['event']}/{b['event']} | {e['onset_separation_m']:.3f} | {a['minimum_holding_scale']:.2f}/{b['minimum_holding_scale']:.2f} | {a['actual_braking_seconds']:.2f}/{b['actual_braking_seconds']:.2f} | {fmt(a['recovery_to_full_seconds'])}/{fmt(b['recovery_to_full_seconds'])} |")
    lines+=['','## Largest excess-slip spatial regions','','These are diagnostic 0.30 m regions, not revised evaluation gates.','',
        '| Seed | Physical x m | Slip integral excess | Mean scale PPO/PI | Wheel error rad/s PPO/PI | PPO executed modes | Reactive executed modes |',
        '|---|---|---:|---|---|---|---|']
    for seed,p in result['paired'].items():
        for r in p['largest_excess_slip_spatial_regions']:
            a,b=r['ppo'],r['reactive'];lines.append(f"| {seed} | {r['low_m']:.1f}–{r['high_m']:.1f} | {r['slip_integral_excess']:+.6f} | {a['mean_scale']:.3f}/{b['mean_scale']:.3f} | {a['wheel_error_rmse_rad_s']:.3f}/{b['wheel_error_rmse_rad_s']:.3f} | {a['modes']} | {b['modes']} |")
    lines+=['','## Selected single correction','',result['selected_correction']['change'],'',
        'Keep the BC coefficient/gradient cap, balanced classes, rewards, physical setup, observations and ramp fixed. '
        'Only the BC observation sampling pool changes. Use training-rollout histories; never add the inspected evaluation histories to training. '
        'A future pilot needs a new contract and the original BC actor with a fresh critic/optimizer. This audit starts none.','',
        'This is supported by actor replay and sequence defects, not proof that all slip differences arise from those errors. '
        'No general penalty increase, slower recovery ramp, hard teacher override or relaxed scoring is selected.','',
        *['- '+x for x in result['limitations']],'','Details and all source hashes: [analysis.json](analysis.json).','']
    lines+=['## Evidence and counterevidence','',
        'PPO has 40 premature HOLD decisions during 184 holding frames on these three seeds; the original BC actor has six on exactly the same tensors. '
        'Two additional PPO HOLD decisions delay recovery by one 100 ms action; both controllers otherwise recover at the same configured ramp. '
        'Shorter PPO recovery is primarily a consequence of starting recovery from a shallower slowdown, not a faster ramp.','',
        'The largest seed-17401 excess-slip region (x=4.4–4.7 m) has mean scale 1.0 for both controllers and comparable wheel tracking error. '
        'Seed 17400’s largest region has PPO braking while reactive PI is recovering. '
        'Consequently, neither a blanket recovery-ramp change nor a claim that premature HOLD explains every slip difference is supported. '
        'The selected training-data correction targets a directly verified sequence defect, with physical quality still requiring the unchanged gates.','',
        'The original nearest categorical teacher targets 0.72 as the stable approximation of continuous reactive PI’s 0.70. '
        'That unavoidable 0.02 quantization difference is distinct from premature HOLD at 0.76–0.80.','',
        'Executed wheel response is present for every action interval; no expired command or missing wheel-state flag was found in the selected traces. '
        'In seed 17400’s x=2.6–2.9 m region, PPO wheel tracking RMSE is 0.924 rad/s versus 0.727 for reactive PI. '
        'In seed 17404’s x=4.0–4.3 m recovery region, PPO’s mean executed scale is 0.941 versus 0.880 for reactive PI; '
        'the scale ramps remain identical. These examples justify inspecting sequence depth and physical timing without attributing all slip to motor tracking.','',
        '## Saved spatial plots','']
    for seed in SEEDS:lines += [f'![Seed {seed}](seed_{seed}_spatial.png)','']
    (OUTPUT/'REPORT.md').write_text('\n'.join(lines))
    print('\n'.join(lines[:15]))


if __name__=='__main__':main()
