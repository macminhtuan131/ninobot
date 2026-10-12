# Rough hardware-sensor confirmation and fresh PPO pilot

## Completed confirmation

All **27/27** physical arrivals passed on the fixed half-relief map, with zero rollovers.

| Physical profile | E1/N1/S1 arrivals | Largest route mean physical RMSE |
|---|---:|---:|
| Nominal | 9/9 | 0.03374 m |
| Wheel friction 0.6 | 9/9 | 0.03382 m |
| Mass/inertia ×1.15 | 9/9 | 0.03400 m |

Evidence: `rl_runs/rough_hardware_confirmation_v1/feasibility_result.json` and per-episode control/drive traces. The largest episode mean localization disagreement across these batches was 0.00176 m. This is simulated known-wall localization, not measured hardware accuracy. These results establish feasibility for the pilot; they do not establish PPO improvement or arbitrary-map robustness.

## Pilot execution

The v2 controller checks passed **6/6** physical E1 arrivals: mean physical RMSE was **0.01690 m** at full speed and **0.01452 m** at scale 0.70. Both profiles had zero settled yaw-reference error and zero additive torque. Source and asset hashes, raw traces and actuator gates are preserved in `rl_runs/rough_longitudinal_pilot_v2/controller_pi`.

Fresh PPO started on CUDA in `rl_runs/rough_longitudinal_pilot_v2/train/20261011-123141-326087`. The first two collection episodes reached the goal; these precede the first PPO update and are not evidence of learned improvement. The runner's live report and final `comparison.json` distinguish collection progress from the later paired evaluation. Optuna remains held.

## Completed pilot and recommendation

The final archive contains **20,480 steps**. The runner completed all three five-episode comparisons and stopped its owned simulator. Evidence: `rl_runs/rough_longitudinal_pilot_v2/comparison.json` and saved episode traces.

| Metric | PPO | Duration-matched PI |
|---|---:|---:|
| Physical arrivals | 5/5 | 5/5 |
| Mean time | 26.94 s | 27.00 s |
| Mean physical path RMSE | 0.01679 m | 0.01676 m |
| Vertical acceleration RMS | 1.27281 m/s² | 1.27688 m/s² |
| Wheel slip RMS | 0.01746 | 0.01608 |

Matching selected PI scale **1.0**, with a duration difference of only 0.22%. PPO's RMS vibration was 0.32% lower and its slip 8.60% higher; these small fixed-map samples do not establish improvement or a repeatable degradation. **All 1,347 saved PPO actions and executed speed scales were exactly 1.0.** This pilot demonstrates preserved PI behavior, not learned terrain-adaptive speed control. The full-speed PI repeat was also essentially equivalent, with vibration RMS 1.28231 m/s² and slip RMS 0.01600.

The earlier three-seed controller screen helps explain the incentives: constant scale 0.70 reduced vibration RMS from 1.29579 to 1.04990 m/s², but increased time from 26.97 to 38.27 s. Mean raw return fell from 21.22 to 16.77. The unscaled cruise-speed tracking cost increased by 3.42 reward units, while integrated vibration cost improved by only 0.38. This supports an incentive explanation for full-speed behavior; it does not prove the optimizer found the global optimum or that every brief slowdown is harmful.

Recommended next action: verify one brief **IMU/encoder-triggered slowdown and recovery** on E1 against matching PI, without using physical truth or known terrain coordinates to trigger it. Measure disturbance-window impact/slip as well as total duration. If this reactive intervention has useful authority, define a new reward contract with an explicit allowed time/quality tradeoff and less pressure to maintain cruise speed during a disturbance, then run one short fresh pilot. Preserve physical arrival, route tracking and timing gates. If the intervention has no useful effect, revise the achievable skill or sensor setup before more training. Do not expand routes or launch Optuna on the current constant-action result.

## Authorized sequence

1. Confirm PI on **E1/N1/S1**, using seeds **13010–13012** on each physical profile:
   - Nominal drive friction `mu=1.2`, nominal link mass/inertia.
   - Lower drive friction `mu=0.6`, nominal mass/inertia.
   - `mu=1.2`, every link mass/inertia multiplied by **1.15**.
