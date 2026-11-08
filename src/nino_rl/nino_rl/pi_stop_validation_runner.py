"""Stop6 validation of selected PI candidate; separate ledger, no learning."""
import argparse
from datetime import datetime, timezone
import fcntl
from functools import partial
import hashlib
import json
from pathlib import Path
import signal
import time
import traceback
import numpy as np
from . import pi_stop_validation_context as context
from .pi_screen_backend import PiScreenBackend
from .reliable_episode import EpisodeLifecycle
from .residual_workflow import save, emit, latest, runtime_versions
from .residual_experiment import source_fingerprint

parent = context.parent.parent
qualified = context.parent.qualified
ACTION = 'sim-pi-stop-validation'
PROTOCOL_ID = 'nino_pi_stop_validation_v1_2026_11_07'
ROOT_NAME = 'sim_pi_stop_validation_v1'


def protocol():
    p=parent.read(parent.frozen.repo()/'src/nino_rl/config/sim_pi_stop_validation_protocol_v1.json')
    if p['protocol_id']!=PROTOCOL_ID:raise ValueError('PI protocol identity mismatch')
    return p


def fingerprint():
    base=parent.frozen.repo()/'src/nino_rl'
    names=['nino_rl/pi_stop_validation_runner.py','nino_rl/pi_stop_validation_preflight.py',
           'config/sim_pi_stop_validation_protocol_v1.json','scripts/pi_stop_validation_runner.sh',
           'test/test_pi_stop_validation_runner.py']
    return hashlib.sha256(json.dumps(dict(context=context.fingerprint(),
        files={name:parent.sha(base/name) for name in names}),sort_keys=True).encode()).hexdigest()


def source(check_runtime=True):
    from . import pi_screen_runner as selected
    dependency=selected.source(False)
    if selected.fingerprint()!='86db564afa9e1a7980b16351db4cf466869c9b6c08c4f9bae27843cde326014f':
        raise ValueError('Frozen selection runner changed')
    root=Path.home()/'nino_research/sim_pi_screen_v1'
    out=selected.validated_latest(root,check_runtime=False)
    expected='6762f5d2903c8bef3bb4208736f14d1e3e13985146243d395fa8ef2afe4da644'
    if parent.sha(out/'manifest.json')!=expected:
        raise ValueError('Candidate selection artifact changed')
    comparison=parent.read(out/'evaluation_result.json')['comparison']
    if comparison['decision']!='descriptive_PI_candidate_separate_validation_required':
        raise ValueError('No selected Ki candidate')
    repo=parent.frozen.repo()
    installed=repo/'install/nino_rl/lib/python3.12/site-packages/nino_rl'
    for name in ('pi_stop_validation_context.py','pi_stop_validation_runner.py','pi_stop_validation_preflight.py'):
        if parent.sha(installed/name)!=parent.sha(repo/'src/nino_rl/nino_rl'/name):
            raise ValueError('Installed validation source drift: '+name)
    for name in ('sim_pi_stop_validation_protocol_v1.json','pi_stop_validation_release_v1.json'):
        if parent.sha(repo/'install/nino_rl/share/nino_rl/config'/name)!=parent.sha(repo/'src/nino_rl/config'/name):
            raise ValueError('Installed validation configuration drift: '+name)
    return dict(frozen_PI_dependency=dependency,selection_artifact=str(out),
        selection_manifest_sha256=expected,context_identity=context.identity(),
        protocol_sha256=parent.sha(repo/'src/nino_rl/config/sim_pi_stop_validation_protocol_v1.json'),
        runtime=runtime_versions() if check_runtime else None)


