# Rough and flat readiness workflows — 11 October 2026

## Authorized execution

The user requested revision-49 rough learning and an evidence-selected flat schedule
correction, followed by conditional pilots/studies. These runners preserve previous
models, frozen packages, study databases, timing checks and physical scoring.

### Rough

Runner: `src/nino_rl/scripts/run_rough_holding_pilot.py`.
Output: `rl_runs/rough_holding_reference_candidate_v1`.

- 20,480 requested transitions, seed 17000, original fresh actor initialization,
  fresh critic/optimizer, no trained-model or optimizer resume.
- Revision 49 adds only the cue-holding speed-reference cost prepared previously.
  Terrain, hardware observation history, estimator, controller, command ramp and
  physical gates stay fixed.
- Prior untrained exploration/PI checks are reused only with their frozen hashes:
  the actor and executable control are identical. Their old reward returns are not
  revision-49 learning evidence. All later comparisons use the new contract.
- PPO/full-speed PI/time-matched PI on 17100–17104; unchanged physical, response,
  tracking, time and window/global quality acceptance.
- If it fails, record exposure from actual training captures, including sustained
  slowdown/recovery counts and holding/quiet scales. Do not automatically edit rewards.
- If it passes, `--tune-if-pass --trials 6` creates **a separate study** at
  `rl_runs/rough_holding_focused_optuna_v1`, never importing old incompatible scores.

The rough study uses the same fresh actor and seed 17000 on every trial, fresh
critic/optimizer, 20,480 steps, fixed map and evaluation seeds. It searches LR,
entropy, epochs, clip range, gSDE refresh interval, and time/velocity/vibration/slip
weights. Velocity weight also affects the holding-reference cost. Action meanings,
speed ramp, physical thresholds and reward normalization sigmas are fixed.

Changing exploration refresh causes a new stochastic exposure screen; original
exposure outcomes are not reused for that setting. The fixed evaluation objective
uses physical arrival feasibility, completion time, physical tracking and window
vibration/slip energy ratios to matched PI. It never uses the varying training
return as the trial score. Qualified candidates alone are exported.

Six trials are an initial search, not proof of convergence. Independent training
seeds, new physical profiles and reserved terrain/routes remain final validation
work after selecting candidates; do not use these five familiar reset scenarios as
a generalization claim.

### Flat audit and one correction

Audit: [saved-trace decomposition](flat_schedule_audit_2026-10-11/REPORT.md).
Runner: `src/nino_rl/scripts/run_flat_quiet_tail_workflow.py`.
Output: `rl_runs/flat_quiet_tail_correction_v2`.

The saved schedule's extra vibration is largely **before** second-cable braking:
mean vibration integral 153.06 versus full PI's 87.47 in that region, while the
second crossing improves from 87.01 to 32.10. Both command scales are 1 before
the intervention. Matching reset seeds did not give identical contact trajectories;
that difference is not evidence that later braking caused earlier vibration.
Recovery after x=4.80 contributes only about 0.00025 vibration integral and
0.000003 slip integral. A larger recovery/slip penalty has no support here.

All five saved schedules are quiet from x=4.55–4.60, with peak vertical acceleration
below 0.036 m/s². The sole tested schedule change is recovery at **4.55 instead of
4.60 m**. Keep braking start 3.90, target .70, ramp .4/s and the first cable unchanged.
This may save time; it does not guarantee whole-course improvement or solve
pre-intervention variation.

Full PI is reused from the unchanged five-seed source with explicit file hashes
and provenance. Corrected schedule and its time-matched PI are newly evaluated on
65000–65004. Keep original gates: all arrivals, mean time ≤18.5 s, physical RMSE
≤1.05×full PI, ≥10% whole-course vibration or slip gain without regression in the
other, and preserved matched crossing-window and duration criteria.

### Conditional flat learning

Only after the corrected schedule passes, prepare
`rl_runs/flat_known_course_pilot_v1`, **revision 50**:

- Full compatible two-action actor parameters copied from the declared saved flat
  actor; fresh critic, optimizer and counter; seed 42; 20,480 steps.
- Existing speed/yaw reference action meanings; bounded .4/s policy speed ramp,
  no motor torque residual. PPO freely selects actions; the schedule never
  overrides a PPO action.
- Replace the four downward-preview input slots with signed mapped cable distance,
  mapped target reference, zero and valid flag. All use estimated pose. No ground
  truth/terrain height enters these new inputs. Five 60-value frames remain 300 values.
- This is explicitly **known-course map-conditioned learning**. It requires a
  mapped cable coordinate and adequate estimated localization. It does not claim
  to anticipate unknown cables or potholes from horizontal LiDAR.
- Observation shape and action meanings match the source, but the four input
  semantics change. Actor transfer is initialization, not behavioral equivalence.
- Existing reward weights remain, plus one executed-speed reference cost. Learner
  reward scale remains .01; raw episode metrics remain available.
- Require new-contract full/time-matched PI comparisons; no original benchmark
  results are silently relabeled as this new controller contract.
- Reports label the learned PPO row explicitly. Preserved physical/time/tracking/
  quality gates control conditional tuning.

If the pilot qualifies, create `rl_runs/flat_known_course_focused_optuna_v1`, up to
six trials with the same source actor/fresh critic/optimizer, seed 42, 20,480 steps
and five evaluation scenarios. Search LR, entropy, epochs, clip range, time/impact/
slip weights and map-reference weight. Its fixed objective uses physical arrival,
time, physical tracking and vibration/slip ratios, not changing training returns.
No prior study scores are imported. Best qualified candidates still need independent
validation.

Offline checks compiled the actual conditional source and exercised real PPO actor
transfer: actor parameters copy exactly, separate critic parameters remain fresh,
optimizer/counter empty, revision 50 rejects the old optimizer resume. These checks
do not replace live startup or physical acceptance.

## Started processes and serialization

Rough was started with `--run --tune-if-pass --trials 6`. Flat was started with
`--run --wait-for-rough --tune-if-pass`. Flat waits on the rough workflow lock, so
the two Gazebo servers do not compete. If rough passes, its bounded six-trial study
also completes before flat obtains the lock. If rough fails, flat can proceed after
the pilot/audit releases it. An infrastructure interruption preserves logs/models
and stops that workflow; it is not a low-quality-policy score.

Status and logs:

```bash
cd ~/ninorobot
cat rl_runs/rough_holding_reference_candidate_v1/status.json
cat rl_runs/flat_quiet_tail_correction_v2/status.json
tail -f rl_runs/rough_holding_reference_candidate_v1/train/train.log
```

Flat's own log:

```bash
cd ~/ninorobot
tail -f rl_runs/flat_quiet_tail_correction_v2/supervisor.log
```

Do not launch duplicate workers while these locks are owned. Re-execution uses
completed matching batches, but deliberately refuses an unfinished training
checkpoint until its interruption is reviewed.

For a stopped workflow with no active worker:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78 GZ_PARTITION=nino_rough_78
python src/nino_rl/scripts/run_rough_holding_pilot.py --run --tune-if-pass --trials 6
```

Flat, in its separate terminal:

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79 GZ_PARTITION=nino_flat_79
python src/nino_rl/scripts/run_flat_quiet_tail_workflow.py --run --wait-for-rough --tune-if-pass
```
