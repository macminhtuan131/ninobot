# Khảo sát mô tả governor — 18/10/2026

**Không áp dụng ngưỡng đề xuất và không kết luận H2 đạt/không đạt.**

Counts: `{"assigned": 16, "attempted": 16, "arrivals": 16, "failures": 0, "native_unknown": 0, "stopping_failures": 0, "metric_missing": {"post_slip": 0, "post_vibration": 0, "whole_slip": 0, "whole_vibration": 0, "native_slip": 0, "time": 0, "tracking": 0, "sequence_slip": 0, "sequence_vibration": 0, "grid_slip": 0, "shifted_slip": 0, "post_peak": 0, "whole_peak": 0, "post_slip_integral": 0, "post_distance": 0, "crossing_slip": 0, "crossing_vibration": 0}}`

## Hai block và aggregate

Benefit dương nghĩa là governor thấp hơn PI. Delta = governor − PI. CI là bootstrap percentile 95% theo cặp; N nhỏ, không bảo đảm power/coverage.

| Metric | Nhóm | PI | Governor | Delta [CI95] | Relative benefit [CI95] |
|---|---|---:|---:|---|---|
| post_slip (s/m) | 77500 | 0.0121189 | 0.0148029 | 0.00268405 [-0.000568812, 0.00593692] | -0.221477 [-0.625926, 0.0385565] |
| post_slip (s/m) | 77501 | 0.014162 | 0.0113122 | -0.0028498 [-0.00576214, 6.25449e-05] | 0.201229 [-0.00488427, 0.371305] |
| post_slip (s/m) | aggregate | 0.0131404 | 0.0130576 | -8.28735e-05 [-0.00242487, 0.00218293] | -0.0101243 [-0.242068, 0.156832] |
| post_vibration (m/s²) | 77500 | 3.86968 | 2.88969 | -0.979993 [-4.86385, 3.01868] | 0.253249 [-2.46018, 0.772295] |
| post_vibration (m/s²) | 77501 | 4.08618 | 3.33565 | -0.750527 [-2.65819, 1.48148] | 0.183675 [-0.499062, 0.471806] |
| post_vibration (m/s²) | aggregate | 3.97793 | 3.11267 | -0.86526 [-3.10418, 1.56492] | 0.218462 [-1.19468, 0.563247] |
| whole_slip (dimensionless) | 77500 | 0.0320877 | 0.0348198 | 0.00273208 [-0.00225495, 0.00830557] | -0.085144 [-0.294874, 0.0627379] |
| whole_slip (dimensionless) | 77501 | 0.0358639 | 0.0331428 | -0.00272115 [-0.00531002, -6.65353e-05] | 0.0758743 [0.00183596, 0.141642] |
| whole_slip (dimensionless) | aggregate | 0.0339758 | 0.0339813 | 5.46376e-06 [-0.00296627, 0.00323943] | -0.00463484 [-0.121904, 0.081467] |
| whole_vibration (m/s²) | 77500 | 2.11267 | 1.6082 | -0.504475 [-1.96216, 0.953208] | 0.238786 [-0.863512, 0.628601] |
| whole_vibration (m/s²) | 77501 | 2.14342 | 1.73389 | -0.409528 [-1.0395, 0.22044] | 0.191063 [-0.141061, 0.381592] |
| whole_vibration (m/s²) | aggregate | 2.12804 | 1.67104 | -0.457002 [-1.25462, 0.38406] | 0.214924 [-0.374954, 0.450312] |
| native_slip (dimensionless) | 77500 | 0.0244904 | 0.0326978 | 0.00820739 [-0.0027303, 0.017934] | -0.335126 [-0.931579, 0.0904023] |
| native_slip (dimensionless) | 77501 | 0.0228238 | 0.0270791 | 0.00425532 [-0.00443015, 0.015427] | -0.186442 [-1.02898, 0.168393] |
| native_slip (dimensionless) | aggregate | 0.0236571 | 0.0298885 | 0.00623135 [-0.00125969, 0.0136727] | -0.260784 [-0.770151, 0.0468925] |
| time (s) | 77500 | 16.6 | 16.75 | 0.15 [0.1, 0.2] | -0.00903614 [-0.0120482, -0.0060241] |
| time (s) | 77501 | 16.6 | 16.7 | 0.1 [0.1, 0.1] | -0.0060241 [-0.0060241, -0.0060241] |
| time (s) | aggregate | 16.6 | 16.725 | 0.125 [0.1, 0.15] | -0.00753012 [-0.00903614, -0.0060241] |
| tracking (m) | 77500 | 0.00388616 | 0.00406806 | 0.000181903 [-0.000625137, 0.000988944] | -0.046808 [-0.29979, 0.139741] |
| tracking (m) | 77501 | 0.00355224 | 0.00356524 | 1.29964e-05 [-0.000654917, 0.00068091] | -0.00365864 [-0.214036, 0.166935] |
| tracking (m) | aggregate | 0.0037192 | 0.00381665 | 9.74499e-05 [-0.000459608, 0.000620806] | -0.0252333 [-0.186903, 0.112646] |
| sequence_slip (s/m) | 77500 | 0.0223777 | 0.0261846 | 0.00380683 [-0.00330139, 0.0119151] | -0.170117 [-0.702168, 0.118927] |
| sequence_slip (s/m) | 77501 | 0.0274871 | 0.0237722 | -0.00371485 [-0.00771332, 0.00054775] | 0.135149 [-0.0196781, 0.257402] |
| sequence_slip (s/m) | aggregate | 0.0249324 | 0.0249784 | 4.59922e-05 [-0.00436781, 0.00481657] | -0.0174841 [-0.308689, 0.150657] |
| sequence_vibration (m/s²) | 77500 | 5.15433 | 3.44115 | -1.71318 [-6.54474, 3.11839] | 0.332376 [-1.78902, 0.768218] |
| sequence_vibration (m/s²) | 77501 | 5.48739 | 4.06708 | -1.42031 [-3.32108, 0.360202] | 0.258831 [-0.0719663, 0.455442] |
| sequence_vibration (m/s²) | aggregate | 5.32086 | 3.75412 | -1.56674 [-4.13892, 1.18982] | 0.295604 [-0.79929, 0.573388] |
| grid_slip (s/m) | 77500 | 0.0121332 | 0.0147692 | 0.00263597 [-0.000617058, 0.005889] | -0.217253 [-0.61285, 0.0420993] |
| grid_slip (s/m) | 77501 | 0.0143639 | 0.0114384 | -0.00292549 [-0.00658856, 0.000501716] | 0.20367 [-0.0391556, 0.418659] |
| grid_slip (s/m) | aggregate | 0.0132485 | 0.0131038 | -0.000144761 [-0.00274742, 0.00238978] | -0.00679134 [-0.250873, 0.173611] |
| shifted_slip (s/m) | 77500 | 0.0129905 | 0.0163091 | 0.0033186 [0.00103061, 0.00548641] | -0.255464 [-0.478441, -0.0603194] |
| shifted_slip (s/m) | 77501 | 0.0142336 | 0.0108246 | -0.00340892 [-0.00438699, -0.00163604] | 0.239498 [0.137257, 0.293562] |
| shifted_slip (s/m) | aggregate | 0.013612 | 0.0135669 | -4.51578e-05 [-0.00140676, 0.00137722] | -0.00798277 [-0.126576, 0.0953394] |
| post_peak (m/s²) | 77500 | 41.402 | 30.1923 | -11.2097 [-62.7579, 40.3384] | 0.270753 [-7.56139, 0.863261] |
| post_peak (m/s²) | 77501 | 39.0608 | 34.6141 | -4.44674 [-24.6049, 21.0683] | 0.113842 [-0.824887, 0.675848] |
| post_peak (m/s²) | aggregate | 40.2314 | 32.4032 | -7.82823 [-36.2587, 22.9609] | 0.192297 [-3.80336, 0.630928] |
| whole_peak (m/s²) | 77500 | 43.4574 | 30.5391 | -12.9183 [-62.0642, 36.2276] | 0.297264 [-3.83537, 0.847187] |
| whole_peak (m/s²) | 77501 | 42.1262 | 35.1162 | -7.01007 [-24.5059, 11.9215] | 0.166406 [-0.41647, 0.627075] |
| whole_peak (m/s²) | aggregate | 42.7918 | 32.8276 | -9.9642 [-36.8915, 17.9138] | 0.231835 [-1.8919, 0.619621] |
| post_slip_integral (s) | 77500 | 0.0139565 | 0.0162847 | 0.00232822 [-0.0013472, 0.00600364] | -0.16682 [-0.548884, 0.0793632] |
| post_slip_integral (s) | 77501 | 0.0162959 | 0.0126401 | -0.00365581 [-0.00694213, -0.000369488] | 0.224339 [0.025052, 0.389069] |
| post_slip_integral (s) | aggregate | 0.0151262 | 0.0144624 | -0.000663793 [-0.00331737, 0.00189376] | 0.0287596 [-0.190586, 0.185922] |
| post_distance (m) | 77500 | 1.15243 | 1.09999 | -0.0524438 [-0.0665566, -0.038331] | 0.045507 [0.033326, 0.0576405] |
| post_distance (m) | 77501 | 1.15119 | 1.11752 | -0.033665 [-0.035598, -0.0318835] | 0.0292437 [0.0277484, 0.0308489] |
| post_distance (m) | aggregate | 1.15181 | 1.10876 | -0.0430544 [-0.0502871, -0.0357964] | 0.0373754 [0.0311109, 0.04358] |
| crossing_slip (s/m) | 77500 | 0.0186355 | 0.0216884 | 0.00305289 [-0.00175778, 0.00786356] | -0.163821 [-0.53667, 0.0777142] |
| crossing_slip (s/m) | 77501 | 0.0216662 | 0.01688 | -0.00478619 [-0.00913667, -0.000435698] | 0.220906 [0.0221729, 0.385801] |
| crossing_slip (s/m) | aggregate | 0.0201509 | 0.0192842 | -0.00086665 [-0.00434322, 0.0025104] | 0.0285425 [-0.185486, 0.184185] |
| crossing_vibration (m/s²) | 77500 | 4.71981 | 3.42301 | -1.2968 [-6.08298, 3.5588] | 0.274758 [-2.54252, 0.782706] |
| crossing_vibration (m/s²) | 77501 | 4.99792 | 3.96908 | -1.02884 [-3.44851, 1.73144] | 0.205853 [-0.47866, 0.493147] |
| crossing_vibration (m/s²) | aggregate | 4.85887 | 3.69605 | -1.16282 [-3.93095, 1.83684] | 0.240305 [-1.22442, 0.581302] |

