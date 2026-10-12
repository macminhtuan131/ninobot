# Rough reference and flat crossing authority — 11 October 2026

## Purpose

The sigma-corrected rough PPO completed its fixed budget but failed behavior and
window-quality acceptance. The latest flat slip-weight pilot also failed quality.
This workflow measures mechanisms before another reward search. Optuna and
curriculum remain held. Old models, source packages, studies and results are preserved.

Output: `rl_runs/disturbance_reference_comparisons_v1/`.
Runner: `src/nino_rl/scripts/run_disturbance_reference_comparisons.py`.

## Rough

- Reuse the complete, hash-verified PPO/full-PI/PPO-time-matched-PI evidence from
  `rough_recovery_sigma_pilot_v1`; no PPO is retrained or reevaluated.
- Evaluate the original validated sensor-only reactive reference on **17100–17104**.
  Target 0.70 for 0.60 s, mandatory recovery to 0.98, then 1.20 s cooldown.
  It receives IMU/encoder and previously published commands, no terrain position,
  ground truth or downward preview. It does not replace PPO actions.
- Use the current nominal fixed E1 half-relief terrain, estimator and controller;
  same original reactive implementation, unchanged 0.4 scale/s ramp and PI steering.
  A separate evaluation package enables the scripted baseline while blocking training.
- Evaluate a separate constant-speed PI matched to the reactive reference's achieved
  duration. Compare response depth, holding time, acceleration/recovery intervals and
  slip, and disturbance-window energy against that PI. The saved PPO retains its own
  time-matched PI; the reactive controller does not inherit PPO's matching factor.
- Windows are selected from the saved full-speed PI only. Physical arrival, ordered
  route gates, tracking, pose-validity and timing checks are unchanged.
- Reference screening additionally requires recovery, no more than 15% extra time,
  at least 5% improvement in one window energy/m measure with positive median paired
  gain, at most 10% regression in the other and whole-run metrics, and matching error ≤3%.

A pass supports selecting one holding-response correction under a new training
contract; it does not authorize resuming the failed model's optimizer or extending
its training. A fail holds the new pilot. Response associations are not a causal test.

## Flat

One schedule, frozen before evaluating **65000–65004**:

- First cable unchanged.
- Second cable at x=4.45 m: target scale **0.70** between estimated x=3.90 and 4.60 m,
  then target 1.0. Reference ramp remains **0.4 scale/s**.
- Compare full-speed PI, this schedule, and constant PI matched to its achieved time.
- Same stage-two geometry, angle/reset scenarios, reward, motor PI, estimator,
  physical scoring and transport in all three batches. All three use encoder
  transport history 100, preserving fusion and feedback timing limits.
- Crossing window fixed at physical x=4.10–4.80 m for offline scoring only.
- Preserve previous screening requirements: all physical arrivals, mean completion
  ≤18.5 s, tracking RMSE ≤1.05× full PI, at least 10% whole-run improvement in
  vibration or slip with no regression in the other. In addition, require matched
  duration within 3% and at least 10% crossing-window energy/m improvement against
  time-matched PI, with no regression in the other window measure.

This uses known cable location and estimated odometry. It is an authority experiment,
not a learned hardware-only policy. Passing it is necessary for the proposed pilot,
but the subsequent policy still needs a declared observation/action/reward contract;
it must not simply hardcode this schedule and label the result learned adaptation.
Failing it holds further PPO updates; no second schedule is searched automatically.

## Execution and recovery

The supervisor runs rough then flat sequentially to avoid competing physics workloads.
It owns only its simulator processes. Each evaluation uses mandatory startup/profile
checks. No freshness, clock, arrival or quality threshold is relaxed on interruption.
Finished batches are reused only with the same frozen hashes and seed list.

```bash
cd ~/ninorobot
cat rl_runs/disturbance_reference_comparisons_v1/rough/status.json
cat rl_runs/disturbance_reference_comparisons_v1/flat/status.json
tail -f rl_runs/disturbance_reference_comparisons_v1/supervisor.log
```

