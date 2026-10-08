# Corrected flat localization and path feedback — 2026-10-08

Profile: `src/nino_rl/config/combined_flat_feedback_pilot.yaml`.

## Changes

- Timestamp-aligned encoder positions and relative IMU heading/pitch, with
  LiDAR position corrections against the known rectangular hall walls.
- The map contains the inner wall coordinates x=-2/32 m and y=-2/2 m;
  sensor-to-base_footprint translation is [0.20, 0, 0.2275] m, from the URDF.
  Scan matching uses these explicit map/extrinsic inputs, not Gazebo pose,
  the goal position, or generated cable coordinates.
- Wall matching rejects short obstacle/self returns, requires multiple
  consistent rays on both axes, rejects excessive tilt and innovations,
  and applies delayed measurements against stored historical estimates.
  Accepted corrections update position, not encoder-derived velocity.
- Missing/stale accepted wall scans fail closed after 0.6 simulated seconds.
  Reset discards old scans/history. Startup verifies raw transport under a
  stop command, then requires localization once reset establishes the origin.
- Pure pursuit follows the estimated straight trajectory with a 0.45 m
  lookahead and a bounded 0.8 rad/s yaw reference. Wheel PI remains the motor
  controller. PPO chooses speed scaling and a bounded yaw residual; that
  residual fades over the last metre and is zero at estimated stopping.
- Training and the deployment policy node share the same command function.
  Control traces distinguish policy yaw residual from the actual yaw command
  and include accepted wall-scan count, age, and raw wheel pose.

The physical arrival radius is still **0.20 m**. Estimated stopping remains
**0.02 m**. Two-cable stage, 22 s target, 30 s deadline, motor settings and
timing-profile reward are unchanged. Ground truth remains independent scoring
and reward information, never localization or actor pose input.

## Contract and initialization

Revision **36** declares the new estimator and yaw-residual interpretation.
Old absolute-yaw actors cannot be directly evaluated or optimizer-resumed
with this profile. Use explicit speed/features transfer via `--init-speed-model`:
the source speed head and actor features are reused, yaw mean is reset to zero,
and critic, optimizer and training counter are fresh.

Source: `rl_runs/flat_speed_yaw_timing_pilot/20261007-205724-376054/nino_ppo_final.zip`.
Planned short pilot: 10,000 requested steps (10,240 with 1,024-step rollouts),
checkpoints every 1,024 steps, CUDA, ROS domain 79, partition `nino_flat_79`.
The pilot starts only after live PI validation passes.

## Targeted live validation

Run: `rl_runs/flat_feedback_pi_targeted/20261008-033715-000826`.
All four previously failing seeds (61000, 61001, 61010, 61015) now physically
arrived within 22 s under PI: **4/4**, mean **17.425 s**, physical path RMSE
**0.03346 m**, mean final estimated/physical position discrepancy **0.00137 m**.
This is a small simulator check, not an unseen-scenario or hardware guarantee.

## Remaining live gate

Full PI validation uses seeds 61000–61023 on the corrected profile, plus a
slower-PI replay of the two former premature-stop seeds to check behavior at
policy-like speeds. Required before starting the pilot:

- Complete full evaluation; at least 22/24 physical arrivals and 21/24 on time.
- Mean physical path RMSE <= 0.04664 m (old fast PI + 1 cm).
- Mean final estimated/physical position discrepancy <= 0.05 m.
- Both targeted slower-PI episodes physically arrive before 30 s.
- Clock error <= 0.02 s and motion-state lag <= 0.04 s.

New localization changes benchmark identity. Historical PI/PPO results are
descriptive comparisons; the final corrected PPO must be compared against
this newly measured PI baseline with matching config and seeds.

## Limits

This is a small corridor-specific scan matcher, not AMCL or a general SLAM
system, and it does not publish localization TF. It assumes known axis-aligned
walls, the configured local origin/heading and calibrated laser mounting.
Different maps require corresponding geometry/localization; blocked wall
views, IMU drift, changed extrinsics and realistic sensor noise need separate
tests. Very small simulation pose errors do not establish real-robot accuracy.

## Completed validation and pilot launch

- Full PI: `rl_runs/flat_feedback_pi_validation/20261008-033904-874087`.
  **24/24 physical arrivals, 24/24 within 22 s**, mean 17.6375 s;
  physical path RMSE 0.03772 m, mean final position discrepancy 0.00108 m.
  Largest physical endpoint distance was 0.199976 m. Clock error stayed below
  3e-10 s and motion-state lag below 0.024 s.
- Slower PI (0.78), seeds 61001/61015:
  `rl_runs/flat_feedback_slow_pi_targeted/20261008-034901-633974`.
  **2/2 physical arrivals**, 26.50 s and 25.80 s. Neither premature-stop
  failure reproduced. Physical tracking was worse at this slower setting
  (individual path RMSE approximately 0.071/0.080 m), so success alone does
  not establish a tracking improvement at every speed.
- Full PI vertical acceleration RMS was 3.294 m/s² and slip RMS 0.1846.
  Comfort did not improve relative to the historical fast PI. The corrected
  PPO still needs to demonstrate its benefit against this new PI reference.
- All declared pre-pilot gates passed. Machine-readable results:
  `docs/flat_feedback_2026-10-08/validation.json`.
- **49 focused tests passed** and the ROS package build succeeded.

The 10k-step pilot was launched in its own process group, PID recorded in
`rl_runs/flat_feedback_pilot/training.pid`. Log:
`rl_runs/flat_feedback_pilot/training.log`. Source actors remain preserved.

Active run: `rl_runs/flat_feedback_pilot/20261008-035120-161159`.
CUDA on the RTX 4080, all mandatory 12 preflight points and `--check-env`
passed. Initialization provenance is in `actor_transfer.json`. The first
training episode physically arrived in 22.50 s, slightly beyond the 22 s
target. This is rollout data before a learned-policy evaluation, not evidence
that PPO already beats the corrected PI.

### Monitor

```bash
cd ~/ninorobot
tail -f rl_runs/flat_feedback_pilot/training.log
```

Optional TensorBoard:

```bash
cd ~/ninorobot
.venv/bin/tensorboard --logdir rl_runs/flat_feedback_pilot --port 6007
```

Clean stop (wait for interrupted checkpoint saving before closing Gazebo):

```bash
cd ~/ninorobot
kill -INT -- -$(cat rl_runs/flat_feedback_pilot/training.pid)
```

### Reproduce a new pilot

Run only when domain 79's trainer/evaluator is idle and its flat Gazebo server
is running. This initializes a fresh run; it does not resume the old contract.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_flat_79

ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_feedback_pilot.yaml \
  --init-speed-model rl_runs/flat_speed_yaw_timing_pilot/20261007-205724-376054/nino_ppo_final.zip \
  --timesteps 10000 --checkpoint-every 1024 --check-env \
  --output rl_runs/flat_feedback_pilot
```

After completion, evaluate the frozen final actor on seeds 61000–61023 with
its saved `ppo.yaml`, flat stage 2 and phase 1. Compare to the corrected full
PI summary above before increasing training length or cable count. No
subsequent evaluation or course advancement is queued automatically.
