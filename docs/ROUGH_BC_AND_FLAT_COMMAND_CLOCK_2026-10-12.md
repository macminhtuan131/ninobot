# Rough actor imitation and flat failure recovery — 2026-10-12

## Status

The failed revision-52 categorical PPO checkpoint is preserved and hash-bound in
the new rough manifest. It is neither resumed nor used as the new actor source.
The new revision-56 PPO pilot starts from a supervised actor with a **fresh critic,
fresh optimizer and zero PPO counter**. Terrain, controller, 360 causal hardware
inputs, action meanings, speed bounds/ramp, reward weights/terms and physical
scoring are unchanged.

Rough run: [`rough_rate_bc_pilot_v2`](../rl_runs/rough_rate_bc_pilot_v2).
Flat diagnostic run: [`flat_command_clock_check_v2`](../rl_runs/flat_command_clock_check_v2).
Optuna remains held. No flat PPO pilot has started.

## Rough: teach complete categorical sequences

The teacher reads only the existing latest observation's holding state and last
executed speed scale. Holding requests the validated reactive reference's 0.70
scale; outside holding it requests recovery to 1.00. Each command is quantized
through the unchanged categorical interface: BRAKE decreases 0.04 per 0.1 s,
HOLD preserves scale, RECOVER increases 0.04. Nearest-target ties favor HOLD.
Starting at 1.00, this yields a stable **0.72** approximation of continuous 0.70,
rather than pretending the discrete ramp can hit 0.70 exactly. No physical pose,
terrain preview or future sensor value is used to choose teacher actions.

Five physical demonstrations passed arrival/tracking and slowdown/recovery gates:

| Seed | Purpose | Arrival | Time s | BRAKE/HOLD/RECOVER counts | Minimum scale |
|---|---|---:|---:|---:|---:|
| 17200 | Training | yes | 28.70 | 56 / 175 / 56 | 0.72 |
| 17201 | Training | yes | 28.80 | 56 / 176 / 56 | 0.72 |
| 17202 | Training | yes | 28.80 | 56 / 176 / 56 | 0.72 |
| 17203 | Epoch-selection validation | yes | 28.50 | 49 / 187 / 49 | 0.72 |
| 17204 | Held-out test | yes | 28.50 | 49 / 187 / 49 | 0.72 |

A fresh seed-17000 actor was trained with balanced categorical cross entropy for
10 epochs. Only actor parameters received gradients. Critic tensors were checked
unchanged; the PPO optimizer remained empty and PPO steps remained zero.

- Validation accuracy: **98.25%**.
- Held-out test accuracy: **97.89%**.
- Held-out BRAKE and RECOVER recall: **100%** each.
- Held-out HOLD recall: **96.79%**.
- Normalized categorical probabilities and exact save/reload probabilities passed.

The deterministic actor then passed all three independent live probe seeds:

| Seed | Physical arrival/tracking | Slowdown then recovery | Time s | Minimum scale |
|---|---|---|---:|---:|
| 17300 | pass | pass | 29.10 | 0.68 |
| 17301 | pass | pass | 28.90 | 0.68 |
| 17302 | pass | pass | 28.70 | 0.68 |

Those live results permitted exactly one **20,480-step** PPO pilot. The transferred
12 actor tensors and source hash are recorded in the training run's
`actor_transfer.json`; critic/optimizer are fresh, counter zero. Training started
at `train/20261012-111637-109195`. Final deterministic PPO/full PI/reactive PI/
time-matched PI comparisons use seeds 17400–17404 and the preserved physical,
behavior, timing, vibration and slip gates. Reactive-reference non-regression is
also retained. A passing imitation probe is **not** evidence that PPO beats PI.

An independent transfer replay used a separately seeded fresh target and verified
all 12 copied actor tensors, bitwise unchanged target critic tensors, empty
optimizer and zero counter. It also verified the preserved failed checkpoint's
hash. At the last check, PPO had completed its first 1,024-step rollout; the
20,480-step training and final paired comparisons remain in progress.

Small fixed-E1 demonstration/test splits do not establish unseen-terrain,
physical-profile or sim-to-real generalization. Final PPO results are pending.

