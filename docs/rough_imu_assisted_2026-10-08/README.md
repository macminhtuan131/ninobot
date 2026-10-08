# Optional IMU-assisted rough odometry — 2026-10-08

## Implemented profile

`src/nino_rl/config/rough_e1_imu_assisted.yaml` enables a local encoder/IMU
estimator for fixed E1 on the original expanded rough terrain.

- Integrate continuous left/right encoder position increments, not sampled
  velocity multiplied by a control timer's elapsed time.
- Interpolate IMU relative heading and pitch at encoder simulation timestamps.
  No future IMU observation is extrapolated across a paused action boundary.
- Project encoder travel horizontally with `cos(pitch)` and integrate using
  midpoint heading.
- Reset encoder baselines and relative heading at every episode reset; ignore
  old/duplicate timestamps and reject excessive sensor gaps.
- Feed the assisted pose to route steering and the policy's navigation inputs.
  Raw `/odom`, effort-drive PI, action decoding and terrain geometry are retained.
- Publish diagnostic `/nino_rl/assisted_odom` in local `odom_imu` coordinates.
  This does not publish TF or replace Nav2 localization. Fixed covariance uses
  the raw driver's defaults; this is not an uncertainty-estimating EKF.
- Reject missing/invalid IMU orientation and stale assisted poses. There is no
  silent fallback to raw wheel odometry in an assisted episode.
- Continue measuring physical arrival and path accuracy with independent
  Gazebo ground truth. The physical goal radius remains **0.20 m**.

The default estimator remains wheel odometry when the new option is absent.
This implementation assumes continuous encoder positions and the project's
body-aligned IMU mounting. A differently mounted IMU needs an extrinsic
rotation before using its heading/pitch. Relative orientation drift and wheel
distance slip may still require independent position localization.

## PI validation completed

| Check | Seeds | Physical arrivals | Mean time | Physical path RMSE |
|---|---|---:|---:|---:|
| Normal PI | 10000–10004 | 5/5 | 26.92 s | 0.0232 m |
| PI speed scale 0.55 | 10000, 10002, 10001 | 3/3 | 57.50 s | 0.0393 m |
| One-degree orientation noise, 20 ms IMU delay | 10000–10002 | 3/3 | 26.90 s | 0.0339 m |

All 11 episodes met the physical arrival criterion. Clock error stayed below
0.02 s and motion/assisted-pose lag below 0.04 s. Validation results, paths and
engineering gates are in `validation.json`. Full raw/assisted pose traces and
physical trajectories are saved under `rl_runs/rough_imu_assisted_validation`.

These checks qualify a short E1 training pilot. They do not establish
unseen-terrain performance, multiple-route reliability, hardware transfer or
independent-seed repeatability. The perturbed profile affects estimator
heading/pitch only; other actor IMU channels retain their existing sensor model.
Changing the estimator also changes benchmark identity, so older raw-odometry
results are descriptive comparisons, not identical-contract evaluations.

Verification: **43 focused tests passed**, package build succeeded, and an
offline transfer check confirmed all 13 actor tensors match the preserved
model while critic tensors, optimizer and step counter remain fresh.

## Rough RL pilot restarted

Profile: `src/nino_rl/config/rough_e1_imu_assisted.yaml`.

- Source: `artifacts/rough_routes_112589/nino_ppo_interrupted.zip`.
- Actor initialization; fresh critic, optimizer and counter. New contract
  revision **35** prevents raw-odometry checkpoint optimizer resume.
- Three existing actions: speed scaling, common torque and differential torque.
- Reward and PPO settings stay inherited from the rough E1 profile.
- Budget: **20,000 requested steps**, approximately **20,480** with 2,048-step
  rollouts. Checkpoints every 1,024 steps.
- Fixed original terrain and E1; no automatic route/stage progression in this
  pilot. Additional routes precede terrain randomization in subsequent work.
- CUDA, ROS domain 78, Gazebo partition `nino_rough_78`.
- Run: `rl_runs/rough_e1_imu_assisted_pilot/20261008-013943-771247`.
- Mandatory 12-point live preflight and `--check-env` passed. Training became
  active on CUDA after copying the source actor. Initial rollout collection
  is not evidence of learned improvement.

The first two recorded training episodes were one timeout and one physical
arrival (44.10 s). The timeout stopped with an estimated goal distance of
0.0476 m while physically 0.3415 m away. PI validation therefore does not
guarantee accuracy under the transferred actor's torque corrections and
exploration. This failure is correctly scored as a failure; wheel distance
drift remains a risk even with IMU-assisted heading. Evaluate the final actor
before increasing the budget or claiming that premature stopping is solved
for every controller.

Initialization provenance is saved in the run's `actor_transfer.json` including
source checksum and original training-step count. Launcher PID is recorded in
`rl_runs/rough_e1_imu_assisted_pilot/training.pid`.

