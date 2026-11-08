> **Mới nhất06/11 — Gain baseline Gazebo đã đóng9/9:** 1.260ticks;283hashes/3.834support checks đạt,0actor/train. Causal/fixed native: +23,0% tại1; +29,8% tại0,98; −15,3% tại1,02. SoB0 còn sampling-sensitive ở1/0,98; chưa promote/learner. Tiếp correction estimator cổ điển offline. [Kết quả](NINO_SIM_GAIN_BASELINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Cập nhật triển khai:** backend/context và parity gain=1 đã kiểm offline; xem [kết quả](NINO_SIM_GAIN_CONTEXT_OFFLINE_RESULT_2026-11-06.md). Chưa qualification Gazebo, runner physics/release hoặc learner mới. Các đoạn mô tả “chưa nối” dưới đây giữ lịch sử tại lúc chốt thiết kế.

# Draft qualification baseline — gain common cố định chưa biết

06/11/2026 · **Chưa runner physics/release; 0 launches hiện tại.**
Thiết kế từ [quyết định benchmark](NINO_SIM_BENCHMARK_DECISION_2026-11-06.md),
machine spec `src/nino_rl/config/sim_gain_benchmark_v1.json`.

## Bước chuẩn bị bắt buộc

1. Tạo backend/context/validator riêng: inject một lần gain common sau shared
   projection, trước drive backend; giữ differential/yaw, zero/stop/ownership.
   Kiểm lại speed/accel/slew/torque bounds trên cả effective reference;
   clipping/intervention không được giấu hoặc gọi là free gain response.
2. Log riêng nominal, policy request, windowed/projected reference, final ROS,
   effective drive reference sau map, actuator target và measured wheel.
   Không gọi target hay `/cmd_vel` là body motion/torque readback.
3. `last_final` trong causal history phải có semantics và source stamp rõ;
   không thay bằng effective injected parameter rồi vô tình cho controller
   biết gain. Ground truth chỉ chấm điểm; kiểm leakage bằng fixture.
4. Gain=1 phải qua parity ở cùng input fixtures; reset/freshness/limits/error
   paths giữ nguyên ý nghĩa. Shape103D/1D giống nhau vẫn cần context hash mới.
5. Candidate hiện là hàm offline, chưa nối vào loop. Kiểm wrapper dùng đúng
   observation thật, timestamp, fallback và shared projection trước release.

## Ma trận dự kiến, không tự cấp slot

Gain1 trước để integration nằm trong budget; sau đó0,98 và1,02.
Mỗi gain: B0 / fixed Classical_scheduled / Causal_gain_candidate.
**3×3=9 fresh launches ×140 ticks = tối đa1.260 ticks**; source stop8s,
horizon14s. Một run/cell là screening mô tả, không đo reliability hay đủ power.
0 actor loads/optimizer/training/hardware, 0 retry hoặc smoke ngoài budget.

Mọi arm: clear-box; nominal0,2m/s; common±0,005m/s, 10Hz, history5; same
drive-ACK+quiet reset, geometry, follower, PI, sensor rates và preview/window.
Initial state và caster có thể khác giữa launch: không là exact-state branching.

## Dữ liệu và metric

- Required mỗi decision: requested/accepted/effective/target/encoder, causal103D
  với ages, ownership/fault/intervention, IMU; GT/body riêng cho evaluator;
  gain/condition chỉ metadata. Primary+independent support/physics ACK/closure.
- Primary giữ whole14s native nominal-body velocity RMSE. Hai header grids
  GT20ms/+10ms riêng. Secondary wheel-reference error, path, stopping,
  intervention, estimate validity và cost theo phase; không thay primary.
- Marker, path RMSE≤40mm và stop quiet2s/horizon14s giữ constraint nghiên cứu.
  5% relative effect là rule mô tả đề xuất, chưa yêu cầu nhà máy chấp nhận.
- Báo từng gain/arm và cả absolute difference; baseline denominator zero,
  nonfinite, sampling-sensitive hoặc pre-intervention imbalance: unknown.

## Qua / dừng / unknown

- Software/measurement fail: đóng attempt và slot còn lại. Không hạ coverage,
  bỏ spike hoặc dùng nguồn khác vá. Tối đa một correction có bằng chứng
  **trước khi phải quyết định lại**; correction cần version/root/protocol mới,
  không có quyền retry từ draft này.
- Không có wheel/body response phù hợp requested→effective change: physical
  authority unknown/no-go; chưa mở learner hoặc sửa reward để che vấn đề.
- Cổ điển đạt nhu cầu: chọn cổ điển. Có gap chưa giải thích: unknown; không
  tự suy TD3 sẽ thắng, tăng số mẫu hoặc nới scale.
- Nếu còn gap có ý nghĩa và useful authority: chốt quyết định learner/holdout
  riêng. Chưa có training steps/seeds/holdout bank nào được cấp tại đây.

**Việc ngay:** backend/context và parity offline; chưa thu thêm real data hoặc
train. Thiếu real SysID chỉ giới hạn calibration/claim sim-to-real, không cấm
kiểm giả thuyết được gắn nhãn rõ trong simulator.
