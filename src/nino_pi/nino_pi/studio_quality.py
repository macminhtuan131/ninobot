"""Recompute raw integrity, sender/receiver clock drift, gap statistics, command-chain consistency, and 10 Hz causal readiness.

No automatic scientific promotion beyond Q2 without calibrated external body reference.
"""
import hashlib
import json
import math
import statistics
from pathlib import Path
from .bag_io import decoded, metadata, source_header

# Empirical Pi audit reference rates (for diagnostic comparison only; expected_hz remains None).
REFERENCE_NOMINAL_HZ = {
    '/imu/data': 47.13,
    '/motor_fb': 47.13,
    '/joint_states': 47.13,
    '/odom/unfiltered': 47.13,
    '/scan_raw': 6.95,
    '/motor_status': 9.96,
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_raw(raw):
    raw = Path(raw).resolve()
    hashes = json.loads((raw/'sha256.json').read_text())
    checked, errors = 0, []
    for name, value in hashes.items():
        if name in ('collector_source', 'audit_source'):
            continue  # provenance labels, not files; never compare them to today's source
        path = (raw/name).resolve()
        if raw not in path.parents or not path.is_file() or digest(path) != value:
            errors.append(name)
        checked += 1
    # New/unhashed raw files are also a discrepancy, including an interrupted WAL.
    extra = {str(p.relative_to(raw)) for p in raw.rglob('*') if p.is_file()} - set(hashes) - {'sha256.json'}
    errors += ['unhashed:'+name for name in sorted(extra)]
    return dict(checked=checked, mismatches=errors)


def _inspect_annotations(root):
    path = root / 'annotations.json'
    if not path.is_file():
        return dict(present=False, count=0, invalid_entries=0, texts=[])
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        return dict(present=True, count=0, invalid_entries=1, texts=[])
    invalid = 0
    texts = []
    last_mono = None
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get('text'), str) or not item['text'].strip():
            invalid += 1
            continue
        mono = item.get('receipt_monotonic_ns')
        if not isinstance(mono, int) or (last_mono is not None and mono < last_mono):
            invalid += 1
        else:
            last_mono = mono
        texts.append(item['text'].strip()[:120])
    return dict(present=True, count=len(data), invalid_entries=invalid, texts=texts[:20])