def evaluate(out, condition, world):
    if condition not in protocol()['evaluation_order']:
        raise ValueError('Undeclared evaluation condition')
    out.mkdir()
    arm = condition['arm']
    ident = context.identity()
    c, g, task, bc = context.configuration(condition['ki'])
    c['purpose'] = task['protocol_id'] = PROTOCOL_ID
    lp = parent.lifecycle_protocol(True)
    lp['protocol_id'] = PROTOCOL_ID
    backend = EpisodeLifecycle(c, out/'episodes', world, g, task, bc, lp,
        backend_factory=partial(PiScreenBackend, allow_physics=True))
    env = context.environment(c, backend, task, bc)
    rows, epoch, error = [], None, None
    save(out/'config.json', dict(config=c, guidance=g, task=task, condition=condition))
    try:
        obs, reset = env.reset(seed=condition['reset_seed'])
        save(out/'reset.json', reset)
        if not backend.namespace or backend.current is None:
            raise ValueError('Fresh evaluation epoch required')
        initial = backend.view()
        save(out/'initial_view.json', initial)
        qualified.require_ready(initial)
        for step in range(140):
            qualified.require_ready(backend.view())
            request = context.request(arm, obs, c['nominal_geometry'])
            parent.frozen.append(out/'control_attempts.jsonl',
                dict(step=step, requested=np.asarray(request).tolist()))
            obs, reward, term, trunc, info = env.step(request)
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc,
                done=bool(term or trunc), **info, qualification_condition=condition,
                episode_namespace=backend.namespace)
            row['TimeLimit.truncated'] = bool(trunc and not term)
            parent.frozen.append(out/'trace.jsonl', row)
            epoch = epoch if epoch is not None else row['sensor_clock_s']-row['task']['elapsed_s']
            context.verify_transition(row, rows[-1] if rows else None, epoch,
                condition['ki'], expected_identity=ident)
            rows.append(row)
            if term or trunc:
                break
    except BaseException as exc:
        error = exc
        save(out/'failure.json', dict(error=repr(exc), traceback=traceback.format_exc(), valid_rows=len(rows)))
        raise
    finally:
        try:
            env.close()
        except BaseException as exc:
            save(out/'cleanup_failure.json', dict(error=repr(exc), original=repr(error)))
            if error is None:
                raise
    target = backend.directory/backend.namespace
    result = parent.frozen.baseline.summarize(rows, target)
    diagnostic = parent.frozen.timing.timestamp_diagnostic(target, rows)
    result.update(evaluation_condition=condition, timestamp_diagnostic=diagnostic,
        actor_loads=0, probes_during_evaluation=0, optimizer_updates_in_job=0,
        reset_backend='drive_ack_and_physical_quiet_v1')
    save(out/'summary.json', result)
    if len(rows) != 140 or not result['functional_proposal_pass'] or not diagnostic['valid']:
        raise ValueError('Evaluation task/measurement failure')
    return result


def compare(runs):
    if len(runs)!=4:raise ValueError('Four complete PI cells required')
    order=protocol()['evaluation_order']
    if [r['evaluation_condition'] for r in runs]!=order:
        raise ValueError('PI block/order mismatch')
    pairs=[]
    def metric(r):
        if not r['functional_proposal_pass'] or not r['timestamp_diagnostic']['valid']:
            raise ValueError('Cannot compare invalid task/measurement result')
        grid=r['timestamp_diagnostic']['header_grid']
        return np.array([r['nominal_velocity_rmse_m_s'],grid['0.0']['rmse_m_s'],grid['0.01']['rmse_m_s']])
    for block,indices in enumerate(((0,1),(3,2))):
        baseline,candidate=(metric(runs[i]) for i in indices)
        if not np.isfinite(np.concatenate((baseline,candidate))).all() or np.any(baseline<=0) or np.any(candidate<0):
            return dict(decision='unknown_nonfinite_or_zero_denominator',pairs=pairs,benefit_verified=False,training_released=False)
        relative=(candidate-baseline)/baseline
        pairs.append(dict(block=block,baseline_indices=list(indices),baseline=baseline.tolist(),
            candidate=candidate.tolist(),candidate_minus_baseline=(candidate-baseline).tolist(),
            relative_candidate_vs_baseline=relative.tolist(),
            grid_sensitive=bool(np.any(relative<0) and np.any(relative>0))))
    relative=np.array([r['relative_candidate_vs_baseline'] for r in pairs])
    if any(r['grid_sensitive'] for r in pairs):decision='unknown_grid_sensitive'
    elif np.all(relative[:,0]<=-.05) and np.all(relative[:,1:]<0):
        decision='descriptive_PI_stop6_validation_pass_baseline_review_required'
    elif np.all(relative>=0) and np.any(relative>0):decision='no_go_candidate_retain_Ki_0_10'
    else:decision='unknown_small_or_block_dependent_effect'
    return dict(decision=decision,pairs=pairs,benefit_verified=False,training_released=False,
        two_blocks_descriptive_not_statistical_confirmation=True,
        paired_conditions_not_exact_state_branching=True,hardware_authorized=False)


