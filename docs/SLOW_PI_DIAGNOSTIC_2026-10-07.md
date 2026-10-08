# Slower PI comparison — 2026-10-07

## Purpose

Compare the saved rough and flat policies with a slower PI controller to
determine whether their comfort gains exceed the benefit of reduced speed.
Keep task geometry, deadlines, goal tolerances and scenario seeds fixed.
No new RL training or Optuna study is required for this diagnostic.

## Current evidence

The completed flat speed/yaw pilot evaluation has 22/24 physical successes,
matching PI's arrival count, but 0/24 arrivals within the 22-second target.
Mean successful completion is 27.23 s versus PI's 19.00 s. Mean physical path
RMSE across all episodes is 0.0503 m versus 0.0366 m. Vibration and slip are
lower for the policy. These are saved evaluations, not simulations rerun for
this report.

The completed rough E1 speed-only evaluation has 20/20 physical successes,
but completion averages 51.99 s versus PI's 27.76 s. Physical path RMSE is
0.1335 m versus PI's 0.0428 m. Disabling additive torque did not recover PI's
physical tracking performance. Other routes remain outside this diagnostic.

## Interrupted flat baseline

Saved directory: `rl_runs/flat_pi_slow_check/20261007-171007-942585`.
Only two of the requested 24 episodes are saved. No complete summary exists.
The evaluator is no longer running. Do not treat this as a completed study.

| Seed | PI scale | Outcome | Duration | Physical endpoint error | Physical path RMSE |
| --- | --- | --- | --- | --- | --- |
| 61000 | 0.70 | timeout | 30.00 s | 0.2234 m | 0.0224 m |
| 61001 | 0.70 | timeout | 30.00 s | 0.2435 m | 0.0507 m |

Final measured forward speed is approximately 0.043 m/s in both episodes.
Their trajectories show continued forward progress during the final approach.
They did not reach the 0.20 m physical goal tolerance before the unchanged
30-second deadline. These two runs do not establish a broad failure rate or
an RL advantage.

## Completed flat comparison: PI scale 0.78

The 24-episode baseline is complete at
`rl_runs/flat_pi_slow_078_check/20261007-171835-555212`.
Its benchmark ID and seeds match the saved speed/yaw pilot evaluation at
`rl_runs/flat_speed_yaw_pilot_eval/20261007-160707-136898`.
The provenance-checked comparison is saved as
`rl_runs/flat_pi_slow_078_check/comparison_vs_ppo.json`, with a paired analysis
at `rl_runs/flat_pi_slow_078_check/paired_analysis_vs_ppo.json`.

| Metric | Fixed-scale PI (0.78) | Speed/yaw PPO |
| --- | --- | --- |
| Physical success | 23/24 | 22/24 |
| Success within 22 s | 0/24 | 0/24 |
| Mean successful completion | 27.63 s | 27.23 s |
| Physical path RMSE, all episodes | 0.0417 m | 0.0503 m |
| Vertical acceleration RMS, all episodes | 1.6857 m/s² | 1.4453 m/s² |
| Wheel slip RMS, all episodes | 0.1657 | 0.1531 |

With similar completion time, PPO's mean vibration is approximately 14.3%
lower and slip approximately 7.6% lower. It has one fewer successful arrival
and approximately 20.5% higher all-episode physical path RMSE. This is a
descriptive comparison of a single trained policy, not a statistically
established advantage or disadvantage in success probability.

The same 21 seeds succeeded under both controllers. On that subset:

| Metric | Fixed-scale PI | PPO |
| --- | --- | --- |
| Completion time | 27.63 s | 27.16 s |
| Physical path RMSE | 0.0396 m | 0.0377 m |
| Vertical acceleration RMS | 1.6036 m/s² | 1.4573 m/s² |
| Wheel slip RMS | 0.1658 | 0.1536 |

The common-success results retain a modest comfort improvement (9.1% lower
vibration and 7.4% lower slip) with slightly better physical tracking. This
subset excludes failures and must not replace the full success/error results.
The results suggest a comfort benefit beyond simply comparing PPO with fast
PI, but do not isolate the contribution of adaptive speed versus policy yaw.
Fixed scale also does not reproduce the policy's time-varying speed profile.
Asynchronous simulation runs and lack of independent training replicas limit
causal and generalization claims.

PI timed out on seed 61022 with physical endpoint error 0.2320 m. PPO timed
out on seeds 61005 and 61019 with physical endpoint errors 0.2095 m and
0.4352 m. Final forward speed was nonzero in all three. These values alone
do not prove whether each miss arose from speed scheduling, steering or
localization; inspect their trajectories before changing the controller.

**Decision:** retain the pilot as a candidate for comfort, but do not claim
overall superiority or start a long run yet. Both controllers miss the 22 s
target, and PPO's scenario-specific failures need attention. The completed
flat check need not be repeated without a specific unresolved question.

## Completed rough comparison

The slower-PI run completed all 20 episodes at
`rl_runs/rough_pi_slow_check/20261007-172112-105348`. The comparison is saved at
`rl_runs/rough_pi_slow_check/comparison_vs_speed_only.json`.

