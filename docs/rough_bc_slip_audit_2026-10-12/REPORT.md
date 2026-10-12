# Rough BC-initialized PPO: saved slip and action audit

Completed revision 56 is preserved byte-for-byte with a verified duplicate. No simulation, learning, reward edits or scoring changes in this audit.

| Mode | PPO seconds | Reactive seconds | PPO slip RMS | Reactive slip RMS | Slip integral difference |
|---|---:|---:|---:|---:|---:|
| startup | 4.90 | 4.90 | 0.06654 | 0.05564 | +0.006527 |
| approach | 6.60 | 6.50 | 0.01109 | 0.00830 | +0.000365 |
| braking | 20.80 | 27.20 | 0.01374 | 0.01256 | -0.000362 |
| holding | 9.60 | 0.00 | 0.01143 | unavailable | +0.001254 |
| recovery | 20.80 | 27.20 | 0.01608 | 0.01659 | -0.002113 |
| cruise | 79.00 | 77.10 | 0.01480 | 0.01328 | +0.003698 |

Startup: first 1 s; approach: physical remaining distance <0.5 m. Else braking/recovery: scale changes exceeding 0.005 per interval; holding: unchanged scale below 0.98. The phase clock is unchanged.

## Executed wheel response

| Controller / mode | Wheel tracking RMSE rad/s | Applied torque RMS Nm | Limit fraction | Stale samples |
|---|---:|---:|---:|---:|
| PPO / startup | 0.6463 | 0.2242 | 0.0000 | 0 |
| PPO / cruise | 0.4809 | 0.2435 | 0.1141 | 0 |
| PPO / braking | 0.6263 | 0.2086 | 0.1471 | 0 |
| PPO / holding | 0.5007 | 0.2151 | 0.0760 | 0 |
| PPO / recovery | 0.5362 | 0.2511 | 0.1111 | 0 |
| PPO / approach | 0.2468 | 0.1031 | 0.0045 | 0 |
| Reactive PI / startup | 0.6440 | 0.2234 | 0.0000 | 0 |
| Reactive PI / cruise | 0.4900 | 0.2280 | 0.1214 | 0 |
| Reactive PI / braking | 0.5811 | 0.2328 | 0.0908 | 0 |
| Reactive PI / recovery | 0.5025 | 0.2629 | 0.1135 | 0 |
| Reactive PI / approach | 0.2569 | 0.1132 | 0.0092 | 0 |

## Exact actor replay

Original BC actor agreement with its teacher on PPO-visited tensors: 99.36%; final PPO: 93.44%.
During holding, PPO selected HOLD instead of teacher BRAKE 75 times; during recovery, HOLD instead of RECOVER 16 times.
Normal braking-to-recovery reversals are not counted as chatter. Per-seed same-event/same-phase reversals and all motor details are in analysis.json.

## Decision

Use the original demonstrated categorical actions as an auxiliary actor BC loss during holding/recovery; no global reward or speed-ramp change.
First check the auxiliary actor gradient against the PPO actor gradient; use a new contract. Keep reward weights, scoring, observations, geometry, bounds and ramp fixed.
Do not slow recovery or increase the global slip penalty from these results: recovery slip RMS is not worse than the reactive reference.
The proposed anchor targets demonstrated behavior erosion; it has not been shown to solve total-course slip.

Phase exposures and physical positions differ; phase comparisons are descriptive, not causal intervention results.
Startup/approach slip differs despite full-scale commands. It is not justified to attribute this difference to PPO braking or recovery.
Ground-truth slip is retained for scoring; no scoring exclusions or metric changes.
Five fixed nominal E1 scenarios, one training seed; no generalization conclusion.
