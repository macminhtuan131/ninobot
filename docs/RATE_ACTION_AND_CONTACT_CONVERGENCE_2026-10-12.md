# Rough rate actions and flat contact comparison — 2026-10-12

Follow-up implementation and measured BC/flat-command-clock results:
[`ROUGH_BC_AND_FLAT_COMMAND_CLOCK_2026-10-12.md`](ROUGH_BC_AND_FLAT_COMMAND_CLOCK_2026-10-12.md).

## Rough: new revision 52

Run directory: [`rough_rate_action_pilot_v2`](../rl_runs/rough_rate_action_pilot_v2).

The external PPO action space is `Discrete(3)`:

| Action | Effect on next speed scale at 10 Hz |
|---|---|
| BRAKE = 0 | Decrease by 0.04, respecting the existing 0.55 floor |
| HOLD = 1 | Retain the last executed scale |
| RECOVER = 2 | Increase by 0.04, respecting the existing 1.00 ceiling |

The underlying wheel PI, yaw authority, terrain, 360-value causal observations,
speed bounds, ramp and all reward weights/terms are preserved. Internal history
records the continuous speed command actually executed. There is no sensor-triggered
override of PPO actions. The reactive PI reference is a separately evaluated baseline.

Holding changes from 0.6 to 0.8 s for the cue and reactive reference. At the existing
0.4 scale/s ramp, full speed to 0.70 requires 0.75 s. A 0.8 s scripted categorical
sequence reaches 0.68; HOLD sustains that value and RECOVER restores 1.00.

Initialization is fresh actor, critic and optimizer, seed 17000, with no checkpoint
transfer. The categorical actor starts near equal probabilities. Gaussian log-standard
deviation and gSDE fields inherited in the source YAML are unused by this action space;
the actual new policy uses categorical softmax likelihoods and entropy.

### Verified before training

- Normalized categorical probabilities on saved realistic input tensors.
- Exact chosen-action log probabilities equal PPO likelihood replay.
- Fresh optimizer, zero training counter, successful save/reload.
- Old continuous-action checkpoints rejected by the new action contract.
- Live execution: 1.00 → 0.68 → sustained HOLD → 1.00.
- Three untrained stochastic scenarios: 3/3 strict physical passes and 3/3
  sustained slowdown/recovery exposures. This demonstrates exposure, not learning.
- Physical/quality scoring regression against saved reference data passed.

An initial revision-51 integration run was stopped after its first completed update
because an inherited *diagnostic* labelled `RECOVER=2` as Gaussian action clipping.
Learning already used correct categorical probabilities. Its interrupted checkpoint
and traces are retained in `rough_rate_action_pilot_v1`; they are not resumed or used
for actor initialization. Revision 52 replaces that obsolete metric with
`policy/invalid_categorical_fraction`. Identical-config live execution evidence is
explicitly referenced in its workflow contract, rather than represented as new runs.

### Automated workflow

1. One fresh **20,480-step** training run.
2. Deterministic PPO on seeds 17100–17104.
3. Full-speed PI, reactive PI with 0.8 s holding, and duration-matched PI on those seeds.
4. Original independent physical arrival, tracking, slowdown/recovery, timing,
   vibration and slip gates. Also require window and global vibration/slip to
   remain within the existing 1.10 non-regression limit against reactive PI.
   This additional reference check was frozen before evaluation. All outcomes
   are recorded; Optuna remains held.

Live state: [`status.json`](../rl_runs/rough_rate_action_pilot_v2/status.json).
Training log: [`train.log`](../rl_runs/rough_rate_action_pilot_v2/train/train.log).
Final comparisons will be `rough_rate_action_pilot_v2/comparison.json` and
`acceptance.json`; the final acceptance report will be `ACCEPTANCE.md`.

### Completed rough result — checked 2026-10-12 at 10:13 +07

The full 20,480-step pilot and all four five-seed comparisons are complete.
All controllers achieved 5/5 physical arrivals. The PPO pilot failed its learned
disturbance-response and ride-quality gates.

| Controller | Arrival | Mean time s | Physical path RMSE m | Vibration RMS m/s² | Slip RMS |
|---|---:|---:|---:|---:|---:|
| Categorical PPO | 5/5 | 27.00 | 0.01689 | 1.2880 | 0.0193 |
| Full-speed PI | 5/5 | 27.00 | 0.01685 | 1.3251 | 0.0189 |
| Reactive PI | 5/5 | 28.84 | 0.01652 | 1.2597 | 0.0177 |
| Time-matched PI | 5/5 | 27.00 | 0.01684 | 1.2992 | 0.0183 |

