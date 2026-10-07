# Flat pilot: arrival diagnosis and next training run

The completed 50,176-step pilot remains at flat curriculum stage 0. On 24
deterministic clear-floor episodes with seeds 50000–50023, its actor achieved
17 successes, the old actor achieved 12, and the PI baseline achieved 22.
All three complete reports use matching task settings and evaluation seeds.
See [the recorded comparison](rl_pretraining_checks/flat_arrival_guard.json).

The pilot's five goal-miss trajectories retained about 0.19–0.22 m/s forward
motion after passing the goal. At that estimated along-path position, the
approach controller requests only 0.03 m/s. Additive RL torque can overpower
that reference. The two remaining pilot timeouts stopped at an estimated
goal pose while the physical robot remained laterally outside the scoring
circle; the torque guard does not correct that localization error.

## Optional arrival guard

`combined_flat_curriculum_arrival_guard.yaml` copies the existing goal-margin
profile and adds `navigation.goal_residual_fade_distance_m: 0.5`.
For wheel-torque control, both residual torques taper linearly from full
authority at 0.5 m estimated path remaining to zero at the 0.05 m estimated
stop margin. A lateral miss or overshoot cannot restore full authority.
The PI speed reference, physical 0.20 m success circle, curriculum gate,
actor input shape, and raw action format retain their existing definitions.
The same decoding is used by training, evaluation, and the policy node.
Estimated path geometry controls the taper; simulator ground truth is used
only for the existing scoring and diagnostics.

This option is absent from the original configs, so existing rough and flat
runs retain their original command decoding. No Gazebo restart is needed.
The guard is a mitigation for arrival speed, not a localization solution or
proof that the full cable course is solved.

## Continue adapting the pilot actor

The new navigation option changes the training contract. Use `--init-model`
with the 50k pilot checkpoint for the new run. The actor and its exploration
scales transfer; the critic and optimizer start fresh, and the curriculum
starts at stage zero. `--resume` remains appropriate only for the unchanged
pilot or for later checkpoints of this guarded run using their saved configs.

Keep flat Gazebo running. In the training terminal:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_flat_79

ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_curriculum_arrival_guard.yaml \
  --init-model rl_runs/flat_curriculum_goal_margin/20261004-130945-967736/nino_ppo_final.zip \
  --timesteps 50000 --checkpoint-every 10000 \
  --output rl_runs/flat_curriculum_arrival_guard
```

Inspect physical success, goal misses, timeouts, and
`episode/next_flat_curriculum_stage` during this run. The existing advance
criterion remains at least 23 successes in the last 30 active-stage episodes.
Do not force advancement based on the deterministic comparison above.

## Verification

The 51 focused goal-approach, actuator/environment, and flat curriculum tests
pass, and the `nino_rl` package builds. The tests cover unchanged legacy
commands, preserved torque authority outside arrival, tapering of both wheel
residuals, zero authority after estimated overshoot, invalid configuration,
and the unchanged physical success tolerance.

A completed two-episode check using the unchanged pilot actor and the new
guard targeted seeds 50003 and 50004, which both missed the goal in the
existing pilot evaluation. Both reached the physical goal; one finished
within the 22 s target and the other took 25.9 s. Their mean physical endpoint
error was 0.199 m. The measured mean odometry-to-physical position error was
still 0.261 m, confirming that the guard does not fix localization.
The report is saved at
`rl_runs/flat_arrival_guard_targeted/20261004-183803-878376/summary.json`.
This small check supports trying the mitigation on selected failures; it is
not a new general success-rate estimate, a statistically established gain,
or an improvement from training model weights.