| Metric | Fixed-scale PI (0.55) | Saved PPO speed-only |
| --- | --- | --- |
| Physical success | 11/20 | 20/20 |
| Mean successful completion | 63.52 s | 51.99 s |
| Mean duration, including timeouts | 83.31 s | 51.99 s |
| Physical path RMSE, all episodes | 0.1851 m | 0.1335 m |
| Vertical acceleration RMS, all episodes | 0.7361 m/s² | 0.9202 m/s² |
| Slip RMS, all episodes | 0.0285 | 0.0302 |

All nine PI failures reached the 107.5 s deadline with estimated goal distance
approximately 0.048–0.0495 m, physical goal distance 0.2049–0.3390 m, and
essentially zero final forward speed. These are consistent with premature
estimated stopping. The estimator issue therefore remains present under
different driving speeds despite the smaller stopping margin.

Scale 0.55 did not match the policy's actual completion time. Long stationary
timeout periods also lower all-episode motion/comfort averages, so those
averages must not be interpreted as a clean comfort advantage. The original
unscaled PI remains faster and more accurate on E1. The rough next step is
localization/arrival diagnosis; no new rough training has been started.

## Comparison settings

The completed flat test used fixed PI scale **0.78**, in a new output directory,
with 24 episodes and seeds 61000–61023. This was an initial approximation based on the partial
0.70 runs and the pilot's observed mean scale of approximately 0.788. Matching
mean scale does not guarantee matching completion time or speed distribution.
The actual timing difference is reported above.

Use rough fixed PI scale **0.55**, 20 episodes, E1, seeds 10000–10019. This
scale is an initial approximation for the 51.99 s speed-only policy. Run one
evaluator per world. The two courses can run concurrently with separate ROS
domains (flat 79, rough 78) and Gazebo partitions; monitor sensor/transport errors.

The baseline-only `--baseline-speed-scale` option changes the executed speed
action. Existing motor control scales both linear and yaw references. No
additive torque or policy yaw correction is introduced. Requested motion
references, route, deadlines and physical scoring rules stay unchanged.
The scale is recorded in evaluation metadata and comparison output.

Evaluate physical arrival first, then physical tracking, timing, vibration and
slip. Inspect both all-episode and common-success results. If timing remains
substantially different, do not attribute comfort differences solely to RL.

## Follow-up after the complete comparisons

### Offline flat approach inspection

`src/nino_rl/scripts/analyze_flat_approach.py` compares the saved fast PI,
slower PI and PPO evaluations. It checks completion and benchmark provenance,
then exports figures for seeds 61000, 61005, 61019 and 61022. Outputs are in
`docs/flat_approach_diagnostic_2026-10-07`.

The seed 61019 plot shows PPO developing a large positive heading deviation
after the second cable crossing, followed by sustained lateral departure
during approach. Its physical heading reaches approximately 14 degrees,
while the estimated heading is approximately 10.6 degrees. This indicates
that timing alone is insufficient to explain this failure. Exact commanded
yaw, policy actions and controller saturation were not saved, so the plot
does not establish why steering failed to correct the deviation.

### Targeted control replay and selected flat pilot

Both seeds were replayed once with stamped controller telemetry at
`rl_runs/flat_failed_control_replay/20261007-175903-826983`. Both arrived:
61005 in 27.80 s, 61019 in 26.60 s. The older failures did not reproduce.
The same seed does not ensure identical asynchronous sensor/contact histories.
These two successes do not supersede the previous 24-episode result.

The replay records policy actions and measured poses in `control_trace.csv`,
and requested/filtered motion references, wheel targets/measurements, PI and
residual efforts, and safety limiting in `drive_trace.csv`. After 22 s, mean
requested yaw was approximately 0.0044–0.0046 rad/s; filtered yaw was
approximately 0.0033–0.0035 rad/s. Neither wheel had final effort limiting in
those late intervals. This verifies speed/yaw coupling but does not establish
it caused the earlier failures. Requested references are not actual body motion.

The chosen first correction targets the repeatable timing shortfall, changing
only `reward_v2.time_penalty` from 0.05 to 0.20 in
`src/nino_rl/config/combined_flat_speed_yaw_timing_pilot.yaml`. Control mapping,
course, arrival tolerance and deadlines remain fixed. See
[the timing pilot record](FLAT_TIMING_PILOT_2026-10-07.md) for the active run
and validation gates.

The available pose traces support physical speed estimates and pose-error
inspection. Speeds in these figures are finite differences, not commands or
motor feedback. Terminal scoring metrics remain authoritative when the last
overlapping plot sample precedes the scored state.

```bash
cd ~/ninorobot
source .venv/bin/activate
python src/nino_rl/scripts/analyze_flat_approach.py \
  --ppo-run rl_runs/flat_speed_yaw_pilot_eval/20261007-160707-136898 \
  --pi-run rl_runs/flat_speed_yaw_pilot_pi/20261007-155635-991948 \
  --slow-pi-run rl_runs/flat_pi_slow_078_check/20261007-171835-555212 \
  --seeds 61000 61005 61019 61022 \
  --output docs/flat_approach_diagnostic_2026-10-07
xdg-open docs/flat_approach_diagnostic_2026-10-07/seed_61019.png
```

1. Inspect estimated/physical pose divergence and final-approach behavior.
2. Check the impact of speed scaling on available steering authority.
3. Select a focused control or reward correction supported by those results.
4. Start a short new-contract training pilot, then evaluate its frozen policy.
5. Consider Optuna only after defining fixed, independent evaluation criteria.

The old 1.5M checkpoint remains a separate historical check; it is not the
training run being continued in this work.