## Mọi attempt, failures và timing

| Attempt | Seed/lặp | Arm | Status | Arrival | Stop | Termination | Timing evidence |
|---:|---|---|---|---|---|---|---|
| 1 | 77501/1 | full | collected | True | True | success | PI arm must retain scale1 |
| 2 | 77501/1 | reactive | collected | True | True | success | measured_reduction_precedes_new_loaded_manifold |
| 3 | 77500/1 | reactive | collected | True | True | success | measured_reduction_precedes_new_loaded_manifold |
| 4 | 77500/1 | full | collected | True | True | success | PI arm must retain scale1 |
| 5 | 77501/2 | reactive | collected | True | True | success | measured_reduction_precedes_new_loaded_manifold |
| 6 | 77501/2 | full | collected | True | True | success | PI arm must retain scale1 |
| 7 | 77500/2 | full | collected | True | True | success | PI arm must retain scale1 |
| 8 | 77500/2 | reactive | collected | True | True | success | measured_reduction_precedes_new_loaded_manifold |
| 9 | 77500/3 | full | collected | True | True | success | PI arm must retain scale1 |
| 10 | 77500/3 | reactive | collected | True | True | success | measured_reduction_precedes_new_loaded_manifold |
| 11 | 77501/3 | reactive | collected | True | True | success | measured_reduction_precedes_new_loaded_manifold |
| 12 | 77501/3 | full | collected | True | True | success | PI arm must retain scale1 |
| 13 | 77500/4 | reactive | collected | True | True | success | measured_reduction_precedes_new_loaded_manifold |
| 14 | 77500/4 | full | collected | True | True | success | PI arm must retain scale1 |
| 15 | 77501/4 | full | collected | True | True | success | PI arm must retain scale1 |
| 16 | 77501/4 | reactive | collected | True | True | success | measured_reduction_precedes_new_loaded_manifold |

