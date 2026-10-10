# Rough turning: contact evidence and isolated localization correction

This report records the v7 correction and its limitations. The pilot was later
saved at 6,326 steps after repeated E1 wall-coverage losses. The current profile
and commands are in [rough localization robustness](ROUGH_LOCALIZATION_ROBUSTNESS_2026-10-09.md).
The wrapper now targets that new contract; the v7 measurements below remain
historical evidence.

## Measured cause of the S1 stall

The original three S1 PI runs stopped at approximately `(2.65, -0.71 m)`.
Wheel rotation continued without chassis translation. A diagnostic capture at
that same pose found the following over 179 contact samples:

| Contact | Samples with contact | Mean vertical support |
|---|---:|---:|
| Chassis collision mesh | 100% | 9.23 N |
| Left drive wheel | 100% | 20.30 N |
| Right drive wheel | 0% | 0 N |
| Right caster wheel | 100% | 24.90 N |
| Left caster wheel | 100% | 0.39 N |
| Either caster fork | 0% | 0 N |

This confirms chassis grounding and an unloaded right drive wheel at the
stalled pose. This capture was made after the failed episode, with stopped
commands; the loads are not synchronized force measurements from the original
wheel-spin trace. No robot masses, friction, torque limits or map geometry were
changed. The diagnostic plugin requests contact data only, following Gazebo's
[ContactSensorData component](https://gazebosim.org/api/sim/8/ContactSensorData_8hh.html)
and the [Physics implementation](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/physics/Physics.cc).

Raw evidence: [contact summary](rough_turn_review_2026-10-09/stall_capture/contact_summary.json),
[contacts](rough_turn_review_2026-10-09/stall_capture/contacts.csv), and
[wall measurement check](rough_turn_review_2026-10-09/stall_capture/wall_observation_check.json).

## New experimental estimator and turn profile

- Known outer wall faces: X `[-2, 12] m`, Y `[-7.2, 7.2] m`.
- Existing 2D LiDAR extrinsics: `[0.20, 0, 0.2275] m` from base footprint.
- IMU orientation rotates laser rays in 3D before wall fitting.
- Endpoint-height checks, ceiling rejection, bounded association and robust
  inlier checks reject nearby terrain and self returns.
- Both axes must be observed. Accepted fixes independently correct wheel XY.
- Three successive wheel-motion/scan-stationary discrepancies suppress encoder
  translation until independent scan displacement indicates movement.
- No physical pose, goal coordinates or terrain height map enter localization.
- Missing localization beyond 0.6 simulated seconds invalidates control. Three scans lose
  X-wall coverage on the E1 crest at about 19 degrees pitch; coverage recovered
  after 0.4 s in the recorded diagnostic. This is a bounded observation outage,
  not permission to ignore long stalls or action timing faults. With fresh
  scan/IMU/encoder input, loss of geometric localization now stops and fails
  the episode as `navigation_invalid`. A stale scan stream, encoder/IMU gap
  or action timing fault still aborts training. Estimated pose is explicitly
  marked invalid; it is not treated as a fresh independent measurement.
- An initial encoder gap during discovery discards the unscored startup epoch;
  gaps after an episode reset remain fatal.
- A dedicated reliable ROS IMU bridge publishes `/rough/imu/data`, with a
  reliable subscriber in the frozen rough package. S1's best-effort profile
  twice stopped on assisted-feedback ages of 42/46 ms. The action-feedback
  limit remains 40 ms; reliability changes delivery, not sensor timestamps.
- PI turn speed is `0.18 m/s`, maximum yaw rate `0.45 rad/s`, replacing
  `0.12 m/s` and `0.8 rad/s`. This avoids the previous very tight turn request.
  At the capped right turn, nominal wheel targets become about `4.11/1.65 rad/s`
  instead of `4.11/-0.27 rad/s`: both wheels are asked to roll forward.
- This is estimator slip handling, not an autonomous reverse/un-sticking controller.

This profile assumes the calibrated IMU heading and known rectangular outer
walls of this map. It is not a general SLAM system; a different environment
requires appropriate map geometry, calibration and independent validation.

At the old S1 pose, all 17 scans produced accepted wall fixes: mean error
`0.0116 m`, maximum `0.0135 m`, with approximately 17 degrees roll. A first
closed-loop S1 probe reached the physical goal in 28.4 s. Both localization and
turn settings changed together, so that probe does not isolate their individual
contributions. Multi-route qualification is required before training.

## Contracts and preservation

The flat study remains on its original sources. Rough runs import an immutable
package copy under `rl_runs/rough_wall_slip_v7/python`; the changed estimator is
copied there only. `manifest.json` hashes package sources, controller, robot and
terrain inputs. `rough_experiment.snapshot_sha256` is part of the PPO contract.

Earlier failed preparation/probe revisions remain under `rough_wall_slip_v1`,
`v2`, `v3`, `v4`, `v5` and `v6`. Original rough/flat studies, failed trial records and source
checkpoints are preserved. Use the wrapper below: direct `ros2 run` without its
isolated `PYTHONPATH` would load the original estimator.

Physical scoring stays at the original 0.20 m goal circle plus ordered route
gates, using ground truth independently from control localization. The PI
qualification additionally requires mean estimated/physical position error
at most 0.10 m, all nine fixed-seed physical arrivals, and matching contracts.
Three episodes per route are a pilot check, not a statistical reliability claim.

## Completed qualification and started pilot

The v7 reliable-IMU profile completed all nine PI episodes under the original
action timing limit. Physical goal scoring and route gates stayed unchanged.

| Route | Arrivals | Mean physical endpoint | Mean pose disagreement | Mean time |
|---|---:|---:|---:|---:|
| E1 | 3/3 | 0.192 m | 0.002 m | 27.10 s |
| N1 | 3/3 | 0.194 m | 0.001 m | 23.93 s |
| S1 | 3/3 | 0.193 m | 0.002 m | 27.63 s |

[Detailed before/after comparison and figure](rough_wall_localization_2026-10-09/README.md).
S1's original lower path RMSE is misleading on its own: it stopped after a
small fraction of the route. The corrected run completes the route, but its
0.197 m physical path RMSE still leaves substantial tracking work for PPO.

The v6 CUDA pilot started on 2026-10-09 at 08:04 local time: budget 20,480
steps, first stage E1, original fixed map, 2,048 steps per PPO update, checkpoints
every 10,240 steps. All 12 runtime preflight checks passed. Thirteen actor
tensors were transferred from the preserved 20,480-step E1 actor; the critic
and optimizer are fresh and this run starts at zero steps.

Training directory:
`rl_runs/rough_wall_slip_v6/curriculum/blocks/block_0000/train/20261009-080455-304489`.
Live log: `rl_runs/rough_wall_slip_v6/curriculum/blocks/block_0000/train.log`.
That pilot stopped when an exploratory action lost wall localization; its
interrupted checkpoint is preserved. V7 changes this case to a failed episode
with stopped commands, rather than an infrastructure exception. V7 passed
new qualification and its new 20,480-step CUDA pilot was launched at 08:19,
with fresh critic/optimizer initialization. Live log:
`rl_runs/rough_wall_slip_v7/curriculum/blocks/block_0000/train.log`.
Run directory:
`rl_runs/rough_wall_slip_v7/curriculum/blocks/block_0000/train/20261009-081917-345646`.
All 12 preflight checks passed and 13 actor tensors were transferred. The first
exploratory E1 episode lost geometric wall coverage at 31.4 simulated seconds;
it ended as `navigation_invalid` and reset into the next E1 episode without
aborting training. This confirms live loss/reset handling, not policy quality.
These PI improvements
are not yet evidence that PPO is better than PI. Promotion and continuation
depend on subsequent evaluations.

## Commands

Run from the repository root. Stop an existing rough Gazebo launch with Ctrl+C
in its own terminal before using the supervisor; leave the flat session running.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

python src/nino_rl/scripts/run_rough_localized.py prepare
python src/nino_rl/scripts/diagnose_rough_localized.py --full
```

The supervisor owns the diagnostic Gazebo instance, checks PI on E1/N1/S1,
then closes that instance. Qualification runs use these exact prior seeds:
E1 `10000/10003/10006`, N1 `10001/10004/10007`, S1 `10002/10005/10008`.

Start a short new curriculum pilot only after the PI gate passes:

```bash
python src/nino_rl/scripts/run_rough_localized.py curriculum \
  --device cuda --timesteps 20480 --block-steps 20480 \
  --checkpoint-every 10240 \
  --init-model rl_runs/rough_e1_imu_assisted_pilot/20261008-013943-771247/nino_ppo_final.zip
```

The wrapper refuses training if qualification is absent, incomplete, physically
unsuccessful, too inaccurate or from different settings/seeds. Actor transfer
keeps the old actor as initialization, with fresh critic/optimizer and a new
step counter. Do not resume an old rough optimizer into this contract.

Stages stay on the original fixed mesh: E1, then E1+N1, then E1+N1+S1. Each
promotion requires 20 evaluation episodes per route, at least 95% physical
success, physical path RMSE at most 0.05 m, and no rollovers. Earlier routes
remain in replay. Terrain randomization is disabled throughout this pilot.

Reward weights and action meanings are retained. Passing PI checks establishes
a working reference controller; it does not establish a PPO improvement. The
pilot must preserve physical arrival and earn improvements in tracking,
completion time, vibration or slip against that PI reference. In particular,
the turning stages' 0.05 m path gate is more demanding than simply arriving.

An interrupted **new-contract** pilot can be resumed with:

```bash
python src/nino_rl/scripts/run_rough_localized.py curriculum \
  --resume --device cuda --timesteps 20480 --block-steps 20480 \
  --checkpoint-every 10240
```

Inspect the numerical gate, rather than treating a completed command as a pass:

```bash
cat rl_runs/rough_wall_slip_v7/pi_gate.json
```

Tests: the focused estimator and qualification tests cover tilted wall rays,
floor/ceiling rejection, wheel-spin drift suppression, movement recovery,
staleness, reset epochs, strict in-episode timing and rejection of unqualified
or incomparable PI evidence.
