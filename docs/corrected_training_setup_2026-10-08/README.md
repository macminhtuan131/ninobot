# Corrected specialist setup — 2026-10-08

## Flat: wheel PI tracking at reduced speed

Profile: `src/nino_rl/config/combined_flat_pi_tracking.yaml`.

The optional `conditional_v1` wheel PI profile removes the continuous integral
leak at speed scales below 1. It keeps bounded integral correction at a steady
reduced reference and freezes integration into PI torque saturation, while
allowing the error to unwind the integral. Zero commands, watchdog handling,
wheel acceleration limits, torque limits and effort slew limits remain active.
Default launches retain `legacy`; the corrected flat launch must explicitly
select `pi_integrator_profile:=conditional_v1`.

PI gains remain Kp=0.30, Ki=0.10, integral limit=4.0. The live simulator uses a
4 N·m motor/PI limit and 10 N·m/s torque slew limit. Scaling linear and yaw
references together remains unchanged. No reward weights were changed.

Training and evaluation read the live controller parameters before acting and
reject mismatched settings. The cached controller settings are read-only ROS
parameters in newly launched nodes; change them through a new launch/profile.
The profile creates training contract revision **37**. Start a new run with
actor initialization and a fresh critic/optimizer; optimizer resume from the
old controller contract is rejected.

Initial paired check at scale 0.78, seeds 61001 and 61015:

| Metric | Previous PI profile | Corrected PI profile |
|---|---:|---:|
| Physical arrivals | 2/2 | 2/2 |
| Completion times | 26.5 / 25.8 s | 21.6 / 22.1 s |
| Path RMSE | about 0.071 / 0.080 m | about 0.015 / 0.024 m |

This comparison changes the controller profile intentionally. It is a paired
engineering check, not an identical-benchmark PPO-versus-PI comparison.
Suite results and exact paths are recorded in `validation.json`.
A slow baseline is not required to meet the full-speed
22-second target; arrival and tracking are evaluated separately from timing.

Completed validation:

| PI check | Physical arrivals | Within 22 s | Mean time | Physical path RMSE |
|---|---:|---:|---:|---:|
| Scale 0.78, full 24-seed suite | 24/24 | 3/24 | 22.354 s | 0.05154 m |
| Scale 1.0, four targeted seeds | 4/4 | 4/4 | 17.500 s | 0.04679 m |

Nominal arrival/time remained reliable in this small check, but nominal path
RMSE was higher than the previous four-seed PI value of 0.03346 m. Thus the
targeted reduced-speed improvement does **not** prove improved tracking at all
speeds. Use a short diagnostic PPO pilot before any full training commitment;
nominal tracking remains a comparison criterion, and the 22-second target was
not relaxed. Neither check establishes statistical significance.

The reduced-speed run stopped after 18 completed episodes on a feedback lag
of 0.058 s, exceeding the existing 0.04 s action-boundary limit. The unfinished
episode was discarded. Seeds 61018–61023 were evaluated after rough evaluation
finished, with rough Gazebo subsequently paused. The complete 24-scenario
summary is `rl_runs/flat_pi_tracking_slow_complete/20261008-validation/summary.json`.
`merge_evaluation_chunks.py` verified identical configuration/provenance,
unique complete scenario coverage and saved physical trajectories before
combining the 18+6 completed episodes. Original results and trace directories
remain intact; the aggregate records their locations. No timing limit changed.

## Rough: fixed E1/N1/S1, with E1 replay

Profile: `src/nino_rl/config/rough_e1_n1_s1_fixed.yaml`.

- Fixed original terrain bank world; no terrain or sensor/motor randomization.
- E1: `(0,0) → (10.5,0)`.
- N1: `(0,0) → (2.5,0) → (2.5,6.2)`.
- S1: `(0,0) → (2.5,0) → (2.5,-6.2)`.
- Each shuffled group of three training episodes includes each route once.
  E1 replay is therefore one third of episodes. No automatic stage promotion.
- Existing three actions remain speed scale, common residual torque and
  differential residual torque. Existing rough rewards/PPO settings are kept.
- Encoder/IMU pose assistance and the legacy wheel PI profile are retained.
- New route/controller contract: actor initialization from the saved 20,480-step
  E1 actor; fresh critic, optimizer and training counter.

Matching route-PI references use this same profile, phase 1, unchanged route
geometry, estimator, physical scoring and seed list. Evaluation is round-robin
E1/N1/S1 with seeds 10000–10011: four scenarios per route. Future PPO evaluation
must use the identical command settings. These are preliminary route references,
not a large held-out statistical qualification.

The first N1 reference failed: the robot stalled near `(2.72,0.62)` while wheel
spin advanced its estimated position. End-of-episode position error was about
4.67 m, and physical distance to the goal was about 5.45 m. S1 also exposed
stall/drift. Preserve these failures as references; do not describe the old
E1 success rate as multi-route reliability. A long rough run is not qualified
by these checks. A short route pilot can test whether bounded RL corrections
help, but persistent wheel-spin localization error needs investigation.