Recovery when no worker owns the lock:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST GZ_PARTITION=nino_flat_79
python src/nino_rl/scripts/run_disturbance_reference_comparisons.py --run
```

Each course writes `comparison.json` and `REPORT.md`. Five fixed-map scenarios are
an authority screen; neither multiple independent training seeds nor unseen terrain
or sim-to-real performance are established by this workflow.

## Completed rough comparison and selected correction

The rough reference passed on all five paired scenarios. It achieved 5/5 physical
arrivals, mean time 28.14 s versus 28.10 s for its matching PI, and physical RMSE
0.01641 m. Window vibration energy/m was **10.92% lower**; window slip energy/m
was **4.89% higher**, inside the unchanged 10% regression limit. Whole-run slip
was about 3.36% higher. This is a passing tradeoff under the declared screen,
not an improvement in every metric.

The scripted reference reached scale 0.76 and recovered in every episode. The
saved PPO reached minima 0.922–0.955 and failed the response gate. The reference
spends about 4.74 s/episode slowing and 4.68 s accelerating; the saved PPO spends
about 3.24 s slowing and 3.36 s accelerating. These mode durations use the same
executed-scale rate definition and exclude startup/final approach.

One candidate is prepared at `rl_runs/rough_holding_reference_candidate_v1`,
**training contract revision 49**:

```yaml
reward_v2:
  holding_reference_target_scale: 0.70
```

It adds one cost **only during the existing actor-visible sensor-cue holding state**:

`-dt * existing_velocity_weight * ((executed_scale - 0.70) * external_PI_linear_request / existing_velocity_sigma)^2`

All previous reward terms are unchanged, including the zero physical-velocity
penalty during holding and sigma 0.1 outside holding. The coefficient and
normalization reuse the existing velocity settings; no global vibration/slip/time
weights are increased. Outside holding the new cost is exactly zero. It reads
neither terrain X nor physical position and does not override an inference action.
The policy still chooses its speed and the original reference ramp executes it.

This addresses the observed weak slowdown directly while retaining the corrected
cruise incentive. It is a soft target, not proof of learned behavior. The 0.6 s hold
and unchanged ramp may prevent reaching 0.70 from full speed; the reference itself
bottoms at 0.76. Reward cannot change that physical command limit. The candidate
may also increase slip, and the original behavior/quality gates must reject it if so.

Offline checks passed: all previous reward contributions identical, new term zero
outside holding, exact target-cost values, identical fresh actor/critic tensors,
empty optimizer/counter, old optimizer resume rejection, causal 360-input interface
and save/reload. The candidate uses the same original fresh initialization and seed
17000, with a declared 20,480-step budget. **It is prepared, not training.** The
user's rough instruction requests selection/preparation; no extra rough learning
run is started by this comparison.

```bash
cd ~/ninorobot
.venv/bin/python src/nino_rl/scripts/prepare_rough_holding_reference_correction.py
```

Flat's first launch stopped before evaluation because the parent shell did not
export the expected ROS domain. The failed startup logs are preserved. Only flat
was restarted with domain 79/partition `nino_flat_79`; physics, scoring and timing
limits were unchanged. The recovery command above includes those exports.

## Completed flat comparison

All three controllers reached 5/5 physical goals and cleared both cables:

| Controller | Time s | Physical RMSE cm | Whole-run vibration RMS m/s² | Whole-run slip RMS |
|---|---:|---:|---:|---:|
| Full-speed PI | 17.58 | 4.04 | 3.128 | 0.19042 |
| Second-cable schedule | 18.52 | 3.90 | 2.899 | 0.19143 |
| Time-matched PI | 18.42 | 3.40 | 2.910 | 0.19971 |

The schedule demonstrated useful **local** authority: second-cable vibration
energy/m fell **63.76%** and slip energy/m fell **3.36%** against time-matched PI.
Duration matching error was 0.54%, within the frozen 3% bound.

It did **not** qualify for the conditional pilot. Against full-speed PI, whole-run
vibration fell only 7.32% (required at least 10% in one quality metric with no
regression in the other), while slip rose 0.53%. Mean time 18.52 s also exceeded
the preserved 18.5 s promotion limit by 0.02 s. Tracking passed. All episodes
arrived before the task's 22 s target; the stricter existing promotion-time gate
still failed. The limit was not rounded or relaxed after observing the result.

No flat PPO pilot, extra schedule search, curriculum or Optuna was started.
The result supports the second-cable mechanism, but not an accepted whole-course
improvement. Before a future learning experiment, the missing whole-course
benefit/time margin needs a declared experiment; one should not bypass those gates
because the local percentage looks favorable.

Final evidence:

- [Rough comparison](../rl_runs/disturbance_reference_comparisons_v1/rough/REPORT.md).
- [Flat comparison](../rl_runs/disturbance_reference_comparisons_v1/flat/REPORT.md).
- [Rough candidate contract](../rl_runs/rough_holding_reference_candidate_v1/pilot_contract.json).
- [Rough candidate verification](../rl_runs/rough_holding_reference_candidate_v1/verification.json).

## Completion

The reference workflow is complete. It made zero PPO updates. Rough revision 49
is a prepared candidate, not a trained policy. The flat conditional learning
branch remains held because its fixed gates failed. Both old studies and the
sigma-corrected rough result remain unchanged.
