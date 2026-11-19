"""Bounded clean-floor Gazebo replay of a held-out real ROS reference.

Uses the retained Recovery backend and its source/clock/ownership gates.
Does not change physics parameters, load a TD3 actor or contact real hardware.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import signal
import time

import numpy as np

from .recovery_runner import require_bank, runtime_configuration, sources
from .recovery_startup import RecoveryBackend
from .factory_velocity_backend import FactoryVelocityBackend, simulation_seconds
from .reliable_episode import EpisodeLifecycle
from .residual_workflow import save
from .unknown_step_runner import append, raw_qc


class RealReferenceBackend(RecoveryBackend):
    """Post-settling wheel response. No spawn-to-task pose reconstruction."""
    def view(self):
        view = FactoryVelocityBackend.view(self)
        if not self.active:
            return view
        now = simulation_seconds(self.time)
        if self.cached_view is not None and self.cached_view['stamp_s'] == now:
            return deepcopy(self.cached_view)
        with self.lock:
            if self.bootstrap_report is None:
                self.bootstrap_report = dict(contract_id='post_settle_wheel_response_v1',
                    task_epoch_s=now, spawn_to_task_pose_reconstructed=False,
                    estimator_used_for_command_or_score=False,
                    startup_journal_preserved=True,
                    source_guard_scope='post_settle_task_epoch_onward',
                    startup_gap_changes_training_qualification=False)
                save(self.episode_dir/'startup_estimator.json', self.bootstrap_report)
            records = self.estimator.advance(now)
            estimate = self.estimator.estimate()
            reference = tuple(self.request)
        for record in records:
            self._store('estimator_update', record['stamp_s'], record)
        view.update(baseline=reference, clock_id=self.gconf['clock_id'], estimator_audit=estimate,
                    guidance_audit=dict(source='external_real_reference_replay', follower_active=False,
                                        estimated_pose_used=False))
        view['features'].update(baseline_v_m_s=reference[0], baseline_yaw_rad_s=reference[1])
        self.cached_view = deepcopy(view)
        return view


def validate_schedule(schedule):
    if (schedule.get('schema_version') != 1
            or schedule.get('purpose') != 'matched_real_reference_gazebo_diagnostic'
            or schedule.get('interval_s') != .1
            or schedule.get('physical_calibration_accepted') is not False
            or schedule.get('td3_replay_eligible') is not False):
        raise ValueError('Unsupported real-reference diagnostic contract')
    rows = schedule['rows']
    if not 20 <= len(rows) <= 350:
        raise ValueError('Finite replay must have 20..350 references')
    for i, row in enumerate(rows):
        values = [row['time_s'], row['comparison_time_s'], row['v_m_s'], row['yaw_rad_s'],
                  row['real_feedback_age_s'], *row['reported_wheel_rad_s']]
        if (not np.isfinite(values).all() or len(row['reported_wheel_rad_s']) != 2
                or abs(row['time_s']-i*.1) > 1e-8
                or abs(row['comparison_time_s']-(i+1)*.1) > 1e-8
                or not 0 <= row['real_feedback_age_s'] <= .15
                or not 0 <= row['v_m_s'] <= .4 or abs(row['yaw_rad_s']) > 1.):
            raise ValueError('Invalid, stale or out-of-envelope reference')
    return rows


def compare(rows):
    usable = [row for row in rows if row['time_s'] >= 1.]
    if not usable:
        raise ValueError('Missing post-startup comparison')
    residual = np.array([np.asarray(row['sim_reported_wheel_rad_s'])
                         -row['real_reported_wheel_rad_s'] for row in usable])
    return dict(comparison_samples=len(usable), initial_second_excluded=True,
                wheel_rmse_rad_s=np.sqrt(np.mean(residual**2, axis=0)).tolist(),
                wheel_mean_error_rad_s=np.mean(residual, axis=0).tolist(),
                scope='Nominal Gazebo PI torque backend vs real velocity backend reported wheels. '
                      'Different nominal wheel radii remain explicit. No body/slip or obstacle claim.')


def run(schedule_path, bank_path, output):
    schedule_path, output = Path(schedule_path), Path(output)
    schedule = json.loads(schedule_path.read_text())
    rows = validate_schedule(schedule)
    bank = require_bank(Path(bank_path))
    layout = next(r for r in bank['layouts'] if (r['family'], r['stage'], r['split'])
                  == ('clean', 0, 'development'))
    c, guidance, task, condition = runtime_configuration(bank['config'], layout)
    c['purpose'] = 'real_velocity_matched_replay_v1'
    c['backend']['startup_initialization'] = 'post_settle_wheel_response_v1'
    identity = dict(recovery_sources=sources(), runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    replay_sha256=hashlib.sha256(schedule_path.read_bytes()).hexdigest())
    if shutil.disk_usage(output.parent).free < 2*1024**3:
        raise ValueError('Less than 2 GiB disk reserve')
    lock_path = Path.home()/'nino_research/.factory_sim.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir(parents=True, exist_ok=False)
        save(output/'schedule.json', schedule)
        save(output/'identity.json', identity)
        save(output/'configuration.json', dict(controller=c, guidance_used=False,
                                               inherited_protocol=task, condition=condition))
        protocol = dict(training_episodes_per_seed_maximum=1, observer_start_deadline_s=15.,
                        feedback_deadline_s=5., observer_ipc_grace_s=1., maximum_support_age_ns=40_000_000)
        backend = EpisodeLifecycle(c, output/'episodes', layout['world'], guidance, task, condition, protocol,
            backend_factory=lambda *args: RealReferenceBackend(*args, expected_envelope=bank['envelope']))
        error, result, trace = None, None, []
        started = time.monotonic()
        previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('Replay wall budget')))
        signal.alarm(600)
        try:
            _, reset = backend.reset(seed=layout['seed'])
            reset_record = dict(reset, physical_sample=asdict(reset['physical_sample']))
            save(output/'episode_0_reset.json', dict(reset=reset_record, private_layout=layout))
            for row in rows:
                _, _, term, trunc, info = backend.advance_reference(row['v_m_s'], row['yaw_rad_s'], .1)
                physical = asdict(info['physical_sample'])
                entry = dict(time_s=row['comparison_time_s'], episode=0,
                    physical_sample=physical, real_reported_wheel_rad_s=row['reported_wheel_rad_s'],
                    sim_reported_wheel_rad_s=list(physical['wheel_rad_s']),
                    final_ros_reference=[row['v_m_s'], row['yaw_rad_s']],
                    drive_diagnostics=info['drive_diagnostics'], source_admission=info['source_admission'])
                append(output/'environment_trace.jsonl', entry)
                trace.append(entry)
                if term or trunc:
                    raise ValueError('Replay interrupted by physical/horizon backend gate')
            result = compare(trace)
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            try:
                backend.close()
            except BaseException as exc:
                error = error or repr(exc)
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            qc = raw_qc(output)
            if not qc.get('valid'):
                error = error or 'Raw source QC failed'
            if sources() != identity['recovery_sources']:
                error = error or 'Source changed during replay'
            save(output/'qc.json', qc)
            if result is not None:
                save(output/'result.json', dict(result, source_qc_valid=qc.get('valid'),
                    sim_geometry=c['nominal_geometry'], real_geometry=schedule['real_geometry'],
                    physical_calibration_accepted=False, learned_benefit_verified=False))
            save(output/'job.json', dict(status='failed' if error else 'completed', error=error,
                wall_s=time.monotonic()-started, completed_steps=len(trace), hardware_actions=0,
                actor_loaded=False, automatic_retries=0))
            save(output/'manifest.json', {str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in output.rglob('*') if p.is_file() and p.name != 'manifest.json'})
        if error:
            raise RuntimeError(error)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--bank', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.schedule, args.bank, args.output), indent=2))


if __name__ == '__main__':
    main()