Completed matching PI references: **E1 4/4, N1 0/4, S1 0/4**. N1 terminated
with `wrong_direction`; S1 timed out. Mean final estimated/physical position
errors were 0.090 m, 3.88 m and 10.57 m respectively. Exact per-route seeds,
physical path errors, successful-only completion times and the original world
checksum are in `rough_route_pi_references.json`. Failed routes have no
successful completion-time reference; their timeout times are not performance
targets to beat.

## Independent physical scoring

Both profiles retain `reward_pose_source: ground_truth` for simulator scoring
and the original **0.20 m physical goal radius**. The actor/controller uses
estimated encoder/IMU/LiDAR pose only. Rough success additionally requires the
ordered physical route gates. Changing PI integration does not change arrival
criteria, and an estimated arrival cannot turn a physical miss into success.
Existing stopping thresholds remain 0.02 m flat and 0.05 m rough; these are
estimated controller thresholds, not the physical success radius.

## Build and launch

Run this setup in each terminal:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python -m colcon build --symlink-install --packages-select nino_control nino_description nino_rl
source install/setup.bash
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
```

Flat simulator terminal, after stopping the existing flat launch:

```bash
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export GZ_PARTITION=nino_flat_79
ros2 launch nino_rl combined_flat_section_training.launch.py \
  headless:=true pi_integrator_profile:=conditional_v1
```

Rough simulator terminal, after stopping the existing rough launch:

```bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export GZ_PARTITION=nino_rough_78
ros2 launch nino_rl training_sim.launch.py \
  world:="$PWD/rl_runs/rough_terrain_bank_v1/worlds/original.sdf" \
  world_name:=combined_rough_section headless:=true pi_integrator_profile:=legacy
```

Each simulator must have its own domain and Gazebo partition. Use at most one
trainer or evaluator per simulator. Both specialists can run concurrently in
their separate domains.

## Reproduce validation

Flat evaluator terminal (domain 79 / partition `nino_flat_79`):

```bash
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export GZ_PARTITION=nino_flat_79
ros2 run nino_rl evaluate_baseline \
  --config src/nino_rl/config/combined_flat_pi_tracking.yaml \
  --baseline-speed-scale 0.78 --flat-stage 2 \
  --episodes 24 --seed 61000 --control-trace \
  --output rl_runs/flat_pi_tracking_slow_validation

ros2 run nino_rl evaluate_baseline \
  --config src/nino_rl/config/combined_flat_pi_tracking.yaml \
  --flat-stage 2 --seeds 61000 61001 61010 61015 --control-trace \
  --output rl_runs/flat_pi_tracking_normal_targeted
```

Rough evaluator terminal (domain 78 / partition `nino_rough_78`):

```bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export GZ_PARTITION=nino_rough_78
ros2 run nino_rl evaluate_baseline \
  --config src/nino_rl/config/rough_e1_n1_s1_fixed.yaml \
  --phase 1 --episodes 12 --seed 10000 --control-trace \
  --output rl_runs/rough_e1_n1_s1_route_pi
```

## Prepared short training commands

No new RL training is started by this setup correction. These commands start
new 20,000-step pilots (20,480 steps with 2,048-step rollouts). Use them only
after the evaluator in that domain has finished; review the rough failures
before budgeting a longer run.

Flat trainer terminal (domain 79 / partition `nino_flat_79`):

```bash
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export GZ_PARTITION=nino_flat_79
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_pi_tracking.yaml \
  --init-model rl_runs/flat_feedback_pilot/20261008-035120-161159/nino_ppo_final.zip \
  --timesteps 20000 --checkpoint-every 1024 --check-env \
  --output rl_runs/flat_pi_tracking_pilot
```

Rough trainer terminal (domain 78 / partition `nino_rough_78`):

```bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export GZ_PARTITION=nino_rough_78
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/rough_e1_n1_s1_fixed.yaml \
  --init-model rl_runs/rough_e1_imu_assisted_pilot/20261008-013943-771247/nino_ppo_final.zip \
  --phase 1 --timesteps 20000 --checkpoint-every 1024 --check-env \
  --output rl_runs/rough_e1_n1_s1_fixed_pilot
```

Offline actor transfer checks are saved in `actor_initialization.json`: all 13
actor tensors copied for each profile, critic/optimizer fresh, source checksum
recorded. Evaluate the final model with the same profile, route/stage, seed and
phase arguments as its PI reference. The existing strict comparison tool can
then compare matching summaries; historical profiles have different identities.

Verification: **121 tests passed**, all three ROS packages built successfully,
live matching controller settings were accepted and a deliberately mismatched
profile was rejected before actuation. A new isolated controller node accepted
startup overrides and exposed cached PI settings as read-only. Both isolated
Gazebo servers were left paused after validation; training preflight resumes
the selected world automatically. No new RL training was launched.
