# Rough reactive PPO: detector, observation and reward audit

Date: 2026-10-11. Status: audit complete; Optuna held; no new pilot started.

Follow-up: the subsequently authorized corrections and fresh pilot are tracked
in [revision 47](ROUGH_OBSERVABLE_PILOT_2026-10-11.md). This audit's original
experiment and results remain unchanged.

## Scope and evidence

The completed `rough_reactive_reward_pilot_v1` trained a fresh one-action PPO for
20,480 steps, seed 16000, on fixed nominal half-relief E1. It used horizontal
LiDAR, IMU and wheel encoders. Its five evaluation scenarios were seeds
16100–16104, paired with full-speed and duration-matched PI.

This audit reads the frozen code/configuration, 71 completed training episodes,
15 completed evaluation episodes and their control traces. The pilot's frozen
asset hashes were verified. Exact saved reward totals were checked against
episode returns; vibration and slip costs were independently recomputed from
the captured interval traces for all 15 evaluation episodes. All checks passed.

Artifacts:

- [Machine-readable audit](rough_reactive_audit_2026-10-11/audit.json)
- [Signal and reward figure](rough_reactive_audit_2026-10-11/signals_and_rewards.png)
- [Audit script](../src/nino_rl/scripts/audit_rough_reactive_pilot.py)
- [Original experiment description](ROUGH_REACTIVE_AUTHORITY_2026-10-11.md)

Reproduce from the project root:

```bash
.venv/bin/python src/nino_rl/scripts/audit_rough_reactive_pilot.py
```

The script writes new diagnostic artifacts. It does not run ROS/Gazebo, change
the frozen experiment, resume training, or launch Optuna.

## 1. Outcome: arrival is reliable, adaptive behavior is absent

| Metric | PPO | Full-speed PI | Duration-matched PI |
|---|---:|---:|---:|
| Physical arrival | 5/5 | 5/5 | 5/5 |
| Time, s | 27.600 | 26.960 | 27.600 |
| Physical path RMSE, m | 0.01649 | 0.01676 | 0.01660 |
| Vertical vibration RMS, m/s² | 1.32188 | 1.31561 | 1.22899 |
| Wheel-slip RMS | 0.01538 | 0.01888 | 0.01901 |
| Mean raw reward | 18.51292 | 18.75968 | 19.67138 |

PPO operated near speed scale 0.975, including both disturbed and quiet periods.
No episode passed the declared conditional slowdown/recovery test. Relative to
duration-matched PI, global vibration was 7.56% higher and slip was 19.09% lower.
Inside the fixed PI-selected disturbance windows, vibration energy per metre
was 17.37% higher and slip energy per metre was 39.31% lower. This is a tradeoff,
not a demonstrated comfort improvement or terrain adaptation.

## 2. Detector: real cues, but policy-dependent rearming suppresses later events

The detector reads previous real-sensor state and previously published commands:

- Gravity-removed, tilt-compensated vertical acceleration: absolute-value EMA,
  time constant 0.15 s, threshold 1.5 m/s².
- Roll/pitch angular-rate norm: threshold 0.35 rad/s.
- Maximum wheel linear-speed error relative to commanded wheel speeds:
  threshold 0.06 m/s.
- Startup exclusion 0.8 s and minimum commanded forward speed 0.15 m/s.

Its phases are ready → holding (0.6 s) → recovering → cooldown (1.2 s) → ready.
**Recovering ends only when executed speed scale reaches 0.98.** This rule is
suitable for the scripted probe, which explicitly requests recovery to 1.0.
The same rule was reused for reward gating and evaluation annotations while
PPO remained free to choose a lower cruise scale.

| PPO seed | Triggers | Total recovering, s | Longest continuous recovering, s |
|---|---:|---:|---:|
| 16100 | 3 | 16.4 | 11.9 |
| 16101 | 4 | 16.6 | 9.1 |
| 16102 | 2 | 19.8 | 12.8 |
| 16103 | 9 | 2.6 | 0.7 |
| 16104 | 2 | 18.8 | 11.1 |