def inspect_session(session):
    root = Path(session).resolve()
    raw = root/'raw'
    result = dict(schema_version=1, rubric='nino_studio_qc_v1', verdict='FAIL', level='Q1',
                  scope='Raw integrity and observed clocks only; no body/slip/TD3 readiness claim',
                  checks=[], topics={}, feature_ready=False, td3_replay_eligible=False,
                  recommendations=[],
                  limitations=['Bag receipt is not actuator execution time.',
                      'No accepted expected rates/coverage or application effect thresholds supplied.',
                      'Encoder odometry is not independent body ground truth.',
                      'PASS for integrity does not release a trial, training or deployment.'])
    def check(name, verdict, detail):
        result['checks'].append(dict(name=name, verdict=verdict, detail=detail))
    try:
        hashes = verify_raw(raw)
        check('checksum', 'PASS' if hashes['checked'] and not hashes['mismatches'] else 'FAIL', hashes)
        manifest = json.loads((raw/'manifest.json').read_text())
        config = json.loads((raw/'collection_config.json').read_text())
        check('lifecycle', 'PASS' if manifest.get('status') == 'captured_not_calibrated' and manifest.get('issues') == [] else 'FAIL',
              dict(status=manifest.get('status'), reason=manifest.get('reason'), issues=manifest.get('issues')))
        meta = metadata(raw/'bag')
        stats = {}; events = {}; commands = {}; intervals = {}
        invalid = []
        bag_first_ns = None
        bag_last_ns = None
        topic_stamps = {'/imu/data': [], '/motor_fb': [], '/joint_states': [], '/odom/unfiltered': [], '/cmd_vel': []}
        for topic, typ, receipt, msg in decoded(raw/'bag'):
            if bag_first_ns is None or receipt < bag_first_ns:
                bag_first_ns = receipt
            if bag_last_ns is None or receipt > bag_last_ns:
                bag_last_ns = receipt
            if topic in topic_stamps:
                topic_stamps[topic].append(receipt)
            source, frame = source_header(msg)
            s = stats.setdefault(topic, dict(
                type=typ, count=0, source_count=0, receipt_backwards=0,
                source_backwards=0, source_duplicates=0, source_zero=0,
                max_receipt_gap_s=0., max_source_gap_s=0.,
                median_receipt_period_s=None, gaps_over_2x_median_period=0,
                reference_nominal_hz=REFERENCE_NOMINAL_HZ.get(topic),
                clock_offset_min_ms=None, clock_offset_max_ms=None, clock_drift_span_ms=None,
                first_receipt_ns=receipt, last_receipt_ns=None, first_source_ns=None, last_source_ns=None, frames=[]))
            s['count'] += 1
            values = []
            if typ == 'sensor_msgs/msg/Imu':
                values = [getattr(v, k) for v in (msg.linear_acceleration, msg.angular_velocity) for k in ('x', 'y', 'z')]
            elif typ == 'sensor_msgs/msg/JointState':
                values = list(msg.position) + list(msg.velocity) + list(msg.effort)
            elif typ == 'geometry_msgs/msg/Twist':
                values = [getattr(v, k) for v in (msg.linear, msg.angular) for k in ('x', 'y', 'z')]
            if any(not math.isfinite(v) for v in values) and topic not in invalid:
                invalid.append(topic)
            if typ == 'std_msgs/msg/UInt8' and topic == '/motor_status':
                counts = events.setdefault('firmware_status_raw_values', {})
                key = str(msg.data); counts[key] = counts.get(key, 0) + 1
            if typ == 'nav2_msgs/msg/CollisionMonitorState':
                counts = events.setdefault('collision_monitor_actions', {})
                key = str(msg.action_type) + ':' + msg.polygon_name; counts[key] = counts.get(key, 0) + 1
            if typ == 'geometry_msgs/msg/Twist':
                c = commands.setdefault(topic, dict(nonzero_samples=0, max_abs_v_m_s=0., max_abs_w_rad_s=0., clock='bag_receipt_not_execution'))
                if math.isfinite(msg.linear.x) and math.isfinite(msg.angular.z):
                    c['nonzero_samples'] += abs(msg.linear.x) > 1e-9 or abs(msg.angular.z) > 1e-9
                    c['max_abs_v_m_s'] = max(c['max_abs_v_m_s'], abs(msg.linear.x))
                    c['max_abs_w_rad_s'] = max(c['max_abs_w_rad_s'], abs(msg.angular.z))
            previous = s['last_receipt_ns']
            if previous is not None:
                s['receipt_backwards'] += receipt < previous
                dt_s = (receipt - previous) / 1e9
                s['max_receipt_gap_s'] = max(s['max_receipt_gap_s'], dt_s)
                if dt_s >= 0:
                    intervals.setdefault(topic, []).append(dt_s)
            s['last_receipt_ns'] = receipt
            if frame is not None and frame not in s['frames']:
                s['frames'].append(frame)
            if source is not None:
                s['source_count'] += 1
                s['source_zero'] += source == 0
                if source > 0:
                    offset_ms = (receipt - source) / 1e6
                    s['clock_offset_min_ms'] = offset_ms if s['clock_offset_min_ms'] is None else min(s['clock_offset_min_ms'], offset_ms)
                    s['clock_offset_max_ms'] = offset_ms if s['clock_offset_max_ms'] is None else max(s['clock_offset_max_ms'], offset_ms)
                previous = s['last_source_ns']
                if previous is not None:
                    s['source_backwards'] += source < previous
                    s['source_duplicates'] += source == previous
                    s['max_source_gap_s'] = max(s['max_source_gap_s'], (source - previous) / 1e9)
                if s['first_source_ns'] is None:
                    s['first_source_ns'] = source
                s['last_source_ns'] = source

        for topic, s in stats.items():
            span = (s['last_receipt_ns'] - s['first_receipt_ns']) / 1e9
            s['observed_receipt_hz'] = (s['count'] - 1) / span if span > 0 else None
            dts = intervals.get(topic, [])
            if dts:
                med = statistics.median(dts)
                s['median_receipt_period_s'] = med
                if med > 0:
                    s['gaps_over_2x_median_period'] = sum(1 for d in dts if d > 2.0 * med)
            if s['clock_offset_min_ms'] is not None and s['clock_offset_max_ms'] is not None:
                s['clock_drift_span_ms'] = s['clock_offset_max_ms'] - s['clock_offset_min_ms']
            s['expected_hz'] = None
            s['sample_loss_fraction'] = None
            s['coverage'] = None

        # Causal 10 Hz readiness diagnostic across observed span (max age 0.25 s).
        causal_ticks = 0
        h1_ok = h5_ok = h8_ok = streak = 0
        if bag_first_ns is not None and bag_last_ns is not None and bag_last_ns >= bag_first_ns:
            wheel_stamps = topic_stamps['/motor_fb'] or topic_stamps['/joint_states'] or topic_stamps['/odom/unfiltered']
            imu_stamps = topic_stamps['/imu/data']
            cmd_stamps = topic_stamps['/cmd_vel']
            i_idx = w_idx = c_idx = 0
            max_age_ns = 250_000_000
            t_ns = bag_first_ns
            while t_ns <= bag_last_ns:
                causal_ticks += 1
                while i_idx + 1 < len(imu_stamps) and imu_stamps[i_idx + 1] <= t_ns:
                    i_idx += 1
                while w_idx + 1 < len(wheel_stamps) and wheel_stamps[w_idx + 1] <= t_ns:
                    w_idx += 1
                while c_idx + 1 < len(cmd_stamps) and cmd_stamps[c_idx + 1] <= t_ns:
                    c_idx += 1
                imu_fresh = bool(imu_stamps and 0 <= t_ns - imu_stamps[i_idx] <= max_age_ns)
                w_fresh = bool(wheel_stamps and 0 <= t_ns - wheel_stamps[w_idx] <= max_age_ns)
                c_fresh = bool(cmd_stamps and 0 <= t_ns - cmd_stamps[c_idx] <= max_age_ns)
                if imu_fresh and w_fresh and c_fresh:
                    streak += 1
                    h1_ok += streak >= 1
                    h5_ok += streak >= 5
                    h8_ok += streak >= 8
                else:
                    streak = 0
                t_ns += 100_000_000

        upstream_nonzero = any(
            commands.get(t, {}).get('nonzero_samples', 0) > 0
            for t in ('/cmd_vel_teleop', '/cmd_vel_selected', '/cmd_vel_smoothed')
        )
        final_nonzero = commands.get('/cmd_vel', {}).get('nonzero_samples', 0) > 0
        cm_actions = events.get('collision_monitor_actions', {})
        cm_stops = sum(v for k, v in cm_actions.items() if k.startswith('1:'))
        command_chain = dict(
            upstream_nonzero=upstream_nonzero,
            final_cmd_vel_nonzero=final_nonzero,
            collision_monitor_stop_samples=cm_stops,
            blocked_upstream_motion=bool(upstream_nonzero and not final_nonzero),
        )
        annotations_info = _inspect_annotations(root)

        result['topics'] = stats
        result['observed_commands'] = commands
        result['observed_events'] = events
        result['command_chain'] = command_chain
        result['annotations_summary'] = annotations_info
        result['causal_10hz_readiness'] = dict(
            ticks_10hz=causal_ticks,
            valid_h1_windows=h1_ok,
            valid_h5_windows=h5_ok,
            valid_h8_windows=h8_ok,
        )
        result['status_interpretation'] = 'Raw status values only; no effective RC/enable/current inference without matching binary schema.'

        check('finite_dynamic_values', 'FAIL' if invalid else 'PASS', invalid)
        count = sum(s['count'] for s in stats.values())
        check('decode_and_metadata', 'PASS' if count > 0 and count == meta['message_count'] else 'FAIL',
              dict(decoded=count, metadata=meta['message_count'], storage=meta['storage_identifier']))
        missing = [r['name'] for r in config['topics'] if r['required'] and not stats.get(r['name'], {}).get('count')]
        check('required_topics', 'FAIL' if missing else 'PASS', missing)
        # Static TF repeats/duplicates are normal; source checks below concern required dynamic header topics.
        dynamic = [r['name'] for r in config['topics'] if r['required'] and r['name'] != '/tf_static']
        bad = [n for n in dynamic if any(stats.get(n, {}).get(k, 0) for k in ('source_backwards', 'source_zero', 'receipt_backwards'))]
        check('dynamic_clock_order', 'FAIL' if bad else 'PASS', bad)
        unknown = [n for n in dynamic if stats.get(n, {}).get('source_count', 0) == 0]
        check('source_clock_availability', 'WARN' if unknown else 'PASS', unknown)
        high_drift = {
            n: round(stats[n]['clock_drift_span_ms'], 2)
            for n in dynamic
            if (stats.get(n, {}).get('clock_drift_span_ms') or 0.0) > 100.0
        }
        check('clock_offset_drift', 'WARN' if high_drift else 'PASS',
              high_drift or 'Sender-receiver clock offset drift <= 100 ms across dynamic header topics')
        gap_summary = {
            n: stats[n]['gaps_over_2x_median_period']
            for n in dynamic
            if stats.get(n, {}).get('gaps_over_2x_median_period', 0) > 0
        }
        check('rate_gap_coverage', 'WARN',
              dict(note='Observed rates and >2x median-period gaps reported; expected rate and accepted window thresholds unavailable. No 95% gate invented.',
                   gaps_over_2x_median_period=gap_summary))
        if command_chain['blocked_upstream_motion']:
            check('command_chain_consistency', 'WARN',
                  dict(issue='Upstream command nonzero while final /cmd_vel stayed zero',
                       collision_monitor_stop_samples=cm_stops))
            result['recommendations'].append(
                'Upstream motion command was blocked before /cmd_vel (check CollisionMonitor STOP polygon or command_gate).'
            )
        else:
            check('command_chain_consistency', 'PASS', command_chain)
        check('annotations_and_safety_events',
              'FAIL' if annotations_info['invalid_entries'] else ('WARN' if cm_stops > 0 else 'PASS'),
              dict(annotations=annotations_info['count'], invalid_annotations=annotations_info['invalid_entries'],
                   collision_monitor_stops=cm_stops))
        check('command_semantics', 'WARN', '/cmd_vel is observed ROS command, not motor target/ACK. RC/status bits require binary/schema verification.')
        check('feature_history', 'WARN',
              f'Causal 10 Hz windows observed (h1={h1_ok}, h5={h5_ok}, h8={h8_ok} of {causal_ticks} ticks); '
              '20-feature RL adapter still needs validated baseline/executed command. Teleop is not TD3 replay.')

        if missing:
            result['recommendations'].append('Verify required publisher nodes on Pi before repeating session: ' + ', '.join(missing))
        if high_drift:
            result['recommendations'].append('Inspect CPU load or serial/transport buffering on topics with >100 ms header-receipt drift.')
        if not annotations_info['count']:
            result['recommendations'].append('Attach video/body reference or event annotations when evaluating wheel-vs-body slip.')

        fail = any(c['verdict'] == 'FAIL' for c in result['checks'])
        result.update(verdict='FAIL' if fail else 'WARN', level='Q1' if fail else 'Q2')
    except Exception as exc:
        check('inspection', 'FAIL', type(exc).__name__+': '+str(exc))
    return result
