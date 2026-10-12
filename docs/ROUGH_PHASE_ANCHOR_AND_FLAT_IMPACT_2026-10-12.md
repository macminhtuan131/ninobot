# Rough phase-selective BC pilot and flat contact audit

Date: 2026-10-12, Asia/Bangkok. This report records implementation, saved-data findings and a running pilot; it does not claim a new performance gain.

## Rough: measured gradient balance

The previous revision-56 PPO checkpoint remains preserved. Its saved traces showed more HOLD actions than the original BC actor when the demonstrated controller required BRAKE or RECOVER. The new correction retains the original demonstrated behavior through an additional **actor-only BC loss on holding/recovery demonstrations**.

The audit reconstructed the first 1,024-step rollout from the original BC-initialized run. Reconstructed critic prediction/target statistics match its recorded TensorBoard values within 0.000015. No optimizer step occurred during measurement; actor/critic parameters stayed unchanged.

| Initial minibatch | PPO actor gradient norm | Unweighted BC actor gradient norm | Critic gradient norm | PPO/BC cosine | Effective BC coefficient | Weighted BC/PPO actor norm ratio |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0.215 | 3.202 | 0.414 | -0.681 | 0.03351 | 0.500 |
| 2 | 0.556 | 3.574 | 0.511 | 0.651 | 0.03749 | 0.241 |
| 3 | 0.528 | 3.656 | 0.568 | 0.910 | 0.03749 | 0.259 |
| 4 | 0.721 | 3.182 | 0.621 | -0.542 | 0.03749 | 0.165 |

The gradients sometimes oppose each other, so an unscaled imitation term would be inappropriate. The base coefficient is **0.037486377** (initial median actor-gradient ratio 0.25), with an adaptive **0.50 upper bound** relative to the current PPO actor gradient. Existing global gradient clipping remains in place. The BC term has no direct gradient path into critic parameters; the existing shared optimizer/global clipping can still couple update magnitudes indirectly.

Demonstrations use only training seeds 17200–17202, never evaluation seeds. Eligible pre-action holding/recovery labels contain 168 BRAKE, 24 HOLD and 168 RECOVER examples; each BC minibatch samples 64 per class. This finite demonstration set is a behavioral reference, not proof of generalization.

Details: [gradient measurements](rough_phase_anchor_gradient_2026-10-12/analysis.json).

## New rough contract and running pilot

**Revision 57**, stored in `rl_runs/rough_phase_anchor_pilot_v2/pilot_contract.json`:

- Original actor: `rl_runs/rough_rate_bc_pilot_v2/bc_actor.zip`, SHA-256 `6012ea2fb6f5eaaf1d530a700b0871c7d186c87b8c64042d65432dc18fbe44a1`.
- Actor-only initialization, fresh critic and optimizer, zero PPO training counter.
- Seed 17000; **20,480 steps**; checkpoints every 4,096 steps.
- Rewards, reward scaling, terrain, controller, estimator, observations, categorical action meanings, speed bounds and ramp are preserved.
- Original revision-56 contract validates the source actor; the resulting policy receives the new revision-57 contract.
- An offline update verified bounded gradients and exact categorical probabilities after standard PPO save/load.
- Runtime at 2,048/3,072 steps reports maximum BC/PPO actor-gradient ratio 0.50; average ratios 0.366/0.330. Training and timing checks are active.

Started at approximately **14:20 local**. At **14:29**, 3,072 steps were logged, about 6 steps/s. Estimated training completion is roughly **15:15**, followed by about **15–20 minutes** of comparisons, subject to measured runtime. These are estimates.

The supervisor automatically evaluates seeds 17400–17404 against full PI, reactive PI and time-matched PI. Existing physical-arrival, tracking, slowdown/recovery and vibration/slip gates remain unchanged. Five nominal E1 seeds are a pilot screen; unseen physical profiles and independent training seeds remain necessary before promotion. Optuna remains held.

Logs: `rl_runs/rough_phase_anchor_pilot_v2/train/train.log`. State: `rl_runs/rough_phase_anchor_pilot_v2/status.json`. Final comparison, when available: `rl_runs/rough_phase_anchor_pilot_v2/comparison.json`.