Four episodes spent long periods unable to trigger another hold. Disturbances
continued during those periods. As a stronger diagnostic, **every matched-PI
episode had only one trigger**, followed by 21.5–24.4 s in recovering: its fixed
scale 0.97681 is below 0.98. Full-speed PI produced 9–10 triggers per episode.
Therefore, trigger counts are contaminated by the chosen cruise speed. They
cannot be interpreted as directly comparable counts of terrain disturbances.

Evaluation's cue monitor and the reward monitor use the same previous state,
command, executed scale and timestep. The evaluation monitor only records cues;
it never replaces PPO actions. The reward monitor suppresses cruise tracking
cost only during holding. Thus this lockout affects training incentives as well
as annotations; it does not invalidate the independent physical arrival score
or the saved PI-selected spatial-window measurements.

### Sampling mismatch

The IMU publishes at 50 Hz; PPO and the detector use endpoint snapshots at
10 Hz. The vibration reward integrates the timestamped IMU samples over each
action interval. In the five PPO traces, 108–113 intervals per episode had a
peak at least 1.5 m/s² while the next observed endpoint was below 1.5 m/s².
The corresponding total high-peak intervals were 144–153 per episode.

This demonstrates loss of within-step information. It is **not** a detector
false-negative rate: a peak threshold differs from an EMA threshold, and the
detector also uses angular rate and encoders. Still, the actor is penalized for
high-frequency disturbance energy that its endpoint observations may not show.

Wheel-versus-command error is not an independent slip measurement. It includes
motor tracking error, acceleration limits and wheel-speed response; it must not
be labelled true slip. Ground-truth slip remains a simulation reward/scoring
quantity, excluded from the actor.

## 3. Observation: short history, hidden reward state and missing executed command

The actor receives **56 features × 5 frames = 280 inputs**, oldest first, at
10 Hz. The oldest-to-newest span is **0.4 s**. On reset, the first frame is
duplicated five times; there is no previous-episode history. The feature extractor
uses the latest frame, latest difference and a learned temporal convolution;
it has no recurrent hidden state beyond those five frames.

Included:

- IMU quaternion, gyro XYZ, accel XYZ, roll/pitch and tilt-compensated vertical
  acceleration.
- Encoder wheel velocities, estimated linear/yaw velocity and horizontal LiDAR.
- Route lookahead, heading/lateral errors, PI references, waypoint/time features.
- Previous raw policy action and two zero residual-action channels.

Excluded or absent:

- Ground-truth velocity/slip, terrain geometry and virtual downward preview.
- Interval IMU energy/RMS/peak and filtered disturbance EMA.
- Detector phase and hold/cooldown timers.
- Actual ramped speed scale and the exact previously executed linear/yaw command.

The actor can partly infer executed behavior from wheel motion and action
history, but there is no explicit matching input for all state used by the
reward gate. The 0.4 s window cannot retain a 0.6 s hold plus 1.2 s cooldown,
especially a potentially indefinite recovery phase. Identical short sensor
histories can receive different cruise penalties due to an older hidden event.

Complete actor tensors and raw 50 Hz IMU histories were not recorded during
this pilot. Consequently, these traces cannot establish causal IMU dependence,
run a faithful observation ablation, or reconstruct teacher training examples.

With horizontal LiDAR, IMU and encoders alone, this controller can react to
contact and wheel disturbances. It has no direct downward pothole preview;
we should assess attenuation after disturbance onset and subsequent recovery,
not assume it can anticipate every first impact on unseen terrain.

## 4. Reward contributions: comfort is already substantial

Exact mean raw return contributions over the five paired evaluation seeds:

| Term | PPO | Full PI | Matched PI |
|---|---:|---:|---:|
| Progress | +20.6040 | +20.6130 | +20.6161 |
| Arrival | +10.0000 | +10.0000 | +10.0000 |
| Vibration | −9.6548 | −9.3377 | −8.3624 |
| Time | −1.3800 | −1.3480 | −1.3800 |
| Path error | −0.6015 | −0.6071 | −0.6098 |
| Slip | −0.2714 | −0.3910 | −0.4097 |
| Heading | −0.1042 | −0.1023 | −0.1033 |
| Cruise velocity | −0.0789 | −0.0672 | −0.0796 |
| Executed reference slew | −0.00025 | 0 | −0.00002 |
| Late completion | 0 | 0 | 0 |

