"""Separate E2 classical oracle context; frozen parent ABI/driver stay unchanged.

The oracle is an experimental schedule, never a sensor-only policy. This module
does not allocate launches. The coordinator requires a separate pinned release.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from nino_control.residual_velocity import ReferenceLimits, ResidualReference
from . import obstacle_authority_draft as draft
from . import equal_information_v2 as parent
from .coverage_reset_readiness import require_uninhibited_transition
from .pi_screen_backend import PiScreenBackend
from .pi_screen_contract import require_audit
from .gain_reference_map import diagnostic_support

CONTEXT_ID = "nino_fixed6mm_postmanifold_authority_runtime_v1"


def sources():
    from . import pi_screen_context, residual_drive_readiness
    paths = ["nino_rl/obstacle_authority_draft.py", "nino_rl/obstacle_authority_runtime.py",
             "nino_rl/obstacle_authority_runner.py", "nino_rl/obstacle_authority_metrics.py",
             "test/test_obstacle_authority_runtime.py", "test/test_obstacle_authority_runner.py",
             "scripts/obstacle_authority_runner.sh", "config/fixed6mm_postmanifold_authority_draft_v1.json"]
    return dict(parent=parent.fingerprint(), pi_context=pi_screen_context.fingerprint(),
                readiness=residual_drive_readiness.fingerprint(),
                files={p: hashlib.sha256((draft.ROOT / "src/nino_rl" / p).read_bytes()).hexdigest()
                       for p in paths})


def identity():
    record = dict(id=CONTEXT_ID, draft_id=draft.PROTOCOL_ID, sources=sources(),
                  observation="inherited causal100D history; oracle absent from features",
                  action="declared common sign only; +/-0.005m/s post-manifold oracle",
                  actor_loading_allowed=False, training_allowed=False, hardware_authorized=False,
                  parent_checkpoint_compatible=False)
    record["abi_sha256"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    return record


def configuration(stop_s):
    plan = draft.load()
    if type(stop_s) not in (int, float) or stop_s not in plan["intervention"]["source_stops_s"]:
        raise ValueError("Unsupported E2 stop")
    c, g, task, condition = parent.configuration(stop_s, "box_c1_6mm")
    c.update(purpose=CONTEXT_ID, hardware_authority=0.0)
    c["training"]["allowed"] = False
    c["backend"].update(pi_ki=0.10, sim_common_gain=1.0, max_episodes=1,
                        scenario_id="box_c1_6mm_postmanifold_authority_v1")
    task["protocol_id"] = CONTEXT_ID
    return c, g, task, condition


class ContactMailbox:
    """Used under the backend's existing RLock; bounded, exact receipt records."""
    def __init__(self, maximum=10000):
        self.rows, self.maximum = [], maximum

    def push(self, packet):
        if draft.c1_manifold(packet):
            if len(self.rows) >= self.maximum:
                raise RuntimeError("E2 contact mailbox full; no silent event drop")
            self.rows.append(deepcopy(packet))

    def snapshot(self, cursor, source_stamp, cutoff):
        if type(cursor) is not int or not 0 <= cursor <= len(self.rows):
            raise ValueError("Invalid E2 contact cursor")
        if not all(draft.finite(v) for v in (source_stamp, cutoff)):
            raise ValueError("Finite E2 decision clocks required")
        rows = deepcopy(self.rows[cursor:])
        if any(r["receipt_monotonic_s"] > cutoff for r in rows):
            raise ValueError("Snapshot includes a callback after the decision cutoff")
        return dict(source_stamp_s=source_stamp, decision_receipt_monotonic_s=cutoff,
                    cursor=len(self.rows), contacts=rows)


class OraclePiBackend(PiScreenBackend):
    """Read-only contact instrumentation on an unchanged, audited Ki0.10 kernel."""
    def __init__(self, *args, **kwargs):
        self.oracle_mailbox = ContactMailbox()
        super().__init__(*args, **kwargs)

    def _store(self, key, source, payload):
        # RLock makes raw storage, oracle copy and decision cutoff one ordering.
        with self.lock:
            super()._store(key, source, payload)
            if key.startswith("contact_"):
                self.oracle_mailbox.push(dict(channel=key, **self.messages[key]))

    def _contact(self, *args):
        try:
            super()._contact(*args)
        except Exception as exc:
            with self.lock:
                self.error = repr(exc)

    def oracle_snapshot(self, cursor):
        with self.lock:
            return self.oracle_mailbox.snapshot(cursor, self.time, time.monotonic())


