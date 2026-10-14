"""Explicit command ownership and wall-clock expiry, independent of ROS."""
from math import isfinite


class CommandSelection:
    def __init__(self, timeout=.3, max_forward=.2, max_reverse=.1, max_yaw=.6):
        values = [timeout, max_forward, max_reverse, max_yaw]
        if not all(isfinite(v) and v > 0 for v in values):
            raise ValueError("Command timeout and speed bounds must be finite and positive")
        self.timeout, self.max_forward, self.max_reverse, self.max_yaw = values
        self.enabled = False
        self.navigation = False
        self.stopped = False
        self.commands = {}

    def enable(self, enabled):
        self.commands.clear()
        if enabled and self.stopped:
            return False
        self.enabled = bool(enabled)
        return True

    def mode(self, navigation):
        self.navigation = bool(navigation)
        self.commands.clear()

    def stop(self):
        self.stopped = True
        self.enabled = False
        self.commands.clear()

    def reset_stop(self):
        if self.enabled:
            return False
        self.stopped = False
        self.commands.clear()
        return True

    def receive(self, source, forward, yaw, stamp):
        if source not in ("manual", "navigation"):
            raise ValueError("Unknown velocity source")
        if not all(isfinite(v) for v in (forward, yaw, stamp)):
            self.commands.pop(source, None)
            return False
        # Commands observed while disabled are not retained for later arming.
        if self.enabled and not self.stopped:
            self.commands[source] = (forward, yaw, stamp)
        return True

    def output(self, now):
        if not self.enabled or self.stopped or not isfinite(now):
            return 0., 0.
        command = self.commands.get("navigation" if self.navigation else "manual")
        if command is None or not 0 <= now-command[2] <= self.timeout:
            return 0., 0.
        forward, yaw, _ = command
        return (max(-self.max_reverse, min(self.max_forward, forward)),
                max(-self.max_yaw, min(self.max_yaw, yaw)))