Offline replay of the saved actor inputs confirms normalized categorical
probabilities. During 336 holding frames, mean BRAKE/HOLD/RECOVER probabilities
were 0.0479/0.2642/0.6878. RECOVER was the most likely action in every frame,
and all 1,350 executed deterministic evaluation actions were RECOVER. Executed
scale remained 1.00 throughout every disturbance holding window.

Saved stochastic training records contained 610 holding events. None reduced
scale by at least 0.25 from its first holding frame; 21 reached 0.70 or below,
which does not establish event-triggered braking because they could start slow.
Thus the categorical implementation works, but the learned policy did not acquire
the intended temporally sustained response.

Against time-matched PI, whole-course vibration improved about 0.9%, slip worsened
about 5.1%, and disturbance-window vibration energy per metre improved only 1.4%.
Against reactive PI, window slip energy per metre increased 10.9%, exceeding the
unchanged 10% non-regression allowance. This result does not qualify Optuna.

Preserve the model without extending it. Recommended next: use the validated
reactive controller to teach complete braking/holding/recovery sequences through
actor-only imitation initialization, verify deterministic response on held-out
demonstrations, then consider one fresh-critic/optimizer PPO pilot under a new
contract. Keep observations, action execution, reward weights and physical gates
fixed for that test. This is a proposed correction, not an already started run.

Full completed result: [`ACCEPTANCE.md`](../rl_runs/rough_rate_action_pilot_v2/ACCEPTANCE.md).

## Flat: reset-controlled 2 ms / 1 ms comparison

Run directory: [`flat_contact_convergence_v3`](../rl_runs/flat_contact_convergence_v3).

The original schedule is retained: brake from x=3.90 m toward scale 0.70;
begin recovery at **x=4.60 m**, with the original 0.4 scale/s ramp.

Physics step is the only world/config change between variants. The control interval
remains 0.1 s, controller-manager update period remains 0.002 s, and geometry,
wheel PI, estimator, cable scenarios and scoring remain unchanged.

The new readback plugin records actual drive/caster joint angles and velocities at
each physics step. The existing contact plugin records collision pairs, penetration
and solver wrench data. Neither probe commands joint positions, torque or velocity.

The initial sequential-episode screen found stationary joints but retained caster
swivel angles in its second episode. Those partial traces remain in
`flat_contact_convergence_v2` as diagnostics; they are not included in the corrected
comparison. The earlier startup-only failure remains in `flat_contact_convergence_v1`.

The corrected comparison uses **one cold simulator per measured episode**:

- 2 ms and 1 ms steps.
- Full PI and the original reference schedule.
- Seeds 65001 and 65004.
- Two repetitions each: **16 episodes**, with counterbalanced order.
- Verify final pre-action joint stationarity and caster swivel angles.
- Separate physical lateral tracking before braking, during crossing, and afterward.

Material timestep sensitivity flags require numerical review; two timesteps alone
do not establish convergence. Full-speed PI comparisons are not described as
time-matched comparisons. A flat PPO pilot is conditional on a stable crossing
benefit with preserved timing/tracking and quality gates.

The corrected sixteen-episode screen is complete: **16/16 physical arrivals**.
All measured initial joint velocities and caster swivel angles passed the frozen
reset checks. The crossing/promotion screen **failed**.

| Physics / profile | Arrivals | Mean time s | Physical path RMSE m | Vibration RMS m/s² | Slip RMS |
|---|---:|---:|---:|---:|---:|
| 2 ms / full PI | 4/4 | 17.40 | 0.0251 | 1.946 | 0.196 |
| 2 ms / original schedule | 4/4 | 18.40 | 0.0220 | 2.075 | 0.176 |
| 1 ms / full PI | 4/4 | 18.45 | 0.0219 | 7.826 | 0.276 |
| 1 ms / original schedule | 4/4 | 19.13 | 0.0222 | 1.823 | 0.228 |

The 1 ms schedule exceeds the unchanged 18.5 s limit. At 2 ms, one repetition's
whole-course vibration worsened despite better second-cable quality. Tracking
also changed before braking, where commands were identical. Caster/cable
penetration remained roughly 6–7 mm. Some severe impacts occurred at the first
cable, before the braking intervention. Reducing the timestep alone did not
establish a stable contact model. These results do not qualify a flat PPO pilot.

