"""Causal 10 Hz sensor-command alignment, missing-data masks, frozen normalization, and grouped session splits.

Strict rules:
- Zero future lookahead: tick t_k only uses messages received at or before t_k (bag_time_ns <= tick_ns).
- Missing or stale channels set *_present=False and keep physical values as None (never fabricated 0.0).
- Teleop and passive observer sessions are never marked td3_replay_eligible.
- Train/validation/test splits group whole sessions; frames from one session never cross splits.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Iterable, Mapping, Sequence

CAUSAL_FRAME_COLUMNS: tuple[tuple[str, str], ...] = (
    ('tick_index', 'int64'),
    ('tick_time_ns', 'int64'),
    ('imu_present', 'bool'),
    ('imu_age_s', 'float64'),
    ('imu_source_header_ns', 'int64'),
    ('imu_wz_rad_s', 'float64'),
    ('imu_ax_m_s2', 'float64'),
    ('imu_ay_m_s2', 'float64'),
    ('imu_az_m_s2', 'float64'),
    ('wheel_fb_present', 'bool'),
    ('wheel_fb_age_s', 'float64'),
    ('wheel_fb_source_header_ns', 'int64'),
    ('wheel_left_rad_s', 'float64'),
    ('wheel_right_rad_s', 'float64'),
    ('odom_present', 'bool'),
    ('odom_age_s', 'float64'),
    ('odom_vx_m_s', 'float64'),
    ('odom_wz_rad_s', 'float64'),
    ('cmd_selected_present', 'bool'),
    ('cmd_selected_age_s', 'float64'),
    ('cmd_selected_vx_m_s', 'float64'),
    ('cmd_selected_wz_rad_s', 'float64'),
    ('cmd_final_present', 'bool'),
    ('cmd_final_age_s', 'float64'),
    ('cmd_final_vx_m_s', 'float64'),
    ('cmd_final_wz_rad_s', 'float64'),
    ('teleop_active', 'bool'),
    ('shadow_proposal_present', 'bool'),
    ('proposal_raw_v', 'float64'),
    ('proposal_raw_w', 'float64'),
    ('applied_ref_vx_m_s', 'float64'),
    ('applied_ref_wz_rad_s', 'float64'),
    ('projection_clipped', 'bool'),
    ('valid_h1', 'bool'),
    ('valid_h5', 'bool'),
    ('valid_h8', 'bool'),
    ('td3_replay_eligible', 'bool'),
)

NUMERIC_FEATURE_COLUMNS: tuple[str, ...] = (
    'imu_wz_rad_s',
    'imu_ax_m_s2',
    'imu_ay_m_s2',
    'imu_az_m_s2',
    'wheel_left_rad_s',
    'wheel_right_rad_s',
    'odom_vx_m_s',
    'odom_wz_rad_s',
    'cmd_selected_vx_m_s',
    'cmd_selected_wz_rad_s',
    'cmd_final_vx_m_s',
    'cmd_final_wz_rad_s',
)


def causal_schema_sha256() -> str:
    payload = json.dumps(CAUSAL_FRAME_COLUMNS, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _finite_float(val: Any) -> float | None:
    if isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val):
        return float(val)
    return None


def _nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    cur: Any = mapping
    for key in keys:
        if not isinstance(cur, Mapping) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _extract_wheel_velocities(fields: Mapping[str, Any]) -> tuple[float | None, float | None]:
    names = fields.get('name') or []
    vels = fields.get('velocity') or []
    if not isinstance(vels, Sequence) or isinstance(vels, (str, bytes)):
        return None, None
    left = right = None
    if isinstance(names, Sequence) and not isinstance(names, (str, bytes)) and len(names) == len(vels):
        for n, v in zip(names, vels):
            label = str(n).lower()
            fv = _finite_float(v)
            if 'left' in label and left is None:
                left = fv
            elif 'right' in label and right is None:
                right = fv
    if left is None and right is None and len(vels) >= 2:
        left = _finite_float(vels[0])
        right = _finite_float(vels[1])
    return left, right


def align_causal_frames(
    events: Iterable[Mapping[str, Any]],
    *,
    rate_hz: float = 10.0,
    max_sensor_age_s: float = 0.25,
    allow_policy_replay: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build causal 10 Hz frames strictly from messages with bag_time_ns <= tick_time_ns.

    Each input event mapping requires:
      - topic (str)
      - bag_time_ns (int)
      - source_header_ns (int | None)
      - fields (dict decoded from ROS message)
    """
    if rate_hz <= 0 or not math.isfinite(rate_hz):
        raise ValueError('rate_hz must be positive finite')
    if max_sensor_age_s <= 0 or not math.isfinite(max_sensor_age_s):
        raise ValueError('max_sensor_age_s must be positive finite')

    ordered = sorted(events, key=lambda e: int(e['bag_time_ns']))
    period_ns = int(round(1_000_000_000 / rate_hz))
    max_age_ns = int(round(max_sensor_age_s * 1_000_000_000))

    if not ordered:
        summary = {
            'schema_version': 1,
            'schema_sha256': causal_schema_sha256(),
            'rate_hz': rate_hz,
            'period_ns': period_ns,
            'max_sensor_age_s': max_sensor_age_s,
            'causal_ticks': 0,
            'history_window_counts': {'h1': 0, 'h5': 0, 'h8': 0},
            'missing_counts': {},
            'td3_replay_eligible_ticks': 0,
            'td3_replay_eligible': False,
        }
        return [], summary

    first_ns = int(ordered[0]['bag_time_ns'])
    last_ns = int(ordered[-1]['bag_time_ns'])
    # First decision tick starts at first_ns so the initial sample is causally present; steps by period_ns.
    ticks: list[int] = []
    t = first_ns
    while t <= last_ns:
        ticks.append(t)
        t += period_ns

    latest: dict[str, dict[str, Any]] = {}
    cursor = 0
    n_events = len(ordered)
    frames: list[dict[str, Any]] = []
    consecutive_core = 0

    def ingest(ev: Mapping[str, Any]) -> None:
        topic = str(ev['topic'])
        stamp = int(ev['bag_time_ns'])
        header_ns = ev.get('source_header_ns')
        fields = ev.get('fields') or {}
        if topic == '/imu/data':
            latest['imu'] = {
                'bag_time_ns': stamp,
                'source_header_ns': header_ns,
                'wz': _finite_float(_nested(fields, 'angular_velocity', 'z')),
                'ax': _finite_float(_nested(fields, 'linear_acceleration', 'x')),
                'ay': _finite_float(_nested(fields, 'linear_acceleration', 'y')),
                'az': _finite_float(_nested(fields, 'linear_acceleration', 'z')),
            }
        elif topic in ('/motor_fb', '/joint_states'):
            # Prefer /motor_fb over /joint_states if both exist at same stamp, otherwise latest causal arrival.
            if topic == '/motor_fb' or 'wheel_fb' not in latest or latest['wheel_fb'].get('topic') != '/motor_fb':
                left, right = _extract_wheel_velocities(fields)
                latest['wheel_fb'] = {
                    'topic': topic,
                    'bag_time_ns': stamp,
                    'source_header_ns': header_ns,
                    'left': left,
                    'right': right,
                }
        elif topic in ('/odom/unfiltered', '/odom'):
            if topic == '/odom/unfiltered' or 'odom' not in latest or latest['odom'].get('topic') != '/odom/unfiltered':
                latest['odom'] = {
                    'topic': topic,
                    'bag_time_ns': stamp,
                    'vx': _finite_float(_nested(fields, 'twist', 'twist', 'linear', 'x')),
                    'wz': _finite_float(_nested(fields, 'twist', 'twist', 'angular', 'z')),
                }
        elif topic == '/cmd_vel_selected':
            latest['cmd_selected'] = {
                'bag_time_ns': stamp,
                'vx': _finite_float(_nested(fields, 'linear', 'x')),
                'wz': _finite_float(_nested(fields, 'angular', 'z')),
            }
        elif topic == '/cmd_vel':
            latest['cmd_final'] = {
                'bag_time_ns': stamp,
                'vx': _finite_float(_nested(fields, 'linear', 'x')),
                'wz': _finite_float(_nested(fields, 'angular', 'z')),
            }
        elif topic == '/cmd_vel_teleop':
            vx = _finite_float(_nested(fields, 'linear', 'x'))
            wz = _finite_float(_nested(fields, 'angular', 'z'))
            latest['teleop'] = {
                'bag_time_ns': stamp,
                'nonzero': bool((vx is not None and abs(vx) > 1e-9) or (wz is not None and abs(wz) > 1e-9)),
            }
        elif topic == '/nino/residual/shadow_trace':
            raw_json = fields.get('data')
            if isinstance(raw_json, str):
                try:
                    parsed = json.loads(raw_json)
                except ValueError:
                    parsed = None
                if isinstance(parsed, Mapping):
                    prop = parsed.get('proposal_raw') or parsed.get('action_raw') or [None, None]
                    app = parsed.get('applied_reference') or parsed.get('projected_reference') or [None, None]
                    latest['shadow'] = {
                        'bag_time_ns': stamp,
                        'raw_v': _finite_float(prop[0]) if isinstance(prop, Sequence) and len(prop) >= 2 else None,
                        'raw_w': _finite_float(prop[1]) if isinstance(prop, Sequence) and len(prop) >= 2 else None,
                        'app_v': _finite_float(app[0]) if isinstance(app, Sequence) and len(app) >= 2 else None,
                        'app_w': _finite_float(app[1]) if isinstance(app, Sequence) and len(app) >= 2 else None,
                        'clipped': bool(parsed.get('projection_clipped')) if 'projection_clipped' in parsed else None,
                        'authority_active': parsed.get('authority_active') is True,
                    }

    def fresh(channel: str, tick_ns: int) -> tuple[bool, float | None, dict[str, Any] | None]:
        entry = latest.get(channel)
        if entry is None:
            return False, None, None
        age_ns = tick_ns - int(entry['bag_time_ns'])
        if age_ns < 0 or age_ns > max_age_ns:
            return False, None, None
        return True, age_ns / 1e9, entry

    for idx, tick_ns in enumerate(ticks):
        while cursor < n_events and int(ordered[cursor]['bag_time_ns']) <= tick_ns:
            ingest(ordered[cursor])
            cursor += 1

        imu_ok, imu_age, imu = fresh('imu', tick_ns)
        imu_valid = bool(imu_ok and imu and imu['wz'] is not None and imu['az'] is not None)

        w_ok, w_age, w_fb = fresh('wheel_fb', tick_ns)
        w_valid = bool(w_ok and w_fb and w_fb['left'] is not None and w_fb['right'] is not None)

        od_ok, od_age, od = fresh('odom', tick_ns)
        od_valid = bool(od_ok and od and od['vx'] is not None and od['wz'] is not None)

        cs_ok, cs_age, cs = fresh('cmd_selected', tick_ns)
        cs_valid = bool(cs_ok and cs and cs['vx'] is not None and cs['wz'] is not None)

        cf_ok, cf_age, cf = fresh('cmd_final', tick_ns)
        cf_valid = bool(cf_ok and cf and cf['vx'] is not None and cf['wz'] is not None)

        tel_ok, _, tel = fresh('teleop', tick_ns)
        teleop_active = bool(tel_ok and tel and tel['nonzero'])

        sh_ok, _, sh = fresh('shadow', tick_ns)
        sh_valid = bool(sh_ok and sh and sh['raw_v'] is not None and sh['raw_w'] is not None)

        core_obs = imu_valid and (w_valid or od_valid) and cf_valid
        consecutive_core = consecutive_core + 1 if core_obs else 0

        row = {
            'tick_index': idx,
            'tick_time_ns': tick_ns,
            'imu_present': imu_valid,
            'imu_age_s': imu_age if imu_valid else None,
            'imu_source_header_ns': imu['source_header_ns'] if imu_valid else None,
            'imu_wz_rad_s': imu['wz'] if imu_valid else None,
            'imu_ax_m_s2': imu['ax'] if imu_valid else None,
            'imu_ay_m_s2': imu['ay'] if imu_valid else None,
            'imu_az_m_s2': imu['az'] if imu_valid else None,
            'wheel_fb_present': w_valid,
            'wheel_fb_age_s': w_age if w_valid else None,
            'wheel_fb_source_header_ns': w_fb['source_header_ns'] if w_valid else None,
            'wheel_left_rad_s': w_fb['left'] if w_valid else None,
            'wheel_right_rad_s': w_fb['right'] if w_valid else None,
            'odom_present': od_valid,
            'odom_age_s': od_age if od_valid else None,
            'odom_vx_m_s': od['vx'] if od_valid else None,
            'odom_wz_rad_s': od['wz'] if od_valid else None,
            'cmd_selected_present': cs_valid,
            'cmd_selected_age_s': cs_age if cs_valid else None,
            'cmd_selected_vx_m_s': cs['vx'] if cs_valid else None,
            'cmd_selected_wz_rad_s': cs['wz'] if cs_valid else None,
            'cmd_final_present': cf_valid,
            'cmd_final_age_s': cf_age if cf_valid else None,
            'cmd_final_vx_m_s': cf['vx'] if cf_valid else None,
            'cmd_final_wz_rad_s': cf['wz'] if cf_valid else None,
            'teleop_active': teleop_active,
            'shadow_proposal_present': sh_valid,
            'proposal_raw_v': sh['raw_v'] if sh_valid else None,
            'proposal_raw_w': sh['raw_w'] if sh_valid else None,
            'applied_ref_vx_m_s': sh['app_v'] if sh_valid else None,
            'applied_ref_wz_rad_s': sh['app_w'] if sh_valid else None,
            'projection_clipped': sh['clipped'] if sh_valid else None,
            'valid_h1': consecutive_core >= 1,
            'valid_h5': consecutive_core >= 5,
            'valid_h8': consecutive_core >= 8,
            'td3_replay_eligible': False,
        }
        frames.append(row)

    # Transition replay eligibility requires explicit allow_policy_replay, active policy proposal, no teleop,
    # and valid next-tick observation s_{t+1}.
    if allow_policy_replay:
        for idx in range(len(frames) - 1):
            cur = frames[idx]
            nxt = frames[idx + 1]
            cur['td3_replay_eligible'] = bool(
                cur['valid_h5']
                and nxt['valid_h1']
                and cur['shadow_proposal_present']
                and cur['applied_ref_vx_m_s'] is not None
                and cur['applied_ref_wz_rad_s'] is not None
                and not cur['teleop_active']
            )

    missing_counts = {
        key: sum(1 for r in frames if not r[key])
        for key in ('imu_present', 'wheel_fb_present', 'odom_present', 'cmd_selected_present', 'cmd_final_present')
    }
    replay_ticks = sum(1 for r in frames if r['td3_replay_eligible'])
    summary = {
        'schema_version': 1,
        'schema_sha256': causal_schema_sha256(),
        'rate_hz': rate_hz,
        'period_ns': period_ns,
        'max_sensor_age_s': max_sensor_age_s,
        'causal_ticks': len(frames),
        'history_window_counts': {
            'h1': sum(1 for r in frames if r['valid_h1']),
            'h5': sum(1 for r in frames if r['valid_h5']),
            'h8': sum(1 for r in frames if r['valid_h8']),
        },
        'missing_counts': missing_counts,
        'td3_replay_eligible_ticks': replay_ticks,
        'td3_replay_eligible': replay_ticks > 0,
    }
    return frames, summary


