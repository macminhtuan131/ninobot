# Rough slip audit and corrected flat repeats — 2026-10-12

## Completed scope

- Preserve the completed revision-56 rough checkpoint without updates.
- Audit the five saved PPO and reactive-PI E1 scenarios, including exact actor inputs, slip phases, motor response and action reversals.
- Run exactly four new cold flat episodes: seed 65004, full PI and the original brake/recovery schedule, twice each, at 1 ms physics under the corrected command clock.
- Retain physical arrival, timing, tracking and quality gates. No training, Optuna or broader simulation batch was started.

## Rough checkpoint preservation

Original: `rl_runs/rough_rate_bc_pilot_v2/train/20261012-111637-109195/nino_ppo_final.zip`.

Verified duplicate: `rl_runs/rough_rate_bc_trace_audit_v1/preserved/nino_ppo_final.zip`.

Both SHA-256: `791c68025ad42b5862c174c53b8ff2133492d332145e753d53c41f56873111f6`.

The audit verifies that 57 source model/config/result/capture/trace files remain unchanged. This is a local backup, not a claim of remote storage.

## Rough findings

Detailed [report](rough_bc_slip_audit_2026-10-12/REPORT.md) and [data](rough_bc_slip_audit_2026-10-12/analysis.json).

| Physical execution mode | PPO slip RMS | Reactive PI slip RMS |
|---|---:|---:|
| Startup, first 1 s | 0.06654 | 0.05564 |
| Final approach, physical remaining distance <0.5 m | 0.01109 | 0.00830 |
| Braking | 0.01374 | 0.01256 |
| Steady reduced-speed holding | 0.01143 | unavailable |
| Acceleration recovery | 0.01608 | 0.01659 |
| Full-speed cruise | 0.01480 | 0.01328 |

These are pooled time-weighted descriptive phase metrics, not a paired causal intervention. Phase duration and physical location differ. Reactive PI has no steady reduced-speed interval under this classification: its 0.8 s cue holding is largely consumed by the ramp to 0.70. Do not interpret the unavailable row as zero slip or omit any episode from physical scoring.

Startup plus final approach contributes about 73.6% of the net difference in the summed slip-square integral. Cruise also contributes positively; recovery contributes negatively. The startup commands are full scale in both cases. Therefore neither a slower recovery ramp nor a global slip-penalty increase is supported as the primary correction by this decomposition.

All five PPO episodes have zero same-event/same-phase speed-direction reversals, zero recovery commands during cue holding and zero braking commands during cue recovery. Normal braking/recovery cycles are not chatter. No stale motor command/policy/wheel-state samples were found.

Braking wheel-tracking RMSE is 0.6263 rad/s for PPO versus 0.5811 for reactive PI. Motor limit flags occurred on 14.7% versus 9.1% of braking wheel samples. The saved feedback supports checking execution rather than assuming the requested speed is achieved instantly; it does not isolate the physical cause of the total slip difference.

### Exact actor replay identifies behavior erosion

On the identical 1,417 PPO-visited pre-action observation tensors:

- Original BC actor agrees with the causal teacher on **99.36%**.
- Final PPO actor agrees on **93.44%**.
- During holding, PPO selects HOLD instead of teacher BRAKE **75 times**; BC does so only **2 times**.
- During recovery, PPO selects HOLD instead of teacher RECOVER **16 times**.
- Saved PPO inference reproduces the actually executed categorical actions exactly; categorical probabilities remain normalized.

The first recorded event illustrates the change: PPO stops braking at scale 0.80 for the remaining holding steps, then initially holds through the transition to recovery. This is incomplete execution of the demonstrated sequence, not action-direction chatter.

### One selected rough correction

For the next **new-contract** candidate, add an auxiliary actor behavior-cloning loss from the original demonstrations **only for holding/recovery observations** during PPO updates. The purpose is to retain complete BRAKE/HOLD/RECOVER sequences while allowing PPO to optimize elsewhere.

