# Completed rough revision-57 pilot and current flat status

Checked 2026-10-12 at approximately 17:51–17:54 Asia/Bangkok.

## Rough: completed, not qualified for promotion

The 20,480-step pilot and its four evaluation batches finished at 15:29. No rough training, flat candidate test or Optuna process was active at this check. The revision-57 frozen inputs and preserved original final checkpoint still match their recorded hashes.

All controllers used nominal fixed E1 and evaluation seeds 17400–17404. These five-seed results are descriptive pilot estimates, not generalization or repeatability evidence.

| Controller | Physical arrivals | Mean time s | Physical path RMSE cm | Vertical vibration RMS m/s² | Wheel-slip RMS |
|---|---:|---:|---:|---:|---:|
| Anchored PPO | 5/5 | 28.44 | 1.616 | 1.279 | 0.01770 |
| Full-speed PI | 5/5 | 26.98 | 1.671 | 1.298 | 0.01656 |
| Time-matched PI | 5/5 | 28.40 | 1.634 | 1.275 | 0.01898 |
| Reactive PI | 5/5 | 28.78 | 1.703 | 1.262 | 0.01629 |

### What succeeded

- Physical-arrival/tracking and learned-response gates passed.
- All five deterministic PPO episodes slowed during disturbances and recovered to scale 1.0 in quiet cruising. Minimum speed scales were 0.72–0.76.
- Against time-matched PI, global slip RMS fell 6.7%; disturbance-window slip energy/metre fell 22.7%. Global vibration was 0.25% higher; disturbance-window vibration energy/metre was 0.70% lower. The existing matched-PI ride-quality gate passed.
- No same-event/phase action reversals, recovery during cue holding, or braking during cue recovery were found in the saved evaluation traces.

### Why the overall pilot failed

Against reactive PI, disturbance-window slip energy/metre was **16.3% higher**, exceeding the unchanged **10% maximum degradation**. Global slip RMS was 8.6% higher. Disturbance-window vibration energy/metre was 1.1% lower. Therefore `pilot_passed` is false; the qualified reactive-reference requirement must remain counted.

The per-seed PPO/reactive window slip-energy ratios were:

| Seed | Slip-energy ratio | Difference |
|---|---:|---:|
| 17400 | 1.381 | +38.1% |
| 17401 | 1.596 | +59.6% |
| 17402 | 0.813 | -18.7% |
| 17403 | 0.940 | -6.0% |
| 17404 | 1.230 | +23.0% |

An additional read-only use of the existing phase audit found pooled recovery slip RMS of 0.01585 for PPO versus 0.01326 for reactive PI; full-speed cruise was 0.01451 versus 0.01274. PPO spent 22.8 s braking across the five episodes versus 30.4 s for reactive PI, and 8.3 s at steady reduced speed versus no such interval for the reactive implementation. These labels classify executed scale changes; their positions/exposures differ, so the aggregates do not identify a causal defect by themselves.

### Recommended next rough step

Preserve the final checkpoint; do not extend the same run or start Optuna. Align saved physical-position traces for seeds 17400, 17401 and 17404, comparing cue onset, BRAKE/HOLD/RECOVER choices, slowdown depth/duration, recovery timing and executed wheel response with reactive PI. Select one correction only after that alignment explains the excess slip. Keep physical scoring strict.

Source results: `rl_runs/rough_phase_anchor_pilot_v2/comparison.json`.

Saved final model: `rl_runs/rough_phase_anchor_pilot_v2/train/20261012-142046-286263/nino_ppo_final.zip`.

## Flat: candidate prepared, simulation validation still pending

No new flat result exists for the caster-damping candidate. Its manifest still records `validated: false` and `simulator_started: false`.

The previous four cold-start seed-65004 screen remains the latest evidence: all physical arrivals passed, but the recovery-at-4.60-m schedule failed local crossing-quality gates in both repetitions. Mean global slip improved, while mean vibration worsened; those global averages do not qualify the crossing behavior.

Recommended next flat step: test the isolated wheel-axle damping candidate `0.01 → 0.001 N·m·s/rad`, retaining swivel damping, geometry, masses, cable placement, 1 ms physics, 100 ms control and existing scoring. Repeat full PI and the original recovery-at-4.60-m schedule twice each on seed 65004. Check clear-floor caster rolling, contact/impact repeatability, arrival, tracking, timing, and local/global vibration/slip before a flat PPO pilot.

The current main robot model is unchanged. The candidate is a supported modeling hypothesis, not a validated remedy for all impacts. Optuna remains held for both courses.

Previous implementation and contact audit: [ROUGH_PHASE_ANCHOR_AND_FLAT_IMPACT_2026-10-12.md](ROUGH_PHASE_ANCHOR_AND_FLAT_IMPACT_2026-10-12.md).