## Tám cặp (giữ cả dữ liệu thiếu)

| Seed/lặp | Post slip PI/Gov | Post rung PI/Gov | Time delta s | Tracking PI/Gov m |
|---|---|---|---|---|
| 77500/1 | 0.00927511 / 0.0142022 | 1.05492 / 6.39113 | 0.1 | 0.00259962 / 0.00336904 |
| 77500/2 | 0.0112436 / 0.0122655 | 1.30576 / 1.77728 | 0.2 | 0.00377626 / 0.00354137 |
| 77500/3 | 0.00969492 / 0.0166417 | 6.25476 / 2.32086 | 0.2 | 0.0051708 / 0.00415542 |
| 77500/4 | 0.0182618 / 0.0161023 | 6.86327 / 1.06948 | 0.1 | 0.00399796 / 0.00520643 |
| 77501/1 | 0.0142431 / 0.00994583 | 2.94207 / 5.48222 | 0.1 | 0.00295305 / 0.00372052 |
| 77501/2 | 0.0167942 / 0.00956714 | 3.04795 / 1.35344 | 0.1 | 0.004167 / 0.00377186 |
| 77501/3 | 0.0157234 / 0.0162075 | 8.82122 / 5.42872 | 0.1 | 0.0036794 / 0.00276471 |
| 77501/4 | 0.00988733 / 0.00952837 | 1.53347 / 1.07822 | 0.1 | 0.00340953 / 0.00400388 |

Sampling sensitivity: `{"77500": {"relative_benefits": {"post_slip": -0.22147716841787646, "grid_slip": -0.2172526904701273, "shifted_slip": -0.2554640322844999}, "sign_reversal": false}, "77501": {"relative_benefits": {"post_slip": 0.2012285745525474, "grid_slip": 0.2036700075707507, "shifted_slip": 0.23949848966314968}, "sign_reversal": false}, "aggregate": {"relative_benefits": {"post_slip": -0.010124296932664534, "grid_slip": -0.006791341449688293, "shifted_slip": -0.007982771310675096}, "sign_reversal": false}}`

Approach comparability và toàn bộ response snapshots nằm trong report.json; không lọc hoặc bù lượt không so sánh được.
Metric thiếu không thành 0. Aggregate cần đủ tám cặp; không dùng mean của các lượt thành công để thay thế.
Một hình học gờ cứng 6 mm, không phải terrain generalization, same-snapshot branching hay sim-to-real.
Không tự mở thêm simulation, tuning, predictor hoặc PPO từ báo cáo này.
