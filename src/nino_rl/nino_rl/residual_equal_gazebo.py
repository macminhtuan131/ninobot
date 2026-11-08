"""Four-launch103D/1D Gazebo integration qualification; no actor or learning."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import pickle
import signal
import time

import numpy as np
from . import equal_information_contract as contract
from . import residual_equal_information as offline
from . import residual_guided_baseline as baseline
from . import residual_classical_common as classical
from . import residual_stop_transfer as timing
from .core import load_config
from .residual_experiment import source_fingerprint
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import emit, json_value, latest, runtime_versions, save

ACTION = 'sim-equal-gazebo'
PARENT_ROOT = Path.home() / 'nino_research/sim_equal_information_v1'


def protocol():
    p = load_config(repo() / 'src/nino_rl/config/residual_equal_gazebo_v1.yaml')
    expected = [('B0', 6.), ('Classical_scheduled', 6.), ('Proposal_probe', 6.), ('Proposal_probe', 8.)]
    if [(r['arm'], r['source_stop_s']) for r in p['order']] != expected:
        raise ValueError('New order/conditions require a new qualification protocol')
    if (p['scenario'], p['steps_per_rollout'], p['maximum_transitions'], p['training_transitions'],
            p['optimizer_updates'], p['actor_inference_calls'], p['hardware_actions'],
            p['native_boundary_support_s']) != ('clear_box', 140, 560, 0, 0, 0, 0, .04):
        raise ValueError('Frozen qualification budget/support mismatch')
    if contract.fingerprint() != p['parent_fingerprint'] or contract.identity()['abi_sha256'] != p['abi_sha256']:
        raise ValueError('Frozen103D/1D parent/ABI changed')
    return p


def fingerprint():
    paths = [Path(__file__), repo() / 'src/nino_rl/config/residual_equal_gazebo_v1.yaml',
             repo() / 'src/nino_rl/scripts/residual_equal_gazebo.sh']
    return hashlib.sha256(json.dumps(dict(parent=contract.fingerprint(), files={
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}), sort_keys=True).encode()).hexdigest()


def parent(check_runtime=True):
    protocol()
    out = offline.validated_latest(PARENT_ROOT, check_runtime=check_runtime)
    q = json.loads((out / 'qualification.json').read_text())
    if not q['learned_parameters_unchanged'] or not q['requested_vs_windowed_vs_accepted_separate'] or q['optimizer_updates']:
        raise ValueError('Offline prerequisite did not qualify')
    return out


def configuration(condition):
    p = protocol()
    if condition not in p['order']:
        raise ValueError('Unregistered qualification condition')
    c, g, task, backend_condition = contract.configuration(condition['source_stop_s'])
    c['purpose'] = p['protocol_id']
    c['backend']['scenario_id'] = 'clear_box_equal_gazebo_qualification_v1'
    task['protocol_id'] = p['protocol_id']
    return c, g, task, backend_condition


def request(arm, observation, step):
    if arm == 'B0':
        return np.zeros(1, np.float32)
    if arm == 'Classical_scheduled':
        return contract.classical_request(observation)
    if arm == 'Proposal_probe':
        return np.array([(-1., 0., 1.)[step % 3]], np.float32)
    raise ValueError('Unknown integration arm; no actor loaded')


def verify_transition(row, previous, epoch, abi):
    """Fail before the next tick if clock, observation or request semantics drift."""
    a = row['plan_projection']
    obs, nxt = row['equal_observation'], row['equal_next_observation']
    if len(obs) != 103 or len(nxt) != 103 or row['abi_sha256'] != abi:
        raise ValueError('103D observation/ABI mismatch')
    np.testing.assert_allclose(obs[:100], row['reference_trace']['observation'], atol=2e-6, rtol=0)
    if row['policy_proposal'] != row['requested_scalar_action'] or len(row['policy_proposal']) != 1:
        raise ValueError('Replay must keep scalar requested action')
    mapped = list(row['controller_proposal'])
    if mapped != list(row['inherited_policy_proposal']) or mapped != list(row['reference_trace']['proposal']):
        raise ValueError('Mapped controller/inherited projection trace mismatch')
    if mapped[1] != 0. or max(map(abs, mapped)) > .125:
        raise ValueError('Common-only physical range changed')
    if not a['window_open'] and any(mapped):
        raise ValueError('Closed shared window emitted a residual')
    if obs[101] != float(a['window_open']) or obs[102] != (previous['requested_scalar_action'][0] if previous else 0.):
        raise ValueError('Window/previous requested action not causal')
    if previous is not None:
        np.testing.assert_array_equal(obs, previous['equal_next_observation'])
    if a['truth_input'] or row['truth_used_for_guidance']:
        raise ValueError('Privileged controller input')
    decision = row['step'] * .1
    if (a['decision_tick'] != row['step'] or abs(a['decision_task_s'] - decision) > 1e-9
            or abs(row['reference_trace']['input_stamp_s'] - epoch - decision) > 1e-8
            or abs(row['sensor_clock_s'] - epoch - row['task']['elapsed_s']) > 1e-8):
        raise ValueError('Plan decision clock/source epoch mismatch')
    stop = row['qualification_condition']['source_stop_s']
    if abs(obs[100] - (stop - decision) / 14.) > 1e-7:
        raise ValueError('Reference generator preview mismatch')
    np.testing.assert_allclose(a['nominal_shaped_body'], row['task']['nominal_shaped_body'], atol=1e-10, rtol=0)
    if abs(sum(row['reward_terms'].values()) - row['reward']) > 1e-9:
        raise ValueError('Scalar reward trace mismatch')


def rollout(out, condition, world):
    out.mkdir()
    p = protocol()
    c, g, task, backend_condition = configuration(condition)
    for name, value in [('config', c), ('guidance_config', g), ('task_config', task)]:
        save(out / (name + '.json'), value)
    backend = baseline.GuidedBackend(c, out / 'backend', world, g, task, backend_condition)
    env = contract.environment(c, backend, task, backend_condition)
    # A read-only legacy rule on this same received source checks predicate and
    # nominal parity; it never overrides the new controller's request.
    legacy_config = dict(contract.protocol(), planned_source_stop_s=condition['source_stop_s'],
        withdraw_at_task_s=condition['source_stop_s'] - .5, common_compensation_m_s=.005, residual_scale_m_s=.04)
    legacy = classical.ClassicalCommonProfile(c, legacy_config)
    from stable_baselines3.common.buffers import ReplayBuffer
    replay = ReplayBuffer(160, env.observation_space, env.action_space, device='cpu', handle_timeout_termination=True)
    rows = []
    epoch = None
    try:
        obs, info = env.reset(seed=701)
        save(out / 'reset.json', info)
        for step in range(p['steps_per_rollout']):
            pipeline = env.env.pipeline
            expected, legacy_audit = legacy.proposal(step * .1, pipeline.last_view, pipeline.history.ready,
                                                     latched=pipeline.reference.latched)
            proposed = request(condition['arm'], obs, step)
            nxt, reward, term, trunc, info = env.step(proposed)
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc, done=bool(term or trunc), **info,
                       qualification_condition=condition, legacy_window_expected=bool(expected[0]),
                       legacy_nominal_shaped_body=legacy_audit['nominal_shaped_body'])
            row['TimeLimit.truncated'] = bool(trunc and not term)
            with (out / 'trace.jsonl').open('a') as stream:
                stream.write(json.dumps(row, default=json_value, allow_nan=False) + '\n')
            if epoch is None:
                epoch = row['sensor_clock_s'] - row['task']['elapsed_s']
            verify_transition(row, rows[-1] if rows else None, epoch, p['abi_sha256'])
            if row['plan_projection']['window_open'] != bool(expected[0]):
                raise ValueError('Shared/legacy eligibility disagree on the same received source')
            np.testing.assert_allclose(legacy_audit['nominal_shaped_body'], row['task']['nominal_shaped_body'], atol=1e-10, rtol=0)
            if condition['arm'] == 'Classical_scheduled':
                np.testing.assert_array_equal(row['controller_proposal'], expected)
            rows.append(row)
            replay.add(obs, nxt, proposed, np.array([reward]), np.array([term or trunc]), [row])
            obs = nxt
            if (step + 1) % 35 == 0:
                emit(ACTION, out.name + f' {step + 1}/140')
            if term or trunc:
                break
    finally:
        env.close()
    # Reuse shared numerical action/observation/reward/terminal checks. Its
    # original offline result label is not reused as a Gazebo evidence claim.
    replay_check = contract.audit_replay(replay, rows)
    with (out / 'diagnostic_replay_not_training.pkl').open('wb') as stream:
        pickle.dump(replay, stream)
    summary = baseline.summarize(rows, out)
    active = [r['plan_projection']['decision_task_s'] for r in rows if r['plan_projection']['window_open']]
    source = [r['plan_projection']['decision_task_s'] for r in rows if r['reference_trace']['original_baseline_body'][0] > 0]
    ages = [max(r['source_lags_s'].values()) for r in rows]
    diagnostic = timing.timestamp_diagnostic(out, rows) if len(rows) == 140 else dict(valid=False, reason='Early closure')
    summary.update(qualification_condition=condition, common_window_ticks=len(active),
        first_window_decision_s=min(active) if active else None, last_window_decision_s=max(active) if active else None,
        first_motion_source_decision_s=min(source) if source else None,
        blocked_nonzero_requests=sum(not r['plan_projection']['window_open'] and r['requested_scalar_action'][0] != 0. for r in rows),
        legacy_rule_and_nominal_parity=True, replay_rows_checked=replay_check['rows_checked'],
        replay_scope='Gazebo diagnostic replay for requested/mapped semantics, not a TD3 training dataset',
        maximum_native_boundary_support_age_s=max(ages), timestamp_diagnostic=diagnostic,
        measurement_pass=bool(max(ages) <= p['native_boundary_support_s'] + 1e-9 and diagnostic['valid']),
        actor_inference_calls=0, optimizer_updates=0, training_transitions=0,
        observation_size=103, action_size=1, benefit_verified=False)
    summary['integration_pass'] = bool(summary['steps'] == 140 and not summary['physical_failure'] and not summary['guidance_faults']
        and summary['functional_proposal_pass'] and summary['measurement_pass'])
    save(out / 'summary.json', summary)
    return summary


def evaluate(out):
    p = protocol()
    save(out / 'dependencies.json', contract.guided.dependency_record(parent()))
    save(out / 'identity.json', contract.identity())
    worlds = prepare_worlds(out)
    runs = []
    for i, condition in enumerate(p['order']):
        emit(ACTION, f'{i + 1}/4 · {condition}', i / 4)
        name = condition['arm'] + '_stop' + str(int(condition['source_stop_s']))
        result = rollout(out / name, condition, worlds['clear_box'])
        runs.append(result)
        save(out / 'qualification_progress.json', runs)
        if result['physical_failure'] or result['guidance_faults'] or result['steps'] != 140:
            raise RuntimeError('Physical/source/guidance failure; remaining slots closed, retain raw, no retry')
        if not result['integration_pass']:
            break
    qualified = len(runs) == 4 and all(r['integration_pass'] for r in runs)
    result = dict(protocol_id=p['protocol_id'], runs=runs, qualification_pass=qualified,
        evaluation_transitions=sum(r['steps'] for r in runs), maximum_transitions=560,
        replay_rows_checked=sum(r['replay_rows_checked'] for r in runs),
        closed_reason=None if qualified else 'Unknown/failed integration; unused slots closed',
        abi_sha256=p['abi_sha256'], observation_size=103, action_size=1,
        actor_inference_calls=0, optimizer_updates=0, training_transitions=0, hardware_actions=0,
        benefit_verified=False, training_released=False, minimum_effect_accepted=None,
        conclusion='103D/1D Gazebo integration only; deterministic probes are not a learned policy or superiority test')
    save(out / 'qualification_result.json', result)
    return result


def validated_latest(root, check_runtime=True):
    out = latest(root, ACTION, check_runtime=check_runtime)
    if json.loads((out / 'manifest.json').read_text()).get('equal_gazebo_fingerprint') != fingerprint():
        raise ValueError('Equal Gazebo source/protocol changed')
    if json.loads((out / 'dependencies.json').read_text()) != contract.guided.dependency_record(parent(check_runtime)):
        raise ValueError('Frozen offline qualification dependency changed')
    contract.require_identity(json.loads((out / 'identity.json').read_text()))
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
            raise ValueError('Gazebo qualification already consumed; no retry or reopening')
        p = protocol()
        parent()
        out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + ACTION)
        out.mkdir()
        ledger = dict(schema_version=1, latest={}, runs=[dict(action=ACTION, path=out.name, status='running', error=None)])
        save(root / 'state.json', ledger)
        save(out / 'protocol.json', p)
        current, started, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame):
            raise TimeoutError('Finite Gazebo qualification wall deadline')
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(p['wall_deadline_s'])
        try:
            result = evaluate(out)
            if fingerprint() != current:
                raise ValueError('Source changed during qualification')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            save(out / 'job.json', dict(action=ACTION, status=status, error=error, wall_s=time.monotonic() - started, hardware_actions=0))
            save(out / 'manifest.json', dict(action=ACTION, status=status, equal_gazebo_fingerprint=current,
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
        print('Gazebo103D qualification failed/retained:', exc, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
