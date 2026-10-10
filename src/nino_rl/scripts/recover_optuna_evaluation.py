#!/usr/bin/env python3
"""Evaluate an intact failed-trial model and append its validated observation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/nino_rl'))
import optuna
from nino_rl.core import load_config
from nino_rl.tuning_trials import assert_trial_inputs, verify_training_result
from nino_rl.tuning_history import read_saved_evaluation
from nino_rl.tuning_objective import record_trial_objective, qualified_best_trial


def recovery_exists(study, number):
    return any(t.state == optuna.trial.TrialState.COMPLETE and
               t.user_attrs.get('evaluation_recovery_of') == number for t in study.trials)


def require_idle_course(section):
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            args = process.joinpath('cmdline').read_bytes().decode(errors='replace').split('\0')
        except OSError:
            continue
        tuner = any(Path(arg).name == 'tune_split_optuna.py' for arg in args)
        if tuner and any(args[i:i+2] == ['--section', section] for i in range(len(args)-1)):
            raise ValueError(f'{section} tuner is still active (PID {process.name}); stop it before recovery')


def append_observation(study, source, model, summary_path, comparable, objective):
    if recovery_exists(study, source.number):
        raise ValueError('This failed trial already has a recovered observation')
    summary, _, _ = read_saved_evaluation(summary_path, objective)
    if (summary.get('controller') != 'ppo' or summary.get('action_ablation', 'none') != 'none'
            or Path(summary.get('model') or '').resolve() != model.resolve()):
        raise ValueError('Recovery requires full PPO evaluation of this exact saved model')
    attrs = dict(source.user_attrs)
    attrs['comparable_training'] = verify_training_result(model, load_config(model.parent / 'ppo.yaml'), comparable)
    attrs.update(model=str(model.resolve()), evaluation_recovery_of=source.number,
                 recovery='completed training retained; fresh complete evaluation', inherited_score=False)

    class CollectedTrial:
        number = source.number
        def set_user_attr(self, name, value):
            attrs[name] = value

    value = record_trial_objective(CollectedTrial(), summary_path, objective)
    trial = optuna.trial.create_trial(state=optuna.trial.TrialState.COMPLETE,
        value=value, params=source.params, distributions=source.distributions, user_attrs=attrs)
    study.add_trial(trial)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--section', choices=('flat', 'rough'), required=True)
    parser.add_argument('--trial', type=int, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--evaluate', action='store_true', help='Run fresh evaluation and append its validated score')
    action.add_argument('--summary', type=Path, help='Append an already completed matching evaluation')
    args = parser.parse_args()
    require_idle_course(args.section)
    output = ROOT / 'rl_runs' / f'{args.section}_focused_optuna_v1'
    database = output / 'study.db'
    with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('Database integrity check failed')
    study = optuna.load_study(study_name=f'combined_{args.section}_section',
                             storage='sqlite:///' + str(database))
    source = next(t for t in study.trials if t.number == args.trial)
    if source.state != optuna.trial.TrialState.FAIL:
        raise ValueError('Only a failed trial with completed training can be recovered here')
    if recovery_exists(study, source.number):
        raise ValueError('This trial already has a recovered observation; resume tuning instead')
    comparable = study.user_attrs['contract']['comparable_trials']
    objective = study.user_attrs['evaluation_objective']
    assert_trial_inputs(comparable)
    trial_dir = Path(source.user_attrs['directory'])
    models = list((trial_dir / 'train').glob('*/nino_ppo_final.zip'))
    if len(models) != 1:
        raise ValueError(f'Expected exactly one completed model, found {len(models)}')
    model = models[0]
    evidence = verify_training_result(model, load_config(trial_dir / 'trial.yaml'), comparable)
    if source.user_attrs.get('comparable_training') != evidence:
        raise ValueError('Saved training evidence differs from the trial record')
    seeds = [str(item['seed']) for item in objective['scenarios']]
    retry_output = trial_dir / ('eval_recovery_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    command = ['ros2', 'run', 'nino_rl', 'evaluate', '--device', comparable['device'],
               '--config', str(model.parent / 'ppo.yaml'), '--model', str(model),
               '--seeds', *seeds, '--output', str(retry_output)]
    if study.user_attrs['contract']['randomized_eval']:
        command.append('--randomized')
    print('Completed training verified:', model, flush=True)
    print('Evaluation-only command:', ' '.join(command), flush=True)
    if not args.evaluate and args.summary is None:
        print('Preview only. Add --evaluate to run evaluation and save the recovered score.')
        return
    assert_trial_inputs(comparable, live=True)
    if args.evaluate:
        retry_output.mkdir()
        with (retry_output / 'evaluate.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        summaries = list(retry_output.glob('*/summary.json'))
        if len(summaries) != 1:
            raise ValueError('Expected exactly one completed recovery evaluation')
        summary_path = summaries[0]
    else:
        summary_path = args.summary.expanduser().resolve()
    require_idle_course(args.section)
    assert_trial_inputs(comparable, live=True)
    backup = output / ('study.db.backup-evaluation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
        with sqlite3.connect(backup) as destination:
            connection.backup(destination)
    value = append_observation(study, source, model, summary_path, comparable, objective)
    qualified_best_trial(study, output)
    remaining = max(0, 12 - sum(t.state == optuna.trial.TrialState.COMPLETE for t in study.trials))
    print(f'Recovered score {value:.6f}; original failed trial and logs preserved.')
    if remaining:
        print(f'Next: bash src/nino_rl/scripts/run_focused_optuna.sh {args.section} tune --trials {remaining}')


if __name__ == '__main__':
    main()
