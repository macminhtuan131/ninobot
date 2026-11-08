"""Nine fixed gain baseline cells. Gain-one integration is inside the budget."""
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
from . import gain_context as context
from . import gain_context_preflight as preflight
from .gain_factory_backend import GainReadinessBackend
from .reliable_episode import EpisodeLifecycle
from .residual_workflow import save, emit, latest, runtime_versions
from .residual_experiment import source_fingerprint

parent = context.parent.parent
qualified = context.parent.qualified
ACTION = 'sim-gain-baselines'
PROTOCOL_ID = 'nino_gain_baseline_qualification_v1_2026_11_06'
PREFLIGHT_MANIFEST = 'e130108934e4d12da74d802f621156a39da41ed51606607c0d472fda485f2ec4'
CONTEXT_FINGERPRINT = 'deccb94680a263042ab4fd688bca7669e79f562602a713f23c4d4dc4243f469f'
ROOT_NAME = 'sim_gain_baselines_v1'


def protocol():
    order = [dict(arm=arm, source_stop_s=8., gain=gain) for gain in (1., .98, 1.02)
             for arm in ('B0', 'Classical_scheduled', 'Causal_gain_candidate')]
    return dict(protocol_id=PROTOCOL_ID, evaluation_order=order, maximum_launches=9,
        steps_per_launch=140, maximum_eval_ticks=1260, wall_deadline_s=2700,
        training_transitions=0, optimizer_updates=0, actor_loads=0, probes=0,
        retries=0, extra_smokes=0, hardware_actions=0,
        primary='whole_14s_native_velocity_rmse', grids=['GT20ms', 'GTshift10ms'],
        minimum_relative_effect_proposed=.05, application_minimum_effect_accepted=None,
        scope='one_cell_per_condition_descriptive_baseline_qualification_not_generalization')


def fingerprint():
    base = parent.frozen.repo() / 'src/nino_rl'
    names = ['nino_rl/gain_baseline_qualification.py', 'scripts/gain_baseline_qualification.sh',
             'test/test_gain_baseline_qualification.py']
    return hashlib.sha256(json.dumps(dict(context=context.fingerprint(),
        files={f: parent.sha(base/f) for f in names}), sort_keys=True).encode()).hexdigest()


def source(check_runtime=True):
    out = Path.home() / 'nino_research/sim_gain_context_preflight_v1/offline_2026_11_06'
    result = preflight.verified_report(out)
    if parent.sha(out/'manifest.json') != PREFLIGHT_MANIFEST or context.fingerprint() != CONTEXT_FINGERPRINT:
        raise ValueError('Frozen gain software qualification changed')
    if result['new_gazebo_launches'] != 0 or result['synthetic_wrapper_transitions'] != 840:
        raise ValueError('Unexpected gain qualification provenance')
    repo = parent.frozen.repo()
    # Entry mapping is outside the frozen scientific family; inspect the actual
    # installed executable, metadata, driver sources and launch before physics.
    entry = repo/'install/nino_rl/lib/nino_rl/sim_gain_effort_drive'
    if 'sim_gain_effort_drive' not in entry.read_text():
        raise ValueError('Gain drive entry missing')
    from importlib.metadata import distribution
    eps = [e for e in distribution('nino-rl').entry_points if e.name == 'sim_gain_effort_drive']
    if len(eps) != 1 or eps[0].value != 'nino_rl.gain_effort_drive:main':
        raise ValueError('Wrong gain drive entry target')
    installed = repo/'install/nino_rl/lib/python3.12/site-packages/nino_rl'
    names = ['gain_reference_map.py', 'gain_drive_kernel.py', 'gain_effort_drive.py',
             'gain_factory_backend.py', 'gain_context.py', 'gain_context_preflight.py', 'gain_drive_fixture.py']
    for name in names:
        if parent.sha(installed/name) != parent.sha(repo/'src/nino_rl/nino_rl'/name):
            raise ValueError('Installed gain code drift: '+name)
    launch = 'training_sim_gain.launch.py'
    if parent.sha(repo/'install/nino_rl/share/nino_rl/launch'/launch) != parent.sha(repo/'src/nino_rl/launch'/launch):
        raise ValueError('Installed gain launch drift')
    return dict(preflight=str(out), preflight_manifest_sha256=PREFLIGHT_MANIFEST,
        context_fingerprint=CONTEXT_FINGERPRINT, context_identity=context.identity(),
        runtime=runtime_versions() if check_runtime else None,
        driver_entry_sha256=parent.sha(entry), driver_entry_target=eps[0].value)


