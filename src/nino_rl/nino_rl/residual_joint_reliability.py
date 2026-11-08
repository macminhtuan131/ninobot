"""One bounded reliability fixture and conditional B0 Gazebo qualification."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pickle
import signal
import subprocess
import sys
import time

from . import joint_boundary_observer as shared
from . import residual_joint_boundary as diagnostic
from . import residual_equal_gazebo as original
from . import residual_stop_transfer as timing
from .joint_reliability_candidate import ReliableBoundaryBackend, qos_record
from .core import load_config
from .residual_experiment import source_fingerprint
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import emit, latest, save, json_value, runtime_versions

ACTIONS = ('sim-joint-reliability-fixture', 'sim-joint-reliability-gazebo')
PARENT_ROOT = Path.home() / 'nino_research/sim_joint_boundary_v1'


def protocol():
    p = load_config(repo() / 'src/nino_rl/config/residual_joint_reliability_v1.yaml')
    f, q = p['fixture'], p['qualification']
    if (f['messages'], f['handshake_messages'], f['source_rate_hz'], f['reader_depth'], f['pause_after_messages'],
            f['pause_duration_s'], q['source_stop_order_s'], q['steps_per_rollout'], q['maximum_transitions']) != (
                1000, 1, 500, 100, 500, .1, [6., 8.], 140, 280):
        raise ValueError('Finite fixture/qualification budget changed')
    if (p['maximum_support_age_ns'], p['training_transitions'], p['optimizer_updates'], p['actor_inference_calls'],
            p['hardware_actions'], p['training_released'], p['minimum_effect_accepted']) != (40_000_000, 0, 0, 0, 0, False, None):
        raise ValueError('No learner/hardware release; preserve support gate')
    if diagnostic.fingerprint() != p['parent_fingerprint']:
        raise ValueError('Frozen diagnostic parent changed')
    return p


def fingerprint():
    paths = [Path(__file__), Path(__file__).with_name('joint_reliability_candidate.py'),
             Path(__file__).with_name('joint_reliability_worker.py'),
             repo() / 'src/nino_rl/config/residual_joint_reliability_v1.yaml',
             repo() / 'src/nino_rl/scripts/residual_joint_reliability.sh']
    return hashlib.sha256(json.dumps(dict(parent=diagnostic.fingerprint(), files={
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}), sort_keys=True).encode()).hexdigest()


def parent(check_runtime=True):
    out = diagnostic.validated_latest(PARENT_ROOT, check_runtime=check_runtime)
    if hashlib.sha256((out / 'manifest.json').read_bytes()).hexdigest() != protocol()['parent_manifest_sha256']:
        raise ValueError('Pinned diagnostic manifest changed')
    return out


def append(path, value):
    with path.open('a') as f:f.write(json.dumps(value, default=json_value, allow_nan=False) + '\n')


def records(path):
    if not path.exists():return []
    with path.open() as f:return [json.loads(l) for l in f]


class FixtureProcess(diagnostic.IndependentProcess):
    def __init__(self, directory, p, role):
        super().__init__(directory, p, p['fixture']['domain_id'])
        self.role = role

    def start(self, environment):
        self.directory.mkdir()
        self.log = (self.directory / 'worker.log').open('w')
        args = [sys.executable, '-u', '-m', 'nino_rl.joint_reliability_worker', '--output', str(self.directory),
                '--domain', str(self.domain), '--role', self.role]
        save(self.directory / 'argv.json', args)
        self.process = subprocess.Popen(args, env=environment, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        end = time.monotonic() + self.p['observer_start_deadline_s']
        while time.monotonic() < end:
            self.check()
            if (self.directory / 'ready.json').exists():
                ready = shared.read(self.directory / 'ready.json')
                if ready['role'] != self.role or ready['domain_id'] != self.domain or ready['motor_command_publishers']:
                    raise ValueError('Reader role/domain/authority mismatch')
                return ready
            time.sleep(.01)
        raise TimeoutError('Fixture reader readiness deadline')


def fixture_message(index, config):
    from sensor_msgs.msg import JointState
    message = JointState()
    stamp = config['handshake_stamp_ns'] if index < 0 else config['source_first_stamp_ns'] + index * 2_000_000
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(stamp, 10**9)
    message.header.frame_id = 'software_fixture_only'
    message.name = ['left_wheel_joint', 'right_wheel_joint']
    message.velocity = [float(index), -float(index)]
    return message


def fixture_metrics(source, readers, pauses, replies, config):
    expected = {r['source_stamp_ns']: r['payload_sha256'] for r in source if r['source_index'] >= 0}
    quality = {}
    for role, rows in readers.items():
        labeled = [r for r in rows if r['source_stamp_ns'] in expected]
        seen = {r['source_stamp_ns'] for r in labeled}
        mismatches = sum(r['payload_sha256'] != expected[r['source_stamp_ns']] for r in labeled)
        missing = sorted(set(expected) - seen)
        pause = pauses.get(role)
        pause_valid = bool(pause and .1 <= (pause['actual_end_ns'] - pause['actual_start_ns']) / 1e9 <= config['maximum_pause_duration_s']
            and 0 <= (pause['actual_start_ns'] - pause['planned_start_ns']) / 1e9 <= config['maximum_pause_start_lag_s'])
        pause_messages = sum(pause['actual_start_ns'] <= r['before_publish_ns'] < pause['actual_end_ns'] for r in source) if pause else 0
        pause_valid = pause_valid and config['minimum_source_messages_during_pause'] <= pause_messages <= config['maximum_source_messages_during_pause']
        source_stamps = [r['source_stamp_ns'] for r in rows]
        quality[role] = dict(source_order_valid=all(a <= b for a,b in zip(source_stamps, source_stamps[1:])), unknown_stamps=[s for s in source_stamps if s not in expected and s != config['handshake_stamp_ns']], received_total=len(rows), labeled_received=len(labeled), labeled_unique=len(seen), missing_source_stamps_ns=missing,
            duplicates=len(labeled) - len(seen), payload_mismatches=mismatches, pause=pause, pause_valid=pause_valid,
            endpoint=replies.get(role), endpoint_supported=bool(replies.get(role, {}).get('supported', False)),
            messages_published_during_pause=pause_messages)
    moving = [r for r in source if r['source_index'] >= 0]
    maximum_publish_s = max((r['after_publish_ns'] - r['before_publish_ns']) / 1e9 for r in source) if source else None
    maximum_interval_s = max((b['before_publish_ns'] - a['before_publish_ns']) / 1e9 for a, b in zip(moving, moving[1:])) if len(moving) > 1 else None
    source_order_valid = bool([r['source_index'] for r in source] == list(range(-1,1000)) and all(r['after_publish_ns'] >= r['before_publish_ns'] for r in source) and all(a['before_publish_ns'] <= b['before_publish_ns'] for a,b in zip(source,source[1:])))
    common_valid = bool(source_order_valid and len(source) == 1001 and len(expected) == 1000 and maximum_publish_s <= config['maximum_publish_call_s']
        and maximum_interval_s <= config['maximum_source_interval_s'] and all(q['pause_valid'] and q['endpoint_supported'] and q['source_order_valid'] and not q['unknown_stamps'] and not q['duplicates'] and not q['payload_mismatches'] for q in quality.values()) and len(quality) == 2)
    reliable, best = quality.get('reliable', {}), quality.get('best_effort', {})
    compatible = bool(common_valid and reliable.get('labeled_unique') == 1000 and reliable.get('labeled_received') == 1000
        and reliable.get('labeled_unique', 0) >= best.get('labeled_unique', 0))
    return dict(source_order_valid=source_order_valid, readers=quality, published_messages=len(source), labeled_source_messages=len(expected),
                maximum_publish_call_s=maximum_publish_s, maximum_source_interval_s=maximum_interval_s,
                fixture_valid=common_valid, candidate_compatible=compatible,
                reliability_benefit_in_this_fixture=bool(compatible and best['labeled_unique'] < 1000),
                general_reliability_benefit_verified=False)


def fixture(out):
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import JointState
    p = protocol();f = p['fixture']
    save(out / 'dependencies.json', diagnostic.parent_task.contract.guided.dependency_record(parent()))
    context = Context();rclpy.init(context=context, domain_id=f['domain_id'])
    node = Node('nino_joint_reliability_source', context=context)
    executor = SingleThreadedExecutor(context=context);executor.add_node(node)
    publisher = node.create_publisher(JointState, '/joint_states', QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE))
    environment = dict(os.environ, ROS_DOMAIN_ID=str(f['domain_id']), ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST', RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
    for key in ('FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):environment.pop(key, None)
    workers = {role: FixtureProcess(out / role, p, role) for role in ('best_effort', 'reliable')}
    source, replies, pauses, error, cleanup_errors = [], {}, {}, None, []
    def publish(index):
        message = fixture_message(index, f)
        before = time.monotonic_ns();publisher.publish(message);after = time.monotonic_ns()
        row = dict(source_index=index, before_publish_ns=before, after_publish_ns=after,
                   evidence='publish() call attempted/returned, not DDS delivery ACK', **shared.message_record(message, index + 2))
        source.append(row);append(out / 'source_publish.jsonl', row)
    try:
        for worker in workers.values():worker.start(environment)
        end = time.monotonic() + 5.
        while time.monotonic() < end:
            if publisher.get_subscription_count() == 2:break
            executor.spin_once(timeout_sec=.01)
        else:raise RuntimeError('Source did not discover both fixture readers')
        save(out / 'source_qos.json', dict(qos=qos_record(publisher.qos_profile), domain_id=f['domain_id'], motor_command_publishers=0))
        time.sleep(f['discovery_quiet_s'])
        publish(-1)
        requests = {role: worker.request(f['handshake_stamp_ns'] / 1e9) for role, worker in workers.items()}
        for role, worker in workers.items():
            reply = worker.response(requests[role])
            save(out / (role + '_handshake.json'), reply)
            if not reply['supported'] or reply['age_ns'] != 0:raise RuntimeError('Single handshake not received by both readers; no resend')
        start = time.monotonic_ns() + round(f['start_lead_s'] * 1e9)
        plan = dict(request_id=1, start_monotonic_ns=start + 10**9, duration_ns=100_000_000)
        save(out / 'pause_plan.json', plan)
        for worker in workers.values():shared.atomic(worker.directory / 'pause_plan.json', plan)
        for index in range(f['messages']):
            target = start + index * 2_000_000
            remaining = (target - time.monotonic_ns()) / 1e9
            if remaining > 0:time.sleep(remaining)
            for worker in workers.values():worker.check()
            publish(index)
            if (index + 1) % 250 == 0:emit(ACTIONS[0], f'ROS source {index + 1}/1000 · paired readers/pause', (index + 1) / 1000)
        target = (f['source_first_stamp_ns'] + 999 * 2_000_000) / 1e9
        requests = {role: worker.request(target) for role, worker in workers.items()}
        for role, worker in workers.items():
            replies[role] = worker.response(requests[role]);save(out / (role + '_endpoint.json'), replies[role])
        time.sleep(f['final_drain_quiet_s'])
    except Exception as exc:error = repr(exc)
    finally:
        for role, worker in workers.items():
            try:worker.close()
            except Exception as exc:cleanup_errors.append(role + ': ' + repr(exc))
        executor.shutdown(timeout_sec=2);node.destroy_node()
        if context.ok():context.shutdown()
    readers = {role: records(worker.directory / 'joint_records.jsonl') for role, worker in workers.items()}
    for role, worker in workers.items():
        if (worker.directory / 'pause_ended.json').exists():
            pauses[role] = dict(shared.read(worker.directory / 'pause_ended.json'), planned_start_ns=plan['start_monotonic_ns'])
    metrics = fixture_metrics(source, readers, pauses, replies, f)
    if error or cleanup_errors:metrics['candidate_compatible'] = False
    result = dict(protocol_id=p['protocol_id'], **metrics, error=error, cleanup_errors=cleanup_errors,
        training_transitions=0, optimizer_updates=0, actor_inference_calls=0, gazebo_launches=0, hardware_actions=0,
        training_released=False, root_cause_of_old_failure='unknown', source_counter_scope='attempted publication and per-reader reception; no middleware delivery ACK',
        conclusion='Software compatibility/fault-recovery fixture only; no old-failure root-cause or training-readiness claim')
    save(out / 'fixture_result.json', result)
    return result


def qualification_rollout(out, stop, world):
    import numpy as np
    from stable_baselines3.common.buffers import ReplayBuffer
    out.mkdir();p = protocol()
    c, g, task, condition = original.contract.configuration(stop)
    c['purpose'] = p['protocol_id'];c['backend']['scenario_id'] = 'clear_box_reliable_joint_candidate_v1'
    task['protocol_id'] = p['protocol_id']
    save(out / 'configuration.json', dict(config=c, guidance=g, task=task, condition=condition))
    independent = diagnostic.IndependentProcess(out / 'independent', p)
    backend = ReliableBoundaryBackend(c, out / 'backend', world, g, task, condition, independent)
    env = original.contract.environment(c, backend, task, condition)
    replay = ReplayBuffer(160, env.observation_space, env.action_space, device='cpu', handle_timeout_termination=True)
    rows, epoch, error, cleanup_errors = [], None, None, []
    abi = original.contract.identity()['abi_sha256']
    try:
        independent.start(backend.environment)
        obs, info = env.reset(seed=701);save(out / 'reset.json', info)
        graph = shared.graph(backend.node);save(out / 'primary_graph.json', graph)
        if len(graph) != 1 or graph[0]['qos']['reliability'] != 1:raise ValueError('Expected one RELIABLE joint publisher')
        backend.phase = 'qualification'
        for step in range(140):
            backend.control_tick = step
            proposed = np.zeros(1, np.float32)
            nxt, reward, term, trunc, info = env.step(proposed)
            row = dict(step=step, reward=reward, terminated=term, truncated=trunc, done=bool(term or trunc), **info,
                       qualification_condition=dict(arm='B0', source_stop_s=stop))
            row['TimeLimit.truncated'] = bool(trunc and not term)
            append(out / 'trace.jsonl', row)
            epoch = epoch if epoch is not None else row['sensor_clock_s'] - row['task']['elapsed_s']
            original.verify_transition(row, rows[-1] if rows else None, epoch, abi)
            # Same inherited support/task/path/estimator gate, no controller change.
            diagnostic.parent_task.feasibility(row)
            replay.add(obs, nxt, proposed, np.array([reward]), np.array([term or trunc]), [row])
            rows.append(row);obs = nxt
            if (step + 1) % 35 == 0:emit(ACTIONS[1], f'B0 stop{stop}s {step + 1}/140')
            if term or trunc:break
    except Exception as exc:error = repr(exc)
    finally:
        try:env.close()
        except Exception as exc:cleanup_errors.append('backend: ' + repr(exc))
        try:independent.close()
        except Exception as exc:cleanup_errors.append('observer: ' + repr(exc))
    replay_check = original.contract.audit_replay(replay, rows) if rows else dict(rows_checked=0, scope='No completed transition')
    with (out / 'diagnostic_replay_not_training.pkl').open('wb') as f:pickle.dump(replay, f)
    summary = original.baseline.summarize(rows, out) if rows else {}
    stamp_diagnostic = timing.timestamp_diagnostic(out, rows) if len(rows) == 140 else dict(valid=False, reason='Incomplete rollout')
    result = dict(summary, source_stop_s=stop, error=error, cleanup_errors=cleanup_errors, complete_steps=len(rows),
        replay_rows_checked=replay_check['rows_checked'], timestamp_diagnostic=stamp_diagnostic,
        maximum_native_boundary_support_age_s=max(max(r['source_lags_s'].values()) for r in rows) if rows else None,
        maximum_primary_joint_age_ms=max((r['primary_after']['age_ns']/1e6 for r in backend.boundaries if r['primary_after']['supported']), default=None),
        maximum_independent_joint_age_ms=max((r['independent']['age_ns']/1e6 for r in backend.boundaries if r['independent'] and r['independent']['supported']), default=None),
        retained_trace_rows=len(records(out / 'trace.jsonl')), feedback_checks=len(backend.boundaries), all_joint_paths_supported=bool(backend.boundaries and all(r['classification'] == 'both_joint_paths_supported' for r in backend.boundaries)),
        training_transitions=0, optimizer_updates=0, actor_inference_calls=0, hardware_actions=0)
    result['qualification_pass'] = bool(len(rows) == 140 and summary.get('functional_proposal_pass') and stamp_diagnostic['valid']
        and result['all_joint_paths_supported'] and not error and not cleanup_errors)
    save(out / 'summary.json', result)
    return result


def qualification(out, root):
    prerequisite = validated_latest(root, ACTIONS[0])
    if not shared.read(prerequisite / 'fixture_result.json')['candidate_compatible']:
        raise ValueError('Fixture no-go/unknown; no qualification launch released')
    save(out / 'dependencies.json', diagnostic.parent_task.contract.guided.dependency_record(prerequisite))
    worlds = prepare_worlds(out);runs = []
    for i, stop in enumerate(protocol()['qualification']['source_stop_order_s']):
        emit(ACTIONS[1], f'Candidate B0 qualification {i + 1}/2 · stop{stop}s', i / 2)
        result = qualification_rollout(out / ('B0_stop' + str(int(stop))), stop, worlds['clear_box'])
        runs.append(result);save(out / 'qualification_progress.json', runs)
        if not result['qualification_pass']:break
    result = dict(protocol_id=protocol()['protocol_id'], runs=runs, qualification_pass=len(runs) == 2 and all(r['qualification_pass'] for r in runs),
        evaluation_transitions=sum(r['complete_steps'] for r in runs), launches=len(runs), remaining_slots_closed=True,
        training_transitions=0, optimizer_updates=0, actor_inference_calls=0, hardware_actions=0, training_released=False,
        benefit_verified=False, minimum_effect_accepted=None, root_cause_of_old_failure='unknown',
        conclusion='RELIABLE joint observer B0 functional qualification only; no optimization-load readiness or learned benefit certification')
    save(out / 'qualification_result.json', result)
    return result


def validated_latest(root, action, check_runtime=True):
    out = latest(root, action, check_runtime=check_runtime)
    if shared.read(out / 'manifest.json').get('joint_reliability_fingerprint') != fingerprint():
        raise ValueError('Candidate scientific source changed')
    upstream = parent(check_runtime) if action == ACTIONS[0] else validated_latest(root, ACTIONS[0], check_runtime)
    if shared.read(out / 'dependencies.json') != diagnostic.parent_task.contract.guided.dependency_record(upstream):
        raise ValueError('Candidate upstream artifact changed')
    return out


def run(root, action):
    root = Path(root).expanduser().resolve();root.mkdir(parents=True, exist_ok=True)
    shared_lock = Path.home() / 'nino_research/.factory_sim.lock';shared_lock.parent.mkdir(parents=True, exist_ok=True)
    with shared_lock.open('a') as resource, (root / '.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB);fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = shared.read(root / 'state.json') if (root / 'state.json').exists() else dict(schema_version=1, latest={}, runs=[])
        if any(r['action'] == action for r in state['runs']):raise ValueError('Candidate stage already consumed; no retry')
        p = protocol();parent()
        if action == ACTIONS[1]:
            prerequisite = validated_latest(root, ACTIONS[0])
            if not shared.read(prerequisite / 'fixture_result.json')['candidate_compatible']:
                raise ValueError('Fixture did not pass; no physics qualification budget')
        out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + action);out.mkdir()
        state['runs'].append(dict(action=action, path=out.name, status='running', error=None));save(root / 'state.json', state)
        save(out / 'protocol.json', p)
        current, started, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame):raise TimeoutError('Finite reliability candidate stage deadline')
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(p['fixture' if action == ACTIONS[0] else 'qualification']['wall_deadline_s'])
        try:
            result = fixture(out) if action == ACTIONS[0] else qualification(out, root)
            if fingerprint() != current:raise ValueError('Candidate sources changed during stage')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed';error = str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM, previous)
            save(out / 'job.json', dict(action=action, status=status, error=error, wall_s=time.monotonic() - started, hardware_actions=0))
            save(out / 'manifest.json', dict(action=action, status=status, joint_reliability_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)): hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file() and f.name != 'manifest.json'}))
            state['runs'][-1].update(status=status, error=error)
            if status == 'completed':state['latest'][action] = out.name
            save(root / 'state.json', state)
            emit(action, status, 1. if status == 'completed' else None, directory=str(out), result=result, error=error)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('action', choices=ACTIONS);p.add_argument('--output', required=True, type=Path)
    a = p.parse_args(argv)
    try:run(a.output, a.action)
    except (Exception, KeyboardInterrupt) as exc:
        print('Joint reliability candidate failed/retained:', exc, flush=True);return 1
    return 0


if __name__ == '__main__':raise SystemExit(main())
