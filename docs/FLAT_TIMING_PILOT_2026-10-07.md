# Flat timing pilot — 2026-10-07

## Completed preparation

- Reviewed the complete rough slower-PI test: 11/20 successes, with nine
  stationary timeouts consistent with premature estimated stopping.
- Added `/nino_drive/diagnostics`, published at the existing 50 Hz torque-status
  rate. It records requested and filtered speed/yaw references, wheel target
  and measured velocities, PI/residual/requested/applied efforts, limiting
  flags and command freshness. Samples have simulation timestamps and a
  field-name layout. No controller behavior was changed.
- Added evaluator `--seeds` for explicit targeted scenarios and
  `--control-trace` for per-step policy/state CSV and stamped drive CSV.
  Logging is excluded from benchmark identity; explicit seed sequences are
  checked when comparing reports. Telemetry does not enter actor observations.
- Replayed seeds 61005 and 61019 with the frozen 20,480-step pilot. Both
  arrived in this replay (27.80 s and 26.60 s). Earlier failures did not
  reproduce. Late approach had small yaw requests and no final effort
  limiting, so a causal steering fix is not justified by this replay alone.
- Passed 49 focused offline tests, plus exact actor-transfer/fresh-critic
  checks. Built `nino_control` and `nino_rl` successfully.

Replay: `rl_runs/flat_failed_control_replay/20261007-175903-826983`.

## One selected change

Profile: `src/nino_rl/config/combined_flat_speed_yaw_timing_pilot.yaml`.

Change only the time penalty from **0.05 to 0.20 per 0.1 simulated second**,
equivalent to 0.5 versus 2 reward units per second. This tests stronger timing
urgency while retaining arrival, tracking and comfort rewards.

The following stay fixed: two-action speed/yaw interface, speed/yaw coupling,
wheel PI settings, terrain, two-cable stage, estimated stopping tolerance,
0.20 m physical goal radius, 22 s timing target and 30 s deadline.
The changed reward requires a new training contract. Its benchmark identity
matches the original pilot because the physical test conditions are unchanged.

## Active training

Run: `rl_runs/flat_speed_yaw_timing_pilot/20261007-180312-369757`.

- Source actor: `artifacts/flat_speed_yaw_20480/nino_ppo_final.zip`.
- Fresh critic, optimizer and training counter. This is actor initialization,
  not continuation of the old 1.5M run or optimizer resume.
- Requested budget: 50,000 steps. With 1,024-step rollouts, expected actual
  completion is 50,176 steps.
- Checkpoints every 10,000 steps, original saved model preserved.
- CUDA on the RTX 4080, ROS domain 79, Gazebo partition `nino_flat_79`.
- Mandatory 12-point live preflight and `--check-env` passed. The first
  1,024-step rollout completed. Early training outcomes are not final results.

Training command already started:

```bash
ros2 run nino_rl train --device cuda \
  --config src/nino_rl/config/combined_flat_speed_yaw_timing_pilot.yaml \
  --init-model artifacts/flat_speed_yaw_20480/nino_ppo_final.zip \
  --timesteps 50000 --checkpoint-every 10000 --check-env \
  --output rl_runs/flat_speed_yaw_timing_pilot
```

Do not launch a second copy against the same world while this run is active.
Training log: `/tmp/nino_flat_timing_pilot.log`.
Initialization provenance: the run's `experiment.json`.

## Queued final validation

`scripts/validate_flat_timing_pilot.py` waits for the specific training PID,
checks that its final model exists and has at least 50,000 steps, then runs
one 24-episode frozen evaluation on seeds 61000–61023 with control traces.
It will not evaluate an interrupted/incomplete training run. Process start
identity is checked to avoid waiting on a reused PID.

After evaluation it saves comparisons against fast PI, slower PI and the
original PPO. Evaluation output is under the run's `final_validation` directory.
State is recorded in `validation_status.json`; errors remain visible there
and in `final_validation.log`. No subsequent training stage starts automatically.

Fixed validation-suite gates:

1. Physical arrival count at least the matching fast PI (22/24).
2. On-time arrival count at least the matching fast PI (21/24).
3. Physical path RMSE no more than PI plus 1 cm (approximately 0.0466 m).
4. Vertical acceleration RMS at least 20% below fast PI (approximately 1.914 m/s²).
5. Slip RMS no worse than slower PI (approximately 0.1657).

These are engineering gates on a reused validation suite, not statistical
proof or untouched final-test performance. Reserved new scenarios and
independent training seeds are required before claims of generalization or
repeatable superiority. Final outcome is currently pending.

To inspect progress:

```bash
tail -n 30 /tmp/nino_flat_timing_pilot.log
cat rl_runs/flat_speed_yaw_timing_pilot/20261007-180312-369757/validation_status.json
```
