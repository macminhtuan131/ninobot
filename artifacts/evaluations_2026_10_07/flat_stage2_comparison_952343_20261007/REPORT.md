# Flat two-cable evaluation — 2026-10-07

Frozen final policy: **952,343 cumulative training steps**.

## Test conditions

- 24 episodes per controller; matching seeds 60000–60023, run sequentially on ROS domain 79 / Gazebo partition `nino_flat_79`.
- Stage 2 (`two_cables`): course cable indices 2 and 4, angle draws within ±2°, no adaptive items and no easier-stage replay.
- Saved training config used for both; physical goal radius 0.20 m and heading tolerance 20°; mission deadline 30 simulation seconds.
- Deterministic PPO inference; model SHA-256 unchanged. PI uses full reference speed scale with zero learned torque residuals.
- PI is the existing straight-reference wheel-speed PI controller, without Nav2 or an outer path PID.
- Controller pose comes from wheel odometry. Goal scoring and reported physical errors use Gazebo ground truth, which is not given to the actor as pose.
- Broad sensor/traction domain randomization disabled for this controlled comparison; stage cable-angle sampling remains active.
- Goal success measures arrival, not docking: `goal_require_stopped` is false.

## Results

| Metric | PI baseline | Saved PPO |
|---|---:|---:|
| Physical success | 23/24 (95.8%) | 11/24 (45.8%) |
| Mean physical path rmse (m) | 0.0323 | 0.1928 |
| Mean physical endpoint error (m) | 0.2022 | 0.3105 |
| Mean final odometry–truth position difference (m) | 0.3279 | 0.4576 |
| Mean rms wheel slip (ratio) | 0.1905 | 0.1527 |
| Mean rms vertical acceleration (m/s²) | 3.3004 | 3.6912 |
| Mean peak vertical acceleration (m/s²) | 93.0986 | 108.0530 |
| Mean rms applied wheel torque (N·m) | 0.3785 | 0.3454 |
| Successful episode completion time (s) | 20.50 | 20.34 |

Terminations: PI `{'success': 23, 'timeout': 1}`; PPO `{'success': 11, 'timeout': 13}`.

Paired outcomes: `{'both_succeed': 11, 'only_ppo_succeeds': 0, 'only_pi_succeeds': 12, 'both_fail': 1}`.

### Same seeds where both controllers succeed

11 matched episodes. This reduces the effect of different failure/success subsets when comparing tracking and impacts.

| Metric | PI | PPO |
|---|---:|---:|
| Physical path RMSE (m) | 0.0306 | 0.0902 |
| Physical endpoint error (m) | 0.1981 | 0.1991 |
| Final odometry–truth position difference (m) | 0.3676 | 0.3352 |
| RMS wheel slip (ratio) | 0.1981 | 0.1613 |
| RMS vertical acceleration (m/s²) | 4.4024 | 4.0540 |
| Peak vertical acceleration (m/s²) | 125.7583 | 105.9060 |
| RMS applied wheel torque (N·m) | 0.3878 | 0.3751 |
| Completion time (s) | 20.5545 | 20.3364 |

## Interpretation and next action

The saved PPO is worse than PI on physical success and tracking in this test. Its lower slip does not compensate for missed goals. Another unchanged long training run is not justified by these results.

Keep this checkpoint and benchmark as the reference. Next, diagnose the learned speed/torque corrections with a short controlled ablation, prioritizing trajectory/heading recovery and arrival over slip alone. Re-evaluate the corrected candidate against PI before increasing the training budget or adding a third cable.

Both controllers also exhibit wheel-odometry drift. PI seed 60009 stopped with estimated goal distance about 0.047 m while its physical distance remained about 0.298 m. PPO seed 60012 similarly stopped at estimated distance about 0.050 m while physically about 0.367 m away. Arrival estimation therefore needs attention alongside the learned corrections.

The benchmark is only 24 trials with two nearly perpendicular cables. It does not qualify six cables, adaptive obstacles, the rough course, real hardware, or general terrain robustness. Matching seeds/settings does not eliminate asynchronous ROS/Gazebo variation. There is no attribution to one reward term without an ablation.

## Artifacts

- [Full comparison](comparison.json)
- [Additional checks and matched-success means](analysis.json)
- [Paired episode records](paired_episodes.csv)
- [Model/config provenance](provenance.json)
- PPO summary: `ppo/20261007-075201-497157/summary.json`
- PI summary: `pi/20261007-080552-516226/summary.json`
- Each timestamped evaluation folder contains config, metadata, episode CSVs, and estimated/physical trajectory CSVs and plots.
