# Targeted flat and rough corrections

## Latest execution and revised N1 candidate

The first stop-and-align N1 screen **failed 0/3** at 16.4 simulated seconds
with `recovery_exhausted`. The existing 8-second alignment timeout was reached
on the tilted corner. Its models, logs and physical scores are preserved at
`rl_runs/course_targeted_corrections_v1/rough`; no limits were relaxed.

The flat targeted pilot has started. A separate **v18 continuous N1 candidate**
is prepared and scheduled after the flat worker exits. It changes N1 lookahead
from **0.45 m to 0.20 m** and enables the existing curvature-preserving speed
limiter for N1 independently of stop-alignment. N1 keeps moving through the
corner; **S1 retains stop-alignment**, and E1/S1 pursuit commands are verified
unchanged. Geometry, yaw limits, estimator, timing checks and physical scoring
remain fixed. These are candidate changes, not yet physically qualified.

The v18 workflow screens N1 on 13000–13002. Only if the screen passes does it
confirm N1/E1/S1 on 13100–13119. No rough RL or curriculum starts automatically.
Live output: `rl_runs/rough_n1_continuous_v18/status.json`, `supervisor.log`,
`route_pi_gate.json` and `REPORT.md`.

```bash
# Start/recover only when no v18 worker owns its lock.
python src/nino_rl/scripts/run_rough_n1_continuous_validation.py --run
```

The initial S1-profile extension below records the first attempted repair.
The v18 candidate supersedes it for N1; its failed evidence remains available.

## Trace evidence

Flat seed-43 PPO and matching PI both achieved 24/24 physical arrivals. Around
the second cable, within **±0.35 m of physical x = 4.45 m**, saved action and
drive traces show:

| Window statistic | PPO | PI |
|---|---:|---:|
| Mean policy speed scale | 0.9807 | 1.0000 |
| Mean physical forward speed | 0.2821 m/s | 0.2950 m/s |
| Mean absolute yaw reference | 0.1140 rad/s | 0.1209 rad/s |
| Window RMS wheel slip | 0.4451 | 0.4204 |
| Mean applied common wheel torque | 0.5590 Nm | 0.5267 Nm |
| Mean absolute differential wheel torque | 0.1115 Nm | 0.1139 Nm |
| Fraction of drive samples flagged limited | 0.5406 | 0.5299 |

Action-window slip samples exactly reconstruct the saved per-episode slip RMS.
The window summaries pool samples across 24 episodes; they are associations,
not causal estimates or independent training-seed uncertainty. Drive samples
are located by interpolating physical x from the action trace at simulation
timestamps. Torque limiter flags do not identify which limiting mechanism fired.

The extra slip is associated with higher common effort and slower crossing,
not increased yaw or differential effort in this aggregate. This supports
testing a slip reward change before changing steering or the motor PI loop.

Rough N1 has repeated outward corner overshoot: physical **x = 2.828–2.835 m**
after the intended **x = 2.5 m** northward turn, at about **10.0–10.1 s**. Pose
estimation agrees closely. Inspection of the frozen v16 controller shows the
bounded stop-and-align and curvature-preserving speed limit enabled for **S1
only**, while N1 still uses the earlier pursuit behaviour.

## Flat pilot: one reward weight changes

Configuration: `src/nino_rl/config/combined_flat_slip_targeted_pilot.yaml`.

- Slip weight changes **0.2120538882 → 0.3180808324**, a 50% increase.
- Same original actor as the completed seed-43 reference, training seed **43**,
  fresh critic/optimizer and timestep zero, exactly **20,480 steps**.
- Preserve reward formula, all other weights, learner scale **0.01**, PPO
  settings, motor controller, estimator, observations, actions and two-cable map.
- New revision-**40** learner contract; incompatible optimizer resume rejected.
- PPO and matching full-speed PI evaluation on **64000–64023**, with traces.
- Same fixed evaluation objective and gates: 24/24 physical arrivals, mean time
  ≤18.5 s, physical RMSE ≤1.05× PI, and ≥10% lower vibration or slip with no
  regression in the other.
- Compare with the completed same-training-seed PPO reference. Different reward
  returns are not directly comparable. One new pilot does not establish seed
  robustness, and qualification does not automatically start Optuna or long training.

Output: `rl_runs/course_targeted_corrections_v1/flat`.

## Rough repair: enable the existing corner profile for N1

Override: `src/nino_rl/config/rough_n1_alignment_override.yaml`.

Add N1 to the existing `stop_align_route_ids` while retaining S1. The frozen
stop-and-align controller approaches the drawn vertex, then rotates toward
the outgoing segment with bounded speed/yaw and an alignment timeout. This
also enables N1's existing curvature-preserving speed limit. No controller
source rewrite, route redraw, estimator change, mesh modification or physical
scoring relaxation is made.

First screen N1 on **13000–13002**. If it passes, confirm N1, E1 and S1 separately
on **13100–13119** with independent physical pose, ordered gates, ≤5 cm mean
physical path RMSE, ≤10 cm mean pose disagreement in every episode, zero
rollovers and ≤2 s longest commanded physical stall. Failed screening holds
rough progression; flat can still run afterward.

This is a new controller contract, not an observation in the old Optuna study.
No rough RL updates occur during validation. Passing PI is a prerequisite to
future actor-initialized curriculum with a fresh critic/optimizer, not proof of
an improved RL policy.

Output: `rl_runs/course_targeted_corrections_v1/rough`.

## Execution

The supervisor runs **rough validation first, then the flat pilot and its two
evaluations**, with separately owned Gazebo sessions. Old models, studies and
frozen package snapshots are preserved. Completed evaluations are reusable;
an interrupted flat training checkpoint requires review before continuation.

```bash
cd ~/ninorobot
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash

# Prepare only; no Gazebo or training starts.
python src/nino_rl/scripts/run_course_targeted_corrections.py

# Start/recover the bounded workflow when no worker owns its lock.
python src/nino_rl/scripts/run_course_targeted_corrections.py --run
```

Once started, inspect `status.json` and `supervisor.log` in the parent output,
and each course's `status.json` and `REPORT.md`. Do not duplicate a running worker.
