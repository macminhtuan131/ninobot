# RL foundation checks — 2026-10-11

No PPO updates or Optuna trials. Historical maps, packages, checkpoints and studies were preserved.

This report records the initial foundation experiments. For the subsequent confirmation and fresh PPO pilot, see [the follow-up workflow](../ROUGH_HARDWARE_PILOT_2026-10-11.md). Its live runner reports distinguish ongoing confirmation, training and completed evaluation.

## Rough physical failure

The unchanged rejected N1 maneuver was recaptured with a diagnostic contact plugin. It failed with recovery exhausted. During the final 14.9 seconds the chassis, right caster and left wheel contacted the terrain; the right drive wheel did not. Physical pose span was below one micrometre. This is strong evidence of a chassis-supported hang-up, rather than a reward or arrival-estimation problem. One reproduction does not qualify every route.

## Hardware constraint

The user confirmed horizontal LiDAR, IMU and wheel encoders only. The simulated downward fan and 33-channel wall sensor are unavailable on the physical robot. Downward preview is diagnostic only. Earlier 3D-wall-assisted PI results do not qualify the hardware estimator.

A separate hardware-sensor preflight removes both virtual sensors from the spawned URDF, uses the existing IMU-compensated horizontal wall fit, and excludes all four preview values from the actor (56/frame, 280 with five frames). It preserves physical links/masses, PI settings, terrain and strict arrival scoring. The known corridor wall geometry is still a localization prior: this is not arbitrary-map localization or a deployment-ready result. Learning is disabled in this preflight snapshot.

IMU and encoder history can support reactive ride adjustment after contact. Horizontal LiDAR may observe obstacles intersecting its scan plane, but does not reliably measure an unseen pothole ahead. The earlier known-location anticipatory intervention is a control-authority reference, not evidence that these sensors provide terrain preview.

## Isolated diagnostic correction

- Candidate terrain: same XY features/topology, 50% elevation relief; one STL for collision and visual. Height range −0.0820…+0.1219 m; maximum triangle grade 0.2944. Original map unchanged.
- Preview uses evaluated URDF extrinsics (.33,0,.20 m), axle height .0625 m, timestamp-matched IMU roll/pitch and proper 3D ray rotation. The original .2325 m sensor height was inconsistent with the .2625 m nominal floor-relative transform.
- Diagnostic preview overlay: separate left/right distance, height and validity, 63 values/frame and 315 with five frames. This overlay is not the hardware actor. Neither its 315-value nor the hardware preflight 280-value contract accepts a 300-value checkpoint resume.
- Missing returns stay invalid. Reset history is refreshed after epoch clearing, with motors stopped; actual paused time defines time zero. Per-action timing checks remain intact.
- Real nominal/low-friction/heavy URDF/SDF profiles are prepared (wheel mu 1.2/0.6, mass/inertia ×1.0/1.15). Converted SDF friction was checked. Randomized training and the mass profile are not yet qualified.
- The [Gazebo DART importer](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/SDFFeatures.cc#L859) reads the SDF ODE friction coefficients into DART contact dynamics; these profiles do not scale policy torque.

## Rough mechanical screening

| Profile | Arrivals | Completion s | Physical RMSE m | Slip | RMS vertical acceleration m/s² |
|---|---:|---:|---:|---:|---:|
| nominal | 1/1 | 28.3000 | 0.0319 | 0.0301 | 1.1631 |
| low friction | 1/1 | 28.3000 | 0.0320 | 0.0314 | 0.9906 |

Both screens use seed 13000 with zero RL residual. One trial per profile cannot establish a repeatable friction effect or qualify E1/S1. The nominal final window has no chassis contact. These are PI results on changed geometry, not improved PPO results.

## Longitudinal authority

The same three reset seeds compare full PI, constant 0.70 scale, and an anticipatory 0.60 scale near cables with a 0.4 scale/s reference ramp. The intervention uses estimated pose and known cable locations, zero RL torque/yaw, unchanged PI and independent physical scoring. It tests control authority; it is not a deployment policy.

| Intervention | Arrivals | Completion s | Physical RMSE m | Second-cable speed m/s | Slip | Vibration m/s² |
|---|---:|---:|---:|---:|---:|---:|
| full | 3/3 | 17.533 | 0.0312 | 0.295 | 0.334 | 4.905 |
| constant | 3/3 | 24.800 | 0.0481 | 0.199 | 0.378 | 3.044 |
| anticipatory | 3/3 | 21.033 | 0.0214 | 0.172 | 0.299 | 3.080 |

## Hardware-only PI screening

| Route | Physical arrivals | Physical RMSE m | Mean pose disagreement m | Screen gate |
|---|---:|---:|---:|---:|
| E1 | 100% | 0.0171 | 0.0017 | True |
| N1 | 100% | 0.0341 | 0.0009 | True |
| S1 | 100% | 0.0213 | 0.0003 | True |

One reset seed (13000) per completed route. Passing a screen does not establish robustness.

Actor-isolation checks passed: injected preview and truth velocity have no effect; the actor does not call the preview API, the estimator does not use a point cloud, and the spawned robot contains only horizontal LiDAR and IMU sensor types.

The [next pilot plan](NEXT_PILOT.md) records the hardware-specific learning task and remaining qualification steps.

## Remaining gates

1. Qualify a mechanically feasible route/terrain combination, including N1 and unchanged route scoring.
2. Validate horizontal-only localization and sensor history. Preserve invalid/stale-data handling; IMU tilt compensation cannot create missing wall returns. Keep virtual preview outside the deployable actor and estimator.
3. Confirm response to physical friction/mass variants at zero RL residual; declare fixed train/holdout distributions.
4. Freeze a narrow speed/acceleration task using hardware sensor history, independent PI steering and reward, then one short learning pilot. Use fresh weights for changed inputs, or an explicitly audited input remapping with fresh critic/optimizer.
5. Once useful behavior is learned, create new focused studies with fixed physical evaluation and matching PI references. Keep independent training seeds and unseen terrain/dynamics for validation.

Read `analysis.json` for completed/pending measurements. Infrastructure or sensor interruptions are not counted as unsuccessful Optuna parameter trials. No automatic long training or tuning.

## Commands

Run from the workspace, after sourcing ROS and the virtual environment:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
# Prepare/recheck the isolated contract (does not start training)
python src/nino_rl/scripts/prepare_rough_foundations.py
# Reuse the complete low-friction mechanical screen
python src/nino_rl/scripts/prepare_rough_foundations.py --screen --profile low_friction
# Capture nominal PI on the same current contract if further screening is needed
python src/nino_rl/scripts/prepare_rough_foundations.py --screen --profile nominal
# Reuse all three completed flat interventions
python src/nino_rl/scripts/run_crossing_authority.py --run
# Hardware-only PI preflight; removes virtual lidars and does not train
python src/nino_rl/scripts/run_hardware_sensor_preflight.py --run
python src/nino_rl/scripts/verify_hardware_sensor_preflight.py
python src/nino_rl/scripts/analyze_foundation_gates.py
```

Rough and flat runners own their simulator/bridge processes on domains 78 and 79, respectively. Do not launch a second simulator in those partitions. No rebuild is required for these isolated snapshots. Changed inputs require a new output directory; old studies are never resumed with this contract.
