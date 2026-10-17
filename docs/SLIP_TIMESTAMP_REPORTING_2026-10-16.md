# Đồng bộ timestamp và chuẩn hóa reporting slip

**Ngày:** 16/10/2026. **Phạm vi:** telemetry và báo cáo offline; không chạy
simulation, không sửa native metric/reward/PI/governor hoặc điểm số study.

## 1. Đã triển khai

### Snapshot native có thể đối chiếu

Khi đánh giá với `--control-trace`, `ros_env.py` bổ sung schema
`native_slip_snapshot_v1` vào **chính control trace hiện có**:

| Trường | Ý nghĩa |
|---|---|
| `slip_joint_stamp_s`, `slip_ground_truth_stamp_s` | Header simulation timestamp của đúng snapshot dùng tính native slip |
| `slip_joint_age_s`, `slip_ground_truth_age_s` | Thời điểm kết thúc action trừ timestamp cảm biến; giữ giá trị âm để lộ dữ liệu mang stamp tương lai |
| `slip_joint_minus_ground_stamp_s` | Độ lệch stamp joint − ground truth; không che bằng trị tuyệt đối hoặc clamp |
| `slip_left_wheel_rad_s`, `slip_right_wheel_rad_s` | Vận tốc bánh của snapshot native |
| `slip_ground_linear_m_s`, `slip_ground_yaw_rad_s` | Vận tốc thân/yaw của cùng snapshot |
| `slip_native_left_ratio`, `slip_native_right_ratio`, `slip_native_mean_square` | Các giá trị đã dùng tính metric native |
| `slip_native_square_sum`, `slip_native_step_count` | Accumulator và số bước native hiện có, không tính lại hay thay thế |

Không gọi thêm ROS snapshot/callback, không chờ sensor mới, không lọc hoặc
đồng bộ lại đầu vào native/reward. Các trường được tạo từ biến `truth`,
`slip_left/right` và accumulator đã tính trong `step`. Missing timestamp
ghi trống/null thay vì `inf` hoặc đoán bằng receipt time.

`evaluation.py` giữ metadata cũ và thêm `metric_weighting_by_name` để nói rõ
`rms_wheel_slip` là **RMS theo control steps**, cùng metadata mô tả reporting
offline riêng. Không sửa `METRICS`, `benchmark_id`, episode metrics, objective
hoặc native summary. Snapshot schema chỉ được khai báo khi bật control trace.

### Một pipeline offline cho mọi cửa sổ

Module chung: [`slip_reporting.py`](../src/nino_rl/nino_rl/slip_reporting.py).
Audit pha trước đây cũng gọi module này, tránh hai bản công thức/quadrature
khác nhau. Snapshot source và artifact audit cũ được giữ nguyên.

- Grid **20 ms / 50 Hz**, origin là first control input từng episode.
- Chỉ dùng header simulation stamps; dedupe timestamp, giữ dòng cuối.
- Nội suy vận tốc joint và GT rồi tính ratio; không extrapolate hoặc nối
  gap GT >40 ms / joint >10 ms. Coverage yêu cầu ≥98%.
- Từ **một chuỗi slip² duy nhất**, tính RMS, tích phân slip² (s), quãng
  đường GT trên segment hợp lệ và tích phân/distance (s/m) cho route,
  crossing và từng pha. Cắt segment tại boundary; tổng pha bảo toàn total.
- Cùng floor 0,10 m/s, clipping và hình học nominal như công thức native.
  Đoạn đi ≤1 cm không báo /m. Missing event/sensor không được gán slip=0.
- CSV đồng bộ ghi cả **hai support timestamps** của từng sensor cho mỗi
  điểm grid. Nội suy sử dụng mẫu ở hai phía nên là **offline/noncausal**;
  không đưa chuỗi này vào governor hoặc policy triển khai.
- Báo riêng diagnostic dịch grid +10 ms. Không thay native bằng con số có
  lợi hơn; giữ giới hạn sensitivity đã thấy ở audit trước.

## 2. Báo cáo riêng trên dữ liệu đã lưu

