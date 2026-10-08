# Rough E1 odometry audit

| Seed | Classification | Estimated goal (m) | Physical goal (m) | Pose disagreement (m) | Wheel reconstruction vs odom (m) |
|---|---|---:|---:|---:|---:|
| 10000 | premature_estimated_stop | 0.049 | 0.378 | 0.384 | 0.020 |
| 10002 | success | 0.097 | 0.199 | 0.178 | 0.056 |
| 10001 | premature_estimated_stop | 0.048 | 0.340 | 0.335 | 0.032 |

## Interpretation

A fresh zero motion command outside the physical goal identifies a navigation stop. Reconstructed wheel odometry checks numerical consistency with sampled wheel feedback; it cannot correct physical drift or establish its cause.

## Limitations

- 50 Hz wheel feedback reconstruction approximates the 500 Hz odometry integrator; differences do not prove a software bug.
- Control trace poses are latest sensor snapshots, not exactly synchronized pose measurements.
- Joint message header timestamps and IMU samples were not recorded in these CSVs; sensor latency, pitch effects and slip causes cannot be isolated.
- Geometry uses the current effort_drive defaults; pass overrides if the launch used other values.
- Physical and estimated poses are compared in the common reset frame used by this E1 evaluation.
