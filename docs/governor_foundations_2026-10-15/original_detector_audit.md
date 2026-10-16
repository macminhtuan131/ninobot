# Governor clean-floor diagnostic

Offline shadow replay; changed actions were not physically executed

Full-speed runs physically executed; reactive decisions below are offline replay, not new motor commands.

| Maneuver | Steps | Max interval peak m/s² | Original events | Confirm .20 s | Confirm .30 s | Physical termination |
|---|---:|---:|---:|---:|---:|---|
| accelerate | 40 | 7.341 | 1 | 1 | 1 | none |
| brake_recover | 40 | 10.206 | 1 | 1 | 1 | none |
| turn | 40 | 4.931 | 1 | 1 | 1 | none |

## Contact/rolling diagnostics

Rolling ratio only when body speed >0.25 m/s, yaw rate <0.05 rad/s, swivel aligned within0.15 rad; simulator diagnostics, not a calibrated slip measurement

| Maneuver | Left median | Right median |
|---|---:|---:|
| accelerate | 0.990 | 0.256 |
| brake_recover | 0.987 | 0.319 |
| turn | unavailable | unavailable |

No physical arrival, positive-contact detection, H2, training or Optuna release is claimed.
A candidate needs closed-loop clean-floor confirmation and positive-contact detection before H2.
