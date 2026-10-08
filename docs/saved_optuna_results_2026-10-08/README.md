# Using saved results in the new Optuna studies

Prepared on 2026-10-08. This follows the
[fixed evaluation objective](../optuna_objective_2026-10-08/README.md) and
[comparable trial inputs](../comparable_optuna_trials_2026-10-08/README.md).

## Current state

| Course | New study directory | Current candidate | Completed/scored trials | Historical scores imported |
|---|---|---|---:|---:|
| Flat | `rl_runs/flat_comparable_optuna_v2` | Trial 0, **WAITING** | 0 | 0 |
| Rough | `rl_runs/rough_comparable_optuna_v2` | Trial 0, **WAITING** | 0 | 0 |

One current configuration is actually queued in each SQLite study. Queuing
parameters does **not** assign them a score, train a model, or mark them as
successful. No Optuna optimization or robot training was started.

The earlier `*_comparable_optuna_v1` plans remain historical preparation
snapshots. The new v2 directories include the saved-result reuse support and
its code fingerprints; their older preparation snapshots are not overwritten.

## 1. PI results are reference performance

PI is not a PPO training trial. Its results are stored as study/reference
metadata and in `saved_results_plan.json`; they are never inserted into the
Optuna sampler's trial observations.

| Reference | Physical arrival | Mean time | Mean physical path RMSE | Role |
|---|---|---:|---:|---|
| Corrected flat PI, scale 0.78, 24 scenarios | 24/24 | 22.354 s | 0.05154 m | Matches the full planned flat scenario list. |
| Corrected flat PI, scale 1.0, four targeted scenarios | 4/4 | 17.500 s | 0.04679 m | Smaller diagnostic comparison; does not replace the full 24-scenario reference. |
| Rough route PI, 12 scenarios | E1 4/4; N1 0/4; S1 0/4 | See per-route reference | See per-route reference | Matches the full planned rough scenario list; failed routes remain failures. |

For rough, E1 successful completion averages 26.975 s. N1 and S1 have no
successful completion-time reference. Their failed-run durations are not
targets to beat. Exact route values are in the
[saved route reference](../corrected_training_setup_2026-10-08/rough_route_pi_references.json).

The reuse audit checks complete reports, physical episode measurements,
matching task/controller/estimator fingerprints and exact scenario coverage.
The fixed objective can also describe a matching PI report's quality cost,
but that is a **reference calculation**, not an Optuna observation. Reports
with smaller/different scenario lists are retained with a diagnostic reason.
These old reports do not contain the full new simulator asset manifest;
task/scenario matching should not be described as proof of arbitrary historical
scene changes or real-world generalization.

## 2. Current parameters are the first candidate

Each tuner runs its own real parameter sampler with the current base values,
verifies that it reproduces the **entire resolved configuration exactly**, then
uses `study.enqueue_trial(..., skip_if_exists=True)` to queue those parameters.
Repeating preparation does not create duplicate queued candidates.

| Parameter | Flat | Rough |
|---|---:|---:|
| Learning rate | 0.00006781612720853196 | 0.00003 |
| Gamma | 0.997 | 0.997 |
| PPO rollout length | 1,024 | 2,048 |
| Entropy coefficient | 0.0007249253652592024 | 0.001 |

The queued reward weights are also the current weights. Unsearched settings
remain those of the resolved profile. These candidates use the same frozen
actors and fresh critic/optimizer method already audited, with **20,480 new
environment steps per trial**. They do not inherit the source actor's original
training score or optimizer state.

If a base value lies outside the declared search range, preparation fails
explicitly. It does not silently clip or omit the current configuration.
Architecture parameters are included when the combined tuner runs from scratch.

Complete candidate dictionaries and reference metrics:

- [Flat saved-results plan](flat_saved_results_plan.json)
- [Rough saved-results plan](rough_saved_results_plan.json)
- [Flat trial-input snapshot](flat_trial_plan.json)
- [Rough trial-input snapshot](rough_trial_plan.json)
- [Verified queue state](preparation_status.json)

## 3. Historical scores require matching conditions

`--history-study PATH` is repeatable and accepts a study directory or SQLite
file. The reader opens the historical SQLite database with `mode=ro`, avoiding
schema migrations or changes to its trials.

A score is imported only when:

1. The source is a single-objective maximization study with exactly the same
   frozen evaluation objective, comparable training contract and base/search
   space contract. This includes controller, estimator, world/assets/code,
   starting actor/method, training seed/budget/device and evaluation scenarios.
