"""One-shot clear-floor planned-stop transfer; no actor, optimizer or hardware."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np

from . import residual_classical_common as common
from . import residual_guided_baseline as baseline
from . import residual_guided_td3 as learner
from .core import load_config
from .residual_experiment import source_fingerprint
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import emit, json_value, latest, runtime_versions, save

ACTION = 'sim-stop-transfer'
PARENT_ROOT = Path.home() / 'nino_research/sim_classical_common_v1'


def protocol():
    p = load_config(repo() / 'src/nino_rl/config/residual_stop_transfer_v1.yaml')
    order = [('B0', 0), ('Classical_scheduled', 0), ('Classical_scheduled', 1),
             ('B0', 1), ('B0', 2), ('Classical_scheduled', 2)]
    if [(r['arm'], r['repeat']) for r in p['order']] != order:
        raise ValueError('New order requires a new transfer protocol')
    if (p['scenario'], p['maximum_transitions'], p['steps_per_rollout'],
            p['training_transitions'], p['optimizer_updates'], p['hardware_actions']) != ('clear_box', 840, 140, 0, 0, 0):
        raise ValueError('Fixed transfer budget/scenario mismatch')
    if (p['planned_source_stop_s'], p['withdraw_lead_s'], p['common_compensation_m_s'],
            p['nominal_steady_m_s'], p['residual_scale_m_s'], p['horizon_s'], p['warmup_s']) != (6., .5, .005, .2, .04, 14., .5):
        raise ValueError('Fixed transfer parameters changed; no tuning in this batch')
    expected = dict(grid_s=.02, shifts_s=[0., .01], maximum_support_age_s=.020000001,
                    first_grid_s=.1, body_interpolation=False)
    if p['timestamp_diagnostic'] != expected or p['minimum_effect_accepted'] is not None:
        raise ValueError('Predeclared diagnostic or unaccepted effect changed')
    if common.fingerprint() != p['parent_fingerprint']:
        raise ValueError('Frozen common parent changed')
    return p


def fingerprint():
    files = [Path(__file__), repo() / 'src/nino_rl/config/residual_stop_transfer_v1.yaml',
             repo() / 'src/nino_rl/scripts/residual_stop_transfer.sh']
    return hashlib.sha256(json.dumps(dict(parent=common.fingerprint(), files={
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}), sort_keys=True).encode()).hexdigest()


def parent(check_runtime=True):
    protocol()
    out = common.validated_latest(PARENT_ROOT, check_runtime=check_runtime)
    result = json.loads((out / 'evaluation_result.json').read_text())
    if (result['evaluation_transitions'] != 840 or not result['descriptive_velocity_separation']
            or not result['all_task_and_stop_pass'] or not result['all_functional_proposals_pass']):
        raise ValueError('Previous classical candidate did not pass its descriptive prerequisite')
    return out


def configuration():
    p = protocol()
    c, g, task, condition = learner.configuration('clear_box')
    task.update(protocol_id=p['protocol_id'], command_until_s=p['planned_source_stop_s'],
                horizon_s=p['horizon_s'], warmup_s=p['warmup_s'])
    c['purpose'] = p['protocol_id']
    c['backend'].update(scenario_id='clear_box_stop_schedule_transfer_v1',
                        command_until_s=p['planned_source_stop_s'], horizon_s=p['horizon_s'])
    c['task'].update(command_until_s=p['planned_source_stop_s'], horizon_s=p['horizon_s'])
    profile = dict(p, withdraw_at_task_s=p['planned_source_stop_s'] - p['withdraw_lead_s'])
    return c, g, task, condition, profile


def timestamp_diagnostic(out, rows):
    """GT-header diagnostic only; held native reference, no interpolated body."""
    p = protocol()['timestamp_diagnostic']
    epoch = rows[0]['sensor_clock_s'] - rows[0]['task']['elapsed_s']
    end = rows[-1]['sensor_clock_s']
    truth = {}
    for path in (out / 'backend').rglob('raw_samples.jsonl'):
        for line in path.open():
            r = json.loads(line)
            if r['channel'] == 'truth' and epoch <= r['stamp_s'] <= end:
                truth[r['stamp_s']] = r['values']['speed']
    stamps = np.array(sorted(truth))
    values = np.array([truth[t] for t in stamps])
    if len(stamps) < 2 or np.max(np.diff(stamps)) > p['maximum_support_age_s']:
        return dict(valid=False, reason='GT-header source gap; diagnostic unknown', body_interpolated=False)
    ends = np.array([r['task']['elapsed_s'] for r in rows])
    nominal = np.array([r['task']['nominal_shaped_body'][0] for r in rows])
    scores = {}
    for shift in p['shifts_s']:
        grid = np.arange(p['first_grid_s'] + shift, protocol()['horizon_s'] + 1e-7, p['grid_s'])
        query = epoch + grid
        support = np.searchsorted(stamps, query + 1e-9, side='right') - 1
        if np.min(support) < 0 or np.max(query - stamps[support]) > p['maximum_support_age_s']:
            return dict(valid=False, reason='Insufficient causal GT support; diagnostic unknown', body_interpolated=False)
        indices = np.searchsorted(ends, stamps[support] - epoch - 1e-9, side='left')
        if np.max(indices) >= len(rows):
            return dict(valid=False, reason='Nominal support missing', body_interpolated=False)
        error = values[support] - nominal[indices]
        scores[str(shift)] = dict(samples=len(grid), unique_truth_samples=len(set(support)),
                                 rmse_m_s=float(np.sqrt(np.mean(error ** 2))),
                                 maximum_support_age_s=float(np.max(query - stamps[support])))
    return dict(valid=True, header_grid=scores, post_hoc=False, primary_native_unchanged=True,
                body_interpolated=False, method='20ms grids / +10ms; latest GT at/before grid; nominal held over native interval at GT header')


def rollout(out, condition, world):
    out.mkdir()
    c, g, task, backend_condition, profile_config = configuration()
    backend_condition['repeat'] = condition['repeat']
    save(out / 'config.json', c)
    save(out / 'guidance_config.json', g)
    save(out / 'task_config.json', task)
    save(out / 'profile_config.json', profile_config)
    backend = baseline.GuidedBackend(c, out / 'backend', world, g, task, backend_condition)
    env = learner.environment(c, backend, task, backend_condition)
    profile = common.ClassicalCommonProfile(c, profile_config)
    rows = []
    try:
        obs, info = env.reset(seed=701)
        save(out / 'reset.json', info)
        for step in range(protocol()['steps_per_rollout']):
            audit = None
            controlled = np.zeros(2, np.float32)
            if condition['arm'] == 'Classical_scheduled':
                pipeline = env.env.pipeline
                controlled, audit = profile.proposal(step * c['control_interval_s'], pipeline.last_view,
                    pipeline.history.ready, latched=pipeline.reference.latched)
            obs, reward, term, trunc, info = env.step(controlled)
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc, **info,
                       actor_raw_proposal=None, controller_proposal=controlled,
                       classical_profile_audit=audit, comparison_condition=condition)
            rows.append(row)
            with (out / 'trace.jsonl').open('a') as stream:
                stream.write(json.dumps(row, default=json_value, allow_nan=False) + '\n')
            if audit is not None:
                np.testing.assert_allclose(audit['nominal_shaped_body'], info['task']['nominal_shaped_body'], atol=1e-10, rtol=0)
            if (step + 1) % 35 == 0:
                emit(ACTION, out.name + f' {step + 1}/140')
            if term or trunc:
                break
    finally:
        env.close()
    result = baseline.summarize(rows, out)
    phases = {}
    for label in ('steady', 'deceleration'):
        selected = [r for r in rows if r['reference_trace']['original_baseline_body'][0] > 0 and abs(r['task']['nominal_shaped_body'][0] - .2) < 1e-8] if label == 'steady' else [r for r in rows if r['reference_trace']['original_baseline_body'][0] == 0 and r['task']['nominal_shaped_body'][0] > 1e-9]
        phases[label] = dict(samples=len(selected), velocity_rmse_m_s=float(np.sqrt(np.mean([
            r['task']['velocity_error_m_s'] ** 2 for r in selected])))) if selected else None
    active = [r['classical_profile_audit']['decision_task_s'] for r in rows if r['classical_profile_audit'] and r['classical_profile_audit']['requested_common_m_s'] > 0]
    result.update(condition=dict(condition, scenario='clear_box'), phases=phases,
        compensation_active_ticks=len(active), compensation_first_decision_s=min(active) if active else None,
        compensation_last_decision_s=max(active) if active else None, actor_inference_calls=0,
        timestamp_diagnostic=timestamp_diagnostic(out, rows), training_dataset_compatible=False,
        training_transitions=0, optimizer_updates=0)
    save(out / 'summary.json', result)
    return result


def decision(runs):
    """Descriptive separation only, never a deployment/benefit promotion."""
    arms = {a: [r for r in runs if r['condition']['arm'] == a] for a in ('B0', 'Classical_scheduled')}
    complete = len(runs) == 6 and all(len(v) == 3 for v in arms.values())
    constraints = complete and all(r['task_success'] and r['stop_completed'] and r['functional_proposal_pass'] for r in runs)
    native = complete and max(r['nominal_velocity_rmse_m_s'] for r in arms['Classical_scheduled']) < min(r['nominal_velocity_rmse_m_s'] for r in arms['B0'])
    diagnostic = complete and all(r['timestamp_diagnostic']['valid'] for r in runs)
    separation = {}
    if diagnostic:
        for shift in ('0.0', '0.01'):
            values = lambda arm: [r['timestamp_diagnostic']['header_grid'][shift]['rmse_m_s'] for r in arms[arm]]
            separation[shift] = max(values('Classical_scheduled')) < min(values('B0'))
    signal_ok = bool(constraints and native and diagnostic and all(separation.values()))
    return dict(descriptive_velocity_separation=bool(native), diagnostic_valid=bool(diagnostic),
                header_separation_by_shift=separation, all_task_and_stop_pass=bool(complete and all(r['task_success'] and r['stop_completed'] for r in runs)),
                all_functional_proposals_pass=bool(constraints), descriptive_transfer_signal=signal_ok,
                decision='descriptive_signal_not_promoted' if signal_ok else 'unknown_or_failed_keep_B0',
                minimum_effect_accepted=None, benefit_verified=False, hardware_authorized=False)


def evaluate(out):
    p = protocol()
    save(out / 'dependencies.json', learner.dependency_record(parent()))
    save(out / 'comparison_contract.json', dict(protocol=p, fingerprint=fingerprint(),
        planning_preview='Known source stop6s; withdrawal=stop-0.5s. No obstacle preview or new TD3 claim.',
        task_configuration=configuration()[2], training_dataset_compatible=False))
    worlds = prepare_worlds(out)
    runs = []
    closed_reason = None
    for index, condition in enumerate(p['order']):
        emit(ACTION, f'{index + 1}/6 · {condition}', index / 6)
        result = rollout(out / (condition['arm'] + '_' + str(condition['repeat'])), condition, worlds['clear_box'])
        runs.append(result)
        save(out / 'evaluation_progress.json', runs)
        if result['physical_failure'] or result['guidance_faults'] or result['steps'] != 140:
            raise RuntimeError('Physical/source/guidance failure; keep data, close unused slots, no retry')
        if not result['functional_proposal_pass']:
            closed_reason = 'Functional proposal failed; remaining slots closed without retry'
            break
    result = dict(protocol_id=p['protocol_id'], runs=runs, evaluation_transitions=sum(r['steps'] for r in runs),
                  actor_inference_calls=0, training_transitions=0, optimizer_updates=0,
                  closed_reason=closed_reason, independent_gazebo_seeds_verified=False, **decision(runs))
    save(out / 'evaluation_result.json', result)
    return result


def validated_latest(root, check_runtime=True):
    out = latest(root, ACTION, check_runtime=check_runtime)
    if json.loads((out / 'manifest.json').read_text()).get('stop_transfer_fingerprint') != fingerprint():
        raise ValueError('Transfer sources/protocol changed')
    if json.loads((out / 'dependencies.json').read_text()) != learner.dependency_record(parent(check_runtime)):
        raise ValueError('Frozen common dependency changed')
    return out


def run(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    shared = Path.home() / 'nino_research/.factory_sim.lock'
    shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root / '.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / 'state.json').exists():
            raise ValueError('Stop-transfer batch already consumed; no retry or reopening')
        protocol()
        parent()
        out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + ACTION)
        out.mkdir()
        ledger = dict(schema_version=1, latest={}, runs=[dict(action=ACTION, path=out.name, status='running', error=None)])
        save(root / 'state.json', ledger)
        save(out / 'protocol.json', protocol())
        current, started, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame):
            raise TimeoutError('Finite stop-transfer wall deadline')
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(protocol()['wall_deadline_s'])
        try:
            result = evaluate(out)
            if fingerprint() != current:
                raise ValueError('Source changed during batch')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            save(out / 'job.json', dict(action=ACTION, status=status, error=error, wall_s=time.monotonic() - started, hardware_actions=0))
            save(out / 'manifest.json', dict(action=ACTION, status=status, stop_transfer_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)): hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file() and f.name != 'manifest.json'}))
            ledger['runs'][0].update(status=status, error=error)
            if status == 'completed':
                ledger['latest'][ACTION] = out.name
            save(root / 'state.json', ledger)
            emit(ACTION, status, 1. if status == 'completed' else None, directory=str(out), result=result, error=error)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.output)
    except (Exception, KeyboardInterrupt) as exc:
        print('Stop transfer failed/retained:', exc, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
