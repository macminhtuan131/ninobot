# Flat Optuna result and held-out PI comparison — 2026-10-09

## Decision

The selected PPO policy passes physical arrival on the two-cable stage but
**does not outperform normal-speed PI** in this held-out comparison. Preserve
the policy and study. Avoid extending unchanged flat tuning or starting a long
training run solely because Optuna selected a best trial.

## Completed study

- Study: `flat_focused_optuna_v1`, 12 completed trials and two historical failed
  executions. All 12 completed trials achieved 24/24 physical arrivals on tuning
  scenarios 61000–61023.
- All completed scores were recomputed from episode CSVs and matched the fixed
  evaluation objective.
- Selected trial: **13**, score **22.962309**. Trial 10 scored 22.926213; this
  small difference does not establish a repeatable gain.
- Trial 13 trained 20,480 new steps from the flat feedback actor with a fresh
  critic/optimizer. It did not resume the old 1.5M checkpoint.
- Flat action mode is two learned speed/yaw references over the corrected PI
  controller, not learned direct motor torque.

## Held-out validation

Ran **24 PPO and 24 normal-speed PI episodes** on seeds **62000–62023**.
World, controller, estimator, physical scoring and scenario seeds match.
The conditional PI profile and 0.20 m physical arrival circle are unchanged.
Model transfer and completed training budget were verified before evaluation.
This test did not update model weights or add observations to the Optuna study.

Both controllers achieved **24/24 physical arrivals**, cleared both cables on
every episode, and completed all episodes within the 22 s quality target.

| Metric | Normal-speed PI | Selected PPO | PPO change versus PI |
|---|---:|---:|---:|
| Completion time | 17.48 s | 19.34 s | +10.7% |
| Physical path RMSE | 3.51 cm | 3.64 cm | +3.8% |
| RMS vertical acceleration | 1.760 m/s² | 2.146 m/s² | +21.9% |
| Mean episode peak vertical acceleration | 36.03 m/s² | 54.29 m/s² | +50.7% |
| RMS wheel slip | 0.1797 | 0.1909 | +6.2% |
| RMS wheel torque | 0.4301 N·m | 0.4292 N·m | −0.2% |

The fixed quality objective gives **PI 25.111** and **PPO 22.924**; higher is
better. Both pass the physical arrival qualification. Objective settings match
tuning, with only the evaluation scenario list and its hash changed for holdout.

## Interpretation and limits

PI is faster and has lower mean RMS vibration, peak acceleration and slip.
Tracking is close: the difference in mean physical RMSE is only **1.33 mm**.
Mean torque is essentially unchanged. Peak acceleration varies across cable
contacts; the table reports mean episode maxima, not a guaranteed impact bound.
No causal explanation or statistical significance is established here.

This supports withholding a claim that this selected PPO policy improves PI.
It does not establish that RL cannot improve. One selected trained policy was
tested, without independent training seeds. Twenty-four successful scenarios
do not establish a population-level 95% arrival guarantee.

The tested stage is **two cables, angles −2° to +2°, no adaptive features**.
Geometry is fixed and sensor/motor domain perturbations are disabled. New seeds
cover configured scenario draws; they are not unseen layouts, wide-angle cables,
six cables or real hardware. The wider angle range in the course configuration
is overridden by the fixed curriculum stage.

The earlier saved slow PI reference at scale 0.78 took 22.35 s with 5.15 cm
physical path RMSE. Comparing only with slow PI made PPO look stronger. The
earlier full-speed PI reference covered only four tuning scenarios; this new
24-seed paired full-speed comparison fills that gap. Historical results remain
preserved.

## Next work

1. Keep normal-speed PI as the two-cable reference and preserve trial 13 as an
   arrival-qualified candidate.
2. Inspect learned speed/yaw behavior near cable crossings and goal approach.
   A targeted yaw-correction ablation on matching scenarios can isolate whether
   steering corrections hurt performance. Evaluation alone changes no reward
   or policy.
3. Define a measurable RL gain, such as reduced impacts while retaining arrival
   reliability and acceptable completion time. Avoid treating lower speed as a
   substitute for measured benefits.
4. Once corrected behavior is justified, use a short three-cable curriculum
   block with two-cable replay. Reward/controller/stage changes require a fresh
   contract; validate before long training or full-course deployment.
5. Do not add identical two-cable Optuna trials merely to increase the count.
   Broader scenario coverage and independent training seeds would provide
   stronger evidence.

## Evidence

- Selected model: `rl_runs/flat_focused_optuna_v1/best_model.txt`.
- PPO: `rl_runs/flat_optuna_holdout_v1/ppo/` (complete timestamped summary,
  episode CSVs and trajectories).
- PI: `rl_runs/flat_optuna_holdout_v1/pi/` (matching complete evidence).
- Machine-readable comparison: `rl_runs/flat_optuna_holdout_v1/comparison.json`.
- Recomputed study scores: `rl_runs/flat_optuna_holdout_v1/study_audit.json`.
- Model/input fingerprints: `rl_runs/flat_optuna_holdout_v1/validation_plan.json`.
- Owned validation runner: `src/nino_rl/scripts/validate_flat_optuna.py`.

The flat simulator was closed after evaluation. The separate rough session was
not stopped or modified.