def execute(out, dependencies):
    runs, attempted = [], []
    try:
        save(out/'evaluation_progress.json',dict(runs=[],attempted=[],remaining_slots_closed=False))
        worlds = parent.frozen.prepare_worlds(out)
        for i, condition in enumerate(protocol()['evaluation_order']):
            attempted.append(condition)
            save(out/'evaluation_progress.json', dict(runs=runs, attempted=attempted, remaining_slots_closed=False))
            emit(ACTION, f'PI cell {i+1}/4: {condition}', i/4)
            runs.append(evaluate(out/f'eval_{i:02d}', condition, worlds['clear_box']))
            if runs[-1]['evaluation_condition']!=condition or runs[-1]['steps']!=140:
                raise ValueError('PI cell outcome/step budget mismatch')
            save(out/'evaluation_progress.json', dict(runs=runs, attempted=attempted, remaining_slots_closed=False))
    except BaseException as exc:
        save(out/'evaluation_progress.json', dict(runs=runs, attempted=attempted, error=repr(exc),
            unused_slots_closed=4-len(attempted), remaining_slots_closed=True))
        raise
    save(out/'evaluation_progress.json',dict(runs=runs,attempted=attempted,
        unused_slots_closed=0,remaining_slots_closed=True))
    ticks = sum(r['steps'] for r in runs)
    if ticks != 560:
        raise ValueError('Exact evaluation tick budget mismatch')
    result = dict(runs=runs, comparison=compare(runs), gazebo_launches=4, evaluation_transitions=ticks,
        training_transitions=0, optimizer_updates=0, actor_loads=0, probes=0, hardware_actions=0,
        remaining_slots_closed=True, benefit_verified=False)
    save(out/'evaluation_result.json', result)
    return result


def release_record():
    return parent.read(parent.frozen.repo()/'src/nino_rl/config/pi_stop_validation_release_v1.json')


def release_ready(root):
    r = release_record()
    if (r.get('released') is not True or r.get('fingerprint') != fingerprint()
            or r.get('protocol_id') != PROTOCOL_ID or r.get('hardware_authorized') is not False
            or r.get('scope') != 'pi_stop6_4_launches_560_ticks_B0_no_actor'
            or r.get('training_authorized') is not False
            or r.get('allocated_physics_slots')!=4
            or r.get('protocol_sha256')!=parent.sha(parent.frozen.repo()/'src/nino_rl/config/sim_pi_stop_validation_protocol_v1.json')
            or Path(r['result_root']).resolve() != Path(root).resolve()):
        raise ValueError('PI stop validation not released for these sources/root')
    if Path(root).resolve() != Path.home()/'nino_research'/ROOT_NAME:
        raise ValueError('Noncanonical qualification root')
    report = Path(r['software_test_report'])
    if parent.sha(report) != r['software_test_report_sha256']:
        raise ValueError('Software test report changed')
    import xml.etree.ElementTree as ET
    suites = list(ET.parse(report).getroot().iter('testsuite'))
    if not suites or sum(int(s.get('tests', '0')) for s in suites) < 15 or any(
            int(s.get(k, '0')) for s in suites for k in ('failures', 'errors', 'skipped')):
        raise ValueError('Software gate not passed')
    cases=list(ET.parse(report).getroot().iter('testcase'))
    if sum('test_pi_stop_validation_runner' in c.get('classname','') for c in cases)<15:
        raise ValueError('PI validation runner test cases not present')
    from .pi_stop_validation_preflight import verified_report
    proof=Path(r['runner_preflight'])
    if parent.sha(proof/'manifest.json')!=r['runner_preflight_manifest_sha256']:
        raise ValueError('PI validation runner offline proof changed')
    verified_report(proof)
    return r


