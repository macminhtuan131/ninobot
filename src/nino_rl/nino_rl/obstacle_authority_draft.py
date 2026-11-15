"""Offline E2 planning and receipt-causal oracle; no ROS, physics or actor runner.

First C1 manifold is privileged simulation information, NOT loaded contact.
This planner cannot grant execution authority. Existing v1/v2 contracts stay frozen.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

PROTOCOL_ID = "nino_fixed6mm_postmanifold_authority_draft_v1_2026_11_08"
COMPONENTS = ("left_wheel", "right_wheel", "caster_left_wheel",
              "caster_right_wheel", "caster_bracket_left", "caster_bracket_right", "chassis")
ROOT = next((p for p in Path(__file__).resolve().parents
             if (p / "src/nino_rl/config").is_dir()), None)
if ROOT is None:
    raise RuntimeError("E2 offline preparation requires the Nino source checkout")
PLAN_PATH = ROOT / "src/nino_rl/config/fixed6mm_postmanifold_authority_draft_v1.json"
NO_RELEASE = dict(physics_allowed=False, allocated_attempts=0, training_allowed=False,
                  training_transitions=0, optimizer_updates=0, hardware_actions=0,
                  runtime_implemented=False)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def load(path=PLAN_PATH, *, verify_inputs=True):
    plan = json.loads(Path(path).read_text())
    if (plan["protocol_id"] != PROTOCOL_ID or plan["status"] != "prepared_not_released"
            or plan["release"] != NO_RELEASE):
        raise ValueError("Offline draft cannot release physics/training/hardware")
    expected = dict(levels=[-1, 0, 1], common_bound_m_s=0.005,
                    control_interval_s=0.1, source_stops_s=[6.0, 8.0], horizon_s=14.0,
                    source_warmup_s=0.5, withdraw_lead_s=0.5,
                    nominal_steady_m_s=0.2, trigger="first_received_causal_C1_manifold")
    if plan["intervention"] != expected:
        raise ValueError("Changed intervention needs a new protocol")
    slots = plan["proposed_attempts"]
    expected_cells = {(b, s, a) for b in (0, 1) for s in (6.0, 8.0) for a in (-1, 0, 1)}
    if (len(slots) != 12 or {r["id"] for r in slots} != {f"E2-{i:02d}" for i in range(1, 13)}
            or {(r["block"], r["stop_s"], r["level"]) for r in slots} != expected_cells):
        raise ValueError("Expected twelve unique complete blocked cells")
    if plan["fixed"]["pi_ki"] != 0.10 or plan["fixed"]["scenario"] != "box_c1_6mm":
        raise ValueError("Ki/scenario changes confound this screen")
    if plan["proposed_budget"]["max_attempts"] != 12 or plan["proposed_budget"]["task_ticks_max"] != 1680:
        raise ValueError("Changed budget requires a separate protocol")
    # Pin all statistical/quality rules too, rather than accepting silent gate edits.
    contract = deepcopy(plan)
    digest = contract.pop("spec_sha256")
    if hashlib.sha256(json.dumps(contract, sort_keys=True, allow_nan=False).encode()).hexdigest() != digest:
        raise ValueError("Draft specification changed")
    if verify_inputs:
        for name, digest in plan["frozen_inputs"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Frozen input changed: " + name)
    return plan


def c1_manifold(packet):
    """Exact terminal collision name; floor support and similarly named items excluded."""
    channel = packet.get("channel", "")
    if channel not in {"contact_" + c for c in COMPONENTS}:
        return False
    for row in packet.get("values", []):
        names = [row.get(k, "").split("::")[-3:] for k in ("collision1", "collision2")]
        if ["cable_bumps", "cables", "C1_collision"] in names and type(row.get("points")) is int and row["points"] > 0:
            return True
    return False


class PostManifoldPlan:
    """One-shot receipt-causal oracle for fixture/adapter preparation only.

    Every arm, including zero, runs the same trigger logic. No backdating from
    a late-arriving older source stamp; no trigger if received after withdrawal.
    Health loss latches this proposed intervention off until a new planner epoch.
    """
    def __init__(self, plan, stop_s, level, *, epoch_s):
        if not finite(stop_s) or stop_s not in plan["intervention"]["source_stops_s"]:
            raise ValueError("Unsupported source stop")
        if type(level) is not int or level not in (-1, 0, 1) or not finite(epoch_s):
            raise ValueError("Explicit level and finite epoch required")
        self.p = deepcopy(plan["intervention"])
        self.stop, self.level, self.epoch = stop_s, level, epoch_s
        self.pending, self.trigger = [], None
        self.last_clock = self.last_receipt = None
        self.latched = False

    def observe(self, packet):
        if not c1_manifold(packet):
            return
        source, receipt = packet.get("stamp_s"), packet.get("receipt_monotonic_s")
        if not finite(source) or not finite(receipt):
            raise ValueError("Contact source and receipt clocks required")
        if source >= self.epoch and self.trigger is None:
            self.pending.append(dict(source_s=source, receipt_monotonic_s=receipt,
                                     component=packet["channel"][8:]))

    def decide(self, stamp_s, receipt_monotonic_s, *, healthy, source_forward, nominal_v):
        if not all(finite(v) for v in (stamp_s, receipt_monotonic_s, nominal_v)) or stamp_s < self.epoch:
            raise ValueError("Finite decision clocks and nominal reference required")
        if type(healthy) is not bool or type(source_forward) is not bool:
            raise ValueError("Explicit health/source flags required")
        if (self.last_clock is not None and (stamp_s <= self.last_clock
                or receipt_monotonic_s < self.last_receipt)):
            raise ValueError("Decision clock duplicate/reversal")
        self.last_clock, self.last_receipt = stamp_s, receipt_monotonic_s
        elapsed = stamp_s - self.epoch
        if not healthy:
            self.latched = True
        available = [e for e in self.pending if e["source_s"] <= stamp_s
                     and e["receipt_monotonic_s"] <= receipt_monotonic_s]
        if self.trigger is None and available and elapsed < self.stop - self.p["withdraw_lead_s"] - 1e-8:
            event = min(available, key=lambda e: (e["receipt_monotonic_s"], e["source_s"]))
            self.trigger = dict(event, decision_stamp_s=stamp_s, decision_task_s=elapsed,
                                decision_receipt_monotonic_s=receipt_monotonic_s)
            self.pending.clear()
        active = bool(self.trigger and not self.latched and source_forward
                      and elapsed >= self.p["source_warmup_s"] - 1e-8
                      and elapsed < self.stop - self.p["withdraw_lead_s"] - 1e-8
                      and abs(nominal_v - self.p["nominal_steady_m_s"]) <= 1e-8)
        return dict(requested_common_m_s=self.level * self.p["common_bound_m_s"] if active else 0.0,
                    active=active, latched=self.latched, trigger=deepcopy(self.trigger),
                    oracle_only=True, loaded_contact_verified=False)


def reference_preview(plan, limits):
    """Synthetic contact at3.2s, receipt visible3.3s; not a body/wheel model."""
    from nino_control.residual_velocity import ReferenceLimits, ResidualReference
    result = []
    dt = plan["intervention"]["control_interval_s"]
    for stop in (6.0, 8.0):
        for level in (-1, 0, 1):
            schedule = PostManifoldPlan(plan, stop, level, epoch_s=0.0)
            schedule.observe(dict(channel="contact_caster_left_wheel", stamp_s=3.2,
                                  receipt_monotonic_s=103.3,
                                  values=[dict(collision1="nino::caster", collision2="cable_bumps::cables::C1_collision", points=1)]))
            nominal = ResidualReference(ReferenceLimits(**limits))
            reference = ResidualReference(ReferenceLimits(**limits))
            rows = []
            for tick in range(140):
                t = round(tick * dt, 9)
                forward = 0.5 <= t < stop
                source = (0.2 if forward else 0.0, 0.0)
                n = nominal.compose(source, (0.0, 0.0), dt, permission=True,
                                    sensors_fresh=True, history_ready=True, command_age_s=0.0)
                decision = schedule.decide(t, 100.0 + t, healthy=True, source_forward=forward,
                                           nominal_v=n["body_reference"][0])
                physical = decision["requested_common_m_s"]
                accepted = reference.compose(source, (physical / limits["residual_wheel_m_s"], 0.0),
                                             dt, authority=1.0, permission=True, sensors_fresh=True,
                                             history_ready=True, command_age_s=0.0)
                rows.append(dict(tick=tick, decision_task_s=t, source_v_m_s=source[0],
                                 accepted_reference=list(accepted["body_reference"]), **decision))
            result.append(dict(stop_s=stop, level=level, rows=rows))
    return result
