# Flat continuation and held rough tuning

Prepared 2026-10-09. Existing scores, physical criteria and model files are retained.
No new tuning, PI evaluation or curriculum training was started during preparation.

## Flat: existing study, bounded startup recovery

Four COMPLETE flat observations exist. Each passed 24/24 physical arrivals. Trial 5
failed before model construction because `/effort_drive/get_parameters` was not
discovered. The controller process was still running. A direct read-only profile
probe subsequently responded and matched every saved parameter, so a permanently
missing or wrongly configured controller is not established by that failure.

Use Ctrl+C in the **flat Gazebo launch terminal**, then restart:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/run_focused_optuna.sh flat sim
```

In another terminal:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/run_focused_optuna.sh flat continue --target-trials 12
```

The continuation wrapper:

- Discovers and queries the controller with a 30-second wall-time limit, verifying
  all fixed profile values without setting parameters.
- Validates the existing study's frozen source/checkpoint/geometry hashes.
- Backs up SQLite and queues the exact parameters of the known pre-training
  controller-discovery failure, preserving the original FAIL record without a score.
- Calculates remaining work from COMPLETE observations (currently eight).
- Retries at most two recognized startup failures per invocation. It never silently
  retries a partial trained checkpoint, controller mismatch, action-timing failure
  or failed evaluation. It does not weaken the original trainer's guards.
- Retains the existing source actor, fresh critic/optimizer method, training budget,
  evaluation scenarios, reward search and physical objective.

This repairs the operational continuation path, not a proven DDS root cause.
If the bounded retries are exhausted, inspect controller/discovery diagnostics
before another continuation. Scores are not inserted for infrastructure failures.

## Rough: controller candidate and trace collection

Both scored rough evaluations have E1 4/4 and N1/S1 0/4. N1 estimated/physical
position disagreements are about 6–7 m. Keep `rough_focused_optuna_v1` as a
diagnostic study; do not continue it into a changed controller/estimator task.

`rough_turn_pi_candidate.yaml` isolates one candidate change: the PI integrator
becomes `conditional_v1`. Wheel gains/torque bounds, route geometry, terrain,
IMU/encoder estimator, action meanings and 0.20 m physical arrival criterion are
unchanged. Sustained PI correction is a candidate to test, not a declared fix for
slip or odometry drift.

Use Ctrl+C in the **rough Gazebo launch terminal**, then start the candidate:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/check_rough_turns.sh sim
```

In another terminal:

```bash
cd ~/ninorobot
bash src/nino_rl/scripts/check_rough_turns.sh
```

This verifies the candidate's live controller parameters and performs three PI
episodes per route, without PPO residuals or policy training:

| Route | Exact seeds |
|---|---|
| E1 | 10000, 10003, 10006 |
| N1 | 10001, 10004, 10007 |
| S1 | 10002, 10005, 10008 |

Reports are under `rl_runs/rough_turn_pi_candidate_20261009/E1`, `N1`, `S1`.
Each timestamped evaluation contains physical/estimated trajectories, control
commands, raw wheel pose, wheel-controller diagnostics and IMU-derived metrics.
Compare these traces with the matching previous route-PI seeds. Physical arrival
and ordered-gate scoring remain independent of the estimated control pose.

Three episodes are a diagnostic pilot. They do not prove 95% reliability or
repair the estimator. Review the traces to determine whether wheel-speed tracking
or slip-driven pose drift still prevents the turn. Correct remaining estimator
problems before full route-PI validation and curriculum training.

## Future curriculum: a new contract, not an old-study resume

The prepared `rough_turn_curriculum_candidate.yaml` has three stages:

1. E1, fixed map.
2. E1 + N1, retaining E1 replay.
3. E1 + N1 + S1, retaining earlier routes.

No terrain randomization is enabled. Each active route requires 20 evaluation
episodes, at least 95% physical success, mean physical path RMSE no greater than
0.05 m, and zero rollovers. The 0.20 m arrival radius and ordered physical gates
remain unchanged. The curriculum runner now forwards the profile's PI integrator
to its owned simulator launches.

Inspect the plan without training:

```bash
cd ~/ninorobot
source .venv/bin/activate
python src/nino_rl/scripts/train_rough_curriculum.py \
  --config src/nino_rl/config/rough_turn_curriculum_candidate.yaml \
  --bank rl_runs/rough_terrain_bank_v1/manifest.json \
  --output rl_runs/rough_turn_curriculum_v2 --plan
```

This is a future candidate. Do not start it until the turning controller and
odometry have been validated. A later estimator change must be included in its
new config before the first training run. Initialize a compatible actor with
fresh critic/optimizer, then freeze that new contract; do not import the old
rough trial scores as measurements of the corrected task.