Entry mới: [`report_synchronized_slip.py`](../src/nino_rl/scripts/report_synchronized_slip.py).
Đọc stage một-obstacle screen đã có `analysis/contact_analysis.json` và raw
logger/control traces; ghi ra **thư mục mới**, từ chối ghi đè report hoặc ghi
vào study input. Loader yêu cầu một episode/case. Failed native outcomes vẫn
được giữ; case thiếu dữ liệu ghi unavailable thay vì bỏ khỏi danh sách.

Đã tạo: [report.json](slip_timestamp_reporting_2026-10-16/report.json),
[windows.csv](slip_timestamp_reporting_2026-10-16/windows.csv),
[provenance](slip_timestamp_reporting_2026-10-16/provenance.json).
Sáu CSV samples có timestamps/support stamps và source snapshots nằm cùng
thư mục. Đây là report bổ sung, không import vào study hoặc chọn lại trial.

| Mean của 3 episode/controller | PI | Governor |
|---|---:|---:|
| Native RMS, giữ nguyên | 0,09037 | 0,09699 |
| Whole-route RMS, chung 50 Hz | 0,08490 | 0,07156 |
| Whole-route ∫slip² dt (s) | 0,12698 | 0,08769 |
| Whole-route ∫slip² dt/distance (s/m) | 0,02028 | 0,01402 |
| Crossing ∫slip² dt/distance, cùng pipeline (s/m) | 0,14096 | 0,08785 |

**Đối chiếu exact:** native outcomes, native RMS, mọi trường whole-route,
crossing và từng pha của **6/6 episode** khớp artifact audit trước. Không có
kết quả simulation mới hoặc cải thiện controller mới trong bảng này.

`native_snapshot_replay` cho **6/6 trace cũ** là unavailable: chúng chưa ghi
timestamp và giá trị bánh của snapshot native. Không hồi điền các trường này
từ raw stream rồi gọi là chính xác. Hàm replay cho trace mới kiểm tra schema,
bước liên tục, công thức và cumulative sum trước khi báo RMS; không tự sửa
native nếu đối chiếu khác nhau.

## 3. Verification và giới hạn

- **9/9 tests offline pass:** 4 tests audit trước và 5 tests bổ sung cho
  native CSV replay, signed/missing timestamps, bước thiếu/trace hỏng, cùng
  quadrature giữa các cửa sổ và missing GT/event.
- Các file Python thay đổi compile thành công.
- Kiểm tra hash **278 file được khóa trước chỉnh sửa**: cấu hình/candidate,
  contract/score/SQLite/selection, các artifact study/audit cũ, core slip và
  governor core **không thay đổi**. Kết quả kiểm tra lưu tại
  [preservation_check.json](slip_timestamp_reporting_2026-10-16/preservation_check.json).
- Không chạy ROS evaluation, Gazebo, training hoặc Optuna. Instrumentation
  mới **chưa được kiểm chứng runtime trong Gazebo**; tests CSV dùng dữ liệu
  tổng hợp. Không tuyên bố đã giải quyết chính xác độ trễ callback thực tế.
- RMS đồng bộ vẫn nhạy theo grid: mean giảm 15,72% ở origin primary, còn
  4,83% khi dịch 10 ms. Không coi nội suy GT 50 Hz là phép đo true slip tần
  số cao hoặc kết luận sim-to-real. [Audit chi tiết](governor_phase_slip_2026-10-16/REPORT.md).

## 4. Cách dùng về sau

Không cần chạy thêm để hoàn tất bước reporting này. Có thể tái tạo offline
vào **output mới**, không cần source ROS:

```bash
cd ~/ninorobot
source .venv/bin/activate
python src/nino_rl/scripts/report_synchronized_slip.py \
  --stage rl_runs/classical_governor_crossing_tune_2026-10-16/validation \
  --output /tmp/nino_slip_report_recheck
PYTHONPATH=src/nino_rl python -m pytest -q \
  src/nino_rl/test/test_governor_phase_slip.py \
  src/nino_rl/test/test_slip_reporting.py
```

Ở lần evaluation được yêu cầu sau này, bật `--control-trace` để có snapshot
fields mới. Trước mọi sửa tham số, đối chiếu trace replay với native RMS,
kiểm tra age/skew và giữ reporting đồng bộ trong namespace riêng. Bước này
không tự cho phép thêm trial hoặc đổi cấu hình governor.
