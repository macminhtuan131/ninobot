# Thí nghiệm delay phanh 200 ms — protocol trước kết quả

Thực hiện theo `docs/governor_height_screen_2026-10-16/next_delay_hypothesis_protocol.json`.
Bản chuẩn bị đó được giữ nguyên với trạng thái lịch sử chưa implement/chưa chạy.
Batch mới lưu ở `rl_runs/governor_brake_delay_2026-10-16`.

## Candidate và đối chứng

- 6 episodes tối đa, cold start từng lượt, không retry.
- Gờ capsule cứng cao 6 mm, radius 3 mm, x=3.10 m, góc +8°, sàn box.
- Thứ tự: 77320 PI / governor 0 ms / governor 200 ms; 77321 governor 200 ms /
  governor 0 ms / PI. Cùng seed là scenario ghép cặp, không phải snapshot
  khôi phục đầy đủ trạng thái caster/contact/PI integrator.
- Chỉ khác tham số `trigger_to_brake_delay_seconds`: 0 → 0.2. Mặc định 0.
- Giữ robot, PI, detector, observations, cruise 0.4 m/s, target 0.90,
  min/max HOLD 0.8/1.0 s, ramp 0.4/s, physics 1 ms, control 100 ms.
- Khi pending, giữ scale hiện tại. HOLD bắt đầu cùng tick phanh đầu tiên.
  Delay áp dụng cho mỗi trigger; nếu có tái kích hoạt, ghi đầy đủ các event.
- Stop, stale/invalid feedback, stall/failsafe không chờ delay. ROS wrapper
  hủy pending và phát zero ngay khi nhận stop, kể cả lúc simulation clock pause.
- Trigger/brake onset lưu cả clock elapsed và timestamp simulation gắn với
  **đầu** khoảng điều khiển. Timestamp cuối action không dùng thay thế.

## Kiểm chứng trước chạy

23 tests core/integration đạt. So sánh 10.000 quyết định, 5 profile với source
trước sửa: mọi trường decision cũ trùng khi delay=0. Các trường telemetry mới
không tham gia kiểm tra bằng nhau. Kết quả lưu `zero_delay_regression.json`.
Source trước sửa core/env được giữ trong `implementation_before/`.

## Scoring và điểm dừng

- Giữ native metrics; replay native RMS, GT-native slip, hai grid sensitivity,
  coverage/age/skew và physical arrival + dừng 2 simulation seconds.
- Giữ các mốc so sánh time/path trung bình ≤1.05× PI, time ≤18.5 s. Không nới
  tracking khi sai số tuyệt đối nhỏ. Đây là mốc thiết kế đã có, không là chuẩn ngành.
- Báo riêng RMS/peak toàn tuyến, crossing RMS và slip² tích phân/m. Chỉ số
  slip này không có đơn vị năng lượng J.
- Dừng ngay nếu reporting/provenance hoặc kiểm tra vật lý lỗi. Giữ failures,
  dữ liệu thiếu và danh sách chưa chạy; không thay bằng episode khác.
- Kết quả mixed/không hữu ích sau ngân sách: bác bỏ candidate trong phạm vi
  thử, không tự thử delay khác. Hướng tốt ở cả hai block chỉ cho phép đề nghị
  confirmation riêng; n=2 không chứng minh tổng quát hóa hoặc sim-to-real.
- Không PPO, predictor, Optuna hoặc thay phần cứng/geometry trong batch.

Theo Deep Research: kiểm chứng H2 authority/timing trước H1 predictor. Batch
hẹp này không thay thế ma trận nhiều obstacle family/tốc độ. Cụm “wheel-first”
trong hypothesis chuẩn bị chỉ regime caster-wheel so với bracket: dữ liệu cũ
ghi caster-left là first manifold; controller không nhận contact identity.
