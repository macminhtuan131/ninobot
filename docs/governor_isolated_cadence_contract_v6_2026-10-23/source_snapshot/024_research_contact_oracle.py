"""Simulation-only H2 intervention. Never import into the deployed governor.

The oracle supplies only the first positive cable contact. Core timing,
feedback checks, speed limits, ramp and release rules remain intact. Automatic
sensor triggering is disabled for this experiment, including before contact.
This is an upper-bound authority test, not a deployable contact detector.
"""
from dataclasses import replace
from threading import Lock
import time

from nino_control.governor_core import GovernorSettings, ReactiveGovernor


class ContactGate:
    def __init__(self):
        self.lock = Lock()
        self.reset(None)

    def reset(self, epoch):
        with self.lock:
            self.epoch, self.first = epoch, None

    def observe(self, stamp, component, collisions, received_sim, received_wall):
        if not any("cable_bumps" in name or "training_cable" in name for name in collisions):
            return
        with self.lock:
            if self.epoch is None or stamp < self.epoch:
                return
            event = dict(contact_time_s=stamp, component=component, collisions=list(collisions),
                         receipt_clock_s=received_sim, receipt_monotonic_s=received_wall)
            # Earliest stamped contact among messages received before decision.
            # A later-arriving older message must not revise an executed decision.
            if self.first is None or stamp < self.first["contact_time_s"]:
                self.first = event

    def snapshot(self):
        with self.lock:
            return dict(self.first) if self.first is not None else None


class OracleIntervention(ReactiveGovernor):
    def __init__(self, settings):
        settings = settings if isinstance(settings, GovernorSettings) else GovernorSettings(**settings)
        # No threshold tuning: suppress automatic triggering explicitly. Original
        # hysteresis still determines moderate-profile release after injection.
        super().__init__(replace(settings, startup_seconds=1.e12))

    def reset(self):
        super().reset()
        self.oracle_contact = None
        self.oracle_command_time = None

    def accept(self, event, command_time):
        if self.oracle_contact is not None or event is None or event["contact_time_s"] > command_time + 1.e-9:
            return
        self.oracle_contact = dict(event)
        self.oracle_command_time = command_time
        if self.settings.profile != "full" and self.phase != "FAILSAFE":
            self.phase, self.hold_elapsed, self.quiet, self.confirmed = "HOLD", 0., 0., 0.
            self.armed = False
            self.events += 1


def environment_factory(config, **kwargs):
    """Explicit opt-in factory; normal evaluate/train cannot activate the oracle."""
    from nino_rl.ros_env import NinoGazeboEnv
    from rclpy.qos import qos_profile_sensor_data
    from ros_gz_interfaces.msg import Contacts
    from nino_rl.governor_logger import CONTACT_COMPONENTS

    experiment = config.get("research_experiment", {})
    if (experiment.get("kind") != "post_contact_oracle_h2" or
            config.get("research_map", {}).get("training_allowed") is not False or
            config.get("research_map", {}).get("optuna_allowed") is not False):
        raise ValueError("Oracle requires an explicit simulation-only, non-training contract")

    class OracleEnv(NinoGazeboEnv):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.governor = OracleIntervention(self.config["governor"]["parameters"])
            self.contact_gate = ContactGate()
            self.contact_subscriptions = [self.ros.create_subscription(
                Contacts, "/nino/contact_lab/" + component,
                lambda msg, component=component: self.on_oracle_contact(component, msg),
                qos_profile_sensor_data) for component in CONTACT_COMPONENTS]

        def on_oracle_contact(self, component, msg):
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1.e-9
            for contact in msg.contacts:
                self.contact_gate.observe(stamp, component,
                    (contact.collision1.name, contact.collision2.name),
                    self.ros.latest_clock_stamp(), time.monotonic())

        def reset(self, **kwargs):
            self.contact_gate.reset(None)
            result = super().reset(**kwargs)
            self.contact_gate.reset(self.lockstep_sim_time)
            return result

        def _governor_command(self, linear, angular):
            self.governor.accept(self.contact_gate.snapshot(), self.lockstep_sim_time)
            command = super()._governor_command(linear, angular)
            event = self.governor.oracle_contact or {}
            # Fixed columns from the first action, including when not contacted.
            self.governor_trace.update(
                oracle_contact_time_s=event.get("contact_time_s"),
                oracle_contact_component=event.get("component"),
                oracle_receipt_clock_s=event.get("receipt_clock_s"),
                oracle_receipt_monotonic_s=event.get("receipt_monotonic_s"),
                oracle_command_time_s=self.governor.oracle_command_time)
            return command

    return OracleEnv(config, **kwargs)