class OracleAdapter:
    def __init__(self, config, stop_s, level, epoch_s, plan=None):
        self.plan = draft.load() if plan is None else plan
        self.schedule = draft.PostManifoldPlan(self.plan, stop_s, level, epoch_s=epoch_s)
        self.nominal = ResidualReference(ReferenceLimits(**config["reference_limits"]))
        self.config, self.epoch, self.stop, self.level = config, epoch_s, stop_s, level
        self.tick = self.cursor = 0

    def decide(self, view, history_ready, reference_latched, snapshot):
        if type(history_ready) is not bool or type(reference_latched) is not bool:
            raise ValueError("Explicit history/latch flags required")
        t = self.tick * 0.1
        stamp = snapshot["source_stamp_s"]
        if abs(stamp - self.epoch - t) > 1e-8 or abs(view["stamp_s"] - stamp) > 1e-8:
            raise ValueError("Decision, feature and simulation epoch mismatch")
        for field in ("permission", "sensors_fresh", "fault", "emergency_stop"):
            if type(view[field]) is not bool:
                raise ValueError("Explicit source health flags required")
        if snapshot["cursor"] != self.cursor + len(snapshot["contacts"]):
            raise ValueError("Oracle cursor reversed or contacts skipped")
        for contact in snapshot["contacts"]:
            if contact["receipt_monotonic_s"] > snapshot["decision_receipt_monotonic_s"]:
                raise ValueError("Contact received after decision cutoff")
            self.schedule.observe(contact)
        self.cursor = snapshot["cursor"]
        source = view["baseline"]
        nominal = self.nominal.compose(source, (0.0, 0.0), 0.1, permission=True,
                                      sensors_fresh=True, history_ready=True, command_age_s=0.0)["body_reference"]
        age = view["command_age_s"]
        source_health = bool(view["permission"] and view["sensors_fresh"] and not view["fault"]
                             and not view["emergency_stop"] and not reference_latched
                             and math.isfinite(age) and 0 <= age <= self.nominal.limits.max_age_s)
        # Initial history padding is the inherited warmup, not a recovered fault.
        healthy = source_health and (history_ready or t < 0.5 - 1e-8)
        decision = self.schedule.decide(stamp, snapshot["decision_receipt_monotonic_s"],
            healthy=healthy, source_forward=bool(source[0] > 0 and 0.5 - 1e-8 <= t < self.stop - 1e-8),
            nominal_v=nominal[0])
        common = decision["requested_common_m_s"] if history_ready else 0.0
        mapped = np.array([common / self.config["reference_limits"]["residual_wheel_m_s"], 0.0], np.float32)
        audit = dict(decision, decision_tick=self.tick, decision_task_s=t,
                     decision_source_stamp_s=stamp, decision_receipt_monotonic_s=snapshot["decision_receipt_monotonic_s"],
                     new_contact_records=deepcopy(snapshot["contacts"]), oracle_cursor=self.cursor,
                     requested_level=self.level, requested_common_m_s=common,
                     effective_scalar=common / 0.005, inherited_controller_proposal=mapped.tolist(),
                     nominal_shaped_body=list(nominal), history_ready=history_ready,
                     oracle_in_observation=False, source_health=source_health)
        self.tick += 1
        return mapped, audit


