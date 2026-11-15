"""Offline source-time queries with explicit ambiguity; never retimestamp raw.

All payloads at a timestamp are retained. A conflicting group has no usable
value, and cannot fall back to an older group or a future sample. Integer
nanoseconds express the existing ROS/Gazebo clock, not extra resolution.
"""
from dataclasses import dataclass
import math
import numpy as np

READER_ID = 'nino_ambiguity_aware_source_query_v1'


def ns(seconds):
    value = float(seconds)
    if not math.isfinite(value):
        raise ValueError('Nonfinite source/query time')
    return round(value * 1_000_000_000)


@dataclass(frozen=True)
class Query:
    values: tuple  # None means unsupported; never a zero measurement.
    supported: np.ndarray
    source_ns: tuple
    reasons: tuple


class SourceSeries:
    def __init__(self, samples):
        groups = []
        shape = None
        for stamp, payload in samples:
            stamp_ns = ns(stamp)
            value = np.atleast_1d(np.asarray(payload, dtype=float))
            if not np.all(np.isfinite(value)):
                raise ValueError('Nonfinite source payload')
            if shape is None: shape = value.shape
            if shape != value.shape:
                raise ValueError('Source payload shape changed')
            if groups and stamp_ns < groups[-1]['source_ns']:
                raise ValueError('Source reversal; do not sort/repair')
            if not groups or stamp_ns != groups[-1]['source_ns']:
                groups.append(dict(source_ns=stamp_ns, payloads=[]))
            groups[-1]['payloads'].append(value.copy())
        if not groups:
            raise ValueError('Missing source channel')
        for group in groups:
            group['ambiguous'] = any(not np.array_equal(v, group['payloads'][0]) for v in group['payloads'])
        self.groups = groups
        self.times_ns = np.asarray([g['source_ns'] for g in groups], dtype=np.int64)
        self.conflicts = [dict(source_ns=g['source_ns'],
                               payloads=[v.tolist() for v in g['payloads']],
                               packet_count=len(g['payloads'])) for g in groups if g['ambiguous']]

    def query(self, times_s, maximum_age_s):
        if not math.isfinite(maximum_age_s) or maximum_age_s < 0:
            raise ValueError('Invalid source age bound')
        maximum_age_ns = ns(maximum_age_s)
        values, valid, sources, reasons = [], [], [], []
        for query_s in times_s:
            stamp_ns = ns(query_s)
            index = int(np.searchsorted(self.times_ns, stamp_ns, side='right')) - 1
            source = None if index < 0 else int(self.times_ns[index])
            if index < 0: reason = 'before_first_source'
            elif self.groups[index]['ambiguous']: reason = 'ambiguous_source'
            elif stamp_ns - source > maximum_age_ns: reason = 'stale_source'
            else: reason = 'supported'
            supported = reason == 'supported'
            values.append(self.groups[index]['payloads'][0].copy() if supported else None)
            valid.append(supported); sources.append(source); reasons.append(reason)
        return Query(tuple(values), np.asarray(valid, dtype=bool), tuple(sources), tuple(reasons))


def contrast(control, candidate, times_s, maximum_age_s):
    a, b = control.query(times_s, maximum_age_s), candidate.query(times_s, maximum_age_s)
    valid = a.supported & b.supported
    deltas = tuple(bv-av if good else None for av,bv,good in zip(a.values,b.values,valid))
    return deltas, valid, a, b
