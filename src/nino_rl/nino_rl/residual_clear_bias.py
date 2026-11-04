"""Frozen V2 checkpoint on clear floor; no optimizer, checkpoint writes or hardware.

Separate ledger and fingerprint preserve V1/V2. A changed upstream checkpoint,
source or task fails closed. Four bounded fresh launches answer one question.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import time
import numpy as np
from nino_control.residual_actor import PortableActor
from .core import load_config
from .residual_factory_workflow import repo
from . import residual_sim_task as v2
from .residual_sim_pilot import prepare_worlds, scenario_config
from .residual_experiment import experiment_contract, source_fingerprint
from .residual_workflow import save, emit, latest, runtime_versions

ACTION = 'sim-bias-clear'


def protocol():
    p = load_config(repo()/'src/nino_rl/config/residual_clear_bias_v1.yaml')
    if (p['order'], p['maximum_transitions'], p['training_transitions'], p['hardware_actions']) != (['B0', 'TD3_h5', 'TD3_h5', 'B0'], 560, 0, 0):
        raise ValueError('Changed diagnostic budget requires a new protocol')
    return p


def fingerprint():
    paths = [Path(__file__), repo()/'src/nino_rl/config/residual_clear_bias_v1.yaml',
             repo()/'src/nino_rl/scripts/residual_clear_bias.sh']
    hashes = {str(p.relative_to(repo())): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(dict(files=hashes, frozen_task=v2.fingerprint()), sort_keys=True).encode()).hexdigest()


def checkpoint(p, check_runtime=True):
    current = v2.validated_latest(p['checkpoint_workflow_root'], 'sim-v2-train', check_runtime)
    if current != Path(p['checkpoint']).expanduser().resolve():
        raise ValueError('Diagnostic requires the explicitly frozen V2 checkpoint')
    dependency = v2.dependency_record(current)
    if dependency['manifest_sha256'] != p['checkpoint_manifest_sha256']:
        raise ValueError('Frozen checkpoint manifest changed')
    meta = json.loads((current/'task_checkpoint.json').read_text())
    if meta['task_fingerprint'] != p['checkpoint_task_fingerprint'] or v2.fingerprint() != p['checkpoint_task_fingerprint']:
        raise ValueError('V2 objective/backend source changed; do not silently rerun as the same diagnostic')
    return current


def bias_metrics(trace, summary, p):
    low, high = p['steady_window_s']
    steady = [r for r in trace if low <= r['task']['elapsed_s'] <= high]
    if not steady: raise ValueError('No steady-window trace; diagnostic is incomplete')
    mean = lambda values: float(np.mean(values))
    return dict(summary, steady_window_s=[low, high],
        mean_proposal=np.mean([r['policy_proposal'] for r in steady], axis=0).tolist(),
        mean_accepted_yaw_rad_s=mean([r['reference_trace']['body_reference'][1] for r in steady]),
        mean_final_yaw_reference_rad_s=mean([r['final_ros_reference'][1] for r in steady]),
        mean_gt_yaw_rate_rad_s=mean([r['body_yaw_rad_s'] for r in steady]),
        mean_final_v_reference_m_s=mean([r['final_ros_reference'][0] for r in steady]),
        final_y_m=float(trace[-1]['truth_pose_m_rad'][1]), final_yaw_rad=float(trace[-1]['truth_pose_m_rad'][2]),
        initial_recorded_pose=trace[0]['truth_pose_m_rad'],
        bias_window_covered=len(steady)==round((high-low)/.1)+1)


def interpret(arms, p):
    baseline = max(abs(r['mean_accepted_yaw_rad_s']) for r in arms['B0'])
    values = [r['mean_accepted_yaw_rad_s'] for r in arms['TD3_h5']]
    observed = all(abs(value)>baseline+p['numerical_yaw_floor_rad_s'] for value in values) and values[0]*values[1]>0
    return dict(clear_floor_reference_bias_observed=bool(observed),
        numerical_floor_rad_s=p['numerical_yaw_floor_rad_s'],
        conclusion=('Checkpoint creates a consistent nonzero yaw reference without obstacles; contact alone cannot explain its steering bias.'
                    if observed else 'No consistent reference bias above the numerical floor; inspect per-run results before attributing contact effects.'),
        minimum_effect_accepted=None, generalization_verified=False, benefit_verified=False,
        hardware_authorized=False, training_transitions=0, checkpoint_modified=False)


def evaluate(out, p):
    trained = checkpoint(p)
    save(out/'dependencies.json', v2.dependency_record(trained))
    c = scenario_config(v2.config(), 'clear_box')
    if c['task']['steps_per_rollout'] != p['steps_per_rollout']:
        raise ValueError('Frozen rollout budget mismatch')
    save(out/'effective_config.json', c)
    worlds = prepare_worlds(out)
    actor = PortableActor(trained, experiment_contract(c)['abi_sha256'])
    results = {'B0': [], 'TD3_h5': []}
    for index, arm in enumerate(p['order']):
        emit(ACTION, f'{index+1}/4 · {arm} · clear floor · frozen checkpoint', index/4)
        directory = out/(arm+'_'+str(len(results[arm])))
        summary = v2.rollout(directory, c, worlds['clear_box'], arm, actor if arm=='TD3_h5' else None)
        trace = [json.loads(line) for line in (directory/'trace.jsonl').read_text().splitlines()]
        result = bias_metrics(trace, summary, p)
        results[arm].append(result)
        save(out/'evaluation_progress.json', results)
        if result['physical_failure'] or not result['deadline_reached'] or not result['bias_window_covered']:
            raise RuntimeError('Incomplete/physical failure diagnostic; retain run, no automatic retry')
    # Revalidate after inference: the upstream binary and entire lineage remain frozen.
    if v2.dependency_record(checkpoint(p)) != json.loads((out/'dependencies.json').read_text()):
        raise ValueError('Checkpoint changed during diagnostic')
    result = dict(scenario='clear_box', checkpoint=str(trained), arms=results, learner_seeds=1,
        evaluation_runs_per_arm=2, protocol_id=p['protocol_id'], **interpret(results, p))
    save(out/'evaluation_result.json', result)
    return result


def validated_latest(root, check_runtime=True):
    path = latest(root, ACTION, check_runtime=check_runtime)
    if json.loads((path/'manifest.json').read_text()).get('diagnostic_fingerprint') != fingerprint():
        raise ValueError('Diagnostic source changed; artifact is historical')
    current = checkpoint(protocol(), check_runtime)
    if json.loads((path/'dependencies.json').read_text()) != v2.dependency_record(current):
        raise ValueError('Frozen diagnostic dependency mismatch')
    return path


def run(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    shared = Path.home()/'nino_research/.factory_sim.lock'
    shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root/'.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # One finite batch. A failed attempt stays closed; a source correction
        # needs a new protocol/root instead of consuming hidden retries.
        if (root/'state.json').exists(): raise ValueError('Diagnostic batch already recorded; inspect retained artifacts, do not repeat')
        out = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION)
        out.mkdir()
        p = protocol()
        save(out/'protocol.json', p)
        current, start, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame): raise TimeoutError('Finite clear-floor diagnostic wall deadline')
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(p['wall_deadline_s'])
        emit(ACTION, 'Start frozen clear-floor steering diagnostic', 0., directory=str(out))
        try:
            result = evaluate(out, p)
            if fingerprint() != current: raise ValueError('Diagnostic sources changed during run')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            save(out/'job.json', dict(action=ACTION, status=status, error=error, wall_s=time.monotonic()-start, hardware_actions=0))
            save(out/'manifest.json', dict(action=ACTION, status=status, diagnostic_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in out.rglob('*') if path.is_file() and path.name!='manifest.json'}))
            save(root/'state.json', dict(schema_version=1, latest={ACTION:out.name} if status=='completed' else {},
                 runs=[dict(action=ACTION, path=out.name, status=status, error=error)]))
            emit(ACTION, status, 1. if status=='completed' else None, directory=str(out), result=result, error=error)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try: run(args.output)
    except (Exception, KeyboardInterrupt) as exc:
        print('Diagnostic failed/retained:', exc, flush=True)
        return 1
    return 0


if __name__=='__main__': raise SystemExit(main())
