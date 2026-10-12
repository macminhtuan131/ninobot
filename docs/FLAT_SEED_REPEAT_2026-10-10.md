# Flat: saved-slip inspection and independent-seed repeat

## Saved evidence

Read-only analysis: `docs/flat_saved_slip_2026-10-10/REPORT.md`, `analysis.json`,
and `paired_episodes.csv`. No simulation was launched for this analysis.

The original scale-only PPO has higher RMS slip in **14/24** paired episodes.
Mean difference is **+0.010123**; the paired scenario bootstrap 95% interval is
**[-0.008406, +0.028436]**, which includes zero. Seeds **64021, 64022, 64014,
64011, 64010, 64012** have the largest increases. Exploratory episode-level
associations with slower completion and higher torque are saved in JSON; they
do not establish the cause or location of slip.

The original runs saved whole-episode slip and pose trajectories, but did not
save per-action slip or control traces. These files cannot determine whether
the increase happened at a cable crossing, during acceleration, yaw correction,
or the final approach. No such phase attribution is claimed.

## Authorized repeat

- Output: `rl_runs/flat_value_scaled_seed43_v1`.
- Training seed **43**, compared with original training seed **42**.
- Exactly **20,480 new steps**, from the same original actor:
  `rl_runs/flat_targeted_actor_pilot_v1/train/20261010-002632-975129/nino_ppo_final.zip`.
- Copy the complete actor; initialize a fresh critic, optimizer and step counter.
- Copy the original scale-only package snapshot, rather than rebuilding from
  potentially changed source files.
- Preserve the task reward, constant **0.01 learner reward multiplier**, PPO
  settings, controller, estimator, observations, action meanings, map and
  fixed two-cable stage.
- Record end-of-action left/right slip and IMU square integral only inside the
  optional evaluation trace branch. All other package files are byte-identical
  to the original frozen snapshot. No signal is added to actor observations.
- Evaluate deterministic PPO and full-speed PI on **64000–64023**, independently
  scoring physical arrival and using the original fixed objective.
- Record control and drive traces for both controllers. Trace logging does not
  change the benchmark hash; asynchronous simulation variation remains possible.

The runner verifies source actor hashes, frozen package/workflow inputs, actual
training seed/configuration, live actor-transfer evidence, exact completed
budget, evaluation scenario coverage and physical benchmark identity.

## Original qualification gates

Require **24/24 physical arrivals**, mean completion **≤18.5 s**, physical path
RMSE **≤1.05× matching PI**, and **≥10% improvement in vibration or slip without
regression in the other metric**. The repeat uses these gates unchanged.

The original run failed quality. A passing second seed alone does not establish
consistent qualification across both training seeds. Two seeds can expose
repeatability problems; they do not establish broad terrain generalization.
There is no automatic Optuna launch, longer training or curriculum promotion.

## Scheduling and monitoring

The repeat waits for the existing rough validation supervisor **PID 50911** to
exit before using Gazebo. Its process command and start time are checked so a
reused PID cannot be mistaken for that supervisor. Rough is not interrupted.
Flat remains isolated in ROS domain **79**, partition `nino_flat_79`.

Live progress is recorded in:

- `rl_runs/flat_value_scaled_seed43_v1/status.json`
- `rl_runs/flat_value_scaled_seed43_v1/supervisor.log`
- `rl_runs/flat_value_scaled_seed43_v1/train/training.log`
- `rl_runs/flat_value_scaled_seed43_v1/ppo/evaluation.log`
- `rl_runs/flat_value_scaled_seed43_v1/pi/evaluation.log`

Final results will be `comparison.json` and `REPORT.md` in the same run folder.
Completed evidence is reused on a rerun; an interrupted training checkpoint is
preserved and requires review before compatible optimizer continuation.

```bash
cd ~/ninorobot

# Read-only saved-data inspection; no ROS/Gazebo needed.
.venv/bin/python src/nino_rl/scripts/analyze_flat_saved_slip.py

# Inspect the already queued repeat.
cat rl_runs/flat_value_scaled_seed43_v1/status.json
tail -n 25 rl_runs/flat_value_scaled_seed43_v1/supervisor.log
```

When no repeat worker owns its lock, this is the launch/recovery command:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
python src/nino_rl/scripts/run_flat_seed_repeat.py \
  --training-seed 43 --wait-for-rough-pid 50911 --run
```

Do not launch a second worker while the current one is queued or running. The
worker closes only its own child processes if a simulation or evaluation fails.