### Preserved integration attempts

`rough_rate_bc_pilot_v1` stopped before BC because the collection helper did not
enable control tracing. Revision 56 in v2 corrects trace collection; the earlier
attempt and initial observation capture remain preserved. No BC/PPO updates from
that attempt were imported.

## Flat: failure-aware reporting

The repaired analyzer writes a separate report without modifying any original
episode, model or frozen contract:
[`REPORT.md`](flat_contact_failure_recovery_2026-10-12/REPORT.md).

It retains **16 episodes and 15 physical arrivals**, including the failed
1 ms/full-PI/seed-65004 episode. Unreached crossing measurements are **null /
unavailable**, never zero, and the failed episode remains in arrival totals.
Unsuccessful durations are explicitly time to termination, not arrival time.
The candidate remains unqualified. Regression on the original complete screen
reproduced all original gate values and ratios exactly.

## Flat: saved-trace audit and one supported diagnostic correction

The original failed episode stopped at physical x approximately 2.20 m, before
the second cable. Over its final two seconds:

- All 95 stamped drive samples had fresh command, policy and wheel-state flags.
- Executed speed reference remained 0.40 m/s.
- Wheel tracking RMSE was 5.71 rad/s while physical translation barely advanced.
- IMU interval coverage and motion timestamp checks remained satisfied.
- Caster wheel/bracket contacts were sustained, with large raw solver wrench
  spikes. These are solver outputs, not a calibrated physical force measurement.

The navigation reference nevertheless checks its **own published command** using
wall-time age. Slow lockstep contact computation can expire this age without
advancing much simulation time. Old traces did not record the particular stale
stream; therefore the initial audit identified a hypothesis, not a proven contact
root cause.

An isolated profile changes only own-command freshness to simulation time in
lockstep. Missing, future and stale simulation-stamped commands still invalidate
the reference. Sensor wall-age checks, motion lag, IMU coverage, feedback barriers,
physical scoring, geometry, controller and 1 ms physics are preserved. Hardware/
default profiles continue to use wall time.

The rerun also waits up to the **existing** two-second DDS delivery timeout for
genuine motor diagnostics whose stamps fall inside the executed action interval.
It advances no physics, substitutes no stale sample and retains the original
error if samples remain absent. The measured maximum wait was 0.00079 s.

### Rerun: 1 ms, full PI, seed 65004, one cold start

| Metric | Result |
|---|---:|
| Physical arrival | pass, 1/1 |
| Completion time | 16.90 s |
| Physical endpoint error | 0.19997 m |
| Physical path RMSE | 0.00905 m |
| Vibration RMS | 3.938 m/s² |
| Slip RMS | 0.10198 |
| Reference valid | every measured interval |
| Own command would expire under old wall-time test | 16 intervals |
| Maximum own-command simulation age | 0.100 s |
| Maximum motion sensor lag | 0.021 s |
| Maximum episode clock disagreement | 8.2e-14 s |
| Initial joint stationarity and caster swivel-angle checks | pass |

This directly demonstrates wall-time command expiry despite current simulation
commands. It supports the freshness correction, but does **not** establish that
the Bullet contact profile is stable or that the original stall is eliminated
reproducibly. The source failed arrival remains counted in its original study.
No broader flat batch, PPO pilot or Optuna study was started.

Flat v1 startup attempts (missing baseline-profile environment variable, then
missing immediate drive-diagnostic delivery) remain preserved separately. The v2
runner supplies its explicit full-PI profile and bounded genuine-sample delivery
wait. These interrupted attempts are not completed evaluation episodes.

## Monitor the running rough pilot

```bash
cd ~/ninorobot
cat rl_runs/rough_rate_bc_pilot_v2/status.json
tail -n 35 rl_runs/rough_rate_bc_pilot_v2/train/train.log
```

The rough supervisor owns ROS domain 78 / Gazebo partition `nino_rough_78` and
closes its simulator after the final comparisons. Flat's diagnostic supervisor
has completed and closed its owned domain-79 simulator. Avoid launching another
rough simulator into the active domain while the pilot runs.