Full per-region and per-seed results:
[`REPORT.md`](../rl_runs/flat_contact_convergence_v3/REPORT.md) and
[`analysis.json`](../rl_runs/flat_contact_convergence_v3/analysis.json).

### One bounded contact-numerics correction candidate

`flat_bullet_contact_candidate_v3` tests an explicit **Bullet collision detector
inside DART**, preserving the solver, geometry, masses, controller intervals,
scenarios and original schedule. This selection is supported by
[Gazebo's physics configuration](https://github.com/gazebosim/gz-sim/blob/main/tutorials/physics.md)
and the [gz-physics 7 implementation](https://raw.githubusercontent.com/gazebosim/gz-physics/gz-physics7/dartsim/src/WorldFeatures.cc).
The installed engine contains the corresponding detector; the runtime log
acknowledged its selection before the first measured action.

This additional sixteen-episode check follows the concrete failed numerical
screen; it is a separate candidate, not a replacement of those saved results.
The two startup-only candidate attempts retained in v1/v2 collected no episodes
(ANSI log formatting and buffered startup acknowledgement). No main world or
existing model is overwritten. **The candidate is not yet adopted or validated;
flat PPO and Optuna remain held.**

Live candidate state:
[`status.json`](../rl_runs/flat_bullet_contact_candidate_v3/status.json).

### Completed candidate episodes, interrupted analysis

All sixteen Bullet-candidate episodes were collected: **15/16 physical arrivals**.
In repetition 1, 1 ms, full PI, seed 65004, the episode terminated with
`navigation_invalid` at 8.40 s and physical x about 2.20 m, before the second cable.
The physical endpoint error was 4.25 m. This termination does not establish a
contact-solver root cause; inspect reference/sensor validity at that instant.

The analyzer then raised `No covered reference disturbance windows` because it
assumed every episode reached the second cable. This is a reporting defect after
completed collection, not an interrupted training rollout. Preserve that failed
scenario and mark its second-cable measurements unavailable; do not drop it or
replace absent data with zero vibration/slip. Candidate qualification remains
failed on arrival regardless of the unavailable crossing comparison.

Recommended next: repair failure-aware reporting, inspect the saved first-cable
navigation/feedback/contact traces, and select one supported startup, feedback or
contact correction. Do not adopt Bullet solely from the other fifteen arrivals.
The conditional flat supervisor is held; no flat PPO or Optuna started.

### Conditional flat pilot

The separate supervisor in `flat_bullet_known_course_pilot_v1` waits for all sixteen
contact-candidate screening gates. A failed screen records a held state and starts
no PPO training. If the candidate passes, it waits for the rough workflow to finish
before running one 20,480-step pilot, avoiding simultaneous expensive training.

That pilot has a new revision-53 contract. It uses compatible speed/yaw actor
parameters only, a fresh critic/optimizer and zero training counter. Its observation
contract explicitly provides mapped cable distance and speed reference from estimated
pose in place of downward terrain preview; this is a known-course experiment, not
a claim of anticipation on unknown terrain with horizontal LiDAR. Shape-compatible
actor transfer does not establish equivalent behavior after that observation change.
The reference recovery point remains 4.60 m. PPO chooses its own actions without
a schedule override. The declared training reward adds the mapped executed-speed
reference cost used by the prepared conditional workflow.

Five cold-start evaluation seeds compare PPO with full-speed and duration-matched
PI, checking physical arrival, tracking, timing, crossing quality, slowdown and
recovery. This is a bounded pilot screen, not final 24-scenario promotion. Optuna
remains held. **At preparation time, this conditional flat pilot has not started.**
Live state: [`status.json`](../rl_runs/flat_bullet_known_course_pilot_v1/status.json).

## Monitoring

```bash
cd ~/ninorobot
cat rl_runs/rough_rate_action_pilot_v2/status.json
tail -n 35 rl_runs/rough_rate_action_pilot_v2/train/train.log
cat rl_runs/flat_bullet_contact_candidate_v3/status.json
```

Both supervisors own their simulators in separate ROS/Gazebo domains (rough 78,
flat 79). They close owned simulators after their workflow. Do not launch duplicate
Gazebo instances into those domains while these workflows are active.