def validated_latest(root, check_runtime=True):
    out = latest(root, ACTION, check_runtime=check_runtime)
    if parent.read(out/'manifest.json')['pi_stop_validation_runner_fingerprint'] != fingerprint():
        raise ValueError('PI validation runner sources changed')
    if dict(parent.read(out/'dependencies.json'), runtime=None) != source(False):
        raise ValueError('PI validation runner dependencies changed')
    return out


def retained_failure(root):
    root = Path(root).resolve()
    try:
        row = parent.read(root/'state.json')['runs'][-1]
        if row['action'] != ACTION or row['status'] not in ('failed', 'cancelled'):
            return None
        out = (root/row['path']).resolve()
        m = parent.read(out/'manifest.json')
        if out.parent != root or m['pi_stop_validation_runner_fingerprint'] != fingerprint() or m['status'] != row['status']:
            return None
        for name, value in m['files'].items():
            path = (out/name).resolve()
            if not path.is_relative_to(out) or parent.sha(path) != value:
                return None
        if dict(parent.read(out/'dependencies.json'), runtime=None) != source(False):
            return None
        return dict(state='retained_failure', path=str(out),
            label='PI SCREEN ĐÃ ĐÓNG DO LỖI · KHÔNG RETRY', error=row['error'])
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


def run(root):
    root = Path(root).expanduser().resolve()
    if (root/'state.json').exists():
        raise ValueError('PI stop validation budget already consumed; no retry/foreign root')
    # Denial must occur before allocating the canonical root or a physical slot.
    release=release_ready(root)
    root.mkdir(parents=True, exist_ok=True)
    shared = Path.home()/'nino_research/.factory_sim.lock'
    shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root/'.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root/'state.json').exists():
            raise ValueError('PI stop validation budget already consumed; no retry/foreign root')
        release, deps, current = release_ready(root), source(), fingerprint()
        out = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION)
        out.mkdir()
        row = dict(action=ACTION, path=out.name, status='running', error=None)
        state = dict(schema_version=1,protocol_id=PROTOCOL_ID,allocated_slots=4,
            maximum_eval_ticks=560,retry_allowed=False,latest={},runs=[row])
        save(root/'state.json', state)
        save(out/'protocol.json', protocol())
        save(out/'release.json', release)
        save(out/'dependencies.json', deps)
        status, error, result, started = 'running', None, None, time.monotonic()
        def timeout(*args):
            raise TimeoutError('PI stop validation wall deadline')
        old = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(protocol()['wall_deadline_s'])
        try:
            emit(ACTION, 'Four fresh PI cells; no actor, learning or exploration')
            result = execute(out, deps)
            if fingerprint() != current or source() != deps:
                raise ValueError('Sources/dependencies changed during evaluation')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            save(out/'failure.json', dict(error=repr(exc), traceback=traceback.format_exc()))
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
            save(out/'job.json', dict(action=ACTION, status=status, error=error,
                wall_s=time.monotonic()-started, hardware_actions=0))
            save(out/'manifest.json', dict(action=ACTION, status=status, pi_stop_validation_runner_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)): parent.sha(f) for f in out.rglob('*')
                       if f.is_file() and f.name != 'manifest.json'}))
            progress=parent.read(out/'evaluation_progress.json') if (out/'evaluation_progress.json').exists() else {}
            attempted=len(progress.get('attempted',[]))
            row.update(status=status,error=error,attempted_slots=attempted,
                unattempted_slots_closed=4-attempted,remaining_slots_closed=True)
            if status == 'completed':
                state['latest'][ACTION] = out.name
            save(root/'state.json', state)
            emit(ACTION, status, 1. if status == 'completed' else None,
                 directory=str(out), result=result, error=error)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output)


if __name__ == '__main__':
    main()