def compute_normalization_stats(
    train_frames: Sequence[Mapping[str, Any]],
    columns: Sequence[str] = NUMERIC_FEATURE_COLUMNS,
) -> dict[str, Any]:
    """Compute frozen normalization mean/std strictly from training split frames (ignoring None)."""
    stats: dict[str, Any] = {}
    for col in columns:
        vals = [
            float(r[col])
            for r in train_frames
            if r.get(col) is not None and not isinstance(r.get(col), bool) and math.isfinite(r[col])
        ]
        if not vals:
            stats[col] = {'count': 0, 'mean': None, 'std': None, 'min': None, 'max': None}
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = max(math.sqrt(var), 1e-6)
        stats[col] = {'count': len(vals), 'mean': mean, 'std': std, 'min': min(vals), 'max': max(vals)}
    return {
        'schema_version': 1,
        'mode': 'frozen_train_stats_v1',
        'train_frame_count': len(train_frames),
        'features': stats,
    }


def apply_frozen_normalization(
    frames: Sequence[Mapping[str, Any]],
    norm_stats: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Apply frozen train stats without fabricating values for None/missing channels."""
    feature_stats = norm_stats.get('features', {})
    output: list[dict[str, Any]] = []
    for row in frames:
        copied = dict(row)
        for col, spec in feature_stats.items():
            raw_val = copied.get(col)
            if raw_val is None or spec.get('mean') is None or spec.get('std') is None:
                copied[col + '_norm'] = None
            else:
                copied[col + '_norm'] = (float(raw_val) - float(spec['mean'])) / float(spec['std'])
        output.append(copied)
    return output


def assign_grouped_splits(
    sessions: Sequence[Mapping[str, Any]],
    *,
    ratios: tuple[float, float, float] = (0.6, 0.2, 0.2),
    seed: int = 11,
) -> dict[str, Any]:
    """Assign whole sessions to train/validation/test without splitting frames from the same session."""
    if len(ratios) != 3 or any(r < 0 for r in ratios) or abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError('Split ratios must be 3 non-negative numbers summing to 1.0')
    seen_ids: set[str] = set()
    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for s in sessions:
        sid = str(s.get('session_id', '')).strip()
        if not sid or sid in seen_ids:
            raise ValueError(f'Missing or duplicate session_id: {sid!r}')
        seen_ids.add(sid)
        scenario = str(s.get('scenario', 'unknown')).strip() or 'unknown'
        # Held-out scenario is always pinned to test split to prevent evaluation leakage.
        entry = {'session_id': sid, 'scenario': scenario, 'condition': str(s.get('floor_load_note', 'default'))}
        by_scenario.setdefault(scenario, []).append(entry)

    rng = random.Random(seed)
    assignments: dict[str, str] = {}
    buckets: dict[str, list[str]] = {'train': [], 'validation': [], 'test': []}

    for scenario in sorted(by_scenario):
        group = sorted(by_scenario[scenario], key=lambda x: x['session_id'])
        if scenario == 'heldout':
            for item in group:
                assignments[item['session_id']] = 'test'
                buckets['test'].append(item['session_id'])
            continue
        rng.shuffle(group)
        n = len(group)
        n_train = max(1, int(round(n * ratios[0]))) if n >= 1 else 0
        n_val = int(round(n * ratios[1])) if n >= 3 else 0
        if n == 2 and ratios[2] > 0:
            n_train, n_val = 1, 0
        if n_train + n_val > n:
            n_val = max(0, n - n_train)
        for idx, item in enumerate(group):
            split = 'train' if idx < n_train else 'validation' if idx < n_train + n_val else 'test'
            assignments[item['session_id']] = split
            buckets[split].append(item['session_id'])

    # Verify strict disjointness across splits.
    overlap = (set(buckets['train']) & set(buckets['validation'])) | (set(buckets['train']) & set(buckets['test'])) | (set(buckets['validation']) & set(buckets['test']))
    if overlap:
        raise RuntimeError(f'Session split leakage detected: {overlap}')

    return {
        'schema_version': 1,
        'split_policy': 'whole_session_grouped_no_frame_leakage_v1',
        'seed': seed,
        'ratios': list(ratios),
        'buckets': {k: sorted(v) for k, v in buckets.items()},
        'session_to_split': assignments,
    }

