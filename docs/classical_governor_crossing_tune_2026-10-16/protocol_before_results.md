# Tuning governor cổ điển — contract mới, phạm vi crossing

## Quyết định sau audit offline

Trace đầy đủ và PI timing ổn định. Lượt 76500 cho thấy wheel/body gần đứng
lại trong nhiều đoạn khi reference vẫn yêu cầu tiến, contact bracket kéo dài
và phục hồi sau đó. Đây là failure mode có ích để khảo sát mức giảm tốc và
hold, không phải lý do đổi PI hoặc đoán lại collision.

RMS/peak impact **chưa đủ tin cậy để làm objective tuning**: ba spike đơn lẻ
chiếm 97–99% tích phân bình phương. Hai pha decimation 50→25 Hz thay đổi lớn
RMS/peak. Đó chỉ là diagnostic sampling sensitivity; không chứng minh aliasing
tại 50 Hz và không cho phép xóa outlier hay coi impact giả.

Theo yêu cầu mới, cho phép một **screen governor cổ điển về thời gian/slip
trong mô phỏng**, không mở predictor/PPO hoặc gọi đây là impact optimization.
Tất cả RMS/peak/P95 vẫn được báo và chặn mọi tuyên bố triển khai thật.
Đây là contract mới, không sửa kết quả hoặc objective của batch cũ.

## Protocol trước simulation — tối đa 18 episodes

Ba candidate cố định, Optuna quản lý trial/SQLite và chọn best observed:

| Trial | Target scale | Maximum hold (s) |
|---|---:|---:|
| 0 — cấu hình hiện tại | 0.85 | 2.5 |
| 1 — giảm ít hơn, phục hồi sớm hơn | 0.90 | 1.0 |
| 2 — giảm nhẹ, hold ngắn | 0.95 | 0.8 |

Không gọi ba điểm enqueue là tìm được optimum toàn search space hoặc một
nghiên cứu Bayesian lớn. Không có trial bổ sung tự động, retry hoặc pruning.

- Development seeds **76600–76601**, mỗi trial 2 seeds × 2 controllers:
  **12 episodes**. Mỗi trial có PI 0.388 m/s riêng, thứ tự PI/candidate ngẫu
  nhiên trong từng block với RNG 76650+trial index. Không identical snapshot.
- Freeze best params trước mở validation **76700–76702**. Chỉ validate nếu
  feasible và development objective <1. Validation 3×2 = **6 episodes**.
  Nếu không có ứng viên tốt hơn PI trên dev, dừng ở 12, không dùng test để chọn.
- Giữ physics/world/robot/PI/reset, detector/observations/quiet/minimum hold
  0.8/ramp 0.4/s, cruise governor 0.400 và physical arrival/stop scoring.
  Chỉ thay `target_scale` và `maximum_hold_seconds`.
- Profile `moderate` hardcode target 0.85, nên tuner dùng `reactive` để target
  có hiệu lực. Regression replay xác nhận reactive 0.85 thực thi giống
  moderate 0.85; không sửa governor core hay action mapping.

### Objective cố định

Cho mỗi seed cùng trial, PI reference là mẫu đối chứng riêng của block:

`cost = 0.5*(T_governor/T_PI + S_governor/S_PI)`
`       + max(0, RMSE_governor/RMSE_PI - 1.05)`

`J = mean(cost)`; minimize. `S` là slip²/m trong cửa sổ event đã có
(first+0.05 → body qua x=3.40 m). J của chính reference là 1.0.

- Arrival/stop failure: `100 + 10*n_failures`, không thể thắng trial feasible.
- Missing/aborted data hoặc PI reference fail: trial FAIL/unavailable, không
  gán thành slip/impact=0 hoặc xóa native physical failure đã ghi.
- Đơn vị cost là dimensionless ratios. Hai weight 0.5 cân bằng thời gian và
  slip như một lựa chọn exploratory đã chốt trước; không phải chuẩn ngành.
- Native peak/RMS/P95 được báo toàn bộ, **không bị bỏ khỏi báo cáo vì không
  nằm trong objective này**. Chưa có impact benefit hay safety guarantee.
- Không retune PI cruise để ép time matching; báo thời gian thật và trade-off.

Validation pass cho **crossing screen**: tất cả arrival/stop, J<1 và mean
path RMSE≤1.05×PI validation. Dù pass, chưa promote hoặc gọi giảm impact;
vẫn cần measurement fidelity và feasibility ngoài một cáp cố định.
Nếu fail, không chọn lại candidate bằng validation, không thêm trial/penalty.

## Phương pháp và nguồn

Optuna lưu study SQLite, enqueue candidate cố định, ask/tell cho lifecycle.
Không import lịch sử PPO hoặc score của contract khác.
[Study API chính thức](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.study.Study.html),
[Persistent storage](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.create_study.html).

Code: `src/nino_rl/scripts/tune_classical_governor.py`.
Raw output mới: `rl_runs/classical_governor_crossing_tune_2026-10-16/`.

## Trạng thái

Protocol đã chốt; kết quả sẽ được ghi sau batch. Không chạy ML/Optuna PPO.
