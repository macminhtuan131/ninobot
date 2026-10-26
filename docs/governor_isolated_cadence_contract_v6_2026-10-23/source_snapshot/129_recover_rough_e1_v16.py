#!/usr/bin/env python3
"""Recover evaluation of a completed E1 trial without retraining or rewriting FAIL."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys


def append_observation(study, source, attrs, value, key):
    """Add comparable completed evidence once; leave the original trial intact."""
    import optuna
    for trial in study.trials:
        if trial.user_attrs.get('recovery_key') == key:
            return trial.number, False
    attrs = {**source.user_attrs, **attrs, 'recovery_of_trial': source.number,
             'recovery_key': key, 'recovered_evaluation_only': True}
    study.add_trial(optuna.trial.create_trial(value=value, params=source.params,
                                             distributions=source.distributions, user_attrs=attrs))
    trial = next(t for t in study.trials if t.user_attrs.get('recovery_key') == key)
    return trial.number, True


def main():
    from tune_rough_e1_v16 import ROOT, OUTPUT, bootstrap, sample_config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=int, required=True)
    parser.add_argument('--evaluate', action='store_true', help='Run full evaluation and append verified score')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--target-completed', type=int, default=8)
    args = parser.parse_args()
    if args.trial < 0 or args.target_completed < 1:
        parser.error('Trial must be nonnegative and target positive')
    os.chdir(ROOT)
    bootstrap()
    import optuna
    import yaml
    from nino_rl.tuning_trials import assert_trial_inputs, validate_trial_config, verify_training_result, digest
    from train_rough_curriculum import assert_isolated
    from rough_localized_processes import ReliableRoughProcesses
    from rough_e1_optuna_objective import record

    output = args.output.expanduser().resolve()
    contract = json.loads((output / 'study_contract.json').read_text())
    comparable, objective = contract['comparable_trials'], contract['objective']
    assert_trial_inputs(comparable)
    with (output / 'worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Study worker is active; stop it before evaluation recovery') from error
        study = optuna.load_study(study_name='rough_e1_v16_quality_v1',
                                  storage='sqlite:///' + str(output / 'study.db'))
        if study.user_attrs.get('contract') != contract:
            raise ValueError('Database contract differs from the saved immutable plan')
        source = next((t for t in study.trials if t.number == args.trial), None)
        if source is None or source.state != optuna.trial.TrialState.FAIL:
            raise ValueError('Recovery requires an existing failed trial with completed training')
        if any(t.state == optuna.trial.TrialState.RUNNING for t in study.trials):
            raise RuntimeError('A RUNNING trial exists; review its artifacts before recovery')
        directory = Path(source.user_attrs['directory'])
        if directory.resolve() != output / f'trial_{args.trial:04d}':
            raise ValueError('Trial directory differs from this study')
        model = Path(source.user_attrs['model'])
        if model.resolve() not in [f.resolve() for f in (directory / 'train').glob('*/nino_ppo_final.zip')]:
            raise ValueError('Expected intact completed model in the source trial directory')
        config = yaml.safe_load((directory / 'trial.yaml').read_text())
        base = yaml.safe_load((output / 'base.yaml').read_text())
        if config != sample_config(optuna.trial.FixedTrial(source.params), base):
            raise ValueError('Trial config does not reproduce its recorded parameters')
        validate_trial_config(config, comparable)
        training = verify_training_result(model, config, comparable)
        if training != source.user_attrs.get('comparable_training'):
            raise ValueError('Saved completed training evidence differs from recovery audit')
        key = f'trial:{args.trial}:model:{digest(model)}:objective:{objective["sha256"]}'

        def next_command():
            completed = sum(t.state == optuna.trial.TrialState.COMPLETE for t in study.trials)
            remaining = max(0, args.target_completed - completed)
            print(f'{completed} completed observations; {remaining} additional trials to target {args.target_completed}.')
            if remaining:
                print(f'Next: python src/nino_rl/scripts/tune_rough_e1_v16.py --device {comparable["device"]} '
                      f'--timesteps {comparable["requested_steps"]} --trials {remaining} --output {output}')

        if any(t.user_attrs.get('recovery_key') == key for t in study.trials):
            print('This trial evaluation was already recovered; no duplicate score added.')
            next_command()
            return
        print(f'Completed {training["training_steps"]}-step training verified: {model}', flush=True)
        parent = directory / 'evaluation_recovery'
        seeds = [s['seed'] for s in objective['scenarios']]
        command = ['ros2', 'run', 'nino_rl', 'evaluate', '--config', model.parent / 'ppo.yaml',
                   '--model', model, '--device', comparable['device'], '--seeds', *seeds, '--output', parent]
        print('Evaluation-only command:', ' '.join(map(str, command)), flush=True)
        if not args.evaluate:
            print('Dry audit only. Add --evaluate to run; original partial evaluation is preserved.')
            return
        summaries = sorted(parent.glob('*/summary.json'), reverse=True)
        summary_path = next((f for f in summaries if json.loads(f.read_text()).get('complete')), None)
        if summary_path is None:
            assert_isolated(78, 'nino_rough_78')
            parent.mkdir(parents=True, exist_ok=True)
            processes = ReliableRoughProcesses(os.environ.copy(), pi_integrator_profile='conditional_v1')
            signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
            try:
                processes.launch(Path(comparable['world']), parent, False)
                assert_trial_inputs(comparable, live=True)
                processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
                    '--config', directory / 'trial.yaml', '--timeout', 60], parent / 'profile.log', timeout=65)
                processes.run(command, parent / 'evaluation.log')
                assert_trial_inputs(comparable, live=True)
            finally:
                processes.close()
            summary_path = next((f for f in sorted(parent.glob('*/summary.json'), reverse=True)
                                 if json.loads(f.read_text()).get('complete')), None)
            if summary_path is None:
                raise RuntimeError('Recovery evaluation incomplete; model and logs remain preserved')
        assert_trial_inputs(comparable)

        from nino_rl.evaluation import prepare_evaluation_config
        summary = json.loads(summary_path.read_text())
        evaluated = yaml.safe_load((summary_path.parent / 'config.yaml').read_text())
        if Path(summary['model']).resolve() != model.resolve():
            raise ValueError('Recovered evaluation used a different model')
        if evaluated != prepare_evaluation_config(config):
            raise ValueError('Recovered evaluation differs from the recorded trial configuration')

        class Collector:
            number = source.number
            attrs = {}

            def set_user_attr(self, key, value):
                self.attrs[key] = value

        collector = Collector()
        value = record(collector, summary_path, objective)
        backup = output / ('study.db.backup-eval-recovery-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        with sqlite3.connect(output / 'study.db') as origin, sqlite3.connect(backup) as target:
            origin.backup(target)
        number, added = append_observation(study, source, collector.attrs, value, key)
        qualified = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE
                     and t.user_attrs.get('arrival_feasible')]
        if qualified:
            best = max(qualified, key=lambda t: t.value)
            (output / 'best_trial.yaml').write_text((Path(best.user_attrs['directory']) / 'trial.yaml').read_text())
            (output / 'best_model.txt').write_text(best.user_attrs['model'] + '\n')
            (output / 'best.json').write_text(json.dumps(dict(trial=best.number, score=best.value,
                objective=best.user_attrs['evaluation_objective'], model=best.user_attrs['model'],
                pi_reference_scores=[r['objective']['score'] for r in contract['pi_references']]), indent=2) + '\n')
            (output / 'best_infeasible.json').unlink(missing_ok=True)
        print(f'Recovered observation {number}, score {value:.6f}; original FAIL and partial logs preserved.')
        print(f'Consistent database backup: {backup}')
        next_command()


if __name__ == '__main__':
    main()
