# Flat timing pilot: final evaluation, 2026-10-08

Final actor: `rl_runs/flat_speed_yaw_timing_pilot/20261007-205724-376054/nino_ppo_final.zip`
(50,401 saved steps after interruption/resume).
Evaluation: `rl_runs/flat_timing_final_eval/20261008-030012-859420/summary.json`.
All 24 episodes completed on seeds 61000–61023, phase 1, flat stage 2.
Benchmark identity and wheel-odometry pose source match the existing comparisons.

| Metric | New timing PPO | Previous PPO | Fast PI | Slow PI (0.78) |
|---|---:|---:|---:|---:|
| Physical arrivals | 20/24 | 22/24 | 22/24 | 23/24 |
| Arrivals within 22 s | 1/24 | 0/24 | 21/24 | 0/24 |
| Mean successful completion time | 23.77 s | 27.23 s | 19.00 s | 27.63 s |
| Physical path RMSE, all episodes | 0.0464 m | 0.0503 m | 0.0366 m | 0.0417 m |
| Vertical acceleration RMS, all episodes | 1.8646 m/s² | 1.4453 m/s² | 2.3928 m/s² | 1.6857 m/s² |
| Slip RMS, all episodes | 0.1647 | 0.1531 | 0.1793 | 0.1657 |

The timing reward pilot improved speed relative to the previous PPO but lost
two physical arrivals and increased vibration and slip. It does not meet the
arrival or on-time gates against fast PI. It meets the predefined PI-plus-1-cm
path RMSE, 20% vibration reduction, and slow-PI slip gates. Three of five
engineering gates pass; the pilot is not qualified for course progression.
These reused validation seeds and asynchronous simulations do not establish
statistical significance or unseen-scenario generalization.

## Failed episodes and existing traces

All four failures reached the 30 s deadline.

| Seed | Final estimated goal distance | Physical goal distance | Final drive request / observed behavior |
|---|---:|---:|---|
| 61000 | 0.2446 m | 0.3155 m | Forward request 0.06 m/s; physical lateral offset +0.3135 m, past goal x |
| 61001 | 0.0145 m | 0.2213 m | Fresh forward request zero; physical speed zero |
| 61010 | 0.2983 m | 0.3284 m | Forward request 0.06 m/s; physical lateral offset −0.3168 m, past goal x |
| 61015 | 0.0136 m | 0.2084 m | Fresh forward request zero; physical speed zero |

Seeds 61001 and 61015 show premature estimated stopping outside the independent
0.20 m physical arrival radius. Seeds 61000 and 61010 show approach drift and
overshoot with small executed yaw requests; the traces alone do not prove
whether estimation, steering design, or policy outputs dominate those failures.

## Next work

1. Preserve both final PPO actors and the fast/slow PI reference results.
2. Correct and validate flat estimated arrival and heading behavior using the
   four saved control/drive traces. Keep independent physical scoring unchanged.
3. Check an optional encoder/IMU flat estimator with PI before using it for RL;
   IMU heading assistance cannot remove longitudinal wheel-slip error by itself.
4. With a validated estimator/arrival profile, initialize a short new-contract
   pilot from the timing actor, using fresh critic/optimizer when required.
5. Repeat the matching PI comparison before increasing cable count or starting
   a long run. Use reserved scenarios and independent training seeds for final
   claims after the validation gates pass.

No new flat training or simulator was launched during this analysis.
