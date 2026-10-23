#!/usr/bin/env python3
"""Recover abandoned focused-study trials after a shutdown, without training."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import optuna

ROOT = Path(__file__).resolve().parents[3]


def active_workers():
    workers = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().decode(errors='replace').split('\0')
        except OSError:
            continue
        if any((Path(arg).name.startswith('tune_') and 'optuna' in Path(arg).name)
               or arg.endswith(('/nino_rl/train', '/nino_rl/evaluate')) for arg in args):
            workers.append(entry.name)
    return workers


def recover(directory, section, *, apply=False, target=12):
    database = directory / 'study.db'
    # Read and check first. SQLite's backup API also includes committed WAL data.
    with sqlite3.connect('file:' + str(database.resolve()) + '?mode=ro', uri=True) as source:
        if source.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError(f'Database integrity check failed: {database}')
    plan = json.loads((directory / 'trial_plan.json').read_text())['trials']
    assets = dict(plan['assets'])
    initialization = plan['initialization']
    if initialization['source']:
        assets[initialization['source']] = initialization['source_sha256']
    for name, expected in assets.items():
        digest = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError(f'Frozen study input changed: {name}')
    study = optuna.load_study(study_name=f'combined_{section}_section',
                             storage='sqlite:///' + str(database.resolve()))
    running = study.get_trials(states=(optuna.trial.TrialState.RUNNING,))
    expected = set(study.user_attrs['starting_candidate']['params'])
    for trial in running:
        if set(trial.params) != expected:
            raise ValueError(f'Trial {trial.number} has incomplete sampled parameters; inspect it manually')
    backup = None
    if apply and running:
        backup = directory / ('study.db.backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        with sqlite3.connect('file:' + str(database.resolve()) + '?mode=ro', uri=True) as source:
            with sqlite3.connect(backup) as destination:
                source.backup(destination)
        for trial in running:
            # Queue before failing the old trial. A repeated recovery remains
            # idempotent even if shutdown occurs between these two operations.
            queued = any(t.user_attrs.get('shutdown_retry_of') == trial.number
                         for t in study.get_trials(states=(optuna.trial.TrialState.WAITING,)))
            if not queued:
                study.enqueue_trial(trial.params, user_attrs={
                    'shutdown_retry_of': trial.number, 'inherited_score': False,
                    'recovery': 'restart same parameters with frozen actor and fresh critic/optimizer'})
            study.tell(trial.number, state=optuna.trial.TrialState.FAIL)
    completed = len(study.get_trials(states=(optuna.trial.TrialState.COMPLETE,)))
    remaining = max(0, target - completed)
    return {'section': section, 'applied': apply, 'completed': completed,
            'interrupted_trials': [t.number for t in running],
            'backup': str(backup) if backup else None,
            'additional_trials_to_target': remaining,
            'command': f'bash src/nino_rl/scripts/run_focused_optuna.sh {section} tune --trials {remaining}'
                if remaining else 'Target already reached; no tuning needed.'}


def retry_startup(directory, section, number):
    """Queue a known pre-training discovery failure, never a policy failure."""
    # Preserve all immutable study inputs and do not silently restart partial training.
    recover(directory, section)
    database = directory / 'study.db'
    study = optuna.load_study(study_name=f'combined_{section}_section',
                             storage='sqlite:///' + str(database.resolve()))
    source = next(t for t in study.trials if t.number == number)
    trial_dir = Path(source.user_attrs['directory'])
    log = trial_dir / 'train.log'
    if (source.state != optuna.trial.TrialState.FAIL
            or 'comparable_training' in source.user_attrs
            or list(trial_dir.glob('train/*/nino_ppo*.zip'))
            or not log.exists()
            or 'TimeoutError: Missing /effort_drive/get_parameters' not in log.read_text(errors='replace')):
        raise ValueError('Only a known controller-discovery failure before training can be retried here')
    if set(source.params) != set(study.user_attrs['starting_candidate']['params']):
        raise ValueError('Incomplete sampled parameters')
    if any(t.user_attrs.get('startup_retry_of') == number for t in study.trials):
        return None
    backup = directory / ('study.db.backup-startup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    with sqlite3.connect('file:' + str(database.resolve()) + '?mode=ro', uri=True) as src:
        with sqlite3.connect(backup) as dst:
            src.backup(dst)
    study.enqueue_trial(source.params, user_attrs={'startup_retry_of': number,
        'inherited_score': False, 'recovery': 'controller discovery failed before PPO training'})
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Back up, queue retries and mark abandoned trials FAIL')
    parser.add_argument('--section', choices=('flat', 'rough', 'both'), default='both')
    parser.add_argument('--target-trials', type=int, default=12)
    args = parser.parse_args()
    if args.target_trials < 1:
        parser.error('--target-trials must be positive')
    if args.apply and (workers := active_workers()):
        parser.error(f'Tuning/training/evaluation workers are still active (PIDs {workers}); stop them before recovery')
    sections = ('flat', 'rough') if args.section == 'both' else (args.section,)
    for section in sections:
        result = recover(ROOT / 'rl_runs' / f'{section}_focused_optuna_v1', section,
                         apply=args.apply, target=args.target_trials)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
