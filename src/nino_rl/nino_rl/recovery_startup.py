from copy import deepcopy
import json
import math
import time

from .causal_planar_estimator import CausalPlanarEstimator
from .unknown_step_gazebo import UnknownStepBackend
from .residual_workflow import save
from .recovery_sim_runtime import configure_dependency, verify_loaded_dependency

INITIALIZATION_ID = 'verified_reanchor_plus_startup_wheel_gyro_v2'


def bootstrap_estimator(rows, *, now_s, receipt_cutoff_s, initial_pose, geometry,
                        estimator_settings, epoch, maximum_prefix_s=.04, source_epoch_s=0.):
    if (not all(math.isfinite(v) for v in (now_s, receipt_cutoff_s, maximum_prefix_s, source_epoch_s))
            or maximum_prefix_s <= 0 or not 0 <= source_epoch_s <= now_s):
        raise ValueError('Finite bootstrap clock and prefix bound required')
    channels = {'imu': [], 'wheel': []}
    anchor_wheel = None
    for row in rows:
        key = row['channel']
        if key not in channels:
            continue
        source, receipt = row['stamp_s'], row['receipt_monotonic_s']
        if not all(type(v) in (float,int) and math.isfinite(v) for v in (source,receipt)):
            raise ValueError('Invalid startup source or receipt clock')
        if source > now_s or receipt > receipt_cutoff_s:
            continue
        if source < source_epoch_s:
            if key == 'wheel' and (anchor_wheel is None or source > anchor_wheel['stamp_s']):
                anchor_wheel = row
            continue
        if channels[key] and source <= channels[key][-1]['stamp_s']:
            raise ValueError('Startup source duplicate or reversal')
        channels[key].append(row)
    if any(len(v) < 2 for v in channels.values()) or sum(map(len,channels.values())) > 20000:
        raise ValueError('Incomplete or excessive startup sensor journal')
    first = channels['wheel'][0]['stamp_s']
    if not 0 <= first-source_epoch_s <= maximum_prefix_s:
        raise ValueError('Startup sensor prefix exceeds declared bound')
    initial_time = first
    if source_epoch_s > 0.:
        if first == source_epoch_s:
            anchor_wheel = channels['wheel'][0]
        if anchor_wheel is None or not 0 <= source_epoch_s-anchor_wheel['stamp_s'] <= maximum_prefix_s:
            raise ValueError('Physical reset epoch lacks causal wheel support')
        if anchor_wheel['stamp_s'] < first:
            channels['wheel'].insert(0, anchor_wheel)
        initial_time = source_epoch_s
    estimator = CausalPlanarEstimator(radius_l=geometry['radius_l'], radius_r=geometry['radius_r'],
                                      **estimator_settings)
    for key, records in channels.items():
        if (max(b['stamp_s']-a['stamp_s'] for a,b in zip(records,records[1:])) > estimator.maximum_gap_s+1e-9
                or now_s-records[-1]['stamp_s'] > estimator.maximum_gap_s+1e-9):
            raise ValueError('Startup source gap or tail exceeds bound: '+key)
    estimator.reset(stamp_s=initial_time, pose=initial_pose, epoch=epoch)
    for key in ('wheel','imu'):
        for row in channels[key]:
            values = [row['values'][2]] if key == 'imu' else row['values']
            estimator.push(key,row['stamp_s'],values,row['receipt_monotonic_s'])
    updates = estimator.advance(now_s)
    if not updates or now_s-estimator.time > estimator.maximum_gap_s+1e-9:
        raise ValueError('Startup integration lacks task-boundary support')
    estimator.initialization = INITIALIZATION_ID
    return estimator, dict(contract_id=INITIALIZATION_ID, source='wheel_imu_odometry',
        truth_input=False, source_epoch_s=source_epoch_s, first_wheel_stamp_s=first,
        unsupported_prefix_s=initial_time-source_epoch_s,
        initial_integration_stamp_s=initial_time,
        initial_wheel_support_stamp_s=channels['wheel'][0]['stamp_s'],
        maximum_prefix_s=maximum_prefix_s, decision_stamp_s=now_s,
        receipt_cutoff_monotonic_s=receipt_cutoff_s,
        counts={k:len(v) for k,v in channels.items()}, updates=len(updates),
        initial_declared_pose=list(initial_pose), task_epoch_estimate=estimator.estimate(),
        source_rule='wheel_source_at_or_before_gyro_already_received_before_first_task_decision')