The earlier `rough_phase_anchor_pilot_v1` directory contains preparation/integration artifacts only; no physical training ran from it. Revision v2 corrected source-contract validation before starting the simulator.

## Flat: what the largest impacts show

Read-only audit: four cold-start seed-65004 episodes, full PI and the original recovery-at-4.60-m schedule, two repetitions each. Physics stays 1 ms; control stays 100 ms. All 16 contact/motor/joint/control input files were hashed and verified unchanged after analysis.

| Repetition/profile | Largest recorded IMU interval peak, m/s² | Physical x, m | Speed scale | Contact association |
|---|---:|---:|---:|---|
| 1 / full PI | 95.92 | 2.400 | 1.00 | Drive-wheel/cable and caster/floor contact; no bracket contact within ±20 ms |
| 1 / schedule | 163.13 | 2.328 | 1.00 | Both casters land on floor; no bracket contact within ±20 ms |
| 2 / full PI | 21.58 | 2.198 | 1.00 | Caster wheel and bracket contact during first-cable climbing |
| 2 / schedule | 28.50 | 4.283 | 0.70 | Caster/floor landing; no bracket contact within ±20 ms |

The strongest first-repeat schedule spike precedes scheduled braking. Its interval contains approximately 681 N and 661 N vertical-dominated caster/floor solver-force peaks, about 0.33 mm penetration, and physical forward speed 0.636 m/s despite an executed 0.400 m/s reference. Motor feedback is present and the command is fresh. The first-repeat full-PI maximum instead overlaps drive-wheel/cable force peaks of about 606–673 N.

Brackets **do** strike the cables earlier in climbing; their nominal lowest mesh point is about 9.03 mm above level floor, below a 20 mm cable top. However, bracket interference is not a sufficient explanation for all large spikes. Contact landing/release and wheel response are the supported associations. Individual raw IMU sample timestamps were not saved, only interval summaries; these data cannot prove which contact generated an exact IMU peak. Solver forces/force-times-dt are diagnostic outputs, not calibrated force/impulse measurements.

## One selected flat physical correction

**Test passive caster wheel-axle damping `0.01 → 0.001 N·m·s/rad`.** Keep swivel damping and all geometry/mass/friction/controller/scoring parameters fixed.

The saved clear-floor segment x=1.0–1.8 m supports this choice independently of cable contact:

- Body speed is approximately 0.388 m/s; a 16 mm caster radius requires approximately **24.25 rad/s** for straight rolling.
- Measured caster rates across all four episodes are only **11.81–13.84 rad/s**: **49–57%** of that reference.
- Swivel angles in this segment are within 0.0037 rad of straight, so orientation does not explain the factor-of-two difference.
- At rolling speed, configured axle damping implies `b*v/r² ≈ 15.16 N` resistance per caster. Saved mean normal load is only 8.81–10.73 N per caster. The candidate reduces that calculated resistance to about 1.52 N.

This calculation uses viscous joint torque `-b*angular_velocity`; the installed DART version is 6.13.2. DART also accounts for damping implicitly, so these observations are **not** a claim that an explicit integration instability has been proved. [DART 6.13.2 joint implementation](https://github.com/dartsim/dart/blob/v6.13.2/dart/dynamics/detail/GenericJoint.hpp).

An isolated candidate is prepared at `rl_runs/flat_caster_damping_candidate_v1/model.urdf.xacro`; its expanded model comparison verifies **only the two caster wheel-joint damping values changed**. The active robot model is unchanged. Candidate manifest: `rl_runs/flat_caster_damping_candidate_v1/candidate.json`.

This is an evidence-supported baseline modeling correction to test, not a validated remedy for all impact spikes. Real caster bearing drag still needs measurement. Next screen: repeat the same four cold-start comparisons, checking caster rolling, impacts/penetration, physical arrival, timing, tracking, and both local/global vibration and slip. No new flat simulation, flat PPO pilot or Optuna study was started in this turn.

Detailed measurements: [flat impact report](flat_peak_contacts_2026-10-12/REPORT.md), [machine-readable audit](flat_peak_contacts_2026-10-12/analysis.json).
