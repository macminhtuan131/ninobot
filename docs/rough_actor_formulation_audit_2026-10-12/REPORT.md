# Rough deterministic actor and formulation audit

Revision-49 final checkpoint preserved. Exact saved inputs replayed; three frozen stochastic episodes (17100–17102), backward passes only. **No PPO update, extension or Optuna.**

| Actor phase | Samples | Raw mean | Deterministic clipping | Requested scale | Executed scale |
|---|---:|---:|---:|---:|---:|
| cooldown | 492 | 1.015 | 51.8% | 0.994 | 0.994 |
| holding | 246 | 0.851 | 3.7% | 0.966 | 0.966 |
| ready | 529 | 0.991 | 49.3% | 0.989 | 0.989 |
| recovering | 101 | 0.914 | 15.8% | 0.979 | 0.978 |

## Findings

- 39.5% of deterministic means exceed the upper bound. Holding itself is mostly unsaturated, so clipping is not the sole explanation.
- Frozen stochastic probe: 51.2% clipped; 27.3% additionally limited by the physical speed ramp. Raw gSDE matrix std 0.064 does not mean action std 0.064: mean observed marginal std is 0.611.
- Latest-frame holding-flag edits change requested scale by only about −0.001; coherent five-frame holding edits change it by about −0.023. These are network sensitivity tests, not physical counterfactuals.
- Final training explained variance ~0.95; frozen-probe explained variance 0.933. Median critic/actor gradient ratio 0.201; retained fraction 0.453. **Weak critic/critic dominance is not supported here.**
- Actual training included 66/72 attempts with sustained slowdown followed by recovery. The deterministic final actor failed to retain sufficient response despite exposure.
- Frozen likelihood score favors lower raw actions during holding (-0.387) and higher ones during recovery (0.161). This does not support automatically increasing the holding penalty. It is a local stochastic-probe signal, not proof of a global reward optimum.
- The holding window is 0.6 s, but a 1→0.70 ramp requires 0.75 s. A new action formulation alone does not resolve this target-duration mismatch; do not credit reaching an unreachable holding target.

## Holding reward contributions (raw mean per episode)

| Term | Contribution |
|---|---:|
| action_rate | -0.00037 |
| command_velocity | 0.00000 |
| heading | -0.02688 |
| holding_reference | -1.39559 |
| late_time | 0.00000 |
| lateral | -0.11635 |
| progress | 3.75473 |
| slip | -0.04398 |
| terminal | 0.00000 |
| time | -0.24600 |
| vibration | -2.28356 |

The holding-reference term is present and nonzero. Return summation is not an attribution of how the physical trajectory would change under another action. No reward weights changed.

## Selected formulation correction

**Replace absolute Gaussian speed targets with categorical BRAKE / HOLD / RECOVER speed-rate actions.** Keep the 0.4/s rate, .55–1 bounds, hardware observations and current reward/scoring. The policy selects actions freely; no cue-driven inference override or teacher-forced slowdown. This removes Gaussian action clipping and gives distinct executed changes inside the speed bounds. It requires a fresh categorical actor/critic/optimizer under a new contract.

Prepared: proposed_contract.json. **Not integrated or trained.** First validate categorical likelihoods, rate execution and sustained exploratory brake/recovery sequences, then run one short pilot. Compare with the validated reactive controller as well as full/time-matched PI. Keep Optuna held.

This proposal is not evidence that the categorical policy will learn or outperform PI.
State saturation at .55/1 remains a physical constraint; HOLD and outward commands can coincide there.
Six .1 s braking actions can only reach .76 from 1 under the unchanged .4/s ramp, not the .70 holding target.
Holding and recovery rewards still compete with progress/comfort; no causal optimum claimed.
Changing action meanings requires a new training contract and new likelihood/rollout verification.
