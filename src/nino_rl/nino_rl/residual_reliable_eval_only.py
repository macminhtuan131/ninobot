"""One bounded evaluation-only job for all three sealed RELIABLE checkpoints."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import time

from . import residual_reliable_td3 as learner
from . import residual_reliable_evaluation as correction
from .core import load_config
from .residual_factory_workflow import repo
from .residual_experiment import source_fingerprint
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import emit, latest, runtime_versions, save

ACTION = 'sim-reliable-eval-only'
PARENT_ROOT = Path.home() / 'nino_research/sim_reliable_td3_v1'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def protocol():
    p = load_config(repo() / 'src/nino_rl/config/residual_reliable_eval_only_v1.yaml')
    if p['evaluation_order'] != learner.protocol()['evaluation_order']:
        raise ValueError('Evaluation order changed; new protocol required')
    if (p['steps_per_episode'], p['maximum_evaluation_transitions'], p['maximum_gazebo_launches'],
        p['training_transitions'], p['optimizer_updates'], p['hardware_actions'], p['resume_allowed'],
        p['minimum_effect_accepted'], p['training_episodes_per_seed_maximum'],
        p['native_boundary_support_s'], p['maximum_support_age_ns']) != (
            140, 1400, 10, 0, 0, 0, False, None, 1, .04, 40_000_000):
        raise ValueError('Evaluation-only budget/gates changed')
    if (not p['evaluation_released_for_this_job_only'] or p['scenario'] != 'clear_box'
        or p['parent_fingerprint'] != learner.fingerprint()
        or p['abi_sha256'] != learner.contract.identity()['abi_sha256']
        or set(p['checkpoint_sha256']) != {11, 22, 33}):
        raise ValueError('Frozen learner/interface or evaluation release changed')
    return p


def fingerprint():
    paths = [Path(__file__), Path(correction.__file__),
        repo() / 'src/nino_rl/config/residual_reliable_eval_only_v1.yaml',
        repo() / 'src/nino_rl/scripts/residual_reliable_eval_only.sh']
    return hashlib.sha256(json.dumps(dict(parent=learner.fingerprint(),
        files={path.name: sha(path) for path in paths}), sort_keys=True).encode()).hexdigest()


def validate_training_artifact(out, p, *, check_runtime=True, check_identity=True):
    """Failed job is usable only for its three completed learners, never its eval."""
    out = Path(out).resolve()
    if sha(out / 'manifest.json') != p['parent_manifest_sha256']:
        raise ValueError('Pinned training manifest changed')
    manifest, job = read(out / 'manifest.json'), read(out / 'job.json')
    if (manifest['status'] != 'failed' or job['status'] != 'failed'
        or job['error'] != p['expected_parent_error']
        or manifest['reliable_td3_fingerprint'] != p['parent_fingerprint']):
        raise ValueError('Unexpected parent failure/learner identity')
    for name, expected in manifest['files'].items():
        path = (out / name).resolve()
        if not path.is_relative_to(out) or sha(path) != expected:
            raise ValueError('Sealed training artifact changed: ' + name)
    if check_runtime and manifest['runtime'] != runtime_versions():
        raise ValueError('Training runtime changed')
    for seed in (11, 22, 33):
        directory = out / f'seed_{seed}'
        result = read(directory / 'training_result.json')
        if (result['seed'], result['training_transitions'], result['optimizer_updates'],
            result['episodes_launched'], result['full_task_terminals'], result['final_segment_steps'],
            result['final_segment_right_censored'], result['model_optimizer_target_replay_parity'],
            result['replay']['rows_checked']) != (seed, 1024, 960, 8, 7, 44, True, True, 1024):
            raise ValueError('Incomplete/invalid training checkpoint')
        if sha(directory / 'model.zip') != p['checkpoint_sha256'][seed] or sha(directory / 'replay_buffer.pkl') != p['replay_sha256'][seed]:
            raise ValueError('Pinned model/replay changed')
        if check_identity:
            learner.require_identity(read(directory / 'learner_identity.json'))
    return out


def parent(check_runtime=True):
    p = protocol()
    qualification = learner.parent(check_runtime=check_runtime)
    out = validate_training_artifact(PARENT_ROOT / p['parent_artifact'], p, check_runtime=check_runtime)
    dependency = learner.contract.guided.dependency_record(qualification)
    if read(out / 'dependencies.json') != dependency:
        raise ValueError('Training qualification dependency changed')
    return out


def dependency_record(out, p):
    return dict(artifact=str(out), manifest_sha256=sha(out / 'manifest.json'),
        learner_fingerprint=p['parent_fingerprint'], checkpoint_sha256={str(k):v for k,v in p['checkpoint_sha256'].items()},
        replay_sha256={str(k):v for k,v in p['replay_sha256'].items()}, checkpoint_selection='all three final fixed-budget checkpoints',
        failed_parent_scope='training complete; evaluation failed at backend namespace integration')


def configuration(stop, p):
    c, g, task, condition = learner.configuration(stop)
    c['purpose'] = task['protocol_id'] = p['protocol_id']
    c['backend'].update(scenario_id='clear_box_reliable_eval_only_v1', max_episodes=1)
    return c, g, task, condition


def execute(out, source):
    import torch
    torch.set_num_threads(1)
    p = protocol()
    save(out / 'dependencies.json', dependency_record(source, p))
    save(out / 'evaluation_identity.json', dict(protocol_id=p['protocol_id'], fingerprint=fingerprint(),
        learner_identity=learner.identity(), training_transitions=0, optimizer_updates=0,
        deterministic=True, checkpoint_selection='all fixed final checkpoints', hardware_actions=0))
    worlds = prepare_worlds(out)
    checkpoints = {seed: source / f'seed_{seed}' for seed in (11, 22, 33)}
    runs = []
    for index, condition in enumerate(p['evaluation_order']):
        emit(ACTION, f'Evaluation {index + 1}/10: {condition}', index / 10)
        if condition['arm'] == 'TD3':
            seed = condition['seed']
            if sha(checkpoints[seed] / 'model.zip') != p['checkpoint_sha256'][seed]:
                raise ValueError('Checkpoint changed before inference')
        try:
            result = correction.evaluate_rollout(out / f'eval_{index:02d}', condition,
                worlds['clear_box'], checkpoints, evaluation_config=configuration(condition['source_stop_s'], p),
                evaluation_protocol=p, action_name=ACTION, verify_actor_unchanged=True)
        except BaseException as exc:
            save(out / 'evaluation_progress.json', dict(runs=runs, failed_slot=index,
                error=repr(exc), remaining_slots_closed=True, training_transitions=0, optimizer_updates=0))
            raise
        runs.append(result)
        save(out / 'evaluation_progress.json', dict(runs=runs, remaining_slots_closed=False,
            training_transitions=0, optimizer_updates=0))
    result = dict(protocol_id=p['protocol_id'], evaluation_completed=True, runs=runs,
        evaluation_transitions=sum(r['steps'] for r in runs), gazebo_launches=len(runs),
        training_transitions=0, optimizer_updates=0, hardware_actions=0,
        actor_inference_calls=sum(r['actor_inference_calls'] for r in runs),
        all_task_stop_bounds_pass=True, minimum_effect_accepted=None, benefit_verified=False,
        remaining_slots_closed=True, evaluation_conditions_seen_before=True,
        conclusion='Bounded descriptive evaluation; no convergence/generalization or hardware promotion')
    save(out / 'evaluation_result.json', result)
    return result


def validated_latest(root, check_runtime=True):
    out = latest(root, ACTION, check_runtime=check_runtime)
    if read(out / 'manifest.json').get('reliable_eval_fingerprint') != fingerprint():
        raise ValueError('Evaluation sources/config changed')
    if read(out / 'dependencies.json') != dependency_record(parent(check_runtime), protocol()):
        raise ValueError('Evaluation training dependency changed')
    return out


def run(root):
    root = Path(root).expanduser().resolve();root.mkdir(parents=True, exist_ok=True)
    shared = Path.home() / 'nino_research/.factory_sim.lock';shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root / '.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB);fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / 'state.json').exists():
            raise ValueError('Evaluation-only budget already consumed; no retry')
        p = protocol();source = parent()
        out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + ACTION);out.mkdir()
        ledger = dict(schema_version=1, latest={}, runs=[dict(action=ACTION, path=out.name, status='running', error=None)])
        save(root / 'state.json', ledger);save(out / 'protocol.json', p)
        current, started, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame):
            raise TimeoutError('Finite evaluation-only wall deadline')
        previous = signal.signal(signal.SIGALRM, timeout);signal.alarm(p['wall_deadline_s'])
        try:
            result = execute(out, source)
            if fingerprint() != current:
                raise ValueError('Scientific source changed during evaluation')
            validate_training_artifact(source, p)
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed';error = str(exc)
            raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM, previous)
            save(out / 'job.json', dict(action=ACTION, status=status, error=error,
                wall_s=time.monotonic() - started, training_transitions=0, optimizer_updates=0, hardware_actions=0))
            save(out / 'manifest.json', dict(action=ACTION, status=status, reliable_eval_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name != 'manifest.json'}))
            ledger['runs'][0].update(status=status, error=error)
            if status == 'completed':ledger['latest'][ACTION] = out.name
            save(root / 'state.json', ledger)
            emit(ACTION, status, 1. if status == 'completed' else None, directory=str(out), result=result, error=error)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.output)
    except (Exception, KeyboardInterrupt) as exc:
        print('Evaluation-only failed/retained:', exc, flush=True);return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