def environment(config, backend, task, condition, level, *, contract_identity=None):
    import gymnasium as gym
    from .residual_experiment import make_environment
    if config["training"]["allowed"] or config["hardware_authority"] != 0.0:
        raise ValueError("E2 has no learner/hardware authority")
    inner = make_environment(config, backend)
    ident = identity() if contract_identity is None else contract_identity

    class OracleEnv(gym.Wrapper):
        def __init__(self):
            super().__init__(inner)
            self.backend, self.done = backend, True
            self.action_space = gym.spaces.Box(-1, 1, (1,), dtype=np.float32)

        def reset(self, **kwargs):
            obs, info = self.env.reset(**kwargs)
            self.steps, self.done = 0, False
            self.score = parent.CommonScoreV2(config, task, condition, scenario="box_c1_6mm")
            self.adapter = OracleAdapter(config, task["command_until_s"], level,
                                         self.env.pipeline.last_view["stamp_s"])
            self.current_observation = obs.copy()
            return obs, dict(info, e2_identity=ident)

        def step(self, declared_level):
            if self.done:
                raise RuntimeError("E2 reset required after episode end")
            if np.asarray(declared_level).shape != (1,) or float(declared_level[0]) != level:
                raise ValueError("E2 accepts only its declared classical level, no actor")
            snapshot = self.backend.oracle_snapshot(self.adapter.cursor)
            before = self.current_observation.copy()
            mapped, audit = self.adapter.decide(self.env.pipeline.last_view,
                self.env.pipeline.history.ready, self.env.pipeline.reference.latched, snapshot)
            obs, _, term, trunc, info = self.env.step(mapped)
            self.steps += 1
            reward, result = self.score.update_request(info, [audit["effective_scalar"]],
                audit["active"], self.steps * 0.1, term)
            np.testing.assert_allclose(audit["nominal_shaped_body"], result["nominal_shaped_body"], atol=1e-10, rtol=0)
            if result["task_deadline"] and not term:
                term, trunc = True, False
                info["termination_reason"] = "task_success" if result["task_success"] else "task_deadline_failure"
            self.done = bool(term or trunc)
            self.current_observation = obs.copy()
            return obs, reward, bool(term), bool(trunc), dict(info, task=result,
                reward_terms=result["reward_terms"], oracle_decision=audit,
                controller_proposal=mapped.tolist(), e2_identity=ident["id"],
                equal_observation=before, equal_next_observation=obs.copy(),
                abi_sha256=ident["abi_sha256"], experiment_contract=ident["abi_sha256"])

    return OracleEnv()


def verify_transition(row, previous, epoch, ident):
    require_uninhibited_transition(row)
    from .residual_common_td3 import feasibility
    feasibility(row, 0.04)
    a, trace = row["oracle_decision"], row["reference_trace"]
    if row["abi_sha256"] != ident["abi_sha256"] or row["e2_identity"] != CONTEXT_ID:
        raise ValueError("E2 identity mismatch")
    if (a["decision_tick"] != row["step"]
            or abs(a["decision_source_stamp_s"] - epoch - row["step"] * 0.1) > 1e-8
            or abs(trace["input_stamp_s"] - a["decision_source_stamp_s"]) > 1e-8
            or abs(row["sensor_clock_s"] - epoch - row["task"]["elapsed_s"]) > 1e-8):
        raise ValueError("E2 decision/measurement timing mismatch")
    if previous and (a["decision_receipt_monotonic_s"] < previous["oracle_decision"]["decision_receipt_monotonic_s"]):
        raise ValueError("E2 receipt cutoff reversed")
    if previous and abs(row["sensor_clock_s"] - previous["sensor_clock_s"] - 0.1) > 1e-8:
        raise ValueError("E2 native observation gap")
    if row["controller_proposal"] != list(trace["proposal"]):
        raise ValueError("E2 proposal trace mismatch")
    if row["controller_proposal"][1] != 0 or abs(row["controller_proposal"][0]) > 0.125:
        raise ValueError("E2 residual outside common-only bound")
    expected = a["requested_level"] * .005 if a["active"] else 0.0
    if (a["requested_level"] != row["qualification_condition"]["level"]
            or a["requested_common_m_s"] != expected
            or a["inherited_controller_proposal"] != row["controller_proposal"]):
        raise ValueError("E2 declared condition/request changed")
    if not a["active"] and any(row["controller_proposal"]):
        raise ValueError("E2 closed window emitted residual")
    if a["trigger"]:
        event = a["trigger"]
        if event["source_s"] > event["decision_stamp_s"] or event["receipt_monotonic_s"] > event["decision_receipt_monotonic_s"]:
            raise ValueError("E2 trigger used future information")
    if set(trace["source_samples"]) != {"imu", "wheel", "baseline", "final", "status"}:
        raise ValueError("Oracle entered the deployable feature packet")
    require_audit(row["pi_screen_audit"], 0.10)
    if not diagnostic_support(row["pi_screen_audit"]["sim_time_s"],
                              row["drive_diagnostics"]["sim_time_s"], row["sensor_clock_s"]):
        raise ValueError("PI diagnostic timing mismatch")
    drive, gain = row["drive_diagnostics"], row["gain_map_audit"]
    if not all(math.isfinite(v) for v in [*drive.values(), *gain.values()]):
        raise ValueError("Nonfinite E2 driver/map telemetry")
    if gain["common_gain"] != 1.0 or gain["map_calls_this_update"] != 1.0 or gain["post_limit_targets_valid"] != 1.0:
        raise ValueError("E2 gain-one mapping invalid")
    if gain["map_active"] != 1 or gain["speed_clip_required"] or not diagnostic_support(
            gain["sim_time_s"], drive["sim_time_s"], row["sensor_clock_s"]):
        raise ValueError("E2 gain map support or clipping invalid")
    np.testing.assert_allclose([gain["reference_linear_m_s"], gain["reference_yaw_rad_s"]],
                              [drive["executed_linear_m_s"], drive["executed_yaw_rad_s"]], atol=1e-10, rtol=0)
    np.testing.assert_allclose([gain["effective_linear_m_s"], gain["effective_yaw_rad_s"]],
                              [drive["executed_linear_m_s"], drive["executed_yaw_rad_s"]], atol=1e-10, rtol=0)
    np.testing.assert_allclose(row["applied_target_rad_s"],
                              [gain["left_target_rad_s"], gain["right_target_rad_s"]], atol=1e-10, rtol=0)
    np.testing.assert_allclose(row["final_ros_reference"], [drive["executed_linear_m_s"], drive["executed_yaw_rad_s"]], atol=1e-10, rtol=0)
    np.testing.assert_allclose(row["applied_target_rad_s"], [drive["left_target_rad_s"], drive["right_target_rad_s"]], atol=1e-10, rtol=0)
    if max(map(abs, row["applied_target_rad_s"])) > 12 + 1e-8 or any(abs(drive[k]) > 4 + 1e-8 for k in ("left_applied_nm", "right_applied_nm")):
        raise ValueError("E2 actuator limit violated")
    return row


