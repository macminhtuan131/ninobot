# Separate focused Optuna studies

These commands create independent flat and rough studies. They use the corrected
profiles, fixed evaluation objective and comparable-trial checks implemented on
2026-10-08. The earlier comparable studies remain preparation records: their
search/code contracts differ, so their directories are not reused.

## Search space

| Parameter | Range / choices |
|---|---|
| Learning rate | 0.00001–0.0001, log scale |
| Entropy coefficient (exploration) | 0.0001–0.003, log scale |
| PPO rollout steps | 1,024 / 2,048 |
| PPO batch size | 128 / 256 / 512 |
| PPO update epochs | 3 / 5 / 8 |
| PPO clipping | 0.10–0.25 |
| Time penalty | Flat: 0.10–0.30; rough: 0.02–0.12 |
| Lateral error weight | 0.25–0.80 |
| Heading error weight | 0.15–0.55 |
| Vertical impact weight | 0.02–0.12 |
| Roll/pitch angular-rate weight | 0.02–0.10 |
| Slip weight | 0.05–0.25 |

Progress, arrival bonus, goal braking, gamma (0.997), GAE (0.95), target KL
(0.015), network architecture and the initial actor's action standard deviations
are fixed. Entropy affects exploration during training. Sampling only
`initial_action_std` would not change a transferred actor: transfer restores its
saved `log_std`, so this search does not offer that ineffective parameter.

The sampler is TPE, seed 42, four startup observations before guided proposals.
The existing parameter configuration is queued first without an inherited score.
Twelve trials are an initial screening budget, not proof of optimal parameters.

Each trial trains **20,480** new environment steps (20,000 requested, aligned to
complete PPO rollouts). Each uses the same course checkpoint with actor-only
initialization and a fresh critic/optimizer. Twelve trials total 245,760 training
steps per course, plus evaluation.

## Fixed settings

- Flat: `combined_flat_pi_tracking.yaml`, fixed two-cable stage, conditional PI,
  assisted odometry and path feedback; two speed/yaw actions. Evaluation: 24
  scenarios starting at seed 61000.
- Rough: `rough_e1_n1_s1_fixed.yaml`, original terrain-bank world, legacy PI,
  IMU-assisted odometry; three speed/common/differential-torque actions. Fixed
  E1/N1/S1 routes with E1 replay. Evaluation: 12 scenarios starting at seed 10000,
  four per route.
- Geometry, physical arrival radius, ordered route gates, controller, estimator,
  action meanings and scenario lists are fixed. No terrain randomization is added.
- The separate evaluation objective stays fixed while training reward weights vary.
  Exporting a qualified best policy requires at least 95% observed physical
  arrivals **on every evaluated route**. This small evaluation set does not establish
  a population-level 95% reliability guarantee.
- PI results are references, not PPO trial observations. Earlier incompatible
  scores are not imported.

The rough N1/S1 PI failures are still known diagnostic issues. This small search
tests whether learning changes performance; it does not establish that tuning
can fix their stalls or estimator drift. Inspect route failures before expanding
the search or launching long training.

## Commands

Build once after these changes:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
python -m colcon build --symlink-install --packages-select nino_control nino_description nino_rl
```

The launcher sources ROS, the virtual environment and the workspace itself. It
sets flat to ROS domain 79 / Gazebo partition `nino_flat_79`; rough uses domain 78 /
partition `nino_rough_78`. Use four terminals and wait for each simulator's
controllers to be ready before starting its tuner. Keep one tuner/evaluator per
world.

Terminal A — flat Gazebo:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/run_focused_optuna.sh flat sim
```

Terminal B — flat Optuna:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/run_focused_optuna.sh flat tune
```

Terminal C — rough Gazebo:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/run_focused_optuna.sh rough sim
```

Terminal D — rough Optuna:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/run_focused_optuna.sh rough tune
```

Use `sim headless:=false` to open the GUI. The default is headless for tuning.
The launcher passes explicit world/profile/checkpoint/evaluation inputs; inspect
`src/nino_rl/scripts/run_focused_optuna.sh` for the full underlying Python commands.

To prepare/queue studies without training or a simulator:

```bash
bash src/nino_rl/scripts/run_focused_optuna.sh flat prepare
bash src/nino_rl/scripts/run_focused_optuna.sh rough prepare
```

Results:

- `rl_runs/flat_focused_optuna_v1`
- `rl_runs/rough_focused_optuna_v1`

Each contains `study.db`, frozen plans, trial logs, saved models and evaluation
breakdowns. `best_trial.yaml` and `best_model.txt` are written only after the
optimization invocation finishes and a trial passes the arrival gate. Otherwise
inspect `best_infeasible.json`; a highest score is not automatically a qualified
policy.

Repeating `tune` continues the same study with **12 additional trials**, including
any waiting candidate. Use `tune --trials 4` for four additional trials. Interrupting
a live trial does not resume its unfinished rollout automatically; an interrupted
trial may remain RUNNING in SQLite. Completed observations remain available to
the sampler. The strict contract rejects changed assets/code/settings: use a new
output directory when intentionally changing them.

When both worlds run concurrently, CPU contention may reduce throughput. Retain
the timing checks; run one study at a time if a simulator cannot meet them.

Before a long training run, evaluate shortlisted policies on new seeds against
matching PI references. Then apply a qualified configuration to training; this
search itself does not deploy a policy to hardware.