Before selecting its coefficient, measure that auxiliary actor gradient against the PPO actor gradient. Preserve reward weights, detector, observations, controller, speed bounds/ramp, terrain and physical scoring. Use the original BC actor and a fresh critic/optimizer; do not resume or modify the preserved final checkpoint.

This correction is selected and documented, **not implemented in the saved actor or trained**. Its potential reduction of physical slip remains unproven. Teacher agreement is a behavior diagnostic, not a replacement for independent physical-quality gates.

## Flat: four corrected cold repeats

Execution: `src/nino_rl/scripts/run_flat_corrected_repeat_v1.py`.

Detailed [report](../rl_runs/flat_corrected_repeat_v1/REPORT.md), [data](../rl_runs/flat_corrected_repeat_v1/analysis.json), and frozen [contract](../rl_runs/flat_corrected_repeat_v1/contract.json).

All episodes use seed 65004, 1 ms physics, 0.1 s action interval, the same Bullet contact profile, corrected simulation-time own-command freshness and bounded genuine diagnostic delivery wait. Each measured episode starts a fresh simulator. Order: full/schedule, then schedule/full. Schedule: brake x=3.90 m toward scale 0.70; recover x=4.60 m, unchanged 0.4 scale/s ramp.

| Repeat | Controller | Physical arrival | Time s | Physical path RMSE m | Vibration RMS m/s² | Slip RMS |
|---|---|---|---:|---:|---:|---:|
| 1 | Full PI | yes | 17.70 | 0.00572 | 4.119 | 0.20885 |
| 1 | Schedule | yes | 18.10 | 0.00417 | 6.019 | 0.15656 |
| 2 | Schedule | yes | 18.40 | 0.00522 | 2.038 | 0.13638 |
| 2 | Full PI | yes | 17.60 | 0.00584 | 2.057 | 0.17459 |

All four episodes pass physical arrival, joint stationarity, caster reset-angle checks, reference validity and crossing coverage. Maximum motion lag is 0.020 s; maximum episode-clock disagreement is below 2e-13 s. Both schedule episodes satisfy the unchanged 18.5 s timing cap and 1.05 tracking-ratio cap.

| Repeat | Schedule/full second-cable vibration energy per metre | Schedule/full second-cable slip energy per metre | Local quality gate |
|---|---:|---:|---|
| 1 | 8.765 | 1.075 | fail |
| 2 | 2.241 | 1.688 | fail |

Whole-course slip improves in both repeats, but that does not establish a crossing benefit. The first schedule repetition has 46.1% higher whole-course vibration. The second has similar whole-course vibration and 21.9% lower slip, yet both second-cable energy metrics are worse. No episode or interval was excluded to make the schedule pass.

### Repeatability and decision

Second-cable vibration energy changes between cold repeats by +34.2% for full PI and -65.7% for the schedule; slip energy changes by -71.1% and -54.6%, respectively. Both exceed the original 10% material-variation screen. Tracking is comparatively stable: repeat differences are 0.12 mm and 1.04 mm in whole-course RMSE.

Contact readback shows extended scheduled caster contact at the second cable (approximately 0.70–0.86 s, versus 0.21–0.43 s for full PI) and large solver-force variations despite valid reset/timing checks. Raw solver wrench spikes are not calibrated physical forces, and these observations do not prove a unique numerical root cause.

**Do not broaden this batch or start flat PPO.** The arrival/timing correction is functioning in these four cases, but crossing quality is unfavorable and not repeatable. The next investigation should use the saved contact/motor/IMU records to determine whether geometry interference or contact-solver impulses explain that instability before selecting a physical correction. No additional reward change is justified by this screen.

## Current status

The four requested flat episodes and rough saved-data audit are complete. Their source models and prior failures remain preserved. The flat runner closed its own simulator. Both courses remain held for Optuna; no further training or simulations are running from this work.