def evaluate(out, condition, world):
    if condition not in protocol()['evaluation_order']:
        raise ValueError('Undeclared evaluation condition')
    out.mkdir()
    arm = condition['arm']
    ident = context.identity()
    c, g, task, bc = context.configuration(condition['gain'])
    c['purpose'] = task['protocol_id'] = PROTOCOL_ID
    lp = parent.lifecycle_protocol(True)
    lp['protocol_id'] = PROTOCOL_ID
    backend = EpisodeLifecycle(c, out/'episodes', world, g, task, bc, lp,
        backend_factory=partial(GainReadinessBackend, allow_physics=True))
    env = context.environment(c, backend, task, bc)
    rows, epoch, error = [], None, None
    save(out/'config.json', dict(config=c, guidance=g, task=task, condition=condition))
    try:
        obs, reset = env.reset(seed=701)
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
                condition['gain'], expected_identity=ident)
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
    if len(runs) != 9:
        raise ValueError('Nine fixed complete cells required')
    indexed = {(r['evaluation_condition']['arm'], r['evaluation_condition']['gain']): r for r in runs}
    if set(indexed) != {(c['arm'], c['gain']) for c in protocol()['evaluation_order']}:
        raise ValueError('Cell matrix mismatch')
    comparisons = []
    def metric(r):
        g = r['timestamp_diagnostic']['header_grid']
        return np.array([r['nominal_velocity_rmse_m_s'], g['0.0']['rmse_m_s'], g['0.01']['rmse_m_s']])
    for gain in (1., .98, 1.02):
        b, f, c = (metric(indexed[(arm, gain)]) for arm in ('B0', 'Classical_scheduled', 'Causal_gain_candidate'))
        if not np.isfinite(np.concatenate((b, f, c))).all() or np.any(b <= 0) or np.any(f <= 0):
            return dict(decision='unknown_nonfinite_or_zero_denominator', comparisons=comparisons, benefit_verified=False)
        relative = (c-f)/f
        comparisons.append(dict(gain=gain, B0=b.tolist(), fixed=f.tolist(), causal=c.tolist(),
            causal_minus_fixed=(c-f).tolist(), relative_causal_vs_fixed=relative.tolist(),
            relative_causal_vs_B0=((c-b)/b).tolist(),
            grid_sensitive=bool(np.any(relative < 0) and np.any(relative > 0))))
    relative = np.array([r['relative_causal_vs_fixed'] for r in comparisons])
    decision = ('unknown_grid_sensitive' if any(r['grid_sensitive'] for r in comparisons) else
        'descriptive_causal_candidate_separate_validation_required' if np.all(relative <= -.05) else
        'retain_fixed_classical_no_learning_justified' if np.all(relative >= 0) else
        'unknown_small_or_gain_dependent_effect')
    return dict(decision=decision, comparisons=comparisons, benefit_verified=False,
        one_cell_per_condition=True, paired_conditions_not_exact_state_branching=True,
        gain_is_ideal_stress_not_hardware_calibration=True, training_released=False)


