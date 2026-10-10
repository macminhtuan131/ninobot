# Flat speed/yaw isolation and targeted PPO pilot — 2026-10-10

## Experiment

The selected flat Optuna actor arrived on all 24 held-out two-cable scenarios,
but normal-speed PI was faster and had lower mean vibration and slip. The
existing reward also gave PI a higher mean return. This experiment first
isolates the two learned outputs, then tests one actor initialization correction.

### Comparison

- Preserve trial 13 and both existing 24-episode reports.
- Reuse seeds 62000–62023, the two-cable stage, angles ±2°, unchanged physical
  arrival scoring and the conditional PI controller.
- **Speed only:** execute PPO's speed action, set its yaw residual to zero;
  estimated-pose PI still steers.
- **Yaw only:** set speed scale to one, execute PPO's yaw residual.
- Overrides happen before `env.step`, so observation history and reward reflect
  the action actually executed. The actor receives no simulator truth inputs.
- Capture policy and motor-controller traces. An existing `--speed-only` flag
  applies only to the older torque action contract; the new runner uses a
  separate evaluator snapshot for these two-action ablations.
- Rank with the existing fixed evaluation objective. This is a descriptive
  comparison of one actor; simulator contact variation can affect the result.

The controller scales both linear and angular references with the speed scale.
Consequently, a speed override also changes executed steering authority. These
ablations measure the current closed-loop interfaces rather than completely
independent physical effects of speed and yaw.

### Targeted pilot

After both ablations finish, reset only an actor output whose removal improves
the fixed quality cost without reducing measured arrival success. If neither
ablation isolates a useful correction, test both heads near PI as an interaction
hypothesis. This rule is declared before pilot evaluation.

- Copy the selected actor's feature extractor and policy trunk.
- A reset speed head starts at scale **0.97**, action standard deviation **0.08**.
- A reset yaw head starts at zero residual, action standard deviation **0.04**.
- Preserve any unselected head. The policy remains trainable; no output is
  permanently disabled in the pilot.
- Initialize a **fresh critic and optimizer**, counter zero; never resume an
  incompatible value model.
- Train **20,480 new steps** (20 complete 1,024-step rollouts), seed 42.
- Keep reward, action meanings, PPO update settings, controller, estimator,
  geometry, physical arrival circle and two-cable stage unchanged.
- Record a new training contract with source actor and code fingerprints.
- Evaluate the pilot and normal-speed PI on **24 new matching seeds
  63000–63023**. These are pilot test scenarios, not the diagnostic scenarios.

The provisional promotion gate requires 24/24 physical arrivals, mean completion
at most 18.5 s, physical path RMSE at most 1.05 times matching PI, and at least
10% lower RMS vibration or slip without worsening the other metric. This is a
pilot decision rule, not proof of population-level reliability or statistical
significance. No three-cable promotion or longer training is automatic.

## Commands

Run in the project virtual environment after sourcing ROS and the workspace:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

python src/nino_rl/scripts/run_flat_speed_yaw_comparison.py
python src/nino_rl/scripts/run_flat_targeted_pilot.py
```

Each runner owns and closes its flat simulator on domain 79 / partition
`nino_flat_79`; it refuses to join an existing flat simulator or trainer.
The independent rough session on domain 78 is preserved.

## Evidence and status

### Completed ablations

All 24 matching scenarios reached the physical goal and cleared both cables.

| Metric | Normal PI | Existing full PPO | PPO speed, PI steering | Full speed, PPO yaw |
|---|---:|---:|---:|---:|
| Physical arrivals | 24/24 | 24/24 | 24/24 | 24/24 |
| Mean time | 17.48 s | 19.34 s | 19.47 s | 17.52 s |
| Physical path RMSE | 3.51 cm | 3.64 cm | 4.33 cm | 3.59 cm |
| RMS vertical acceleration | 1.760 m/s² | 2.146 m/s² | 2.208 m/s² | 2.991 m/s² |
| RMS wheel slip | 0.1797 | 0.1909 | 0.1956 | 0.1871 |
| Fixed quality score (higher is better) | 25.111 | 22.924 | 22.212 | 22.451 |

Removing learned yaw did not improve these aggregate metrics. Preserve the
possibility that learned yaw helps, rather than assuming all learned steering
is harmful. Full speed recovered PI-like completion time, but had higher mean
vibration. Neither ablation improved the full actor's fixed quality score.

The frozen decision rule selected the interaction hypothesis: **reset both
action heads near PI**, retaining actor features/trunk, with a fresh critic and
optimizer. Reward and controller remain unchanged. This tests whether a more
competent initial action distribution helps; the ablations do not prove that
both heads independently caused every poorer result.

- Diagnostic plan and results: `rl_runs/flat_speed_yaw_ablation_v1/`.
- Pilot plan, model, TensorBoard and evaluation: `rl_runs/flat_targeted_actor_pilot_v1/`.
- Initialization/action-isolation checks: `src/nino_rl/test/test_flat_targeted_pilot.py`
  — five checks passed before running the pilot.
- Original comparison: [flat Optuna report](FLAT_OPTUNA_RESULT_2026-10-09.md).

### Pilot completed — evaluation result

The pilot started on CUDA at approximately **00:26 on 2026-10-10** (Asia/Bangkok)
and completed **20,480 steps**. All 12 mandatory live preflight checks passed.
The saved actor-transfer record confirms both head resets, the selected source
model, and fresh critic/optimizer with counter zero. All **112 completed training
episodes** arrived; training outcomes are separate from the test below.

The final actor and matching normal-speed PI were each evaluated on all **24
fresh scenarios, seeds 63000–63023**. Both reached the physical goal and cleared
both cables in every episode.

| Metric | Matching PI | Targeted PPO pilot | PPO change |
|---|---:|---:|---:|
| Physical arrivals | 24/24 | 24/24 | Equal |
| Mean completion | 17.53 s | 18.20 s | +3.8% |
| Physical path RMSE | 2.88 cm | 3.59 cm | +24.5% |
| RMS vertical acceleration | 2.735 m/s² | 3.658 m/s² | +33.8% |
| Mean episode peak vertical acceleration | 65.90 m/s² | 89.94 m/s² | +36.5% |
| RMS wheel slip | 0.1915 | 0.1895 | −1.0% |

**Do not promote this pilot to longer training or the next cable stage.** It
passes arrival and the 18.5 s completion gate, but fails both tracking and the
comfort/slip improvement gate. The small slip reduction does not meet the
declared 10% improvement requirement, and vibration worsened.

PI-centered initialization retained reliable arrival and acceptable completion
time but did not produce the intended gain over matching PI. The final logged
critic explained variance remained near zero; review value learning and reward
measurement alignment before another pilot. This does not by itself identify
a unique cause or prove that a longer run would fail.

These scenarios differ from the earlier ablation test. Compare the pilot with
its **matching PI**, rather than treating changes in absolute vibration between
the earlier and current tables as a controlled policy comparison. No independent
training seeds or statistical significance are established.

Run directory:
`rl_runs/flat_targeted_actor_pilot_v1/train/20261010-002632-975129/`.

The final model is saved as `nino_ppo_final.zip` in that run directory.
Complete results are in `rl_runs/flat_targeted_actor_pilot_v1/comparison.json`.
The runner has finished and closed its owned flat simulator. Existing studies
and checkpoints are retained, and no pilot observation was imported into the
old Optuna study.
