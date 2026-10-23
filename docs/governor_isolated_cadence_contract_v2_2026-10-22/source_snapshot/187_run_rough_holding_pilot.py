#!/usr/bin/env python3
"""Run frozen revision 49; open a new, bounded study only after its fixed gates pass."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(Path(__file__).parent), str(ROOT / 'src/nino_rl')]
from prepare_rough_foundations import digest, immutable
from prepare_rough_holding_reference_correction import OUTPUT, prepare
from prepare_rough_recovery_sigma_pilot import OUTPUT as SOURCE
import run_rough_observable_pilot_v2 as runner
from run_rough_recovery_sigma_pilot import score_batches, verify_scoring_rules


def read(path):
    return json.loads(Path(path).read_text())


def verify(plan):
    for group in ('assets', 'implementation'):
        for path, expected in plan.get(group, {}).items():
            if digest(path) != expected:
                raise ValueError('Frozen holding workflow changed: ' + path)


def state(output, stage, **extra):
    value = dict(stage=stage, pid=os.getpid(), updated_utc=datetime.now(timezone.utc).isoformat(),
                 contract_revision=49, **extra)
    path = output / 'status.json'
    tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(value, indent=2)+'\n'); tmp.replace(path)
    with (output / 'status_history.jsonl').open('a') as stream:
        stream.write(json.dumps(value)+'\n')
    (output / 'REPORT.md').write_text('# Rough holding-response pilot / focused tuning\n\n'
        'Revision 49. Fresh initialization, critic and optimizer. Fixed E1, hardware-only observations, '
        'unchanged physical scoring and reference ramp. Only a cue-holding speed-target cost is added.\n\n'
        'Stage: '+stage+'\n\n```json\n'+json.dumps(extra, indent=2)+'\n```\n')
    print(stage, flush=True)


def effective_plan(output, plan):
    source = read(SOURCE / 'pilot_contract.json')
    result = deepcopy(plan)
    result['implementation'] = {str(Path(__file__).resolve()): digest(__file__)}
    result['validated_screen_source'] = source['validated_screen_source']
    result['controls'] = source['controls']; result['observations'] = source['observations']
    # Prior checks have the identical untrained actor, observation/action/controller
    # and physics. Their reward returns are NOT reused as revision-49 evidence.
    result['screen_reuse_qualification'] = 'Physical and untrained exposure checks only; reward-only change'
    return result


def run_pilot(output, config, plan):
    verification = read(output / 'verification.json')
    for key in ('single_conditional_cost', 'all_previous_reward_terms_identical',
                'fresh_actor_critic_identical', 'fresh_optimizer', 'old_optimizer_resume_rejected'):
        if not verification[key]: raise ValueError('Holding correction verification failed: '+key)
    verify(plan); verify_scoring_rules(config, plan)
    immutable(output / 'holding_workflow_contract.json', json.dumps(dict(
        assets=plan['implementation'], prepared_contract_sha256=digest(output / 'pilot_contract.json'),
        verification_sha256=digest(output / 'verification.json'),
        steps=20480, seed=17000, scoring_regression_passed=True), indent=2)+'\n')
    runner.state = state
    runner.run(output, config, plan)
    if not (output / 'comparison.json').exists(): return None
    return read(output / 'comparison.json')


def failed_exposure_audit(output):
    """Audit actual training scales/phase exposure; never change this pilot on failure."""
    import numpy as np
    records = []
    for path in sorted((output / 'train/actor_capture').glob('chunk_*.npz')):
        with np.load(path, allow_pickle=False) as block:
            # Capture schema is checked below; do not invent absent evidence.
            records.extend(json.loads(str(x)) for x in block['records'])
    phases = {}
    by_attempt = {}
    for r in records:
        trace = dict(r['cue'], elapsed_s=r['elapsed_s'], speed_scale=r['scale'])
        phase = trace['cue_phase']
        phases.setdefault(phase, []).append(float(trace['speed_scale']))
        by_attempt.setdefault(r['attempt'], []).append(trace)
    from probe_rough_observable_exploration import response
    responses = [response([dict(scale=float(t['speed_scale']), elapsed_s=float(t['elapsed_s']),
                     cue={k:v for k,v in t.items() if k.startswith('cue_')}) for t in rows])
                 for rows in by_attempt.values() if rows]
    audit = dict(training_actions=len(records), attempts=len(responses),
        attempts_with_sustained_slowdown_recovery=sum(r['sustained_disturbance_slowdown_then_recovery'] for r in responses),
        phase_mean_executed_scale={k:float(np.mean(v)) for k,v in phases.items()},
        phase_counts={k:len(v) for k,v in phases.items()},
        next_step='Inspect formulation/deterministic learning if exposure is present; inspect exploration if absent',
        automatic_reward_change=False, optuna_held=True)
    (output / 'failed_exposure_audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    return audit


def start_study(pilot_output, trials):
    """Fixed objective and common fresh actor; no incompatible historical score import."""
    import optuna
    from train_rough_curriculum import complete_evaluation
    if not read(pilot_output / 'comparison.json')['pilot_passed']:
        raise ValueError('Revision-49 pilot failed; tuning refused')
    output = ROOT / 'rl_runs/rough_holding_focused_optuna_v1'; output.mkdir(parents=True, exist_ok=True)
    lock = (output / 'study.lock').open('a'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    base = yaml.safe_load((pilot_output / 'config.yaml').read_text())
    base_plan = effective_plan(pilot_output, read(pilot_output / 'pilot_contract.json'))
    search = dict(learning_rate=[3e-5, 2e-4], ent_coef=[1e-5, .003], n_epochs=[2,3,5],
        clip_range=[.12,.25], sde_sample_freq=[3,6,10], time=[.03,.08],
        velocity=[.15,.40], vibration=[.5,1.2], slip=[.07,.18])
    contract = dict(revision='rough_holding_focused_optuna_v1', pilot_sha256=digest(pilot_output/'pilot_contract.json'),
        pilot_comparison_sha256=digest(pilot_output/'comparison.json'), runner_sha256=digest(__file__),
        package_sha256={str(p):digest(p) for p in (pilot_output/'python/nino_rl').glob('*.py')},
        fixed_config=base, search=search, steps_per_trial=20480, training_seed=17000,
        evaluation_seeds=list(range(17100,17105)), max_trials=trials,
        initialization='Same original fresh actor/critic; empty optimizer; no trained checkpoint transfer',
        objective='Physical infeasible: -1000 - 100*failed_fraction - tracking_rmse/.05. Otherwise '
          '-(.30*time/full_PI_time + .20*tracking_rmse/.05 + .25*window_vibration_energy_per_m/matched_PI '
          '+ .25*window_slip_energy_per_m/matched_PI). Evaluation procedure and weights fixed.',
        promotion='Original physical, slowdown/recovery and ride-quality gates; export qualified candidates only',
        historical_scores_imported=False, qualification='Six-trial screening, not converged tuning or final validation')
    immutable(output/'study_contract.json', json.dumps(contract, indent=2)+'\n')
    study = optuna.create_study(study_name='rough_holding_focused_v1',
        storage='sqlite:///'+str(output/'study.sqlite3'), load_if_exists=True, direction='maximize',
        sampler=optuna.samplers.TPESampler(seed=17000, n_startup_trials=3))
    def objective(trial):
        config = deepcopy(base)
        p = config['ppo']; w = config['reward_v2']['longitudinal_weights']
        for key in ('learning_rate','ent_coef'):
            p[key] = trial.suggest_float(key, *search[key], log=True)
        for key in ('n_epochs','sde_sample_freq'): p[key] = trial.suggest_categorical(key, search[key])
        p['clip_range'] = trial.suggest_float('clip_range', *search['clip_range'])
        for key in ('time','velocity','vibration','slip'):
            w['time_per_s' if key=='time' else key] = trial.suggest_float('reward.'+key,*search[key])
        root = output / f'trial_{trial.number:04d}'; root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(pilot_output/'python', root/'python', ignore=shutil.ignore_patterns('__pycache__'))
        immutable(root/'config.yaml', yaml.safe_dump(config,sort_keys=False))
        shutil.copyfile(pilot_output/'verification.json', root/'verification.json')
        plan = deepcopy(base_plan)
        # Fresh actor tensors are unchanged by these update/reward/refresh settings.
        # Do not reuse source *exploration* outcomes for altered refresh frequency.
        plan['validated_screen_source'] = str(root/'pretraining_source')
        shutil.copytree(pilot_output/'controller_pi', root/'pretraining_source/controller_pi')
        (root/'pretraining_source/exploration').mkdir(parents=True)
        plan['assets'] = dict(base_plan['assets'])
        plan['assets'].update({str(x):digest(x) for x in (root/'python/nino_rl').glob('*.py')})
        plan['assets'][str(root/'config.yaml')] = digest(root/'config.yaml')
        plan['revision'] = f'rough_holding_focused_trial_{trial.number}'
        immutable(root/'pilot_contract.json',json.dumps(plan,indent=2)+'\n')
        runner.run(root,config,plan)
        if not (root/'comparison.json').exists():
            raise RuntimeError('Pretraining gate held this trial; inspect logs')
        result = read(root/'comparison.json')
        gate = result['arrival_tracking_gate']; physical = gate['passed'] and all(
            x['passed'] for x in result['pi_physical_gates'].values())
        m = lambda label,k: result[label]['metrics_all_episodes'][k]['mean']
        if not physical:
            score = -1000-100*(1-gate['physical_arrival_rate'])-gate['truth_path_rmse_m']/.05
        else:
            q=result['window_quality_ratios_to_pi_matched']
            score=-(.30*m('ppo','time_seconds')/m('pi_full','time_seconds')+
                    .20*gate['truth_path_rmse_m']/.05+
                    .25*q['vibration_energy_per_m']+.25*q['slip_energy_per_m'])
        trial.set_user_attr('qualified',result['pilot_passed'])
        trial.set_user_attr('comparison',str(root/'comparison.json'))
        trial.set_user_attr('model',result['ppo']['model'])
        return score
    remaining = max(0,trials-len(study.trials))
    try:
        state(output,'focused tuning',optuna_held=False,trial_budget=trials)
        study.optimize(objective,n_trials=remaining,catch=(RuntimeError,))
        qualified = [t for t in study.trials if t.state==optuna.trial.TrialState.COMPLETE and t.user_attrs.get('qualified')]
        if qualified:
            best=max(qualified,key=lambda t:t.value)
            (output/'best_qualified.json').write_text(json.dumps(dict(trial=best.number,score=best.value,
                params=best.params,**best.user_attrs,requires_unseen_seed_physics_confirmation=True),indent=2)+'\n')
        state(output,'complete: focused screening',optuna_held=False,qualified_candidates=len(qualified))
    finally: lock.close()


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--run',action='store_true')
    p.add_argument('--tune-if-pass',action='store_true'); p.add_argument('--trials',type=int,default=6)
    args=p.parse_args();os.chdir(ROOT)
    if args.trials<1 or args.trials>10: p.error('Use a bounded 1–10 trial screening')
    prepared=prepare();config=yaml.safe_load((OUTPUT/'config.yaml').read_text())
    plan=effective_plan(OUTPUT,prepared);verify(plan)
    if not args.run: print('Revision 49 verified; no process launched.'); return
    lock=(OUTPUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        result=run_pilot(OUTPUT,config,plan)
        if result is None: return
        if not result['pilot_passed']:
            audit=failed_exposure_audit(OUTPUT)
            state(OUTPUT,'complete: pilot failed; Optuna held',pilot_passed=False,exposure_audit=audit)
        elif args.tune_if_pass:
            state(OUTPUT,'complete: pilot passed; opening separate focused study',pilot_passed=True)
            start_study(OUTPUT,args.trials)
        else: state(OUTPUT,'complete: pilot passed; ready for focused Optuna',pilot_passed=True)
    except BaseException as exc:
        state(OUTPUT,'interrupted',error=str(exc)); raise
    finally: lock.close()


if __name__=='__main__':main()
