# Completed specialist checks and next work — 2026-10-08

The final flat evaluation was saved under
`rl_runs/flat_feedback_final_eval~/20261008-093659-281734` (literal trailing
tilde in its parent directory). It is complete, 24 matching seeds, with the
10,240-step corrected actor. Strict comparison against corrected PI is saved
in `flat_vs_corrected_pi.json`.

| Flat metric | Corrected PPO | Corrected PI |
|---|---:|---:|
| Physical arrivals | 24/24 | 24/24 |
| Arrivals within 22 s | 14/24 | 24/24 |
| Mean completion time | 22.179 s | 17.638 s |
| Physical path RMSE | 0.06004 m | 0.03772 m |
| Vertical acceleration RMS | 1.5607 m/s² | 3.2940 m/s² |
| Wheel slip RMS | 0.19575 | 0.18464 |

Arrival is reliable on this suite and vibration is substantially reduced.
Timing, tracking and slip gates are not all met. The controller is not yet
qualified for a third cable. Mean speed scale is 0.906; mean absolute learned
yaw residual is only 0.00104 rad/s (maximum 0.00612 rad/s).

### Flat existing-trace finding

Across samples within 1 m of the physical goal where the executed yaw command
magnitude exceeds 0.05 rad/s, PPO traces have mean absolute executed yaw
0.3944 rad/s versus physical yaw 0.0401 rad/s; mean absolute yaw tracking error
is 0.3543 rad/s. The matching PI values are 0.2456, 0.0557, and 0.1899 rad/s.
Mean per-wheel target error is 0.9613 rad/s for PPO and 0.5225 rad/s for PI.
These pooled descriptive samples differ in speed/scenario exposure; they do
not prove a specific cause.

`effort_drive.py` continuously bleeds both PI integrals whenever filtered
speed scale is below 1. This can prevent integral effort overcoming persistent
wheel error even at a steady reduced reference. The saved traces justify
investigating scaled-reference wheel PI tracking before another reward change
or a long PPO run. Do not conclude that speed/yaw scaling alone is the cause:
equal ideal scaling preserves commanded curvature, and contact dynamics and
PI tracking also affect actual steering.

Next flat work: implement an optional, bounded PI integral/anti-windup profile
that preserves steady-state tracking at reduced references while retaining
stop/watchdog reset and effort limits. Validate PI at normal and PPO-like
speed, then use a short new-contract actor-initialized PPO pilot. Keep the
two-cable stage and physical goal radius. Learned superiority still requires
matched-speed and reserved-scenario comparisons.

## Rough current-actor torque ablation completed

`rl_runs/rough_imu_final_speed_only/20261008-093724-119215` completed all 20
matching seeds. Comparisons: `rough_full_vs_speed_only.json` and
`rough_full_vs_slow_pi.json`.

| Rough metric | Full PPO | PPO speed only | Slower PI (0.70) |
|---|---:|---:|---:|
| Physical arrivals | 20/20 | 20/20 | 20/20 |
| Mean time | 42.425 s | 46.040 s | 43.700 s |
| Physical path RMSE | 0.03135 m | 0.03013 m | 0.02919 m |
| Vertical acceleration RMS | 1.0699 m/s² | 1.0059 m/s² | 1.0267 m/s² |
| Slip RMS | 0.03225 | 0.03660 | 0.03282 |

Torque corrections are not clearly harmful here: full PPO is faster with less
slip than the speed-only deployment, at the cost of slightly higher vibration
and path error. The ablation also changes action history and subsequent speed
decisions; it is not a comparison against a separately trained speed-only actor.
Slower PI remains competitive, so a general learned advantage is unproven.

Next rough work: retain the current three-action interface and move to fixed
E1/N1/S1 route coverage with E1 replay. Validate route PI before training;
initialize the preserved final actor into a new route contract with fresh
critic/optimizer. Score each route independently, preserving physical arrival
and ordered gates. Introduce terrain randomization only after those routes
qualify. No long E1-only run is justified by this simple fixed-route suite.

No new training or evaluation was started during this review. Both saved
specialists remain available. Current results use one training seed and reused
validation scenarios, not independent-seed or unseen-layout evidence.