2. Require all nine route/profile batches to pass the unchanged physical arrival, ordered-route, localization and **0.05 m mean path RMSE** gates. Three reset seeds per batch are a feasibility screen, not a final robustness estimate. Starting pose and terrain remain fixed; these are not independent training seeds or unseen maps.
3. Validate the new controller on E1 at full and 0.70 target-speed scale, with seeds **13100–13102**. Inspect actual drive diagnostics: policy speed changes must not scale PI yaw, the adapter's requested multiplier must be one, and additive torque must be zero. The unchanged driver has a half-second startup ramp shared by PI and PPO; verify its exact response and unchanged yaw after that ramp. Timing and IMU coverage checks remain active.
4. Train a **fresh 20,480-step PPO pilot**, training seed **14000**, on fixed half-relief E1 with nominal physics. Old checkpoints are preserved and are not loaded.
5. Evaluate PPO, full-speed PI and approximately speed-matched PI using seeds **14010–14014**. Report whether the duration match is achieved, along with physical arrival, tracking, vibration and slip. **Optuna remains held** throughout.

## New learning contract

The actor uses **horizontal LiDAR, IMU and wheel encoders**, estimated route state, and command/action history. The simulated downward scanner and multi-channel wall sensor are excluded. Five frames contain 280 values. The known rectangular wall map remains a localization prior; hardware calibration and arbitrary-map localization are not established by this simulation.

There is **one action**: target translational speed scale from **0.55 to 1.0**. A fixed **0.4 scale/s** ramp smooths the reference. The path follower's yaw request is not scaled. Left/right wheel PI follows the resulting velocity references. No learned yaw correction or additive torque is applied.

The fresh Gaussian actor starts near PI (approximately 0.955 speed scale); the critic, optimizer and training counter are fresh. This task is reactive: history may inform adjustment after contact. It does not provide advance geometry for an unseen pothole.

The preserved `rough_longitudinal_pilot_v1` screen completed 3/3 physical E1 arrivals, then held before PPO: its actuator check incorrectly treated the driver's existing startup ramp as lost steering authority. The measured discrepancy was exactly explained by that ramp, with zero settled yaw error and zero additive torque. Version 2 corrects this diagnostic and the one-action yaw trace label; it keeps the controller, reward, timing and physical scoring unchanged. No v1 PPO was trained.

The compact reward logs signed physical path progress, time, tracking of the **unscaled external PI speed request**, measured vertical acceleration squared energy, physical slip, path/heading error, action changes and physical terminal outcomes. Truth is allowed in reward and scoring, and excluded from actor observations. A fixed 0.1 multiplier sets learner reward units. Legacy reward weights are retained only for archived helper compatibility and are unused by the new reward function.

Initial training settings: learning rate `1e-4`, 1,024 steps per PPO rollout, batch 256, three update epochs, clipping 0.2, entropy coefficient 0.001. These are fixed pilot settings, not newly tuned or proven optimal values.

## Commands

No rebuild is required. Each runner owns its simulator and bridges on ROS domain 78 / Gazebo partition `nino_rough_78`; run them sequentially.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

# Reuses complete confirmation batches; no PPO or Optuna here.
python src/nino_rl/scripts/run_rough_hardware_confirmation.py --run

# Prepare and check the new isolated learning contract.
python src/nino_rl/scripts/prepare_rough_longitudinal_pilot_v2.py
python src/nino_rl/scripts/verify_rough_longitudinal_pilot.py --snapshot rl_runs/rough_longitudinal_pilot_v2

# Requires completed confirmation; validates new PI control, then trains/evaluates.
python src/nino_rl/scripts/run_rough_longitudinal_pilot_v2.py --run
```

Live progress:

```bash
cd ~/ninorobot
cat rl_runs/rough_hardware_confirmation_v1/REPORT.md
cat rl_runs/rough_longitudinal_pilot_v2/REPORT.md
tail -f rl_runs/rough_longitudinal_pilot_v2/train/train.log
```

TensorBoard, after training creates event files:

```bash
cd ~/ninorobot
.venv/bin/tensorboard --logdir rl_runs/rough_longitudinal_pilot_v2/train --port 6008
```

The initial pilot runner stops on an infrastructure interruption and preserves logs/checkpoints. It does not silently restart a fresh run or change a failed gate. A saved incomplete pilot requires review before continuation. Existing experiments, models and Optuna studies are immutable inputs to the new workflow.
