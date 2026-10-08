# Rough sensor audit — 2026-10-08

## Sources and scope

- Bag: `rl_runs/rough_odometry_bags/20261008-002701` (all seven requested topics).
- Evaluation: `rl_runs/rough_odometry_timestamp_check/20261008-002720-659085`.
- Fixed route E1, seed 10000, PI speed scale 0.55, original expanded terrain.
- One completed episode: physical arrival in **62.90 simulated seconds**.
- The bag contains 1,429.842 simulated seconds. Analysis selects the recorded
  episode, not the long periods before/after it. The common sensor interval
  is approximately 62.80 s.

Bag dates near January 1970 are expected with `--use-sim-time`: the displayed
timestamp is simulated clock time, not the wall-clock recording date.

## Recorded estimates

| Quantity | Result |
|---|---:|
| Estimated goal distance at arrival | 0.0992 m |
| Physical goal distance at arrival | 0.1997 m |
| Estimated versus physical position RMS | 0.1958 m |
| Maximum estimated versus physical position error | 0.3164 m |
| Final estimated versus physical position error | 0.1328 m |
| Estimated versus physical heading RMS | 5.970 degrees |
| Maximum estimated versus physical heading error | 11.690 degrees |
| Encoder-position versus published odometry heading change, maximum | 0.0557 degrees |

Encoder positions reconstruct published wheel-odometry heading accurately.
This argues against a large heading-integration error in this episode; the
wheel-derived heading itself does not match physical body heading. Slip,
nonplanar travel and imperfect differential-drive assumptions remain relevant
possibilities. The measurement does not establish the exact cause of each
earlier failed episode.

## Timestamp checks

No backwards header timestamps occurred in the selected sensor window.
IMU, odometry and ground-truth samples had maximum header gaps of 20 ms.
Joint-state maximum positive gap was 6 ms; there were 619 duplicate joint
header timestamps. The recorder's ROS timestamp differed from message headers
by at most approximately 2 ms. Recorder timing is not controller callback
latency, and the recording does not show exactly which joint packet each
control callback consumed.

## Offline reconstruction

Using the recorded encoder position increments, reconstruct horizontal motion
with IMU relative heading; optionally project encoder travel by the cosine of
IMU pitch. All comparisons use overlapping simulation timestamps. Encoder
positions are continuous values and are not wrapped between revolutions.

| Pose calculation | Position RMS versus physical pose | Final position error |
|---|---:|---:|
| Published wheel odometry | 0.1958 m | 0.1328 m |
| Encoders + IMU heading | 0.0603 m | 0.0815 m |
| Encoders + IMU heading + pitch projection | 0.0134 m | 0.0166 m |

These are passive reconstructions of already-executed motion. No controller,
navigation pose source, training contract or arrival scoring was changed.
The figures do not measure closed-loop success after an estimator change.

The current simulated IMU orientation is almost identical to physical ground
truth. Its URDF sensor declares noise for angular velocity and acceleration,
but this run's orientation error was effectively zero. Hardware orientation
has uncertainty and drift; an estimator pilot must also be checked with noisy
and delayed IMU information before making transfer claims.

## Next implementation

Introduce an opt-in IMU-assisted rough odometry profile: use timestamped
encoder increments, relative IMU heading and horizontal pitch projection.
Retain the raw wheel odometry for comparison, preserve the physical 0.20 m
arrival criterion, and keep the active flat training profile unchanged.
Validate the estimator with PI before initializing another rough RL run.
Position correction from an independent localization source may still be
needed when wheel distance itself drifts.

## Reproduce

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate

python src/nino_rl/scripts/analyze_rough_sensor_bag.py \
  --bag rl_runs/rough_odometry_bags/20261008-002701 \
  --run rl_runs/rough_odometry_timestamp_check/20261008-002720-659085 \
  --output docs/rough_sensor_audit_2026-10-08
```

Full statistics: `sensor_audit.json`. Timestamp-aligned measurements:
`aligned_sensor_comparison.csv`. No bag replay or new simulation run is needed
to reproduce the analysis.
