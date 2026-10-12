# Rough reward-only recovery pilot — 2026-10-11

## Purpose and contract

Test the single correction selected by the [saved-trace audit](rough_observable_audit_2026-10-11/REPORT.md).
Output: `rl_runs/rough_recovery_sigma_pilot_v1`. Training contract revision **48**.
The original observable v2 model, results, package and contract remain preserved.

The complete configuration differs in exactly one value:

```yaml
reward_v2:
  longitudinal_weights:
    velocity_sigma_m_s: 0.1  # source pilot: 0.4 m/s
```

This makes the existing physical velocity-tracking cost 16 times stronger outside holding periods.
The holding cost remains exactly zero. All other reward coefficients, reward formula,
learner multiplier 0.1, controller, odometry, terrain, observations, action meaning,
exploration and physical scoring remain identical.

Training uses **20,480 steps**, seed **17000**, the same original fresh actor initialization,
a fresh critic and optimizer, and timestep zero. No trained checkpoint is loaded.
The copied package differs only in training-contract metadata (47 → 48).
Offline verification checks exact equality of all fresh policy/critic tensors and empty optimizer states.
An old revision-47 checkpoint cannot resume its optimizer under this contract.

## Control and validation

- Fixed half-relief E1, nominal physical profile, no route/terrain curriculum progression.
- Horizontal LiDAR, IMU and wheel encoders; 72 values per frame × 5 frames = 360 causal inputs.
- One speed target in 0.55–1, unchanged 0.4 scale/s reference ramp, unscaled PI yaw, zero residual torque.
- Same PPO settings and gSDE refresh every six control steps; CUDA.
- Same lockstep timing and sensor-coverage checks, with the mandatory 12-point preflight.
- Save a checkpoint every 4,096 steps.

Previously completed untrained exposure and PI feasibility screens are reused only after their hashes
and executable/controller/physics/actor settings are verified. Their old reward totals are not
new-contract evaluation evidence. The same original scoring function is regression-checked
against the entire v2 comparison, including physical arrival and disturbance-window allocation.

After training, evaluate PPO, full-speed PI and duration-matched PI on diagnostic seeds
**17100–17104**. Each controller receives a separately owned simulator session.
Acceptance thresholds remain unchanged: physical arrival and ordered route gates, ≤5 cm mean physical
tracking RMSE, ≤10 cm episode-mean pose disagreement, no rollovers; lower holding speed with
quiet mean scale ≥0.95 and recovery; completion within 1.15× full-speed PI; at least 5% improvement
in one disturbance-window energy-per-metre measure, at most 10% regression in the other;
whole-run vibration and slip ratios ≤1.10; duration matching within 3%.

The read-only action-response monitor additionally compares acceleration, slowdown, persistent
reduced-speed and cruise intervals with v2. It reports acceleration-related slip and quiet recovery
in `ACTION_RESPONSE_REPORT.md`. Those diagnostic associations do not change the frozen acceptance gates.
The stronger speed penalty may favor constant full speed or increase acceleration-related slip;
the pilot must still demonstrate useful slowdown/recovery and pass the quality gates.

## Conditional confirmation

Only a passing primary pilot triggers confirmation of the same trained model:

- New reset seeds **18100–18104**.
- Nominal physics; drive friction **μ = 0.6** versus nominal 1.2; **+15% mass/inertia**.
- PPO, full-speed PI and profile-specific duration-matched PI for each physical profile.
- Same physical, response, timing and quality rules in each profile.

This is 45 additional evaluation episodes if triggered. No further policy updates occur.
These physical profiles were absent from PPO training; the map is still fixed. This confirmation
does not establish generalization to unseen terrain or repeatability across independent training seeds.
All results are preserved. **Optuna remains held even if confirmation passes.**

## Running and monitoring

The supervisor was started for this request. Do not launch a duplicate worker.
It owns headless Gazebo in ROS domain **78**, partition **nino_rough_78**.

```bash
cd ~/ninorobot
cat rl_runs/rough_recovery_sigma_pilot_v1/status.json
tail -f rl_runs/rough_recovery_sigma_pilot_v1/train/train.log
```

Optional TensorBoard in another terminal:

```bash
cd ~/ninorobot
.venv/bin/tensorboard --logdir rl_runs/rough_recovery_sigma_pilot_v1/train --port 6008
```

Runner commands for a session when no worker owns the lock:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

python src/nino_rl/scripts/prepare_rough_recovery_sigma_pilot.py
python src/nino_rl/scripts/verify_rough_recovery_sigma_pilot.py
python src/nino_rl/scripts/run_rough_recovery_sigma_pilot.py --run
```

The runner refuses to silently restart fresh training over an unfinished checkpoint.
Completed evaluation stages can be reused with the same frozen assets and seed list.

The separate read-only response monitor was also started:

```bash
cd ~/ninorobot
.venv/bin/python src/nino_rl/scripts/compare_rough_recovery_response.py --wait
```

## Results

- `status.json`, `REPORT.md`, `supervisor.log`: live workflow state.
- `verification.json`, `pilot_contract.json`, `workflow_contract.json`: initialization and immutable input evidence.
- `train/`: fresh model, checkpoints, TensorBoard and captured actor observations.
- `comparison.json`: primary PPO/PI comparison and unchanged gates.
- `ACTION_RESPONSE_REPORT.md`, `action_response_comparison.json`: acceleration/slip and quiet-cruise diagnostic.
- `confirmation/<profile>/comparison.json`, `confirmation/result.json`: conditional physical-profile confirmation.