def fixture_backend(config, stop_s, *, contact=True):
    """Reduced-order software fixture; no claim to Ki/contact dynamics."""
    from .residual_equal_information import fixture_backend as base
    backend = base(config, stop_s)
    def snapshot(cursor):
        packet = dict(channel="contact_caster_left_wheel", stamp_s=3.2,
                      receipt_monotonic_s=103.3, values=[dict(collision1="nino::caster",
                      collision2="cable_bumps::cables::C1_collision", points=1)])
        rows = [packet] if contact and cursor == 0 and backend.time >= 3.3-1e-8 else []
        return dict(source_stamp_s=backend.time, decision_receipt_monotonic_s=100+round(backend.time, 9),
                    cursor=max(cursor, int(bool(rows))), contacts=rows)
    backend.oracle_snapshot = snapshot
    return backend


def neutral_parity():
    results = []
    for stop in (6.0, 8.0):
        c, _, task, condition = configuration(stop)
        c["backend"].update(wheel_gain=[1.0, 1.0], motor_lag_s=[0.16, 0.16], imu_noise_std=0.0)
        old = parent.environment(c, fixture_backend(c, stop), task, condition, "box_c1_6mm")
        new = environment(c, fixture_backend(c, stop), task, condition, 0)
        try:
            a, _ = old.reset(seed=701); b, _ = new.reset(seed=701)
            for tick in range(140):
                np.testing.assert_array_equal(a[:100], b)
                a, r1, t1, u1, i1 = old.step(np.array([0.0], np.float32))
                b, r2, t2, u2, i2 = new.step(np.array([0.0], np.float32))
                if (r1, t1, u1) != (r2, t2, u2):
                    raise ValueError("Neutral reward/termination parity failed")
                for key in ("reference_trace", "applied_target_rad_s", "final_ros_reference"):
                    if i1[key] != i2[key]:
                        raise ValueError("Neutral reference/history parity failed: " + key)
            if not t2 or u2:
                raise ValueError("Neutral fixture did not reach clean task deadline")
            results.append(dict(stop_s=stop, paired_decisions=140, exact_parity=True,
                                trigger_observed=i2["oracle_decision"]["trigger"] is not None))
        finally:
            old.close(); new.close()
    return results
