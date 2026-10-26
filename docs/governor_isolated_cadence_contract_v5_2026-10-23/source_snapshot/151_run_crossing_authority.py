#!/usr/bin/env python3
"""Zero-update PI interventions to test useful longitudinal control authority.

The anticipatory reference uses known cable positions and estimated pose.
It is an experimental intervention, not a trained policy or a sim-to-real claim.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'rl_runs/course_targeted_corrections_v1/flat'
OUTPUT=ROOT/'rl_runs/foundations_20261011/flat_authority_v1'


def target_scale(x,profile):
    if profile=='full': return 1.
    if profile=='constant': return .7
    if profile!='anticipatory': raise ValueError('Unknown intervention')
    return .6 if any(cable-.6 <= x <= cable+.3 for cable in (2.45,4.45)) else 1.


def scripted_scale(env,previous):
    # Estimated odometry only; simulator physical pose is reserved for scoring.
    profile=os.environ['NINO_AUTHORITY_PROFILE']
    target=target_scale(env.ros.snapshot().x,profile)
    return min(previous+.04,max(previous-.04,target))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0]=[str(ROOT/'src/nino_rl'),str(Path(__file__).parent)]
    import yaml
    from nino_rl.tuning_trials import digest,assert_trial_inputs
    from train_rough_curriculum import Processes,assert_isolated,complete_evaluation
    from prepare_rough_foundations import immutable
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    contract=json.loads((ROOT/'rl_runs/flat_focused_optuna_v1/trial_plan.json').read_text())['trials']
    assert_trial_inputs(contract)
    original=json.loads((SOURCE/'targeted_plan.json').read_text())
    for path,expected in original['snapshot_assets'].items():
        if digest(path)!=expected: raise ValueError('Frozen source changed: '+path)
    overlay=output/'python'
    if not overlay.exists():
        shutil.copytree(SOURCE/'python',overlay,ignore=shutil.ignore_patterns('__pycache__'))
    code=(SOURCE/'python/nino_rl/evaluation.py').read_text()
    old='                    action[0] = 2.0 * args.baseline_speed_scale - 1.0'
    if code.count(old)!=1: raise ValueError('Unexpected intervention anchor')
    code=code.replace(old,old+'\n'
        '                    from nino_rl.crossing_authority import scripted_scale\n'
        '                    intervention_scale = scripted_scale(env, intervention_scale)\n'
        '                    action[0] = 2.0 * intervention_scale - 1.0')
    code=code.replace('            while True:\n','            intervention_scale = 1.\n            while True:\n')
    immutable(overlay/'nino_rl/evaluation.py',code) if (output/'authority_contract.json').exists() else (overlay/'nino_rl/evaluation.py').write_text(code)
    immutable(overlay/'nino_rl/crossing_authority.py',Path(__file__).read_bytes())
    config=yaml.safe_load((SOURCE/'evaluation.yaml').read_text())
    immutable(output/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    assets={str(p):digest(p) for p in (overlay/'nino_rl').glob('*.py')}
    plan=dict(revision='flat_longitudinal_authority_v1',source=str(SOURCE),source_trial_contract=contract['sha256'],
        assets=assets,config_sha256=digest(output/'config.yaml'),seeds=[65000,65001,65002],
        interventions=['full','constant','anticipatory'],updates=0,
        same_controller_estimator_geometry_and_scoring=True,
        anticipation='Known cable x; estimated pose; speed floor .6, reference ramp .4 scale/s; zero yaw/torque residual',
        physics='nominal unchanged; authority does not establish generalization or learner convergence')
    immutable(output/'authority_contract.json',json.dumps(plan,indent=2)+'\n')
    print('Prepared authority test',output,flush=True)
    if not args.run:return
    os.environ.update(ROS_DOMAIN_ID='79',NINO_ROS_DOMAIN_ID='79',GZ_PARTITION='nino_flat_79',
                      ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    environment=os.environ.copy()
    environment['PYTHONPATH']=str(overlay)+os.pathsep+environment.get('PYTHONPATH','')
    processes=Processes(environment,pi_integrator_profile='conditional_v1')
    results={}
    try:
        for profile in plan['interventions']:
            directory=output/profile;directory.mkdir(exist_ok=True)
            processes.env['NINO_AUTHORITY_PROFILE']=profile
            if complete_evaluation(directory,3) is None:
                for path,expected in assets.items():
                    if digest(path)!=expected:raise ValueError('Intervention asset changed')
                assert_isolated(79,'nino_flat_79')
                processes.world=processes.start(['ros2','launch','nino_rl','training_sim.launch.py',
                    f'world:={contract["world"]}','world_name:=combined_flat_section','headless:=true',
                    'pi_integrator_profile:=conditional_v1'],directory/'gazebo.log')
                processes.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
                assert_trial_inputs(contract,live=True)
                processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',output/'config.yaml',
                    '--timeout','60'],directory/'profile.log',timeout=65)
                processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',output/'config.yaml',
                    '--seeds',*plan['seeds'],'--control-trace','--output',directory],directory/'evaluate.log',timeout=360)
                processes.close()
            evidence=complete_evaluation(directory,3)
            if evidence is None:raise RuntimeError('Incomplete authority intervention')
            results[profile]=dict(summary=evidence[1],directory=str(directory))
            (output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
            print('Completed intervention',profile,flush=True)
    finally:processes.close()


if __name__=='__main__':main()