2. The source trial is **COMPLETE**, with a finite scalar score and matching
   parameter distributions. Incomplete, running and infrastructure-failed
   trials remain diagnostic records.
3. Its saved evaluation is full PPO, not PI or a speed-only/action ablation.
   The model, task fingerprint, physical measurements and exact scenarios must
   match. Recomputing the fixed objective from the saved episodes must reproduce
   the stored score and qualification flag.
4. The saved trial configuration matches its sampled parameters. Its model,
   training contract, exact completed step count and initialization evidence
   must pass the comparable-trial verifier.
5. The frozen source checkpoint/assets remain available and unchanged.

Accepted trials use `study.add_trial` with source database/study/trial provenance.
Import is idempotent: the same source trial is not added twice. A correctly
recorded **poor policy result** is eligible when conditions match, so the sampler
can learn from unsuccessful parameter sets. Low performance alone is not a
reason to discard a completed trial.

These checks are deliberately strict. Matching a learning rate or a success
percentage is insufficient. Legacy scores are not relabeled as the new objective,
and changing conditions is not repaired by merely recalculating an old score.

## 4. Earlier incompatible results remain diagnostic

All **eight** existing historical databases lack the new fixed-objective and
comparable-trial contracts. No historical trial score was imported. Their
databases, checkpoints, logs and evaluation reports were left intact.

- [Historical inventory and original score records](historical_inventory.json)
- [Flat import audit](flat_history_import_report.json)
- [Rough import audit](rough_history_import_report.json)

The historical inventory labels old values as stored scores, not current
objective scores. Keep them to diagnose torque corrections, estimator drift,
reward trade-offs and training behavior. Compatible actor weights and current
parameter choices can still provide initialization/candidate values; that is
different from importing their earlier performance observations.

## Prepare or recheck the queued studies

Run the shared setup in the relevant terminal:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
```

Flat preparation:

```bash
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export GZ_PARTITION=nino_flat_79
python src/nino_rl/scripts/tune_split_optuna.py --section flat \
  --config src/nino_rl/config/combined_flat_pi_tracking.yaml \
  --world src/nino_description/worlds/combined_flat_section.sdf \
  --init-model rl_runs/flat_feedback_pilot/20261008-035120-161159/nino_ppo_final.zip \
  --device cuda --timesteps 20000 --eval-episodes 24 --eval-seed 61000 \
  --pi-reference rl_runs/flat_pi_tracking_slow_complete/20261008-validation/summary.json \
  --pi-reference rl_runs/flat_pi_tracking_normal_targeted/20261008-110002-871004/summary.json \
  --history-study rl_runs/combined_flat_optuna_fresh \
  --history-study rl_runs/combined_flat_optuna_v2 \
  --history-study rl_runs/combined_flat_optuna \
  --history-study rl_runs/flat_curriculum_optuna \
  --output rl_runs/flat_comparable_optuna_v2 --prepare-study
```

Rough preparation:

```bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export GZ_PARTITION=nino_rough_78
python src/nino_rl/scripts/tune_split_optuna.py --section rough \
  --config src/nino_rl/config/rough_e1_n1_s1_fixed.yaml \
  --world rl_runs/rough_terrain_bank_v1/worlds/original.sdf \
  --init-model rl_runs/rough_e1_imu_assisted_pilot/20261008-013943-771247/nino_ppo_final.zip \
  --device cuda --timesteps 20000 --eval-episodes 12 --eval-seed 10000 \
  --pi-reference rl_runs/rough_e1_n1_s1_route_pi/20261008-104043-455255/summary.json \
  --history-study rl_runs/combined_rough_optuna_fresh \
  --history-study rl_runs/combined_rough_optuna \
  --output rl_runs/rough_comparable_optuna_v2 --prepare-study
```

`--prepare-only` writes plans without creating/queuing a study.
`--prepare-study` additionally initializes the study, queues the current
candidate and audits/imports matching history; neither option launches training.
All four tuner scripts support these options.

When ready to train, launch the matching simulator/controller and run the same
command with `--prepare-study` removed. Retain the other inputs; choose
`--trials` for the number of additional trials. The waiting current candidate
is evaluated first. Study optimization has not been started by this preparation.
The rough N1/S1 stall/estimation failures still require attention before a long
search; queuing a candidate does not resolve them.

Verification: **50 tests passed**, including a real-checkpoint compatible import,
unchanged historical database checksum, duplicate prevention, rejected mismatched
observations, and accepted matching poor-policy observations.
