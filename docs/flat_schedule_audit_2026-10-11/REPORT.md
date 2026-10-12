# Flat saved braking/recovery audit

Five matched reset seeds; saved data only. Regions use physical X for offline accounting.

| Region | Full PI vibration energy | Schedule vibration energy | Full PI slip energy | Schedule slip energy |
|---|---:|---:|---:|---:|
| before_braking | 87.470804 | 153.064712 | 0.204343 | 0.251212 |
| braking | 0.000156 | 0.000145 | 0.000005 | 0.000004 |
| crossing | 87.005820 | 32.104712 | 0.450430 | 0.431406 |
| recovery | 0.000224 | 0.000248 | 0.000005 | 0.000003 |
| remaining | 0.000842 | 0.000827 | 0.000135 | 0.000110 |

Full and schedule command scales are 1 before intervention. Large pre-intervention differences cannot be attributed to second-cable braking; same reset seeds do not guarantee identical contacts.

Recovery is not a large source of slip or vibration here. Do not increase a recovery/slip penalty based on these traces.

Selected one small schedule correction: recovery X 4.60 → 4.55 m. Peak acceleration in the removed tail is below 0.036 m/s² in every seed. Keep all gates; do not claim this small correction solves the whole-run quality loss.

If the correction qualifies, the next learning contract is explicitly a known-course reference using estimated pose and mapped cable coordinates, not downward LiDAR or unknown-terrain anticipation.
