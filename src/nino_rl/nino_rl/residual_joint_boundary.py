"""Bounded zero-only dual-process joint diagnostic; no learner or hardware."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from . import residual_common_td3 as parent_task
from . import residual_guided_baseline as baseline
from . import joint_boundary_observer as observer
from .core import load_config
from .residual_experiment import source_fingerprint
from .residual_factory_workflow import repo
from .residual_sim_pilot import prepare_worlds
from .residual_workflow import emit, latest, runtime_versions, save

ACTION = 'sim-joint-boundary'
PARENT_ROOT = Path.home() / 'nino_research/sim_common_td3_v1'


def protocol():
    p = load_config(repo() / 'src/nino_rl/config/residual_joint_boundary_v1.yaml')
    if (p['launches_maximum'], p['zero_ticks_per_launch'], p['maximum_complete_control_ticks'],
            p['control_interval_s'], p['physics_chunk_steps'], p['maximum_support_age_ns'],
            p['feedback_deadline_s'], p['training_transitions'], p['optimizer_updates'],
            p['actor_inference_calls'], p['hardware_actions'], p['forward_reference'],
            p['training_released'], p['upstream_publish_counter_available']) != (
                2, 100, 200, .1, 50, 40_000_000, 5., 0, 0, 0, 0, False, False, False):
        raise ValueError('Bounded zero-only diagnostic contract changed')
    if p['scenario'] != 'clear_box' or parent_task.fingerprint() != p['parent_fingerprint']:
        raise ValueError('Scientific parent/config changed')
    return p


def fingerprint():
    paths = [Path(__file__), Path(observer.__file__), repo() / 'src/nino_rl/config/residual_joint_boundary_v1.yaml',
             repo() / 'src/nino_rl/scripts/residual_joint_boundary.sh']
    return hashlib.sha256(json.dumps(dict(parent=parent_task.fingerprint(), files={
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}), sort_keys=True).encode()).hexdigest()


def parent():
    p = protocol()
    out = PARENT_ROOT / p['parent_artifact']
    manifest = observer.read(out / 'manifest.json')
    if hashlib.sha256((out / 'manifest.json').read_bytes()).hexdigest() != p['parent_manifest_sha256']:
        raise ValueError('Sealed partial training manifest changed')
    if manifest['status'] != 'failed' or manifest['common_td3_fingerprint'] != p['parent_fingerprint']:
        raise ValueError('Wrong failed parent')
    for name, value in manifest['files'].items():
        path = (out / name).resolve()
        if not path.is_relative_to(out.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != value:
            raise ValueError('Sealed partial training file changed: ' + name)
    return out


def configuration():
    c, g, task, condition = parent_task.contract.configuration(6.)
    # New diagnostic identity; no actor/environment/reward, no source forward.
    # All physics, PI, geometry, estimation and instrument subscriptions retained.
    c['purpose'] = protocol()['protocol_id']
    c['backend'].update(scenario_id='clear_box_zero_joint_diagnostic_v1', command_until_s=0., max_episodes=1, horizon_s=10.)
    c['task'].update(command_until_s=0., horizon_s=10.)
    task.update(protocol_id=protocol()['protocol_id'], command_until_s=0., horizon_s=10.)
    return c, g, task, condition


def classify(primary_ok, independent_ok, primary_error=None):
    if primary_ok and independent_ok:
        return 'both_joint_paths_supported' if primary_error is None else 'other_channel_or_wait_failure'
    if not primary_ok and independent_ok:
        return 'primary_path_missing_independent_supported'
    if primary_ok and not independent_ok:
        return 'independent_path_missing_primary_supported'
    return 'both_joint_paths_missing_source_or_shared_delivery_unknown'


def append(path, row):
    with path.open('a') as f:
        f.write(json.dumps(row, allow_nan=False) + '\n')


class IndependentProcess:
    def __init__(self, directory, config, domain=129):
        self.directory, self.p, self.domain = Path(directory), config, domain
        self.process = self.log = None
        self.sequence = 0

    def start(self, environment):
        self.directory.mkdir()
        self.log = (self.directory / 'worker.log').open('w')
        args = [sys.executable, '-u', '-m', 'nino_rl.joint_boundary_observer', '--output', str(self.directory), '--domain', str(self.domain)]
        save(self.directory / 'argv.json', args)
        self.process = subprocess.Popen(args, env=environment, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + self.p['observer_start_deadline_s']
        while time.monotonic() < deadline:
            self.check()
            if (self.directory / 'ready.json').exists():
                ready = observer.read(self.directory / 'ready.json')
                if ready['domain_id'] != self.domain or ready['motor_command_publishers']:
                    raise ValueError('Independent observer domain/authority mismatch')
                return ready
            time.sleep(.01)
        raise TimeoutError('Independent observer readiness deadline; no launch')

    def check(self):
        if self.process is not None and self.process.poll() is not None:
            raise RuntimeError('Independent observer exited; retain worker.log')

    def request(self, target):
        self.check()
        self.sequence += 1
        now = time.monotonic_ns()
        request = dict(request_id=self.sequence, target_stamp_ns=round(target * 10**9),
            request_monotonic_ns=now, deadline_monotonic_ns=now + round(self.p['feedback_deadline_s'] * 10**9),
            maximum_age_ns=self.p['maximum_support_age_ns'])
        observer.atomic(self.directory / 'snapshot_request.json', request)
        return request

    def response(self, request):
        end = request['deadline_monotonic_ns'] + round(self.p['observer_ipc_grace_s'] * 10**9)
        while time.monotonic_ns() < end:
            self.check()
            path = self.directory / 'snapshot_response.json'
            if path.exists():
                reply = observer.read(path)
                if reply['request_id'] == request['request_id']:
                    if reply['target_stamp_ns'] != request['target_stamp_ns']:
                        raise ValueError('Observer snapshot target mismatch')
                    return reply
            time.sleep(.002)
        raise TimeoutError('Independent observer snapshot ACK missing')

    def close(self):
        if self.process is None:
            if self.log:self.log.close()
            return
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGINT)
            try:self.process.wait(timeout=5.)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:self.process.wait(timeout=2.)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=2.)
        code = self.process.returncode
        self.log.close()
        save(self.directory / 'process_exit.json', dict(returncode=code, shutdown_ack=(self.directory / 'closed.json').exists()))
        if code or not (self.directory / 'closed.json').exists():
            raise RuntimeError('Independent observer shutdown did not close cleanly')


class BoundaryBackend(baseline.GuidedBackend):
    def __init__(self, c, directory, world, g, task, condition, independent):
        super().__init__(c, directory, world, g, task, condition)
        self.independent = independent
        self.audit_dir = Path(directory).parent
        self.primary_records = (self.audit_dir / 'primary_joint_records.jsonl').open('w', buffering=65536)
        self.primary_last, self.primary_count = None, 0
        self.phase, self.control_tick, self.wait_count = 'setup', None, 0
        self.boundaries = []

    def _receive(self, key, message):
        if key == 'wheel':
            try:
                with self.lock:
                    self.primary_count += 1
                    self.primary_last = observer.message_record(message, self.primary_count)
                    self.primary_records.write(json.dumps(self.primary_last, allow_nan=False) + '\n')
            except Exception as exc:
                with self.lock:self.error = repr(exc)
                return
        super()._receive(key, message)

    def _check(self):
        super()._check()
        self.independent.check()

    def _wait_feedback(self, target):
        request = self.independent.request(target)
        with self.lock:
            before = dict(count=self.primary_count, last=self.primary_last)
        result = reply = None
        error = None
        try:
            result = super()._wait_feedback(target)
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            try:
                reply = self.independent.response(request)
            finally:
                with self.lock:
                    last, count = self.primary_last, self.primary_count
                    processed_stamp = self.messages.get('wheel', {}).get('stamp_s')
                primary_ok = observer.endpoint_supported(last, request['target_stamp_ns'])
                row = dict(check_index=self.wait_count, phase=self.phase, control_tick=self.control_tick,
                    target_stamp_ns=request['target_stamp_ns'], request=request, primary_before=before,
                    primary_after=dict(count=count, last=last, processed_wheel_stamp_s=processed_stamp,
                        supported=primary_ok, age_ns=None if last is None else request['target_stamp_ns'] - last['source_stamp_ns']),
                    primary_wait_error=error, source_lags_s=result, independent=reply,
                    classification=classify(primary_ok, reply['supported'], error) if reply is not None else 'observer_ipc_unknown',
                    comparison_monotonic_ns=time.monotonic_ns(), physics_retries=0)
                self.wait_count += 1
                self.boundaries.append(row)
                append(self.audit_dir / 'boundary_checks.jsonl', row)
                self.primary_records.flush()
            if reply is None or not reply['supported']:
                if error is None:
                    raise RuntimeError('Independent joint support/ACK failed; remaining slots closed')
        return result

    def close(self):
        try:super().close()
        finally:
            self.primary_records.flush()
            self.primary_records.close()


def rollout(out, world, index):
    out.mkdir()
    p = protocol()
    c, g, task, condition = configuration()
    save(out / 'configuration.json', dict(config=c, guidance=g, task=task, condition=condition))
    independent = IndependentProcess(out / 'independent', p)
    backend = BoundaryBackend(c, out / 'backend', world, g, task, condition, independent)
    ticks, error, cleanup_error, reset = [], None, None, None
    try:
        independent.start(backend.environment)
        view, reset = backend.reset(seed=701)
        save(out / 'reset.json', reset)
        endpoints = observer.graph(backend.node)
        save(out / 'primary_graph.json', endpoints)
        if len(endpoints) != 1 or endpoints[0]['node_name'] != 'joint_state_broadcaster':
            raise ValueError('Expected one identified joint_state_broadcaster publisher')
        backend.phase = 'zero_control'
        for tick in range(p['zero_ticks_per_launch']):
            backend.control_tick = tick
            view, labels, term, trunc, info = backend.advance_reference(0., 0., .1)
            drive = info['drive_diagnostics']
            if any(abs(drive[k]) > 1e-12 for k in ('requested_linear_m_s', 'requested_yaw_rad_s', 'executed_linear_m_s', 'executed_yaw_rad_s')):
                raise ValueError('Zero-only reference contract violated')
            if term or info['guidance_audit']['fault'] or any(view['baseline']):
                raise ValueError('Zero diagnostic physical/guidance/source failure')
            if trunc != (tick == 99):
                raise ValueError('Diagnostic horizon drift')
            row = dict(tick=tick, requested_reference=[0., 0.], sensor_clock_s=info['sensor_clock_s'],
                source_lags_s=info['source_lags_s'], drive_diagnostics=drive, truth_used_for_control=False,
                estimator_audit=info['estimator_audit'])
            ticks.append(row)
            append(out / 'zero_trace.jsonl', row)
            if (tick + 1) % 25 == 0:
                emit(ACTION, f'Zero launch{index + 1}/2 · {tick + 1}/100ticks', (index * 100 + tick + 1) / 200)
    except Exception as exc:
        error = repr(exc)
    finally:
        try:backend.close()
        except Exception as exc:cleanup_error = repr(exc)
        try:independent.close()
        except Exception as exc:cleanup_error = repr(exc) if cleanup_error is None else cleanup_error + '; ' + repr(exc)
        result = dict(launch=index, complete_zero_ticks=len(ticks), error=error, cleanup_error=cleanup_error,
            reset_completed=reset is not None, feedback_checks=len(backend.boundaries),
            boundary_classifications=sorted(set(r['classification'] for r in backend.boundaries)),
            all_support_pass=bool(backend.boundaries and all(r['classification'] == 'both_joint_paths_supported' for r in backend.boundaries)),
            training_transitions=0, actor_inference_calls=0, optimizer_updates=0, hardware_actions=0,
            instrumentation_changes='additional primary CDR hash log + independent ROS process; no optimization load',
            upstream_publish_counter_available=False, root_cause='unknown')
        result['collection_complete'] = bool(len(ticks) == 100 and error is None and cleanup_error is None and result['all_support_pass'])
        save(out / 'summary.json', result)
    return result


def execute(out):
    upstream = parent()
    save(out / 'dependencies.json', parent_task.contract.guided.dependency_record(upstream))
    worlds = prepare_worlds(out)
    runs = []
    for i in range(protocol()['launches_maximum']):
        emit(ACTION, f'Zero-only diagnostic launch{i + 1}/2; no learner')
        run = rollout(out / f'launch_{i}', worlds['clear_box'], i)
        runs.append(run)
        save(out / 'diagnostic_progress.json', runs)
        if not run['collection_complete']:
            break
    complete = len(runs) == 2 and all(r['collection_complete'] for r in runs)
    result = dict(protocol_id=protocol()['protocol_id'], runs=runs, launches=len(runs), launches_maximum=2,
        complete_zero_control_ticks=sum(r['complete_zero_ticks'] for r in runs), maximum_complete_control_ticks=200,
        collection_complete=complete, failure_reproduced=any(r['error'] for r in runs),
        outcome='not_reproduced_unknown' if complete else 'stopped_on_failure_review_paths',
        root_cause='unknown', upstream_publish_counter_available=False, training_released=False,
        training_transitions=0, optimizer_updates=0, actor_inference_calls=0, hardware_actions=0,
        remaining_slots_closed=True, partial_td3_batch_reopened=False,
        conclusion='Zero-only diagnostic; clean runs do not establish loss-free acquisition under training load or release more TD3 budget')
    save(out / 'diagnostic_result.json', result)
    return result


def validated_latest(root, check_runtime=True):
    out = latest(root, ACTION, check_runtime=check_runtime)
    if observer.read(out / 'manifest.json').get('joint_boundary_fingerprint') != fingerprint():
        raise ValueError('Diagnostic scientific source changed')
    if observer.read(out / 'dependencies.json') != parent_task.contract.guided.dependency_record(parent()):
        raise ValueError('Sealed partial TD3 parent changed')
    return out


def run(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    shared = Path.home() / 'nino_research/.factory_sim.lock'
    shared.parent.mkdir(parents=True, exist_ok=True)
    with shared.open('a') as resource, (root / '.job.lock').open('a') as lock:
        fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / 'state.json').exists():raise ValueError('Joint diagnostic already consumed; no retry')
        p = protocol()
        parent()
        out = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + ACTION)
        out.mkdir()
        ledger = dict(schema_version=1, latest={}, runs=[dict(action=ACTION, path=out.name, status='running', error=None)])
        save(root / 'state.json', ledger)
        save(out / 'protocol.json', p)
        current, started, status, error, result = fingerprint(), time.monotonic(), 'running', None, None
        def timeout(signum, frame):raise TimeoutError('Joint diagnostic finite wall deadline')
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(p['wall_deadline_s'])
        try:
            result = execute(out)
            if fingerprint() != current:raise ValueError('Scientific source changed during diagnostic')
            status = 'completed'
        except BaseException as exc:
            status = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
            error = str(exc)
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            save(out / 'job.json', dict(action=ACTION, status=status, error=error, wall_s=time.monotonic() - started, hardware_actions=0))
            save(out / 'manifest.json', dict(action=ACTION, status=status, joint_boundary_fingerprint=current,
                source_fingerprint=source_fingerprint(), runtime=runtime_versions(), hardware_actions=0,
                files={str(f.relative_to(out)): hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file() and f.name != 'manifest.json'}))
            ledger['runs'][0].update(status=status, error=error)
            if status == 'completed':ledger['latest'][ACTION] = out.name
            save(root / 'state.json', ledger)
            emit(ACTION, status, 1. if status == 'completed' else None, directory=str(out), result=result, error=error)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:run(args.output)
    except (Exception, KeyboardInterrupt) as exc:
        print('Joint diagnostic failed/retained:', exc, flush=True)
        return 1
    return 0


if __name__ == '__main__':raise SystemExit(main())