Relative to matched PI, PPO loses about **1.2924 reward from vibration**, gains
only **0.1383 from slip**, and ends with **1.1585 less total return**. The penalty
therefore detects the poorer ride. It is not absent, negligible, or outweighed
by the tiny velocity-tracking penalty in these final evaluation episodes.
Arrival/progress are mostly shared across successful policies; their large
absolute totals alone do not establish which policy changes receive useful
advantage signals.

Across training, the first ten episodes averaged speed scale 0.906 and time
29.70 s; the last ten averaged scale 0.962 and time 28.01 s. Mean raw return
rose from 18.7531 to 19.3028. This supports learning a faster cruise behavior,
not the intended event-conditioned response. The late penalty never activated
in the 71 completed training episodes, so it cannot explain that trend.

The earlier offline scripted-authority reward reconstruction favored reactive
PI by **+0.3408 on average**, but reactive PI won only **5/10 pairs**, with median
gain **−0.1058**. Those reconstructed returns were a weak incentive check, not
evidence that PPO would consistently learn the behavior. Fixed-map reset seeds
also do not provide unseen terrain diversity.

## 5. Exploration: the useful scripted slowdown was poorly represented

The configured `initial_speed_scale: 0.78` is a normalized head setting. With
the action mapping's 0.55 floor, its initialization bias corresponds to actual
scale **0.901**, not 0.78. This distinction was already documented in the pilot
contract, but the field name is easy to misinterpret.

The Gaussian raw action standard deviation stayed about 0.20, corresponding
to scale standard deviation **0.045 before clipping/ramping**. The scripted
probe requested scale 0.70 for 0.6 s and reached executed scale about 0.76.

At the initialization bias, probability of a *single target* at or below scale
0.70 is about **0.000004**. At the mean final deterministic raw action it is
about **0.0000000005**. These are analytic Gaussian tail estimates, not measured
event-conditioned training frequencies. Several lower targets must also
persist through the 0.4 scale/s reference ramp to obtain a substantial slowdown.

The saved training episodes' lowest executed scale was **0.7972**, and the last
ten episodes' lowest was **0.8572**. The policy therefore never executed a
slowdown as deep as the successful scripted probe in these completed episodes.
More vibration weight cannot reveal an action sequence the rollout does not
adequately try.

## 6. What to correct before another pilot

1. **Separate disturbance sensing from the scripted probe's recovery state.**
   Use a bounded, sensor-based event/refractory rule for reward gating, independent
   of whether the actor happens to exceed an absolute cruise scale of 0.98.
   Preserve the independent evaluation test for actual slowdown and recovery.
   Replay the rule on these traces first; matched PI must not remain locked out.
2. **Expose causal hardware summaries to the actor.** Add prior-interval IMU
   RMS/peak, filtered cue strength and wheel tracking error, plus actual executed
   speed/yaw references and ramped scale. If reward remains phase-gated, expose
   its causal phase/timer too, or remove that hidden state from the reward.
   Use a new observation/reward contract. Do not insert truth slip or virtual
   preview into actor inputs.
3. **Verify exploration before the next run.** Map initialization to the intended
   physical scale explicitly; ensure safe, sustained lower-speed sequences are
   actually encountered during disturbances. If using teacher initialization,
   collect exact synchronized hardware observation/action examples first;
   current CSVs cannot faithfully supply them. Any alternative exploration
   scheme must preserve correct PPO action log probabilities and the speed ramp.
4. **Keep the current reward weights initially.** Its exact accounting already
   disfavors the final poorer ride. Correct observability/rearming/exposure
   before selecting another comfort weight. Log event-conditioned reward totals,
   actual observation summaries and ramp response in the next contract.
5. **Then run one short pilot**, with the same physical arrival, tracking and time
   criteria and matched PI comparison. Require event-conditioned response and
   measured disturbance-window benefit. Optuna stays held until useful learned
   behavior is demonstrated; route/terrain expansion follows that check.

The audited detector lockout is established from code and traces. Missing
observation summaries and narrow exploration are supported limitations. Their
relative contribution to PPO failure still requires a corrected controlled
pilot; this audit does not claim a single proven cause or guaranteed fix.