def execute(out, dependencies):
    import torch
    torch.set_num_threads(1)
    worlds = parent.frozen.prepare_worlds(out)
    runs, attempted = [], []
    try:
        for i, condition in enumerate(protocol()['evaluation_order']):
            attempted.append(condition)
            save(out/'evaluation_progress.json', dict(runs=runs, attempted=attempted, remaining_slots_closed=False))
            emit(ACTION, f'Baseline {i+1}/9: {condition}', i/9)
            runs.append(evaluate(out/f'eval_{i:02d}', condition, worlds['clear_box']))
            save(out/'evaluation_progress.json', dict(runs=runs, attempted=attempted, remaining_slots_closed=False))
    except BaseException as exc:
        save(out/'evaluation_progress.json', dict(runs=runs, attempted=attempted, error=repr(exc),
            unused_slots_closed=9-len(attempted), remaining_slots_closed=True))
        raise
    ticks = sum(r['steps'] for r in runs)
    if ticks != 1260:
        raise ValueError('Exact evaluation tick budget mismatch')
    result = dict(runs=runs, comparison=compare(runs), gazebo_launches=9, evaluation_transitions=ticks,
        training_transitions=0, optimizer_updates=0, actor_loads=0, probes=0, hardware_actions=0,
        remaining_slots_closed=True, benefit_verified=False)
    save(out/'evaluation_result.json', result)
    return result


def release_record():
    return parent.read(parent.frozen.repo()/'src/nino_rl/config/gain_baseline_release_v1.json')


def release_ready(root):
    r = release_record()
    if (r.get('released') is not True or r.get('fingerprint') != fingerprint()
            or r.get('protocol_id') != PROTOCOL_ID or r.get('hardware_authorized') is not False
            or r.get('scope') != 'gain_baselines_9_launches_1260_ticks_no_actor'
            or Path(r['result_root']).resolve() != Path(root).resolve()):
        raise ValueError('Gain baseline qualification not released for these sources/root')
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
    return r


def validated_latest(root, check_runtime=True):
    out = latest(root, ACTION, check_runtime=check_runtime)
    if parent.read(out/'manifest.json')['gain_baseline_fingerprint'] != fingerprint():
        raise ValueError('Gain qualification sources changed')
    if dict(parent.read(out/'dependencies.json'), runtime=None) != source(False):
        raise ValueError('Gain qualification dependencies changed')
    return out


def retained_failure(root):
    root = Path(root).resolve()
    try:
        row = parent.read(root/'state.json')['runs'][-1]
        if row['action'] != ACTION or row['status'] not in ('failed', 'cancelled'):
            return None
        out = (root/row['path']).resolve()
        m = parent.read(out/'manifest.json')
        if out.parent != root or m['gain_baseline_fingerprint'] != fingerprint() or m['status'] != row['status']:
            return None
        for name, value in m['files'].items():
            path = (out/name).resolve()
            if not path.is_relative_to(out) or parent.sha(path) != value:
                return None
        if dict(parent.read(out/'dependencies.json'), runtime=None) != source(False):
            return None
        return dict(state='retained_failure', path=str(out),
            label='GAIN BASELINE ĐÃ ĐÓNG DO LỖI · KHÔNG RETRY', error=row['error'])
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


def run(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    shared = Path.home()/'nino_research/.factory_sim.lock'
    shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root/'.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root/'state.json').exists():
            raise ValueError('Gain qualification budget already consumed; no retry/foreign root')
        release, deps, current = release_ready(root), source(), fingerprint()
        out = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION)
        out.mkdir()
        row = dict(action=ACTION, path=out.name, status='running', error=None)
        state = dict(schema_version=1, latest={}, runs=[row])
        save(root/'state.json', state)
        save(out/'protocol.json', protocol())
        save(out/'release.json', release)
        save(out/'dependencies.json', deps)
        status, error, result, started = 'running', None, None, time.monotonic()
        def timeout(*args):
            raise TimeoutError('Gain qualification wall deadline')
        old = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(protocol()['wall_deadline_s'])
        try:
            emit(ACTION, 'Nine fresh baseline cells; no actor, learning or exploration')
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
            save(out/'manifest.json', dict(action=ACTION, status=status, gain_baseline_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)): parent.sha(f) for f in out.rglob('*')
                       if f.is_file() and f.name != 'manifest.json'}))
            row.update(status=status, error=error)
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
