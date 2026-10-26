#!/usr/bin/env python3
"""Continue the existing flat study with bounded pre-training discovery retries."""
import argparse
from pathlib import Path
import subprocess
import optuna

from recover_focused_optuna import ROOT, active_workers, recover, retry_startup
from wait_for_drive_profile import check_controller, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-trials', type=int, default=12)
    parser.add_argument('--startup-retries', type=int, default=2)
    args = parser.parse_args()
    if args.target_trials < 1 or args.startup_retries < 0:
        parser.error('Target must be positive and retry limit nonnegative')
    if active_workers():
        parser.error('A tuner/trainer/evaluator is already active; start this continuation first')
    directory = ROOT / 'rl_runs/flat_focused_optuna_v1'
    study = optuna.load_study(study_name='combined_flat_section',
                             storage='sqlite:///' + str(directory / 'study.db'))
    profile = load_config(ROOT / 'src/nino_rl/config/combined_flat_pi_tracking.yaml')
    attempts = 0
    while True:
        plan = recover(directory, 'flat', target=args.target_trials)
        if plan['interrupted_trials']:
            raise ValueError('Abandoned RUNNING trial: use shutdown recovery before continuation')
        remaining = plan['additional_trials_to_target']
        if not remaining:
            print('Flat completed-trial target reached.')
            return
        check_controller(profile)
        trials = study.trials
        if trials and trials[-1].state == optuna.trial.TrialState.FAIL:
            if attempts >= args.startup_retries:
                raise RuntimeError('Startup retry limit reached; inspect the controller/discovery logs')
            backup = retry_startup(directory, 'flat', trials[-1].number)
            if backup:
                attempts += 1
                print(f'Queued identical startup-failed parameters; database backup: {backup}', flush=True)
        command = ['bash', str(ROOT / 'src/nino_rl/scripts/run_focused_optuna.sh'),
                   'flat', 'tune', '--trials', str(remaining)]
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode == 0:
            return
        if result.returncode in (130, -2, -15):
            raise SystemExit(result.returncode)
        # On another error, retry_startup rejects partial training, evaluation,
        # timing, profile mismatch and all unrecognized failures on the next pass.


if __name__ == '__main__':
    main()
