#!/usr/bin/env python3
"""Run an owned rough PI probe; close its Gazebo and rosbag processes on exit."""
import argparse
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='E1/N1/S1 fixed three-seed qualification')
    parser.add_argument('--slow-e1', action='store_true', help='Three E1 seeds at 0.65 speed scale')
    parser.add_argument('--s1-only', action='store_true', help='Fixed S1 seeds 10002/10005/10008')
    args=parser.parse_args()
    sys.path.insert(0,str(ROOT/'src/nino_rl/scripts'))
    from run_rough_localized import EXPERIMENT, verify
    verify()
    # Children use the frozen package; never replace the live flat sources.
    overlay=str(EXPERIMENT/'python')
    os.environ['PYTHONPATH']=overlay+os.pathsep+os.environ.get('PYTHONPATH','')
    sys.path.insert(0,overlay)
    from train_rough_curriculum import assert_isolated
    from rough_localized_processes import ReliableRoughProcesses
    assert_isolated(78,'nino_rough_78')
    env=os.environ.copy()
    env.update(ROS_DOMAIN_ID='78',NINO_ROS_DOMAIN_ID='78',GZ_PARTITION='nino_rough_78',
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    directory=EXPERIMENT/('qualification_logs' if args.full else
                          'slow_e1_logs' if args.slow_e1 else 's1_probe_logs')
    directory.mkdir(parents=True,exist_ok=True)
    env['NINO_ROUGH_LOCALIZATION_LOG']=str(directory/'wall_observations.jsonl')
    processes=ReliableRoughProcesses(env,pi_integrator_profile='conditional_v1')
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        processes.launch(ROOT/'rl_runs/rough_terrain_bank_v1/worlds/original.sdf',directory,False)
        if args.full and args.slow_e1:
            processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',EXPERIMENT/'config.yaml',
                '--route','E1','--baseline-speed-scale','0.65','--seeds','10000','10003','10006',
                '--control-trace','--output',EXPERIMENT/'slow_e1'],directory/'slow_pi.log')
        if args.s1_only:
            processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',EXPERIMENT/'config.yaml',
                '--route','S1','--baseline-speed-scale','1.0','--seeds','10002','10005','10008',
                '--control-trace','--output',EXPERIMENT/'pi/S1'],directory/'pi.log')
        elif args.full:
            processes.run([sys.executable,'src/nino_rl/scripts/run_rough_localized.py','pi'],directory/'pi.log')
        elif args.slow_e1:
            processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',EXPERIMENT/'config.yaml',
                '--route','E1','--baseline-speed-scale','0.65','--seeds','10000','10003','10006',
                '--control-trace','--output',EXPERIMENT/'slow_e1'],directory/'pi.log')
        else:
            processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',EXPERIMENT/'config.yaml',
                '--route','S1','--baseline-speed-scale','1.0','--seeds','10002','--control-trace',
                '--output',EXPERIMENT/'s1_probe'],directory/'pi.log')
    finally:
        processes.close()
    print(f'PI diagnostic finished; logs: {directory}. No PPO training started.')


if __name__=='__main__':
    main()
