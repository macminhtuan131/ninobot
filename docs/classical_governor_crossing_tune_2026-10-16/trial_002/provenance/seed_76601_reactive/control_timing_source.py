"""Read-only timing accumulator; never changes PI state, effort or scheduling."""
from math import isfinite


class ControlTimingWindow:
    def __init__(self):
        self.reset()

    def reset(self):
        self.count=self.invalid=self.fallbacks=self.long_intervals=self.future_joints=0
        self.total=0.
        self.minimum=self.maximum=self.joint_age_max=None

    def observe(self, raw_dt, joint_age=None):
        self.count+=1
        if isfinite(raw_dt):
            self.total+=raw_dt
            self.minimum=raw_dt if self.minimum is None else min(self.minimum,raw_dt)
            self.maximum=raw_dt if self.maximum is None else max(self.maximum,raw_dt)
            self.fallbacks+=int(raw_dt<=0. or raw_dt>.25)
            self.long_intervals+=int(raw_dt>.004+1.e-9)
        else:
            self.invalid+=1
        if joint_age is not None and isfinite(joint_age):
            self.joint_age_max=joint_age if self.joint_age_max is None else max(self.joint_age_max,joint_age)
            self.future_joints+=int(joint_age<-.001-1.e-9)

    def take(self):
        values=dict(control_updates=self.count, control_raw_dt_sum_s=self.total,
            control_raw_dt_min_s=self.minimum if self.minimum is not None else -1.,
            control_raw_dt_max_s=self.maximum if self.maximum is not None else -1.,
            control_dt_fallbacks=self.fallbacks,control_dt_invalid=self.invalid,
            control_dt_over_4ms=self.long_intervals,
            control_joint_age_max_s=self.joint_age_max if self.joint_age_max is not None else -1.,
            control_future_joint_updates=self.future_joints)
        self.reset()
        return values
