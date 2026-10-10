# Rough localization robustness correction

This report preserves the v11 localization diagnosis. Current S1 controller
work and v16 qualification are in [the S1 recovery report](ROUGH_S1_RECOVERY_2026-10-09.md).
The wrapper commands now target that new contract; they do not resume v11.

## Diagnosis

The v7 PPO pilot was stopped and saved at 6,326 steps. Its repeated
`navigation_invalid` endings occurred near X ≈ 8.1 m. The failing raw scan
at simulation stamp 46.5 s, pitch 0.260 rad and roll 0.031 rad contained
54 rear-wall-associated rays before the height filter. Their transformed hit
heights were roughly 2.72–3.09 m relative to the base; the 2.5 m upper limit
discarded them. Forward rays hit the floor, leaving no accepted X measurement.

Raising the height cutoff alone does not solve the general observability
problem: a tilted single 2D plane can intersect the ceiling instead of a wall.
IMU orientation can transform measured rays, but cannot create missing returns.

The model and all v7 results remain in `rl_runs/rough_wall_slip_v7`.

## New rough-only sensor contract

The isolated `rough_wall_cloud_v11` experiment adds a localization-only GPU
LiDAR at the existing laser pose. It uses 360 horizontal samples and 33 vertical
channels over ±0.65 rad, at 10 Hz, with 16 m range and 5 mm range noise.
Gazebo supports vertical laser channels and bridged PointCloud2 output; see
the [official GPU LiDAR example](https://github.com/gazebosim/ros_gz/blob/ros2/ros_gz_point_cloud/examples/gpu_lidar.sdf).

IMU orientation selects measured beams with absolute world vertical direction
at most 0.025. Known wall geometry, sensor extrinsics, association and robust
inlier checks then estimate XY independently of wheel displacement. Floor and
ceiling returns do not become XY fixes. Both axes must remain observed.

The existing `/scan`, terrain preview, policy observations and action meanings
are retained. No physical robot links, inertias, collision surfaces, map
geometry, arrival gates or reward weights change. The new sensor and launch
files live inside a hashed experiment snapshot; the flat study sources remain
unchanged. This is a sensor capability change, not a software-only upgrade for
the real robot: deployment requires equivalent multi-layer LiDAR coverage,
calibrated extrinsics and the correct physical sensor mass.

The estimator retains the 0.6 s accepted-fix age limit. Once a fix is too old,
the 0.25 s input-age check distinguishes stale input from fresh scans without
usable wall observations. It also retains bounded 0.30 m correction,
slip/stall detection, strict encoder/IMU gaps and
the 40 ms action-feedback limit. It is known-wall localization, not SLAM.

## Transport corrections

V8 failed during unscored startup because an IMU callback released encoder
samples across a discovery gap. V9 applies the existing bounded startup reset
to either callback. Gaps after a finite episode reset remain fatal.

V9 then failed before the crest with 42 ms assisted-pose lag. A one-sample
encoder subscription can drop the sample needed to bracket an IMU timestamp
during lockstep bursts. V10 retains a bounded 100-sample encoder queue, keeping
the actual measurement stamps. Neither the 40 ms limit nor physics time
accounting is relaxed. V8/V9 logs are preserved.

V10 completed all slow E1, normal E1 and normal N1 arrivals, but one of three
S1 seeds physically stalled. Wall localization continued throughout that stall;
the physical trace remained within 0.3 mm of its resting position. This was a
real contact/control failure, not missing localization. Its strict arrival
gate failed and no v10 PPO training was started.

Adjacent 10 Hz wall fixes contain mm noise that can defeat a stationary-motion
test based on one scan interval. V11 measures independent displacement over
0.5 s (minimum span 0.3 s) before its three-scan stall decision. Replaying the
saved stationary S1 observations gives mean speed 0.000020 m/s and 95th
percentile absolute speed 0.00431 m/s. Stall detection remains active for all
samples after warmup. [Saved replay measurements](rough_cloud_localization_2026-10-09/stall_replay.json).
This suppresses false encoder translation/velocity; it does not reverse or
physically free a grounded robot. Qualification is repeated under a fresh
v11 contract, and a physical stall still blocks training.

## Validation and training gate

Focused tests cover tilted multi-layer measurements, ceiling-only rejection,
wheel-spin suppression, stale input, queued encoder/IMU alignment and fatal
in-episode gaps. Live qualification requires:

- E1/N1/S1: three fixed seeds each at normal PI speed.
- E1: the same three seeds at 65% PI speed, including the failing crest.
- Every run must arrive inside the original physical 0.20 m goal circle and
  pass ordered route gates; mean estimated/physical disagreement must be ≤0.10 m.
- Saved configs and scenario seeds must match the frozen contract.
- The PI readiness gate also rejects more than 2 s of continuous commanded
  wheel travel with physical XY translation speed below 0.025 m/s, outside the final 0.5 m
  approach. This additional readiness check does not relabel physical arrival
  or change the environment's success criteria or reward weights.

These are pilot checks, not proof of generalization or RL superiority. Additional
sensor noise, dropped packets and unseen routes still need later held-out tests.
Do not resume the v7 optimizer into this sensor/estimator contract.

## Commands

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

python src/nino_rl/scripts/run_rough_localized.py prepare
python src/nino_rl/scripts/diagnose_rough_localized.py --slow-e1
python src/nino_rl/scripts/diagnose_rough_localized.py --full
python src/nino_rl/scripts/run_rough_localized.py gate
```

The diagnostic supervisor launches and closes its own domain-78 Gazebo instance.
Keep the independent flat study in domain 79. After all checks pass, use actor
initialization with a fresh critic/optimizer for the new E1 pilot:

```bash
python src/nino_rl/scripts/run_rough_localized.py curriculum \
  --device cuda --timesteps 20480 --block-steps 20480 \
  --checkpoint-every 10240 \
  --init-model rl_runs/rough_e1_imu_assisted_pilot/20261008-013943-771247/nino_ppo_final.zip
```

The wrapper refuses training without normal-speed and slow-crest qualification.
Further routes precede terrain randomization. Physical scoring stays independent
of localization throughout.

## Current results

V11 completed all 12 evaluations without geometric localization loss or a
timing-guard exception. Maximum motion-feedback lag was **0.022 s**, below the
unchanged 0.040 s limit. All 182 captured wall observations around
X=7.7–8.6 m produced bounded accepted fixes, with at least 55 X rays and 81 Y
rays. This is evidence of coverage at the tested crest, not arbitrary-map SLAM.

| Profile | Physical arrivals | Mean position disagreement | Time |
|---|---:|---:|---|
| E1 normal | 3/3 | 0.00177 m | 27.1 s each |
| E1 at 65% speed | 3/3 | 0.00139 m | 41.7–41.8 s |
| N1 normal | 3/3 | 0.00097 m | 24.2 s each |
| S1 normal | 2/3 | 0.00104 m | 26.8 s, 95.6 s, timeout at 98.5 s |

S1 seed 10005 eventually reached the physical goal after a prolonged stall;
seed 10008 timed out. During their stationary intervals, the 95th percentile
of absolute estimated speed was 0.00475/0.00443 m/s, versus wheel-driven
estimated speeds reaching roughly 0.30 m/s in v10. The longest continuous
commanded stall in v11 was **87.6 s**. Position continued to be observed; wheel
rotation did not create false goal progress.

The strict readiness gate is **not passed**, and no v11 PPO training was
started. The supervisor closed its rough simulator. The flat study and all
saved models/results were preserved. Next work is physical S1 stall recovery
in the controller, followed by matching PI qualification; another Optuna run
cannot substitute for this prerequisite.

**32 focused tests passed.** Detailed results, sources and paths are in the
[comparison report](rough_cloud_localization_2026-10-09/README.md).
