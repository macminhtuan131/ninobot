# Comparable specialist Optuna trials — 2026-10-08

This implements trial preparation after the
[fixed evaluation objective](../optuna_objective_2026-10-08/README.md).
No Gazebo evaluation, Optuna trial or RL training was started in this step.

**Current runnable preparation commands:** the subsequent
[saved-result reuse guide](../saved_optuna_results_2026-10-08/README.md) prepares
the v2 studies and queues the current configurations without training.
The v1 plans/commands below describe this earlier preparation snapshot; their
source fingerprints predate the saved-result support and are retained as history.

## Prepared inputs

| Setting | Flat study | Rough study |
|---|---|---|
| Resolved profile | `combined_flat_pi_tracking.yaml` | `rough_e1_n1_s1_fixed.yaml` |
| World | `src/nino_description/worlds/combined_flat_section.sdf` | `rl_runs/rough_terrain_bank_v1/worlds/original.sdf` |
| Controller | Wheel PI `conditional_v1`, existing path feedback | Wheel PI `legacy`, existing route reference controller |
| Estimator | Encoder + IMU + corridor LiDAR | Encoder + IMU |
| Starting actor | Saved flat feedback actor, 10,240 source steps | Saved rough E1 assisted-odometry actor, 20,480 source steps |
| Initialization | Actor only; fresh critic, optimizer and step counter | Actor only; fresh critic, optimizer and step counter |
| Training seed | 42 | 42 |
| Requested training budget | 20,000 steps per trial | 20,000 steps per trial |
| Executed training budget | **20,480 steps per trial** | **20,480 steps per trial** |
| Training task | Fixed two-cable stage 2 | Fixed terrain, E1/N1/S1 balanced shuffle; E1 replay once per three episodes |
| Evaluation | 24 scenarios, seeds 61000–61023, stage 2 | 12 scenarios, seeds 10000–10011, E1/N1/S1 round-robin |
| ROS domain / Gazebo partition | 79 / `nino_flat_79` | 78 / `nino_rough_78` |
| Physical success | Existing 0.20 m physical goal radius | Existing 0.20 m physical goal radius plus ordered physical route gates |

Both profiles retain simulator ground-truth success scoring independently of
the estimated pose used by the controller/actor. Reward weights and PPO update
parameters are the searched variables; controller, estimator, route geometry,
terrain profile and physical arrival criteria are not sampled.

The exact source checkpoint paths, checksums, fixed configuration, asset
fingerprints and evaluation scenarios are in
[flat_plan.json](flat_plan.json) and [rough_plan.json](rough_plan.json).
These are copies of the prepared runtime plans:

```text
rl_runs/flat_comparable_optuna_v1/trial_plan.json
rl_runs/rough_comparable_optuna_v1/trial_plan.json
```

The rough snapshot fingerprints `original.sdf` and its referenced
`original.stl`, not the obsolete `combined_rough_ground.stl`. The default rough
SDF instead references `rough_diverse_ground.stl`; these are distinct declared
worlds and cannot be silently substituted in one study.

## Enforced comparability

All four Optuna entry points use
[tuning_trials.py](../../src/nino_rl/nino_rl/tuning_trials.py):

1. Resolve the inherited base configuration and validate the declared SDF's
   world name. Fingerprint its referenced local assets, robot geometry/config,
   controller/estimator/training source and tuner source.
2. Freeze the source actor's checksum, initialization method, training seed,
   budget, device, ROS domain and Gazebo partition.
3. Audit actor transfer on CPU without ROS: check observation/action
   compatibility and action meanings, copy the actor, and verify that the
   independent critic remains unchanged, the optimizer is empty and the new
   training counter is zero. Both selected actors passed; each copied 13
   actor tensors. A three-action old actor cannot initialize the two-action
   flat policy through a full actor copy.
4. Align the budget to the least common multiple of sampled rollout lengths.
   With 1,024/2,048-step rollouts, 20,000 requested steps becomes 20,480 for
   **every** trial. This prevents incidental PPO rounding from giving some
   trials more environment interaction. PPO update count and compute time may
   still differ because those settings are being tuned.
5. Before each training/evaluation, verify fingerprints and require exactly
   one local Gazebo server in the chosen partition with the selected SDF launch
   path. The normal environment/preflight separately checks live controller
   parameters, sensors and action timing.