The first 2,048-step rollout completed at approximately 6 environment steps
per wall-clock second. Checkpoints at steps 1,024 and 2,048 were saved; training
continued into the next rollout. The first four episodes contained three
physical arrivals and one timeout. These early training samples are not a
frozen-policy evaluation.

Monitor the already-started pilot:

```bash
cd ~/ninorobot
tail -f rl_runs/rough_e1_imu_assisted_pilot/training.log
```

Optional TensorBoard:

```bash
cd ~/ninorobot
.venv/bin/tensorboard --logdir rl_runs/rough_e1_imu_assisted_pilot --port 6008
```

To stop this pilot cleanly and save an interrupted checkpoint:

```bash
cd ~/ninorobot
kill -INT -- -$(cat rl_runs/rough_e1_imu_assisted_pilot/training.pid)
```

The pilot was started in its own process group. Wait for the interrupted-model
save message before shutting down the rough simulator.

## Commands for a new run after the current pilot ends

Do not start another trainer or evaluator against the active rough world.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_rough_78

ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/rough_e1_imu_assisted.yaml \
  --init-model artifacts/rough_routes_112589/nino_ppo_interrupted.zip \
  --timesteps 20000 --checkpoint-every 1024 --check-env \
  --output rl_runs/rough_e1_imu_assisted_pilot
```

After completion, evaluate the frozen final actor on E1 before increasing
the training budget or introducing N1/S1. Use the saved run's `ppo.yaml` and
the same assisted profile for both policy and PI comparisons.

## Final E1 pilot evaluation

PPO: `rl_runs/rough_imu_final_eval/20261008-030023-937626`.
Matching PI: `rl_runs/rough_imu_matching_pi/20261008-032036-561948`.
Both evaluations completed on seeds 10000–10019; benchmark identity,
IMU/encoder pose source, phase and seed sequence match. The strict comparison
is saved in `final_comparison_vs_pi.json`.

| Metric | Final PPO | Matching PI |
|---|---:|---:|
| Physical arrivals | 20/20 | 20/20 |
| Mean completion time | 42.425 s | 26.935 s |
| Physical path RMSE | 0.03135 m | 0.02409 m |
| Vertical acceleration RMS | 1.0699 m/s² | 1.5695 m/s² |
| Wheel slip RMS | 0.03225 | 0.04503 |
| Wheel torque RMS | 0.2984 Nm | 0.3425 Nm |
| Mean final estimated/physical position discrepancy | 0.03287 m | 0.07617 m |

PPO preserves observed arrival reliability and reduces vibration by 31.8%
and slip by 28.4%, but takes 57.5% longer and has 30.2% greater path RMSE.
Both controllers meet this course's existing time budget; that does not mean
PPO is faster. PPO's mean speed scaling is 0.665 versus PI's 1.0. These
comfort gains may therefore largely result from slower movement. This fixed
E1 suite does not establish terrain/route generalization or a learned benefit
over an equivalently slow PI controller.

### Next decision

Evaluate PI at a reduced speed on the same assisted profile and seeds to
isolate slowing down from learned torque correction. Scale 0.70 is an initial
calibration choice, not a measured match; compare the resulting completion
time against PPO's 42.425 s. Claim a matched-speed benefit only when measured
completion times are close (for example, within 5%). If beneficial comfort and
tracking remain, introduce N1/S1 while retaining E1 replay before terrain
randomization. If slower PI explains the gains, revisit the policy's speed/
torque contribution and timing objective before a longer E1 training run.

No new rough training was started during this final-result review.

## Slower PI comparison completed

Run: `rl_runs/rough_imu_slow_pi_comparison/20261008-040611-258952`.
20 matching seeds, same IMU/encoder benchmark, PI speed scale 0.70.
Strict comparison: `final_comparison_vs_slow_pi.json`.

| Metric | PPO | Slower PI |
|---|---:|---:|
| Physical arrivals | 20/20 | 20/20 |
| Completion time | 42.425 s | 43.700 s |
| Physical path RMSE | 0.03135 m | 0.02919 m |
| Vertical acceleration RMS | 1.0699 m/s² | 1.0267 m/s² |
| Slip RMS | 0.03225 | 0.03282 |

Completion times differ by 2.9%, within the declared 5% matching criterion.
PPO is slightly faster, but slower PI has slightly better tracking and
vibration, while slip is nearly equal. This provides no convincing evidence
of a learned comfort advantage beyond reducing speed on fixed E1. It does
not prove torque corrections are always harmful or that RL cannot help other
routes; there is one training seed and this terrain layout stays fixed.

Next: evaluate this final PPO once with its torque corrections disabled
(`--speed-only`) on the same seeds. That measures the contribution of the
current learned torque outputs while retaining its speed decisions. Use that
result to choose the control interface before further rough training. Then
introduce N1/S1 with E1 replay and matching route-PI references; terrain
randomization follows route qualification. Keep the slower PI as a reference.
