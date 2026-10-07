# Flat speed-only ablation — completed 2026-10-07

## Matched comparison

All three controllers completed 24 episodes on stage 2, seeds 60000–60023,
two course cables with angle draws within ±2°, and no adaptive items. The
benchmark hashes, recorded per-seed cable/task settings, and model SHA-256
were checked. The saved 952,343-step model was unchanged.

| Metric | PI baseline | Full saved PPO | PPO speed-only |
|---|---:|---:|---:|
| Physical success | 23/24 (95.8%) | 11/24 (45.8%) | 20/24 (83.3%) |
| Timeouts | 1 | 13 | 4 |
| Physical path RMSE | 0.0323 m | 0.1928 m | 0.0309 m |
| Physical endpoint error | 0.2022 m | 0.3105 m | 0.2020 m |
| Final odometry–truth position difference | 0.3279 m | 0.4576 m | 0.1768 m |
| RMS wheel slip | 0.1905 | 0.1527 | 0.1514 |
| RMS vertical acceleration | 3.3004 m/s² | 3.6912 m/s² | 1.4454 m/s² |
| Successful completion time | 20.50 s | 20.34 s | 28.61 s |
| Success within 22 s target | 20/24 | 7/24 | 0/24 |

Completion has a 30 s failure deadline; the 22 s target is a separate timing
objective. Speed-only completes most missions but misses that timing target.

## What the ablation supports

Removing the learned torque branches recovered much of physical success and
tracking while reducing slip and impacts. This points to the additive torque
correction path as a major problem in the tested configuration. The speed-only
controller is about eight seconds slower on successful episodes than PI.

For the 19 matching seeds where PI and speed-only both succeeded, path RMSE
was 0.0301 m versus 0.0239 m, slip 0.1890 versus 0.1535, and vertical RMS
acceleration 3.7779 versus 1.4238 m/s². Thus the comfort benefit is also present
after excluding failed episodes; reduced travel speed remains a confounder.

These are closed-loop ablations, not replayed speed commands: action-history
masking and changed robot motion can change later predictions. ROS/Gazebo
transport remains asynchronous. The test does not isolate the common-mode
and differential torque branches separately or establish robustness to six
cables, large cable angles, adaptive items, or hardware.

## Four remaining speed-only failures

| Seed | Physical goal distance | Estimated goal distance | Final ground speed | Outcome |
|---|---:|---:|---:|---|
| 60000 | 0.2233 m | 0.0468 m | approximately zero | Timeout after premature stop |
| 60003 | 0.2139 m | 0.1439 m | 0.0192 m/s | Timeout while still moving |
| 60022 | 0.2106 m | 0.0612 m | 0.0206 m/s | Timeout while still moving |
| 60023 | 0.2161 m | 0.0485 m | approximately zero | Timeout after premature stop |

Two failures stopped inside the estimated 5 cm circle while physically
outside the 20 cm goal radius. Two were still approaching slowly when the
30 s deadline elapsed. Goal approach and estimated/physical pose agreement
remain issues alongside the learned speed schedule.

## Recommended next work

1. Keep stage 2 and the physical 0.20 m goal check, 22 s target, and 30 s
   deadline. Correct near-goal stopping/approach behavior; aiming further
   inside the estimated circle and retaining sufficient approach speed are
   proposed mitigations, not a replacement for reliable localization.
2. Keep wheel-speed PI as the motor controller. Prepare a corrected RL
   control interface that selects speed and bounded steering references
   instead of large additive steering torques. This preserves differential
   wheel control through the PI wheel targets. Changing action meanings needs
   a new training contract/profile; direct checkpoint resume would be invalid.
3. Run a short stage-2 pilot, then compare physical success, timing, tracking,
   slip and impacts against PI before extending training or adding a cable.

The speed-only option was an evaluation intervention. The saved checkpoint
still outputs its original torque actions; resuming the old training command
would restore them. No corrected training run was started in this analysis.

## Saved evidence

- [Speed-only summary](summary.json)
- [Comparison against PI](comparison_vs_pi.json)
- [Comparison against full PPO](comparison_vs_full_ppo.json)
- [Matched successful-episode statistics and failure records](ablation_analysis.json)
- [Per-episode records](episodes.csv)