6. Reject sampled configs that change the fixed task/controller/estimator/
   seed or use an unbudgeted rollout length.
7. Before scoring, inspect the completed model, `ppo.yaml`, `run_metadata.json`
   and `actor_transfer.json`. Require the exact training step count, the fixed
   source checksum, fresh critic/optimizer evidence and matching reward/policy
   contract. Then apply the frozen evaluation objective and exact scenario
   coverage checks.

The local Gazebo check reads `/proc`; it does not advance simulation. It checks
launch provenance and declared files, rather than certifying arbitrary manual
edits to a running scene. Use the declared launch, let the environment reset
its cable/adaptive items, and do not edit the scene during a study. Remote or
uninspectable simulators are rejected by this local workflow.

Prepared plans cannot be silently overwritten with changed inputs. Existing
study contracts must also match exactly. An interrupted **study** can resume
with unchanged inputs; a new trial always starts again from the frozen actor.
It does not inherit the preceding trial's trained policy or optimizer.

## Checkpoint resume versus actor initialization

- `train --resume`: continue the same reward/controller/estimator/policy/PPO
  contract, including its optimizer and counter. `validate_resume` rejects
  incompatible contracts.
- `train --init-model`: construct a new PPO model, transfer a compatible actor,
  retain the fresh critic/optimizer, and start at step zero. This is how the
  prepared studies handle sampled reward/PPO changes and the corrected
  controller/route profiles.
- `--from-scratch`: a separate study with no starting checkpoint. It cannot
  be combined with an explicit `--init-model`. Starting from scratch and actor
  initialization are different experiments.

Changing controller or estimator settings requires a newly validated profile,
new comparison references and a new study directory. Changing action meanings
may also require explicit speed-only transfer or starting from scratch; a
fresh optimizer alone does not make incompatible actions transferable.

## Reproduce preparation without starting tuning

The following commands audit the actors and write/recheck the plans only.
They do not require an active simulator. Keep the environment variables when
later running against the corresponding simulator.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST

export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export GZ_PARTITION=nino_flat_79
python src/nino_rl/scripts/tune_split_optuna.py --section flat \
  --config src/nino_rl/config/combined_flat_pi_tracking.yaml \
  --world src/nino_description/worlds/combined_flat_section.sdf \
  --init-model rl_runs/flat_feedback_pilot/20261008-035120-161159/nino_ppo_final.zip \
  --device cuda --timesteps 20000 --eval-episodes 24 --eval-seed 61000 \
  --output rl_runs/flat_comparable_optuna_v1 --prepare-only

export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78
export GZ_PARTITION=nino_rough_78
python src/nino_rl/scripts/tune_split_optuna.py --section rough \
  --config src/nino_rl/config/rough_e1_n1_s1_fixed.yaml \
  --world rl_runs/rough_terrain_bank_v1/worlds/original.sdf \
  --init-model rl_runs/rough_e1_imu_assisted_pilot/20261008-013943-771247/nino_ppo_final.zip \
  --device cuda --timesteps 20000 --eval-episodes 12 --eval-seed 10000 \
  --output rl_runs/rough_comparable_optuna_v1 --prepare-only
```

To start a study later, use the same command with `--prepare-only` removed,
after launching its matching world/controller. Launch instructions are in
[the corrected setup guide](../corrected_training_setup_2026-10-08/README.md).
Choose `--trials` to set how many additional trials to run; it does not change
the per-trial budget or comparison contract.

## Readiness and evidence

Preparation makes results comparable; it does not qualify long training.
The existing flat PI reference has 24/24 physical arrivals but timing/tracking
costs remain. The rough PI reference has E1 4/4, N1 0/4 and S1 0/4. Preserve
those failures, investigate the turn-route stall/odometry problem and use a
short diagnostic budget before committing to a long search. The 12-episode
rough evaluation has only four examples per route and is not a statistically
strong reliability test. Increasing the evaluation sample requires a new
study so all trials receive the same test.

The preparations passed real checkpoint transfer audits and read-only live
world/partition checks. Tests cover budget alignment, actual mesh changes,
fixed controller/estimator/physical criteria, incompatible resume, invalid
actor dimensions, source checkpoint changes, wrong running worlds and
completed-model provenance. No new training was started.
