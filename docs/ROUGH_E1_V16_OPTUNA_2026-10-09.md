# New rough E1 Optuna study — 2026-10-09

## Status

Created `rl_runs/rough_e1_v16_optuna_v1/study.db`, study name
`rough_e1_v16_quality_v1`. Trial 0 is WAITING with the current PPO/reward
parameters queued. No inherited score, historical trial import, Gazebo session
or training run was started during preparation. Earlier rough and flat studies
and saved models remain preserved.

Ten focused tests passed. The actor-transfer audit verified 13 copied actor
tensors, an unchanged fresh critic, empty optimizer state and a zero training
counter. This preparation is not evidence that tuned policies improve PI.

## Fixed inputs

- Original v16 rough terrain and E1 only; no terrain randomization or N1/S1.
- Frozen v16 localization, 33-layer cloud sensor, controller and recovery code.
- Existing three-action `wheel_torque` meanings and network architecture.
- Ground-truth physical arrival scoring, 0.20 m goal circle, ordered route
  gates and existing physical failure thresholds.
- Source actor: `rl_runs/rough_wall_recovery_v16/curriculum/blocks/block_0000/train/20261009-101753-653623/nino_ppo_final.zip`.
- Source SHA-256: `105168ca385f28969b0b3e6a062a3f813a4159c0442489be61e20d17a2bcb943`.
- Every trial imports only that actor with a new critic/optimizer, seed 42 and
  20,480 new steps. Trial training uses `--init-model`, never `--resume`.
- Twenty deterministic evaluation episodes, seeds 10000–10019, per trial.
- Full-speed and speed-matched PI results are reference records only, not
  synthetic Optuna observations.

Source code, snapshot files, world/mesh assets, robot/controller configuration,
actor, objective and reference evidence are fingerprinted. Changes require a
new study directory. A file lock prevents simultaneous workers in this study.

## Search space

| Parameter | Search range |
|---|---|
| Learning rate | 1e-5–1e-4, log scale |
| Entropy coefficient | 1e-4–3e-3, log scale |
| Rollout steps | 1024 or 2048 |
| Batch size | 128, 256 or 512 |
| PPO epochs | 3, 5 or 8 |
| PPO clipping | 0.10–0.25 |
| Time penalty | 0.03–0.50, log scale |
| Lateral reward weight | 0.25–0.80 |
| Heading reward weight | 0.15–0.55 |
| Impact reward weight | 0.02–0.12 |
| Body-rate reward weight | 0.02–0.10 |
| Slip reward weight | 0.05–0.40 |

Both rollout choices divide the identical 20,480-step budget. Architecture,
discounting, observation definitions and physical/controller parameters remain
fixed. Initial action standard deviation is not sampled: actor transfer restores
the checkpoint's `log_std`, so that constructor setting would not affect trials.
TPE starts with four startup trials, including the queued current candidate.

## Fixed evaluation objective

Settings: `src/nino_rl/config/rough_e1_v16_optuna_objective.yaml`.
Implementation: `src/nino_rl/scripts/rough_e1_optuna_objective.py`.

Qualification requires **at least 19/20 physical arrivals and zero rollovers**.
Every claimed arrival must be inside the physical goal circle with all ordered
route gates passed. Failed episodes receive maximum quality costs, preventing a
stationary or early-failing robot from winning on low vibration.

The quality cost combines duration, lateness, physical path error, RMS vertical
acceleration, mean episode peak vertical acceleration and slip. Time target is
**31.0 s**, approximately 14% above full-speed PI's 27.1 s. This is an evaluation
quality target; the physical episode deadline and training success conditions
are unchanged.

Fixed weights are duration 1, lateness 4, path error 4, RMS vibration 1, slip 2,
and peak acceleration 1. Normalization scales are path RMSE 0.05 m, RMS vertical
acceleration 1.153 m/s², slip 0.041123, and peak acceleration 11.70 m/s². These
are frozen before tuning and are never sampled as training reward parameters.

Qualified score is `100 / (1 + quality_cost)`; unqualified trials score below
-1000. A completed policy evaluation that fails the task is a legitimate
negative observation. Transport/startup/timing failures are execution errors,
not evidence that its sampled learning parameters are bad.

## Start or continue

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

python src/nino_rl/scripts/tune_rough_e1_v16.py \
  --device cuda --trials 8 --timesteps 20480
```

The runner automatically sets domain 78 and `nino_rough_78`, starts its own
headless rough simulator with the reliable sensor bridge, checks the controller
profile, trains and evaluates sequentially, then closes its owned processes.
Do not launch a separate rough simulator. Domain-79 flat work is independent.

`--trials` means additional trials per invocation. Repeating the same command
continues the same database; it does not erase earlier scores. Changing the
step budget, device, actor, evaluation objective or frozen inputs requires a
new `--output` directory. An abandoned RUNNING trial after a hard shutdown
requires artifact review; this runner refuses to silently discard/retrain it.

Execution errors stop the worker with the trial directory and logs preserved;
they do not silently consume further trials or receive fabricated scores.
Inspect `trial_NNNN/train.log`, `evaluation.log`, `profile.log` and `gazebo.log`.

Preparation can be checked again without training:

```bash
python src/nino_rl/scripts/tune_rough_e1_v16.py --prepare-study
```

## Outputs and next gate

- `study_contract.json`, `trial_plan.json`, `evaluation_objective.json`: fixed
  comparable conditions and scoring settings.
- `trial_NNNN/trial.yaml`, trained model and evaluation records: per-trial
  evidence, including actor-transfer and completed-budget verification.
- `best_trial.yaml`, `best_model.txt`, `best.json`: best arrival-qualified
  candidate, exported after each completed trial.
- `best_infeasible.json`: no qualified completed candidate yet.

Best means best among the evaluated candidates, not automatically better than
PI. Compare its score and raw metrics with both saved PI references. Confirm
the selected candidate using held-out seeds (for example 12000–12019) before
a long run, then introduce N1 with E1 replay on fixed terrain. The current E1
study does not tune turning routes or establish unseen-terrain generalization.

## Recover trial 2 after Ctrl+C during evaluation

At 15:57 on 2026-10-09, Ctrl+C interrupted trial 2's evaluation after 12
successful episodes. Training had completed all 20,480 steps and its final
model and initialization/budget evidence were verified. This is an interrupted
execution, not a measured bad parameter result.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

python src/nino_rl/scripts/recover_rough_e1_v16.py --trial 2 --evaluate
```

The helper starts and closes its own rough simulator. It reruns the full fixed
20 evaluation seeds without retraining and preserves the original partial
evaluation and FAIL record. After checking model/configuration, physical
scoring, initialization and step budget, it makes a consistent database backup
and appends one completed observation with the original parameters and
distributions. A repeated recovery cannot add the same observation twice.
Recovery execution itself has not been launched by the dry audit.

After successful recovery, three completed observations remain in the study.
Continue with five additional trials to reach eight completed observations:

```bash
python src/nino_rl/scripts/tune_rough_e1_v16.py \
  --device cuda --timesteps 20480 --trials 5
```

The recovery helper also prints the current remaining count. Omitting
`--evaluate` performs only a model/contract audit and prints the command.
