# Flat course: speed and yaw references through PI

## Why start a new contract

The 952,343-step torque checkpoint scored 11/24 physical successes against
23/24 for PI on the two-cable stage. Disabling its additive torque outputs
raised success to 20/24 and reduced physical path RMSE to 0.031 m, but successful
episodes averaged 28.61 s; none finished within the 22 s target. This supports
testing a different control interface. It does not establish that the new
interface will outperform PI.

The saved torque checkpoint retains its original three outputs. New contract
**revision 34** uses two outputs:

| Output | Mapping |
|---|---|
| Speed | `scale = (clip(u_speed, -1, 1) + 1) / 2` |
| Yaw | `yaw_reference = 0.25 * clip(u_yaw, -1, 1)` rad/s |

PI controls the two drive motors using these references. Both additive torque
commands remain zero, including after injected torque noise. The drive node
scales linear and angular references by its filtered speed scale, so the
executed yaw target can be smaller than the policy's unscaled yaw reference.
Actual PI motor torques are still measured and penalized by the reward.

The actor still receives five 60-value sensor/history frames (300 inputs),
including IMU, wheel feedback and terrain preview. Previous additive torque
observation fields are zero; action history stores `[u_speed, 0, u_yaw]`.
Training, evaluation and deployment share this mapping. This mode currently
requires a straight course; drawn routes are rejected.

Profile: `src/nino_rl/config/combined_flat_speed_yaw_pilot.yaml`.

- Fixed stage 2: cables 2 and 4, angles ±2°, no adaptive items or easier replay.
- Estimated stop threshold: 0.02 m instead of 0.05 m.
- Minimum approach reference: 0.06 m/s instead of 0.03 m/s, before speed scaling.
- Physical success radius: 0.20 m; heading tolerance: 20°; target: 22 s;
  failure deadline: 30 s. These criteria remain unchanged.
- Reward coefficients, PPO architecture and learning rate are inherited from
  the arrival-guard profile. Learning rate: `6.781612720853196e-5`.
- New yaw exploration standard deviation: 0.04 normalized, or 0.01 rad/s
  before clipping and drive scaling. Speed exploration is transferred.

The tighter stop margin is a proposed mitigation for early estimated stops.
It does not correct odometry drift or guarantee arrival. The inherited reward
still trades arrival/time against motion stability; assess both after the pilot.

## Transfer, not direct resume

`--init-speed-model` copies the old actor's feature layers, policy trunk,
speed output row and speed standard deviation. Its two old torque output rows
are discarded. The new yaw output weights and bias start at zero. The critic,
optimizer, stage history and step counter start fresh. Sensor/history meanings
have changed, so transferred speed behavior is an initialization, not a
guarantee of identical closed-loop motion.

Do not use `--resume` on the old torque checkpoint with this profile. Shape and
contract checks reject it. Later continuation of this pilot uses `--resume`
with the pilot's own saved `ppo.yaml` and checkpoint.

## 1. Shell setup and rebuild

Run setup in each terminal. The rough simulator can remain on its separate
domain 78 and partition `nino_rough_78`.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python -m colcon build --symlink-install --packages-select nino_rl
source install/setup.bash
export ROS_DOMAIN_ID=79
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION=nino_flat_79
```

## 2. Flat simulator (terminal A)

If the existing flat simulator is running in domain 79 with this partition,
reuse it. Otherwise:

```bash
ros2 launch nino_rl combined_flat_section_training.launch.py headless:=true
```

Run only one trainer or evaluator against this simulator at a time.

## 3. Short pilot (terminal B)

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_speed_yaw_pilot.yaml \
  --init-speed-model rl_runs/flat_arrival_guard_200k/20261006-230417-364560/nino_ppo_final.zip \
  --timesteps 20000 --checkpoint-every 5000 --check-env \
  --output rl_runs/flat_speed_yaw_pilot
```

PPO collects 1,024 steps per rollout, so this request normally completes at
20,480 steps. Environment validation performs additional simulator checks but
does not count as policy training. The mandatory preflight remains enabled.
The run saves `actor_transfer.json`, the resolved `ppo.yaml`, checkpoints,
training metrics and the final model. It starts at step zero.

## 4. Laya and TensorBoard (separate terminals)

```bash
python src/nino_rl/scripts/laya_training_monitor.py rl_runs/flat_speed_yaw_pilot \
  --course flat --watch --interval 60 --window 30 --min-episodes 5 --threads 1 \
  --output rl_runs/laya_monitors/flat_speed_yaw_pilot.jsonl
```

```bash
.venv/bin/tensorboard --logdir rl_runs/flat_speed_yaw_pilot --port 6006
```

Laya provides advisory tracking; it does not change rewards, model weights or
curriculum. TensorBoard includes `policy/std_yaw_reference_rad_s` and the
existing arrival, physical tracking, IMU, slip and applied torque metrics.

## 5. Frozen comparison after the pilot

Run these sequentially in terminal B, with the same flat simulator. This picks
the latest *completed* pilot. Use the printed saved run if comparing an older
pilot deliberately. Seeds 61000–61023 are separate from the diagnostic seeds.

```bash
PILOT_RUN="$(python -c 'from pathlib import Path; print(sorted(p.parent for p in Path("rl_runs/flat_speed_yaw_pilot").glob("*/nino_ppo_final.zip"))[-1])')"

ros2 run nino_rl evaluate_baseline \
  --config "$PILOT_RUN/ppo.yaml" --flat-stage 2 --episodes 24 --seed 61000 \
  --output rl_runs/flat_speed_yaw_pilot_pi

ros2 run nino_rl evaluate --device cuda \
  --config "$PILOT_RUN/ppo.yaml" --model "$PILOT_RUN/nino_ppo_final.zip" \
  --flat-stage 2 --episodes 24 --seed 61000 \
  --output rl_runs/flat_speed_yaw_pilot_eval

PI_SUMMARY="$(python -c 'from pathlib import Path; print(sorted(Path("rl_runs/flat_speed_yaw_pilot_pi").glob("*/summary.json"))[-1])')"
PPO_SUMMARY="$(python -c 'from pathlib import Path; print(sorted(Path("rl_runs/flat_speed_yaw_pilot_eval").glob("*/summary.json"))[-1])')"
ros2 run nino_rl compare_evaluations \
  --baseline "$PI_SUMMARY" --candidate "$PPO_SUMMARY" \
  --output rl_runs/flat_speed_yaw_pilot/comparison.json
```

Use a new PI evaluation because the approach settings changed. The old PI
results explain the diagnosis but are not a matching benchmark for this profile.
Before extending training, inspect physical success, success by 22 s, timeouts,
path RMSE, endpoint error, odometry/truth divergence, vertical acceleration and
slip. Reduced vibration alone does not establish improvement if arrival worsens.

## Implementation checks

95 focused tests passed, covering legacy control, the two-action environment
path, contracts, save/reload and a synthetic PPO update. Offline transfer from
the actual 952,343-step checkpoint reproduced its speed output exactly on 32
fixed observations, initialized yaw to zero and preserved a fresh critic and
optimizer. The original checkpoint SHA256 remained unchanged:
`146398abd63bc28afc7f27532636a93f487d6d89b7002e70b3683b34bc2c4ee5`.

Local verification: `rl_runs/flat_speed_yaw_offline_check/verification.json`.
Its `transferred_untrained.zip` is only an offline test artifact, not a trained
pilot. No live training was started as part of implementing this change.
