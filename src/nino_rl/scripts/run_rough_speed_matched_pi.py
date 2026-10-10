#!/usr/bin/env python3
"""Compare the frozen E1 pilot with PI at approximately matching duration."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys


def main():
    from run_rough_localized import ROOT, EXPERIMENT, verify
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speed-scale', type=float, default=0.70)
    args = parser.parse_args()
    if not 0 < args.speed_scale <= 1:
        parser.error('Speed scale must be in (0, 1]')
    os.chdir(ROOT)
    manifest = verify()
    overlay = str(EXPERIMENT / 'python')
    sys.path.insert(0, overlay)
    os.environ['PYTHONPATH'] = overlay + os.pathsep + os.environ.get('PYTHONPATH', '')
    from train_rough_curriculum import assert_isolated
    from rough_localized_processes import ReliableRoughProcesses
    from nino_rl.evaluation import compare_summaries

    candidate_path = EXPERIMENT / 'curriculum/blocks/block_0000/evaluation/original/20261009-111540-895313/summary.json'
    candidate = json.loads(candidate_path.read_text())
    seeds = list(range(10000, 10020))
    if not candidate.get('complete') or candidate.get('evaluation_seeds') != seeds or candidate.get('episodes') != 20:
        raise RuntimeError('Expected complete 20-seed E1 PPO pilot evidence')
    directory = EXPERIMENT / f'speed_matched_pi_{args.speed_scale:.2f}'
    directory.mkdir(parents=True, exist_ok=True)
    existing = sorted(directory.glob('*/summary.json'), reverse=True)
    complete = next((f for f in existing if json.loads(f.read_text()).get('complete')), None)
    config = EXPERIMENT / 'curriculum/baselines/stage_0/original/config.yaml'
    if complete is None:
        assert_isolated(78, 'nino_rough_78')
        env = os.environ.copy()
        env.update(ROS_DOMAIN_ID='78', NINO_ROS_DOMAIN_ID='78', GZ_PARTITION='nino_rough_78',
                   ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
        processes = ReliableRoughProcesses(env, pi_integrator_profile='conditional_v1')
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        (directory / 'comparison_plan.json').write_text(json.dumps({
            'candidate_summary': str(candidate_path), 'config': str(config),
            'snapshot_sha256': manifest['snapshot_sha256'], 'seeds': seeds,
            'baseline_speed_scale': args.speed_scale,
            'duration_match_relative_tolerance': 0.05,
            'note': 'Completion-time matching is approximate; compare achieved durations before attributing comfort gains.'
        }, indent=2) + '\n')
        try:
            processes.launch(ROOT / 'rl_runs/rough_terrain_bank_v1/worlds/original.sdf', directory, False)
            print(f'Running PI scale {args.speed_scale}; 20 matching E1 seeds. Log: {directory / "evaluation.log"}', flush=True)
            processes.run(['ros2', 'run', 'nino_rl', 'evaluate_baseline', '--config', config,
                '--baseline-speed-scale', args.speed_scale, '--seeds', *seeds,
                '--output', directory], directory / 'evaluation.log')
        finally:
            processes.close()
        complete = next((f for f in sorted(directory.glob('*/summary.json'), reverse=True)
                         if json.loads(f.read_text()).get('complete')), None)
        if complete is None:
            raise RuntimeError('PI evaluation did not complete')
    baseline = json.loads(complete.read_text())
    if baseline.get('controller') != 'path_pi_baseline' or baseline.get('baseline_speed_scale') != args.speed_scale:
        raise RuntimeError('Saved PI speed/controller differs from requested comparison')
    result = compare_summaries(baseline, candidate)
    pi_time = baseline['metrics_all_episodes']['time_seconds']['mean']
    ppo_time = candidate['metrics_all_episodes']['time_seconds']['mean']
    relative_gap = abs(pi_time - ppo_time) / ppo_time
    result.update(baseline_summary=str(complete), candidate_summary=str(candidate_path),
                  duration_relative_gap=relative_gap, duration_matched_within_5_percent=relative_gap <= .05)
    output = directory / 'comparison.json'
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(f'Comparison saved: {output}', flush=True)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
