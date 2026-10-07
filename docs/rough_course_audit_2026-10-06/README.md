# Rough-course audit — 2026-10-06

## Conclusion

The terrain is physically uneven. The weak point is what the benchmark establishes: arrival on one fixed surface does not establish that RL improves terrain adaptation beyond the existing wheel PI controller. There is not enough evidence to conclude that the policy learned nothing.

This audit uses the actual mesh, current source, the saved rough-run configuration, and existing episode logs. No new Gazebo evaluation was run. Flat training was not stopped or modified.

Evidence: [geometry preview](geometry_audit.png), [measured values and hashes](evidence.json).

## Geometry

- Visual and collision use the same STL and pose. There is no flat floor covering the rough section.
- Ground height ranges from −16.4 cm to +24.4 cm. Maximum sampled slope across the hall is 28.7°. This maximum is not the slope of the entire driving route.
- Ideal straight drive-wheel paths can differ in ground height by 9.9 cm. The map therefore contains real asymmetric disturbances.
- Five of the nine added broad bowls do not intersect either ideal straight drive-wheel path. They may still affect casters or a drifting robot, but their presence alone does not establish exposure during training.
- The terrain is baked with seed 42. Changing an evaluation seed does not generate a new physical terrain mesh.

In the preview, blue outlines are added broad bowls, orange outlines are wheel-size bowls, and black numbered circles are reward regions. The black numbers are reward-region identifiers, not the user's previous bowl labels.

## What success measures

For this task, `core.goal_reached()` checks endpoint distance ≤0.20 m and heading error ≤20°. It does not check final speed, tilt, or path quality. The rough configuration allows 1.0 m of lateral deviation before its sustained off-path failure condition.

The configuration has `goal_require_stopped: false`. Even if that flag were enabled, the current generic goal function does not implement its state checks. A stop task needs an implemented stop gate; a rough-to-flat policy handoff can legitimately finish moving and needs a separate handoff gate.

Reward and success use simulator ground-truth pose; the actor uses estimated wheel odometry and sensor inputs. An estimated goal-distance log above 0.20 m on a successful episode is therefore not by itself evidence of fabricated success.

The five fixed challenge regions are separate circular metadata, while the carved bowls are elliptical and more numerous. The tracker projects wheel positions into XY regions and checks forward clearance. It does not measure physical contact, wheel loading, bottoming out, or recovery quality. Thus “5/5 cleared” is a geometric traversal flag, not proof of five well-controlled physical crossings.

Adaptive terrain, curriculum, and domain randomization are disabled in the saved rough configuration. All 43 episode layouts are empty. The adaptive progress counter can still advance because its outcome recorder checks progression rather than spawning enablement. The configured adaptive spawn zone is beyond this rough course's goal, so enabling it alone would not fix coverage.

## Latest stopped run

Run: `rl_runs/rough_specialist/20261005-193508-209000`, interrupted checkpoint at **676,124 steps**.

| Measure | Result |
|---|---:|
| Logged episodes in this run | 43 |
| Goal successes | 25 / 43 = 58.1% |
| Collision terminations | 16 |
| Timeouts | 2 |
| Mean physical path RMSE, successful episodes | 16.8 cm |
| Mean physical endpoint error, successful episodes | 19.1 cm |
| Mean odometry-to-truth position error, successful episodes | 26.7 cm |
| Successful episodes finishing faster than 0.10 m/s | 23 / 25 |
| Mean peak tilt, successful episodes | 19.7° |
| Mean commanded speed scale, successful episodes | 0.668 |

These are training episodes, not a fresh deterministic validation set. They must not be directly treated as regression against an earlier high-success rolling window with different sampling or run conditions. Tilt above 10° during traversal is also not automatically inappropriate on sloping ground.

In successful episodes, mean terminal reward is +100 and the five-region completion bonus is +90. Mean impact penalty is −4.61 and attitude penalty −3.18, while lateral penalty is −58.07. This is evidence that arrival and geometric completion dominate several comfort terms, not evidence that all quality terms are absent.

## Recommended next revision

1. **Measure the RL contribution first.** Compare straight PI, PI at a reduced fixed speed matching RL's average command, learned speed with torque residuals masked, and full RL on identical conditions. The last two ablations need explicit evaluation support. Report physical tracking error, completion time, impact, slip, and torque alongside goal success. A straight PI baseline is not equivalent to a tuned trajectory PID baseline.
2. **Separate arrival from quality.** Keep `goal_success`, add tracking and recovery metrics, and implement either a stop gate or a moving handoff gate. Initial trajectory targets such as 10 cm RMS and 20 cm peak error are proposed calibration targets, not validated thresholds or current rules. Check feasibility against the baseline.
3. **Use one geometry definition for mesh and scoring.** Export bowl footprints, wheel-scale features, and slope zones from the generator. Distinguish geometric passage from stable exit. Fix disabled adaptive counters before interpreting curriculum charts.
4. **Rebuild for controlled disturbances, not uniformly deeper terrain.** Start with mild broad slopes, then a single left-wheel hole, a right-wheel hole, staggered holes, and mixed mounds. Place selected disturbances on the drive-wheel tracks. Keep safe approaches and a flat handoff pad. The existing map already has steep areas; making everything deeper risks replacing a weak benchmark with an unreliable physics challenge.
5. **Train and test on different physical surfaces.** Generate several feasible meshes with varied hole positions, widths, depths, and slope transitions; reserve unseen meshes for validation. Add realistic pose, sensor, and dynamics variation progressively. Current `traction` randomization multiplies residual torque; it does not change Gazebo ground friction.
6. **Investigate state-estimation error.** The observed odometry discrepancy can undermine trajectory feedback. Evaluate IMU/odometry fusion and independent localization before attributing every drift problem to reward weights.

Retain the existing checkpoint for comparisons and possible compatible initialization. A changed terrain/reward benchmark needs a new run identity and validation set. Do not carry old success percentages forward as evidence for the redesigned course.

## Research context

[Residual Reinforcement Learning for Robot Control](https://arxiv.org/abs/1812.03201) supports combining learned residuals with conventional feedback; it does not establish that this robot's residual policy improves its baseline. [Sim-to-Real Transfer of Robotic Control with Dynamics Randomization](https://arxiv.org/abs/1710.06537) motivates varied simulated dynamics, but its results do not guarantee transfer for this wheeled robot.
