"""Recompute raw integrity and clock statistics. No automatic scientific promotion."""
import hashlib
import json
import math
from pathlib import Path
from .bag_io import decoded, metadata, source_header


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


def inspect_session(session):
    root = Path(session).resolve()
    raw = root/'raw'
    result = dict(schema_version=1, rubric='nino_studio_qc_v1', verdict='FAIL', level='Q1',
                  scope='Raw integrity and observed clocks only; no body/slip/TD3 readiness claim',
                  checks=[], topics={}, feature_ready=False, td3_replay_eligible=False,
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
        stats = {};events={};commands={}
        invalid=[]
        for topic, typ, receipt, msg in decoded(raw/'bag'):
            source, frame = source_header(msg)
            s = stats.setdefault(topic, dict(type=typ, count=0, source_count=0, receipt_backwards=0,
                source_backwards=0, source_duplicates=0, source_zero=0, max_receipt_gap_s=0., max_source_gap_s=0.,
                first_receipt_ns=receipt, last_receipt_ns=None, first_source_ns=None, last_source_ns=None, frames=[]))
            s['count'] += 1
            values=[]
            if typ=='sensor_msgs/msg/Imu':
                values=[getattr(v,k) for v in (msg.linear_acceleration,msg.angular_velocity) for k in ('x','y','z')]
            elif typ=='sensor_msgs/msg/JointState':
                values=list(msg.position)+list(msg.velocity)+list(msg.effort)
            elif typ=='geometry_msgs/msg/Twist':
                values=[getattr(v,k) for v in (msg.linear,msg.angular) for k in ('x','y','z')]
            if any(not math.isfinite(v) for v in values) and topic not in invalid:invalid.append(topic)
            if typ=='std_msgs/msg/UInt8' and topic=='/motor_status':
                counts=events.setdefault('firmware_status_raw_values',{})
                key=str(msg.data);counts[key]=counts.get(key,0)+1
            if typ=='nav2_msgs/msg/CollisionMonitorState':
                counts=events.setdefault('collision_monitor_actions',{})
                key=str(msg.action_type)+':'+msg.polygon_name;counts[key]=counts.get(key,0)+1
            if typ=='geometry_msgs/msg/Twist':
                c=commands.setdefault(topic,dict(nonzero_samples=0,max_abs_v_m_s=0.,max_abs_w_rad_s=0.,clock='bag_receipt_not_execution'))
                if math.isfinite(msg.linear.x) and math.isfinite(msg.angular.z):
                    c['nonzero_samples']+=abs(msg.linear.x)>1e-9 or abs(msg.angular.z)>1e-9
                    c['max_abs_v_m_s']=max(c['max_abs_v_m_s'],abs(msg.linear.x))
                    c['max_abs_w_rad_s']=max(c['max_abs_w_rad_s'],abs(msg.angular.z))
            previous = s['last_receipt_ns']
            if previous is not None:
                s['receipt_backwards'] += receipt < previous
                s['max_receipt_gap_s'] = max(s['max_receipt_gap_s'], (receipt-previous)/1e9)
            s['last_receipt_ns'] = receipt
            if frame is not None and frame not in s['frames']:
                s['frames'].append(frame)
            if source is not None:
                s['source_count'] += 1
                s['source_zero'] += source == 0
                previous = s['last_source_ns']
                if previous is not None:
                    s['source_backwards'] += source < previous
                    s['source_duplicates'] += source == previous
                    s['max_source_gap_s'] = max(s['max_source_gap_s'], (source-previous)/1e9)
                if s['first_source_ns'] is None:
                    s['first_source_ns'] = source
                s['last_source_ns'] = source
        for s in stats.values():
            span = (s['last_receipt_ns']-s['first_receipt_ns'])/1e9
            s['observed_receipt_hz'] = (s['count']-1)/span if span > 0 else None
            s['expected_hz'] = None
            s['sample_loss_fraction'] = None
            s['coverage'] = None
        result['topics'] = stats
        result['observed_commands']=commands;result['observed_events']=events
        result['status_interpretation']='Raw status values only; no effective RC/enable/current inference without matching binary schema.'
        check('finite_dynamic_values','FAIL' if invalid else 'PASS',invalid)
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
        check('rate_gap_coverage', 'WARN', 'Observed rates/gaps reported; expected rate, source sequence and accepted window thresholds unavailable. No 95% gate invented.')
        check('command_semantics', 'WARN', '/cmd_vel is observed ROS command, not motor target/ACK. RC/status bits require binary/schema verification.')
        check('feature_history', 'WARN', 'Raw message export only; causal 20-feature adapter needs validated baseline/executed command and source-age mapping. Teleop is not TD3 replay.')
        fail = any(c['verdict'] == 'FAIL' for c in result['checks'])
        result.update(verdict='FAIL' if fail else 'WARN', level='Q1' if fail else 'Q2')
    except Exception as exc:
        check('inspection', 'FAIL', type(exc).__name__+': '+str(exc))
    return result
