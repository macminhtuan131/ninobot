# Next pilot with the actual sensor set

**Follow-up implementation:** the [confirmation and fresh pilot workflow](../ROUGH_HARDWARE_PILOT_2026-10-11.md) now implements the one-action contract and gates described below. The historical `hardware_sensors_v2` snapshot remains PI-only. Live progress is in `rl_runs/rough_hardware_confirmation_v1/REPORT.md` and `rl_runs/rough_longitudinal_pilot_v2/REPORT.md`.

Hardware confirmed by the user: **horizontal LiDAR, IMU, wheel encoders**. No downward terrain sensor or multi-channel wall LiDAR.

## What changes

- The corrected downward preview remains a simulation diagnostic. It is excluded from the deployment actor and localization inputs.
- The hardware preflight has 56 sensor/command values per frame, five frames (280 values). Its executable checks inject preview and truth velocity and verify that neither changes the actor observations.
- Localization currently uses IMU, encoders and tilt-compensated horizontal LiDAR against known rectangular walls. This map prior, sensor calibration and IMU yaw assumptions must be supplied or replaced on hardware. Passing this simulated corridor does not establish localization on an arbitrary map.
- The existing 300-value models and optimizer states cannot be resumed in this observation contract. Old models remain comparison records; explicit actor remapping would need its own verification.

## Intended skill

Train a **reactive longitudinal supervisor**: adjust speed from IMU motion, wheel response and recent command history, then recover requested speed after a disturbance. PI supplies path steering and independent wheel control.

Horizontal LiDAR can see objects intersecting its scan plane. IMU detects the robot's motion after a disturbance reaches it. This sensor set cannot reliably provide advance geometry for an unseen depression; a policy must not be credited with that ability because it memorized a fixed obstacle position. The known-location cable intervention establishes that changing the speed reference can affect crossing quality, but is not a sensor-only learned controller.

## Before starting the pilot

1. Complete the hardware-only E1/N1/S1 feasibility screen, then a small confirmation batch for the route chosen for the pilot. Preserve physical arrival, localization validity and tracking limits.
2. Confirm the mechanical response for actual friction and mass profiles using the same hardware-only inputs. Separate fixed nominal learning from later physical randomization. Declare held-out terrain/dynamics before selecting candidates.
3. Freeze a new learning contract. The first task should have one bounded speed action, a fixed reference ramp, no additive torque or learned yaw residual, and PI heading authority that remains available during slowing. Verify the executed wheel references and stop behavior before learning; the current shared linear/yaw scale is not that proposed controller.
4. Start fresh actor/critic/optimizer weights, with initial behavior near the validated PI reference. A short pilot should demonstrate repeatable sensor-conditioned speed adjustment and recovery. Use a fixed reward normalization; log motion tracking, time, vibration, slip and action-rate contributions separately.
5. Evaluate the pilot against full-speed and speed-matched PI, on held-out scenarios. Arrival remains strict. Include crossing-window vibration/slip as well as whole-episode averages, so a longer quiet approach cannot conceal a poor crossing.

These were the prerequisite learning steps for the follow-up implementation linked above. `hardware_sensors_v2` explicitly disables training: its three-action PI interface is retained only for the feasibility screen. The separate `rough_longitudinal_pilot_v2` snapshot has the new one-action policy and fresh training contract.

## When Optuna becomes useful

After the new task shows useful learned response, create a **new study**, with identical actor initialization, budget and evaluation scenarios per trial. Tune learning rate, entropy, PPO update settings and a small set of normalized reward weights. Keep action meanings, physical criteria and the evaluation objective fixed. Preserve earlier studies without importing incompatible scores.

Require independent training seeds and unseen physical layouts/dynamics before claiming generalization or a sim-to-real improvement. Real motor delay/limits, encoder calibration, IMU alignment/noise and LiDAR timing still require measurements from the physical robot.
