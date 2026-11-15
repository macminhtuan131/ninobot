"""Per-slot E2 QC/primary on supported source samples; no causal benefit verdict."""
import json
import math
from pathlib import Path
import numpy as np
from .obstacle_authority_draft import c1_manifold


def grids(truth, nominal, start, end):
    """Causal ZOH at20ms and+10ms; integrate actual supported widths, no interpolation."""
    def series(rows):
        times, values = np.asarray(rows, float).T
        if not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)) or np.any(np.diff(times) <= 0):
            raise ValueError("Nonfinite/duplicate/reversed source samples")
        return times, values
    t, v = series(truth); n, ref = series(nominal)
    if not start < end or t[0] > start or t[-1] < end or n[0] > start:
        raise ValueError("Primary window boundaries unsupported")
    inside = t[(t >= start - .04) & (t <= end + .04)]
    if len(inside) < 2 or np.max(np.diff(inside)) > .040000001:
        raise ValueError("GT source gap exceeds40ms")
    out = {}
    for shift in (0.0, 0.01):
        q = start + shift + np.arange(150) * .02
        q = q[q < end - 1e-9]
        width = np.minimum(.02, end - q)
        idx = np.searchsorted(t, q + 1e-9, side="right") - 1
        ni = np.searchsorted(n, q + 1e-9, side="right") - 1
        support = (idx >= 0) & (ni >= 0)
        support &= q - t[np.maximum(idx, 0)] <= .040000001
        support &= q - n[np.maximum(ni, 0)] <= .100000001
        covered = float(np.sum(width[support]))
        coverage = covered / (end - start)
        if coverage < .98:
            raise ValueError("Primary duration coverage below98%")
        error = v[idx[support]] - ref[ni[support]]
        out[str(shift)] = dict(ise_m2_s=float(np.sum(error ** 2 * width[support])),
            coverage_fraction=coverage, supported_duration_s=covered, window_duration_s=end-start,
            samples=int(np.sum(support)), maximum_gt_age_s=float(np.max(q[support] - t[idx[support]])),
            semantics="causal_asof_ZOH_actual_supported_widths_no_future_interpolation")
    return out


def assess(rows, raw_paths):
    if len(rows) != 140 or not rows[-1]["task"]["task_success"] or not rows[-1]["task"]["stop_completed"]:
        raise ValueError("E2 full task/stop not complete")
    epoch = rows[0]["oracle_decision"]["decision_source_stamp_s"]
    end = rows[-1]["sensor_clock_s"]
    contacts, truth, last_truth_stamp = {}, {}, None
    for path in raw_paths:
        for line in Path(path).open():
            packet = json.loads(line)
            if not epoch <= packet["stamp_s"] <= end + 1e-9:
                continue
            if c1_manifold(packet):
                component = packet["channel"][8:]
                contacts[component] = min(contacts.get(component, math.inf), packet["stamp_s"])
            if packet["channel"] == "truth":
                stamp, speed = packet["stamp_s"], packet["values"]["speed"]
                if last_truth_stamp is not None and stamp < last_truth_stamp:
                    raise ValueError("GT source reversal retained; do not repair by sorting")
                if stamp in truth and truth[stamp] != speed:
                    raise ValueError("Conflicting duplicate GT source sample")
                truth[stamp] = speed
                last_truth_stamp = stamp
    if not contacts:
        raise ValueError("No C1 manifold; authority question is unknown")
    tc = min(contacts.values())
    triggers = [r["oracle_decision"]["trigger"] for r in rows if r["oracle_decision"]["trigger"]]
    if not triggers:
        raise ValueError("No receipt-causal trigger before withdrawal; unknown")
    trigger = triggers[0]
    if any(t != trigger for t in triggers):
        raise ValueError("Executed oracle trigger was backdated/revised")
    nominal = [(r["oracle_decision"]["decision_source_stamp_s"],
                r["oracle_decision"]["nominal_shaped_body"][0]) for r in rows]
    metrics = grids(sorted(truth.items()), nominal, tc, tc + 3.0)
    native = [r for r in rows if tc <= r["sensor_clock_s"] < tc + 3.0]
    drive = [contacts[k] for k in ("left_wheel", "right_wheel") if k in contacts]
    return dict(status="per_slot_measurement_pass_not_benefit", first_manifold_sim_s=tc,
        first_manifold_by_component_sim_s=contacts, trigger=trigger,
        first_drive_manifold_sim_s=min(drive) if drive else None,
        trigger_to_first_drive_source_interval_s=min(drive)-trigger["decision_stamp_s"] if drive else None,
        primary_gt_grids=metrics, native_window_samples=len(native),
        native_window_ise_m2_s=float(sum(r["task"]["velocity_error_m_s"]**2 * .1 for r in native)),
        native_full_vrmse_m_s=float(np.sqrt(np.mean([r["task"]["velocity_error_m_s"]**2 for r in rows]))),
        active_ticks=sum(r["oracle_decision"]["active"] for r in rows),
        loaded_contact_verified=False, useful_body_authority_verified=False,
        comparison="pending candidate/B0 pairs, caliper and all blocks; no automatic nomination")
