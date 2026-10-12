# Second-cable response after targeted slip reward

Saved data only. Each column averages the same 24 seeds; cable window x=4.45 +/-0.35m.

| Second-cable metric | Previous PPO | Targeted PPO | PI |
|---|---:|---:|---:|
| action_windows | 25.208333 | 24.833333 | 24.000000 |
| window_seconds | 2.520833 | 2.483333 | 2.400000 |
| mean_speed_scale | 0.980667 | 0.979726 | 1.000000 |
| physical_speed_m_s | 0.284965 | 0.281669 | 0.295715 |
| absolute_physical_yaw_rad_s | 0.078658 | 0.081912 | 0.074118 |
| crossing_rms_slip | 0.425334 | 0.436858 | 0.406231 |
| requested_linear_m_s | 0.400000 | 0.400000 | 0.400000 |
| executed_linear_m_s | 0.392263 | 0.391888 | 0.400000 |
| left_target_rad_s | 6.238980 | 6.225202 | 6.357433 |
| right_target_rad_s | 6.313400 | 6.315233 | 6.442567 |
| left_actual_rad_s | 5.300078 | 5.292608 | 5.493546 |
| right_actual_rad_s | 5.339763 | 5.340472 | 5.492227 |
| absolute_requested_yaw_rad_s | 0.111528 | 0.126753 | 0.103114 |
| common_applied_torque_nm | 0.549214 | 0.548001 | 0.528081 |
| absolute_differential_torque_nm | 0.112212 | 0.119601 | 0.111270 |
| wheel_tracking_rmse_rad_s | 2.616994 | 2.655418 | 2.635718 |
| limiter_flag_fraction | 0.490079 | 0.497099 | 0.495613 |

| Phase mean-square slip contribution | Previous PPO | Targeted PPO | PI |
|---|---:|---:|---:|
| start | 0.00024051 | 0.00023709 | 0.00020251 |
| cable1 | 0.01345246 | 0.01431938 | 0.01072981 |
| cable2 | 0.02762543 | 0.02713030 | 0.02385975 |
| approach | 0.00000512 | 0.00000452 | 0.00000463 |
| remaining | 0.00000615 | 0.00000452 | 0.00000524 |

Paired differences and 95% scenario bootstrap intervals are in analysis.json.

Scenario bootstrap uses one targeted training seed; command/response associations do not establish causality. Drive pose interpolation is limited to the recorded control-time range; limiter flags do not identify the limiting mechanism.

Do not increase slip reward again based on these data alone; examine bounded crossing acceleration/reference response before another pilot.
