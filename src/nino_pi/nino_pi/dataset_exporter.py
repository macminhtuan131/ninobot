"""Derived long-form message table and causal 10 Hz sensor-command frames; never fabricates zeros or RL replay."""
import json
import math
from pathlib import Path
from .bag_io import decoded, source_header
from .causal_alignment import CAUSAL_FRAME_COLUMNS, align_causal_frames
from .studio_quality import verify_raw, digest


def strict_fields(value):
    if isinstance(value,float) and not math.isfinite(value):
        return {'invalid_float':str(value)}
    if isinstance(value,dict):return {k:strict_fields(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [strict_fields(v) for v in value]
    return value


def _arrow_type(pa, name):
    return {'int64': pa.int64(), 'float64': pa.float64(), 'bool': pa.bool_(), 'string': pa.string()}[name]


def export_session(session, output):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from rosidl_runtime_py.convert import message_to_ordereddict
    root, out = Path(session).resolve(), Path(output).resolve()
    raw = root/'raw'
    if out == root or root in out.parents or out in root.parents:
        raise ValueError('Derived export must be outside original session')
    hashes = verify_raw(raw)
    if not hashes['checked'] or hashes['mismatches']:
        raise ValueError('Raw checksum failure; export blocked')
    out.mkdir(parents=True, exist_ok=False)
    schema = pa.schema([('topic', pa.string()), ('ros_type', pa.string()), ('bag_time_ns', pa.int64()),
        ('source_header_ns', pa.int64()), ('frame_id', pa.string()), ('fields_json', pa.string())])
    causal_schema = pa.schema([(col, _arrow_type(pa, typ)) for col, typ in CAUSAL_FRAME_COLUMNS])
    rows, causal_events, count = [], [], 0
    try:
        with pq.ParquetWriter(out/'messages.parquet', schema) as writer:
            for topic, typ, stamp, message in decoded(raw/'bag'):
                header, frame = source_header(message)
                ordered_dict = strict_fields(message_to_ordereddict(message))
                # Tag invalid floats (including legitimate LaserScan inf); do not replace with zero.
                payload = json.dumps(ordered_dict, ensure_ascii=False, allow_nan=False)
                rows.append(dict(topic=topic, ros_type=typ, bag_time_ns=stamp, source_header_ns=header,
                                 frame_id=frame, fields_json=payload))
                causal_events.append(dict(topic=topic, ros_type=typ, bag_time_ns=stamp,
                                          source_header_ns=header, fields=ordered_dict))
                count += 1
                if len(rows) >= 1000:
                    writer.write_table(pa.Table.from_pylist(rows, schema=schema)); rows=[]
            if rows:
                writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        causal_frames, causal_summary = align_causal_frames(causal_events, rate_hz=10.0, max_sensor_age_s=0.25,
                                                            allow_policy_replay=False)
        pq.write_table(pa.Table.from_pylist(causal_frames, schema=causal_schema), out/'causal_frames.parquet')
        (out/'causal_manifest.json').write_text(json.dumps(causal_summary, ensure_ascii=False, indent=2)+'\n')
        after = verify_raw(raw)
        if after != hashes:
            raise ValueError('Raw changed during export')
        result = dict(schema_version=1, status='completed', table_schema='nino_raw_messages_long_v1',
            rows=count, causal_frames_rows=len(causal_frames),
            source_session=str(root), raw_sha256_index=digest(raw/'sha256.json'),
            table_sha256=digest(out/'messages.parquet'),
            causal_table_sha256=digest(out/'causal_frames.parquet'),
            causal_schema_sha256=causal_summary['schema_sha256'],
            causal_history_window_counts=causal_summary['history_window_counts'],
            exporter_sha256=digest(__file__),
            purpose='analysis/sysid inputs + causal 10Hz sensor/command alignment with explicit missing masks; teleop/observer sessions never promoted to TD3 replay',
            td3_replay_eligible=False, feature_ready=False)
        (out/'export.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        return result
    except BaseException as exc:
        (out/'EXPORT_FAILED.json').write_text(json.dumps(dict(status='failed_partial', error=str(exc)))+'\n')
        raise