class RetainedSourceGuard:
    channels = ('imu','wheel','truth','drive')

    def __init__(self, path, *, start_s, maximum_gap_s=.04, maximum_control_gap_s=None):
        self.path, self.start, self.gap = path, start_s, maximum_gap_s
        self.control_gap = maximum_control_gap_s
        self.maximum_control_dt = 0.
        self.offset, self.failed = 0, False
        self.last, self.maximum, self.counts = {}, {}, {}

    def admit(self, boundary_s):
        if self.failed:
            raise RuntimeError('Source guard is failed')
        try:
            with self.path.open() as stream:
                stream.seek(self.offset)
                for line in stream:
                    row = json.loads(line)
                    channel = row['channel']
                    if channel not in self.channels:
                        continue
                    t = row['stamp_s']
                    if type(t) not in (int,float) or not math.isfinite(t):
                        raise ValueError('Invalid retained source stamp')
                    if t < self.start-self.gap-1e-9:
                        continue
                    if channel == 'drive' and self.control_gap is not None:
                        values = row['values']
                        minimum, maximum = values['control_raw_dt_min_s'], values['control_raw_dt_max_s']
                        if (not all(math.isfinite(v) for v in (minimum,maximum))
                                or not 0 < minimum <= maximum <= self.control_gap+1e-9
                                or values['control_updates'] < 1
                                or any(values[k] != 0 for k in ('control_dt_invalid',
                                    'control_dt_fallbacks','control_dt_over_4ms','control_future_joint_updates'))):
                            raise ValueError('Retained PI control timing failed')
                        self.maximum_control_dt = max(self.maximum_control_dt,maximum)
                    if channel in self.last:
                        delta = t-self.last[channel]
                        if delta <= 0 or delta > self.gap+1e-9:
                            raise ValueError('Retained source order/gap failed: '+channel)
                        self.maximum[channel] = max(delta,self.maximum.get(channel,0.))
                    self.last[channel] = t
                    self.counts[channel] = self.counts.get(channel,0)+1
                self.offset = stream.tell()
            for channel in self.channels:
                if channel not in self.last or not -1e-8 <= boundary_s-self.last[channel] <= self.gap+1e-9:
                    raise ValueError('Retained source tail failed: '+channel)
            return dict(valid=True,boundary_s=boundary_s,counts=dict(self.counts),
                        maximum_source_gap_s=dict(self.maximum),last=dict(self.last),
                        maximum_control_dt_s=self.maximum_control_dt,
                        maximum_control_gap_s=self.control_gap)
        except BaseException:
            self.failed = True
            raise


class RecoveryBackend(UnknownStepBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simulation_runtime = self.config['backend']['simulation_runtime']
        self.environment = configure_dependency(self.environment, self.simulation_runtime)

    def reset(self, seed=None):
        self.startup_journal = []
        self.bootstrap_report = None
        view, info = super().reset(seed=seed)
        loaded = verify_loaded_dependency(self.launch, self.simulation_runtime,partition=self.partition)
        save(self.episode_dir/'simulation_runtime.json', loaded)
        self.flush_raw()
        self.source_guard = RetainedSourceGuard(self.episode_dir/'raw_samples.jsonl',
            start_s=info['physical_sample'].stamp_s,
            maximum_control_gap_s=self.config['backend']['simulation_scheduling']['maximum_control_gap_s'])
        support = self.source_guard.admit(view['stamp_s'])
        save(self.episode_dir/'source_admission.json',support)
        return view, dict(info, startup_bootstrap=self.bootstrap_report,
                          estimator_audit=deepcopy(view['estimator_audit']),source_admission=support,
                          simulation_runtime=loaded)

    def settle(self):
        super().settle()
        from .recovery_reset import reanchor
        self.reanchor_report = reanchor(self, self.config['backend']['initial_pose_xy_yaw'])
        with self.lock:
            self.startup_journal = deepcopy([r for r in self.raw if r['channel'] in ('imu','wheel')])

    def view(self):
        if self.active and self.bootstrap_report is None:
            with self.lock:
                self.estimator, self.bootstrap_report = bootstrap_estimator(self.startup_journal,
                    now_s=self.time, receipt_cutoff_s=time.monotonic(),
                    initial_pose=self.protocol['initial_pose_m_rad'],
                    geometry=self.config['nominal_geometry'], estimator_settings=self.protocol['estimator'],
                    epoch=self.estimator.epoch, source_epoch_s=self.reanchor_report['source_epoch_s'])
            save(self.episode_dir/'startup_estimator.json', self.bootstrap_report)
        return super().view()

    def advance_reference(self, *args):
        result = super().advance_reference(*args)
        try:
            support = self.source_guard.admit(result[0]['stamp_s'])
        except BaseException as exc:
            save(self.episode_dir/'source_admission.json',dict(valid=False,error=repr(exc)))
            raise
        save(self.episode_dir/'source_admission.json',support)
        result[-1]['source_admission'] = support
        return result
