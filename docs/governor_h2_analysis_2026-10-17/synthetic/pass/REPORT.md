# H2: Đạt

Nguồn: **synthetic**. Analyzer chạy **0 simulation episodes**.

**DỮ LIỆU TỔNG HỢP — không phải kết quả robot, chấp nhận tiêu chí hoặc cấp ngân sách.**

Assigned: 16; attempted: 16; physical failures: 0; stop failures: 0; native unknown: 0.

## Gates

| Gate | Kết luận |
|---|---|
| complete_16 | Đạt |
| physical_arrival_and_stop | Đạt |
| measurement_and_provenance | Đạt |
| required_metrics_present | Đạt |
| approach_comparable | Đạt |
| executed_intervention_before_next_contact | Đạt |
| worthwhile_primary_benefit | Đạt |
| secondary_and_whole_route_no_worsening | Đạt |
| complete_contact_sequence_same_direction | Đạt |
| existing_time_tracking_caps | Đạt |
| application_added_time | Đạt |
| primary_sampling_direction_stable | Đạt |

## Metric và bất định

Delta = governor − PI; benefit >0 là giảm metric, chỉ có lợi theo ngữ cảnh của metric. Không lấy benefit thời gian/tracking làm objective mới.

| Metric | Block | PI mean | Governor mean | Delta | CI95 delta | Benefit | CI95 benefit |
|---|---|---:|---:|---:|---|---:|---|
| post_slip (s/m) | 77500 | 10.25 | 8.2 | -2.05 | [-2.3, -1.75] | 0.2 | [0.2, 0.2] |
| post_slip (s/m) | 77501 | 10.25 | 8.2 | -2.05 | [-2.3, -1.75] | 0.2 | [0.2, 0.2] |
| post_slip (s/m) | aggregate | 10.25 | 8.2 | -2.05 | [-2.25, -1.825] | 0.2 | [0.2, 0.2] |
| post_vibration (m/s²) | 77500 | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |
| post_vibration (m/s²) | 77501 | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |
| post_vibration (m/s²) | aggregate | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |
| whole_slip (dimensionless) | 77500 | 0.02 | 0.019 | -0.001 | [-0.001, -0.001] | 0.05 | [0.05, 0.05] |
| whole_slip (dimensionless) | 77501 | 0.02 | 0.019 | -0.001 | [-0.001, -0.001] | 0.05 | [0.05, 0.05] |
| whole_slip (dimensionless) | aggregate | 0.02 | 0.019 | -0.001 | [-0.001, -0.001] | 0.05 | [0.05, 0.05] |
| whole_vibration (m/s²) | 77500 | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |
| whole_vibration (m/s²) | 77501 | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |
| whole_vibration (m/s²) | aggregate | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |
| time (s) | 77500 | 16.025 | 16.225 | 0.2 | [0.2, 0.2] | -0.0124805 | [-0.0124883, -0.0124727] |
| time (s) | 77501 | 16.025 | 16.225 | 0.2 | [0.2, 0.2] | -0.0124805 | [-0.0124883, -0.0124727] |
| time (s) | aggregate | 16.025 | 16.225 | 0.2 | [0.2, 0.2] | -0.0124805 | [-0.0124863, -0.0124747] |
| tracking (m) | 77500 | 0.005 | 0.005 | 0 | [0, 0] | 0 | [0, 0] |
| tracking (m) | 77501 | 0.005 | 0.005 | 0 | [0, 0] | 0 | [0, 0] |
| tracking (m) | aggregate | 0.005 | 0.005 | 0 | [0, 0] | 0 | [0, 0] |
| sequence_slip (s/m) | 77500 | 10.25 | 8.2 | -2.05 | [-2.3, -1.75] | 0.2 | [0.2, 0.2] |
| sequence_slip (s/m) | 77501 | 10.25 | 8.2 | -2.05 | [-2.3, -1.75] | 0.2 | [0.2, 0.2] |
| sequence_slip (s/m) | aggregate | 10.25 | 8.2 | -2.05 | [-2.25, -1.825] | 0.2 | [0.2, 0.2] |
| sequence_vibration (m/s²) | 77500 | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |
| sequence_vibration (m/s²) | 77501 | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |
| sequence_vibration (m/s²) | aggregate | 2 | 1.9 | -0.1 | [-0.1, -0.1] | 0.05 | [0.05, 0.05] |

Benefit được ghi theo fraction (0.1 = 10%). Khoảng bootstrap n=4 cặp/block không bảo đảm coverage danh nghĩa hoặc đại diện quần thể địa hình.

## Tám cặp đã phân công

| Pair | PI attempt | Governor attempt | Delta slip²/m | Delta time (s) |
|---|---:|---:|---:|---:|
| seed_77500_repeat_1 | 4 | 3 | -2 | 0.2 |
| seed_77500_repeat_2 | 7 | 8 | -2.4 | 0.2 |
| seed_77500_repeat_3 | 9 | 10 | -1.6 | 0.2 |
| seed_77500_repeat_4 | 14 | 13 | -2.2 | 0.2 |
| seed_77501_repeat_1 | 1 | 2 | -2 | 0.2 |
| seed_77501_repeat_2 | 6 | 5 | -2.4 | 0.2 |
| seed_77501_repeat_3 | 12 | 11 | -1.6 | 0.2 |
| seed_77501_repeat_4 | 15 | 16 | -2.2 | 0.2 |

## Giới hạn / quyết định

Review separate bounded classical tuning budget

Không zero-impute missing/censored, không chọn subset success, không gộp seed cũ, không tự chạy thêm hoặc mở Optuna/PPO/predictor.

Một gate point-estimate không đạt không tự chứng minh tác hại có ý nghĩa thống kê. Không đạt/chưa đủ bằng chứng không phủ định H2 cho mọi controller.

