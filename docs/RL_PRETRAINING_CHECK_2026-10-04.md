# RL pretraining checks — 2026-10-04

Use rough trial 6 for continued training. For flat training, initialize the
old 1.5M actor into the new goal-margin curriculum profile. Further flat
Optuna trials should wait until the revised arrival behavior has been trained
and checked across curriculum stages.

## Measured results

Evaluations use deterministic inference, new seeds starting at 30000, the
current robot geometry, and independent Gazebo partitions/domains 78 and 79.
Randomized evaluation is disabled. Each flat test has 12 episodes; each rough
test has 24. All success counts refer to the physical ground-truth goal.

| Course/controller | Physical successes | On-time successes | Physical path RMSE |
| --- | ---: | ---: | ---: |
| Rough trial 3, original profile | 15/24 | 11/24 | 0.157 m |
| Rough trial 6, original profile | 21/24 | 20/24 | 0.122 m |
| Clear flat PI baseline, original stop | 6/12 | 6/12 | 0.038 m |
| Clear flat PI baseline, goal margin | 10/12 | 10/12 | 0.080 m |
| Old 1.5M actor, one cable, original stop | 0/12 | 0/12 | 0.238 m |
| Old 1.5M actor, one cable, goal margin | 10/12 | 10/12 | 0.116 m |
| Tuned flat trial 6, one cable, original stop | 2/12 | 2/12 | 0.176 m |
| Tuned flat trial 6, one cable, goal margin | 8/12 | 8/12 | 0.162 m |

The goal-margin comparisons change the approach controller, not model weights.
Both flat actors cleared the single cable in all 12 episodes of their revised
evaluations. The old actor's two failures were goal misses; the tuned actor
had two goal misses and two off-path failures. The higher success count does
not establish that either actor handles all six cables and adaptive items.

Source paths, benchmark IDs, termination counts, and endpoint/odometry errors
are recorded in [validation.json](rl_pretraining_checks/validation.json).

## Odometry and stopping diagnosis

Drive-wheel radius is 0.0625 m and separation is 0.34273666 m in both URDF and
controller settings. Episode resets produce a near-zero starting odometry
pose. Three completed clear-stage runs were reconstructed from wheel joint
position increments. Their reconstructed pose and the controller's
velocity-integrated pose agreed within approximately 3 mm. Both estimates
differed from physical motion, so the audit does not support replacing the
integrator as a cure for the measured drift. Wheel slip/contact behavior is
consistent with the remaining errors.

Previously, `approach_speed()` stopped the straight command as soon as wheel
odometry entered the same 0.20 m circle used to score physical success. The
effort controller then disabled the RL torque residual because the straight
reference commanded no motion. Several timed-out runs had odometry distance
around 0.17–0.20 m while physical distance remained outside 0.20 m.

`navigation.goal_stop_tolerance_m` now allows a smaller estimated stopping
circle. The new `combined_flat_curriculum_goal_margin.yaml` profile uses
0.05 m. Slowdown also targets this inner circle, and forward speed remains
bounded after estimated overshoot. Physical scoring still uses the original
0.20 m circle and heading limit. The approach controller uses estimated pose;
Gazebo ground-truth pose is not supplied to that controller. This is a margin
for measured estimation error, not a localization solution.

The profile uses flat Optuna trial 6's PPO/reward settings, an unlocked
curriculum, and the old actor as the selected initialization. Its navigation
contract differs from saved models, so use `--init-model` for the new flat run.
Original study YAMLs remain the inputs for reproducing their recorded trials.

## Training commands

Keep the corresponding Gazebo simulator running. In every training terminal:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
```

Continue rough trial 6 with approximately 450k additional steps. The checkpoint
already has 50,176 steps; PPO rounds the extra budget to complete rollouts.

```bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export GZ_PARTITION=nino_rough_78

ros2 run nino_rl train --device cuda \
  --config rl_runs/combined_rough_optuna_fresh/trial_0006/train/20261003-024526-879245/ppo.yaml \
  --resume rl_runs/combined_rough_optuna_fresh/trial_0006/train/20261003-024526-879245/nino_ppo_final.zip \
  --timesteps 450000 --checkpoint-every 25000 \
  --output rl_runs/rough_specialist
```

Start a 50k-step flat curriculum pilot from the selected old actor. Actor
transfer starts the new task at step zero with a fresh critic and optimizer.
Use the pilot's physical outcomes and stage progress to decide whether to
extend it. The short smoke run does not establish a learning improvement.

```bash
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export GZ_PARTITION=nino_flat_79

ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_curriculum_goal_margin.yaml \
  --init-model artifacts/old_1_5m/nino_ppo_final.zip \
  --timesteps 50000 --checkpoint-every 10000 \
  --output rl_runs/flat_curriculum_goal_margin
```

Flat stages start with no obstacles, add six cables, widen their angles, then
add up to six adaptive items. Advancement requires at least 75% physical
successes over 30 active-stage episodes. Twenty percent of episodes replay
the preceding stage; those outcomes do not advance the active stage.

Evaluate checkpoints separately from training, with fresh seeds and the
appropriate `--flat-stage`. Retain checkpoints using physical success,
tracking error, and time rather than the latest training reward alone. If the
pilot advances and validation remains good, continue its chosen checkpoint
with `--resume`, its saved `ppo.yaml`, and an additional budget. This restores
the optimizer and curriculum stage/window; a new `--init-model` would restart
the curriculum.

## Verification and limits

The relevant 55 unit tests pass, including recorded early-stop behavior,
legacy defaults, invalid stopping thresholds, curriculum gates and checkpoint
state, task geometry, and wheel kinematics. Three older adaptive-terrain test
fixtures were updated to explicitly select their non-flat curriculum path.
The `nino_rl` package builds and installs the new profile successfully.

The 2,048-step flat smoke run passed all 12 live preflight checks, completed
two PPO rollouts/updates, and saved a loadable checkpoint with its stage-zero
curriculum state. It recorded 6 physical successes in 11 completed stochastic
training episodes. The window is still below the required 30 samples, so the
stage did not advance. Its short training history is not a final policy
evaluation. Both this checkpoint's resume contract and rough trial 6's
original resume contract were checked successfully.

These tests cover fixed geometry without full domain perturbations. Wheel
odometry still drifts, and the clear baseline retained two failures. A real
robot may need calibrated or externally corrected localization. The final
flat curriculum stage and the rough-to-flat policy handoff need their own
validation before claiming combined-course performance.
