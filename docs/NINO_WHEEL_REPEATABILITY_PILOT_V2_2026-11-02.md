# Nino — pilot repeatability v2, tối đa 3 lượt mới

> **Đánh giá raw lượt v2 bị ngắt:** chỉ còn 3,703 s trước trial; mẫu cuối trước forward 5,381 s. SQLite index integrity fail, không còn primary motion window. Helper log source completed không thay raw. Pilot giữ stopped 1/3; chưa thu thêm. Báo cáo workspace: `artifacts/interrupted_pilot_v2_evaluation_2026-11-02/REPORT.md`. Đề xuất tiếp: một capture đứng yên kiểm recorder closure trước ngân sách motion mới.


> **Cập nhật sau reboot 02/11:** Agent và sensor readers đã nối lại ở boot 415f7fe9; raw IMU/hai bánh/LiDAR/TF có dữ liệu. Pilot v2 **đóng ở 1/3**, hai slot còn lại đóng: trial source đã kết thúc nhưng recorder chưa có closure trước reboot. Giữ raw, chưa retry. Không dùng lệnh thu bên dưới để chạy lại đợt đã đóng.


Người dùng đồng ý mở đợt mới ngày 02/11/2026: “Làm tiếp theo recommand đi”.
V1 dừng ở 1/3 vì startup lifecycle không hoàn tất; hai slot cũ đóng.
V2 độc lập, hiện **0/3**, chưa thu hoặc chạy motion.

## Correction và kiểm chứng

- Launcher chờ lifecycle active và fresh zero command trước READY, tối đa 20 s.
- Recorder kiểm live lại sau metadata, trước cấp slot; readiness fail ở đây chưa tiêu slot.
- Sau cấp slot, failure/unknown vẫn đóng các slot còn lại; không retry/bù.
- 26 tests và 6 mocked handoff cases đạt. Live zero-check `20261102T055335143925Z` đạt, launch đóng exit 0. Không source/enable, không thay firmware/PI/current/QoS.
- Một zero-check đạt không chứng minh middleware hết lỗi hoặc motion sắp tới thành công.

## Thu lượt 1

Trên Pi, giữ RC AUTO, xe đứng yên cùng sàn trống/tải; người vận hành cạnh nút dừng. Profile giữ 0,05 m/s, shaping 0,10 m/s², source tiến 2 s rồi zero/disable; bag 60 s.

Terminal 1 — đợi READY:
```bash
bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v2/start_stack.sh
```

Terminal 2 — nhập AUTO, ghi tư thế/caster (`unknown` nếu chưa biết):
```bash
bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v2/record_wheel.sh
```

Khi terminal 2 in Output và bắt đầu thu, terminal 3 chạy ngay:
```bash
bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v2/run_trial.sh
```

Đợi recorder tự kết thúc 60 s, rồi Ctrl+C terminal 1. Gửi output và quan sát tiến/tự dừng/lệch/giật; cần review trước lượt 2. Không tự chạy lại khi lỗi.

Dữ liệu required: source/selected/smoothed/final command, motor_enable, motor_fb, motor_status, raw IMU. LiDAR/TF/odom chỉ context, không GT độc lập. Primary giữ mean wheel velocity ở source+1,25..1,75 s trừ baseline -2..0 s; giữ mọi spike và support rules đã freeze.

## Giới hạn

Mới có một lượt feasibility sàn sạch trước pilot, chưa chứng minh repeatability, body/slip, physical stop latency hoặc obstacle/governor benefit. Assistant chỉ kiểm/phát reference zero từ stack disabled; người vận hành khởi chạy nonzero trial.

Artifact workspace: `artifacts/wheel_repeatability_pilot_v2_2026-11-02/RELEASE_REPORT.md`.
Contract SHA256: `bf8baf73ec398522aa04e68e48528ed8d1e684da9cdd9098b7251a32cd1f4bcd`.
