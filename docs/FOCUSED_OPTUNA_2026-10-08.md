# Separate focused Optuna studies

## Flat action comparison and pilot — 2026-10-10

Both 24-seed speed/yaw ablations arrived reliably, but neither improved the
selected actor's fixed quality score. Removing yaw worsened tracking; forcing
full speed recovered PI-like time but increased vibration. A single 20,480-step
pilot completed PI-centered action-head initialization, retaining actor
features with a fresh critic/optimizer and unchanged reward/controller.
On 24 new matching seeds, both it and PI arrived 24/24 times. The pilot took
18.20 s versus PI's 17.53 s, with 24.5% higher physical path RMSE and 33.8%
higher RMS vibration. It failed the tracking and quality promotion gates;
withhold a longer run or next-stage promotion pending a targeted correction.
See the [experiment, results and commands](FLAT_SPEED_YAW_TARGETED_PILOT_2026-10-10.md).

## Flat result — evaluated 2026-10-09

Flat tuning finished 12 completed trials. Trial 13 was selected. In the new
24-seed held-out two-cable comparison, both PPO and normal-speed PI arrived
24/24 times, but PI was faster and had lower mean vibration and slip. The
selected PPO policy is arrival-qualified; superiority over PI is not established.
See the [complete result and next steps](FLAT_OPTUNA_RESULT_2026-10-09.md).
Further identical flat tuning or a long unchanged training run is not recommended
from this evidence alone.

## Current rough status — 2026-10-09

The [S1 controller and bounded recovery correction](ROUGH_S1_RECOVERY_2026-10-09.md)
is the current rough candidate. It uses the new v16 contract; check its complete
PI gate before an actor-initialized PPO pilot or a new Optuna study.

The old rough study remains held. Its saved scores and models are diagnostic
records, not candidates for the changed estimator contract. The v7 rough
pilot exposed repeated loss of 2D wall coverage at the E1 crest and was saved
at 6,326 steps. Use the [rough localization robustness profile](ROUGH_LOCALIZATION_ROBUSTNESS_2026-10-09.md)
for slow/normal PI qualification and the new actor-initialized pilot. Further
rough Optuna tuning requires a separate study after that setup is validated.
The existing flat study continues independently on its original contract.

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

## Recovery after a shutdown

With all tuner/training/evaluation processes stopped, preview recovery:

```bash
cd ~/ninorobot
.venv/bin/python src/nino_rl/scripts/recover_focused_optuna.py
```

Apply recovery before restarting the simulators and tuners:

```bash
.venv/bin/python src/nino_rl/scripts/recover_focused_optuna.py --apply
```

The helper checks SQLite integrity and frozen input hashes, creates a consistent
database backup, queues each abandoned trial's exact parameters, and marks the
old unfinished trial FAIL without inventing a score. Completed trials remain
unchanged. Repeating recovery does not duplicate a queued retry. An incomplete
parameter set is rejected for inspection.

It prints the remaining trial count to reach 12 completed observations. After
launching each simulator with the commands above, run its printed `tune --trials N`
command. Interrupted parameter sets restart training from the frozen starting
actor with fresh critic/optimizer; they do not resume a partial checkpoint or
unfinished rollout. Their earlier log/checkpoint directories are preserved.

The shutdown inspected on 2026-10-08 left flat with two completed trials and
trial 2 abandoned, rough with one completed trial and trial 1 abandoned. At that
snapshot, the recovery commands were:

```bash
bash src/nino_rl/scripts/run_focused_optuna.sh flat tune --trials 10
bash src/nino_rl/scripts/run_focused_optuna.sh rough tune --trials 11
```

Before a long training run, evaluate shortlisted policies on new seeds against
matching PI references. Then apply a qualified configuration to training; this
search itself does not deploy a policy to hardware.

## Recover an evaluation failure without retraining

On 2026-10-08, rough trial 2 completed all 20,480 training steps, then evaluation
failed during initial sensor setup with `Assisted odometry encoder gap exceeded
its bound`. The configured encoder gap is 0.25 s. No evaluation episodes were
written, so this is an infrastructure/startup failure, not an evaluated poor
policy score. The exact cause of the timestamp gap has not been established.

Restart rough Gazebo using Ctrl+C in its simulator terminal, then:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/run_focused_optuna.sh rough sim
```

Once its controllers are ready, in the rough tuner terminal:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/run_focused_optuna.sh rough recover-eval --trial 2 --evaluate
```

This checks the intact completed model, frozen assets and original training
evidence, reruns the exact 12 evaluation seeds, and appends a completed
observation only after the full report passes the objective checks. The original
FAIL record is preserved; it is not rewritten as COMPLETE. A consistent database
backup is made before appending. Repeating recovery cannot add the same score
twice. No PPO training, model weights, estimator bounds or physical arrival
criteria are changed.

The helper prints the number of remaining trials. At the failed-trial snapshot,
after successful score recovery the continuation command is:

```bash
bash src/nino_rl/scripts/run_focused_optuna.sh rough tune --trials 10
```

The flat tuner can continue independently. If the same sensor gap occurs again,
inspect the new `trial_0002/eval_recovery_*/evaluate.log`; this retry does not
establish that restarting transport permanently fixes the startup fault. A source
or estimator change requires a new study contract, rather than weakening the
timestamp guard inside this study.

## Rough speed-matched comparison — completed 2026-10-09

The frozen v16 E1 pilot and PI both reached 20/20 physical goals. A further
20-seed PI evaluation at speed scale 0.70 matched PPO completion time within
0.4%. Most of PPO's RMS vibration advantage over full-speed PI was reproduced
by simply slowing PI. PPO retained lower peak acceleration and slightly better
tracking than slow PI, but had higher slip. See the
[complete comparison](ROUGH_SPEED_MATCHED_PI_2026-10-09.md) before a long rough
continuation. Rough Optuna remains held; the earlier study and models are preserved.

## New validated E1 study — prepared 2026-10-09

A separate `rough_e1_v16_quality_v1` study is now prepared in
`rl_runs/rough_e1_v16_optuna_v1`. It fixes the v16 E1 terrain/controller/scoring,
copies the same pilot actor into a fresh critic/optimizer for every trial, and
tunes learning/update settings plus time, tracking, impact and slip rewards.
Its independent fixed evaluation objective includes a 31 s quality target,
peak acceleration, slip costs, at least 19/20 physical arrivals and zero
rollovers. Trial 0 is queued; preparation launched no training. See
[setup and start commands](ROUGH_E1_V16_OPTUNA_2026-10-09.md). The older rough
study remains held; its scores are not mixed into the new study.

## Flat critic and impact correction — prepared 2026-10-10

The completed flat pilot remains below matching PI on tracking and vibration.
A read-only probe confirmed weak value predictions and critic-dominated global
gradient clipping. The old clipped impact reward also assigned lower impact
cost to PPO despite its higher RMS vibration. Two new isolated revision-38
profiles are prepared: reward units ×0.01 with the old task reward, then the same
units with timestamped acceleration energy and an episode-peak cost. Both use
the same saved actor and a fresh critic/optimizer. No new pilot training has
started. Physical scoring and historical studies remain unchanged. See the
[diagnosis, checks and controlled run commands](FLAT_REWARD_CRITIC_CORRECTION_2026-10-10.md).
