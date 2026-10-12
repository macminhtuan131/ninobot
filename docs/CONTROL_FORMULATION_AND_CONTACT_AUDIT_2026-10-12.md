# Rough actor formulation and flat contact audit — 2026-10-12

## Completed work

- Rough: exact replay of 1,368 saved deterministic observations; three frozen stochastic episodes, 850 actions; backward-only gradient audit. No optimizer update or model extension.
- Flat: 24 PI evaluations: seeds 65001 and 65004, three fresh simulator starts for each of full PI, original 4.60 m schedule, shortened 4.55 m schedule and time-matched PI. Alternating seed order and counterbalanced profile order. Contacts captured at every 2 ms physics step.
- All 24 flat runs arrived physically. The rough frozen probe also arrived in all three episodes. Existing arrival, timing, localization and scoring checks stayed active.
- Saved models/studies remain intact. No flat PPO pilot or Optuna worker was started. Diagnostic simulators were closed after capture.

## Rough: evidence and selected correction

| Finding | Measurement | Interpretation |
|---|---:|---|
| Deterministic action clipping | 39.5% overall | Many distinct raw means execute at the same maximum speed |
| Holding speed | Mean 0.966 executed scale | Final policy still does not make the intended substantial slowdown |
| Holding deterministic clipping | 3.7% | Clipping is not the sole cause of weak holding response |
| Frozen stochastic clipping | 51.2% | Large marginal action noise despite gSDE matrix std around 0.064 |
| Frozen stochastic ramp limiting | 27.3% | Additional absolute targets collapse to the same rate-limited command |
| Frozen critic explained variance | 0.933 | Weak final critic fit is not supported |
| Median critic/actor gradient norm | 0.201 | No measured critic dominance |
| Median gradient retained after clipping | 45.3% | Not the earlier extreme critic-induced suppression |
| Training exposure | 66/72 attempts showed slowdown/recovery | Exposure alone did not translate into deterministic response |

Holding-reference reward was present (mean −1.396 raw return per episode). The frozen likelihood signal favors lower raw actions in holding and higher ones in recovery. This is not evidence for automatically increasing penalties. Saved training gradients cannot be reconstructed exactly; the gradient results above are a frozen final-policy probe.

**Selected formulation:** categorical speed-rate actions **BRAKE / HOLD / RECOVER** at −0.4 / 0 / +0.4 scale per second. Keep .55–1 physical bounds, hardware observations, unscaled PI yaw, terrain and current reward weights. The actor chooses freely; the cue does not force slowdown. A categorical policy removes Gaussian action clipping while giving each interior action a distinct executed speed change.

This is an evidence-supported hypothesis, not a demonstrated improvement. It needs a new contract, fresh categorical actor, fresh critic and optimizer. The old Gaussian checkpoint cannot be resumed with the new action meanings. Space-only categorical likelihood replay and speed-rate algebra were verified; ROS integration and live exploration have **not** been completed.

Also note the existing target-duration mismatch: a 1→.70 reduction requires .75 s at .4/s, but holding lasts .6 s. Six braking actions reach .76, not .70. The next pilot must not be credited with reaching an unreachable holding target.

Details: [rough report](rough_actor_formulation_audit_2026-10-12/REPORT.md), [proposed contract](rough_actor_formulation_audit_2026-10-12/proposed_contract.json).

## Flat: a repeated average benefit, with qualification still failing

| Profile | Physical arrival | Time s | Physical RMSE m | Vibration RMS m/s² | Slip RMS |
|---|---:|---:|---:|---:|---:|
| Full PI | 6/6 | 17.67 | .0279 | 2.564 | .207 |
| Original schedule, recovery at 4.60 m | 6/6 | 18.32 | .0276 | 1.623 | .176 |
| Shortened schedule, recovery at 4.55 m | 6/6 | 18.35 | .0317 | 1.859 | .173 |
| Time-matched PI | 6/6 | 18.23 | .0294 | 2.905 | .202 |

The original schedule reduced pooled crossing vibration energy per metre by **53.2%** and slip energy per metre by **28.8%** against time-matched PI. Both schedules passed the local quality check on the two-seed batch mean in each of the three repetitions.

**That does not mean each scenario improved.** For example, the shortened schedule in repetition 3 on seed 65001 had vibration and slip ratios of **3.51 and 2.94** versus matched PI. Original-schedule seed 65004 in repetition 1 had a slip ratio of **2.03**. These are repeated scenarios, not unseen seeds or a generalization study.

All promotion gates passed in **2/3 repetitions** for the original schedule and **1/3** for the shortened one. The failures were tracking comparisons; the full set of existing gates therefore remains unmet. Do not open the conditional flat PPO pilot based only on pooled vibration improvement.

Contact inspection found:

- Both caster-fork/cable contacts and drive-wheel/cable impacts. No chassis contacts in these second-cable windows.
- Nominal fork clearance about **9.03 mm**; caster radius **16 mm**; second cable top **20 mm**. Fork contact is geometrically plausible, rather than automatically a reward or recovery defect.
- Caster/cable penetration readings reached **7.48 mm**. These are solver outputs; contact-resolution convergence and actual hardware clearance need checking before treating their magnitudes as calibrated physical impacts.
- Contact loss/recontact, caster orientation and motor response vary across repeats. Large impacts can occur while scale remains .70, before recovery.
- Lateral error already differs before braking despite the same full-speed command. For example, repetition 2 pre-braking lateral RMS was .0198 m for full PI versus .0275 m for the shortened schedule. A later schedule cannot cause an earlier difference; initial/contact repeatability is a confounder.

Details: [flat report](flat_contact_repeatability_2026-10-12/REPORT.md), [all contact/motor/region statistics](flat_contact_repeatability_2026-10-12/analysis.json).

## Next bounded work

1. **Rough:** integrate the selected categorical rate formulation under a new contract. Verify execution and sustained exploratory braking/recovery; then one fresh short pilot against the validated reactive reference and full/time-matched PI. No old-model extension or reward-weight increase.
2. **Flat:** retain the original 4.60 m schedule as the behavioral reference. First check contact numerical convergence and initial/caster-state repeatability, using the two existing scenarios. Preserve geometry and physical gates while comparing smaller physics steps at the same control interval. Resolve repeat tracking failures before a PPO pilot.
3. **Optuna stays held.** Numerical/controller validation and a demonstrated learned behavior remain prerequisites.
