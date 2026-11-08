"""Versioned zero-settling candidate; frozen factory backends remain unchanged."""
from copy import deepcopy
import json
from .joint_reliability_candidate import ReliableBoundaryBackend
from .coverage_reset_readiness import assess_zero_reset


class DriveReadinessBackend(ReliableBoundaryBackend):
    def settle(self):
        """Require drive ACK AND physical quiet for 0.5s within the same 5s cap."""
        quiet=0.;rows=[]
        try:
            for _ in range(50):
                self.step_world(50);self.step_world(50);self._wait_feedback(self.time)
                with self.lock:
                    truth=deepcopy(self.messages['truth']['values'])
                    wheel=list(self.messages['wheel']['values'])
                    drive=deepcopy(self.messages['drive'])
                physically_quiet=(truth['speed_norm']<.01 and abs(truth['yaw_rate'])<.05
                    and max(map(abs,wheel))<.15 and max(abs(truth['roll']),abs(truth['pitch']))<.2)
                check=assess_zero_reset(drive['values'],source_age_s=self.time-drive['stamp_s'],
                    physically_quiet=physically_quiet)
                quiet=quiet+.1 if check['ready'] else 0.
                rows.append(dict(sim_time_s=self.time,physical_quiet=physically_quiet,
                    speed_norm_m_s=truth['speed_norm'],wheel_rad_s=wheel,
                    drive_stamp_s=drive['stamp_s'],drive=drive['values'],readiness=check,
                    continuous_ready_quiet_s=quiet))
                if quiet>=.5-1e-8:return
            raise RuntimeError('Drive ACK and zero-settling not established within 5 simulation seconds')
        finally:
            (self.episode_dir/'settling.json').write_text(json.dumps(dict(rows=rows,
                passed=quiet>=.5-1e-8,gate='drive_ack_and_physical_quiet_v1',
                maximum_setup_sim_s=5.,required_continuous_s=.5),indent=2)+'\n')
