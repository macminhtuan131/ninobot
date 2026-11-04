# Sim tiếp tục — kiểm bias sàn sạch và chuẩn bị guidance

04/11/2026. [Protocol chốt trước chạy](NINO_SIM_CLEAR_BIAS_PROTOCOL_2026-11-04.md).

## Quyết định

**[N — sim] Bias yaw của checkpoint v2 xuất hiện cả khi không có gờ.**
Đã chạy bốn lượt clear floor: B0, TD3, TD3, B0. Hai lượt TD3 tạo yaw
reference âm khoảng −0,076 rad/s, thân xe lệch phải khoảng 0,217 m cuối task.
Không train thêm, không sửa checkpoint, không chạy lại batch v1/v2.

**Chưa promote hoặc tăng training.** Gờ/contact không giải thích toàn bộ
lỗi steering. Nên hoàn thiện baseline có path guidance và objective velocity
tracking bằng một contract v3 riêng trước training lớn.

**[N — phần mềm] Guidance adapter đã xây và đạt kiểm offline** qua pipeline
residual hiện hành; chưa nối guidance vào Gazebo/ROS/robot, chưa xác minh
estimator thật. Không gọi fixture offline là thí nghiệm closed-loop robot.

## 1. Kết quả checkpoint đóng băng trên clear floor

Actual Nino URDF/caster, Gazebo + wheel PI, policy/native scoring 100 ms,
physics 1 ms. Giữ nguyên v2 task 14 s, source cruise 0,2 m/s từ 0,5–8 s,
ramp 0,1 m/s², stop quiet 2 s. Một learner seed cũ; hai fresh launches/arm,
không phải exact-state pairs hoặc nhiều training seeds. World controlled
solid-box trong hall factory; không phải full mixed factory route/cáp mềm.

| Arm/lượt | Mean accepted ω 3–8 s (rad/s) | Mean GT ω (rad/s) | RMSE v chuẩn (m/s) | RMSE ngang (mm) | y cuối (m) | Task / stop |
|---|---:|---:|---:|---:|---:|---|
| B0/1 | 0,00000 | +0,00026 | 0,00491 | 0,81 | +0,0012 | Đạt / đạt |
| B0/2 | 0,00000 | +0,00033 | 0,00515 | 1,25 | +0,0019 | Đạt / đạt |
| TD3/1 | −0,07550 | −0,06631 | 0,02168 | 145,01 | −0,2165 | Đạt / đạt |
| TD3/2 | −0,07590 | −0,06708 | 0,02171 | 144,90 | −0,2171 | Đạt / đạt |

TD3 mean executed v khoảng 0,173 m/s; final yaw khoảng −0,463/−0,465 rad.
Không dùng task/stop đạt để gọi chất lượng tốt. Không đổi reward, scale,
time grid hoặc lấy thêm mẫu sau kết quả. Numerical yaw floor 1e−6 rad/s
chỉ phân biệt zero số học, không là effect/safety threshold đã chấp nhận.
Không có CI hoặc claim generalization từ hai lượt.

**[S]** Reference differential có bias và GT body quay cùng phía trên sàn
sạch: bằng chứng phù hợp với lỗi policy/reference trước contact. Nó bác bỏ
cách giải thích “chỉ do gờ” cho checkpoint này. Chưa phân biệt khởi tạo actor,
reward weighting, critic/warmup hoặc thiếu training là nguyên nhân duy nhất.
Không sửa output trung bình hoặc clip differential sau khi thấy kết quả để
biến checkpoint cũ thành policy tốt.

## 2. Đã sửa phần thiết kế nào?

Audit source cho thấy `residual_sim_task` dùng constant straight baseline,
chưa nối `flat_motion_command`/route follower đang tồn tại trong pipeline cũ.
Actor proprioceptive h5 không nhận absolute lateral/heading, trong khi reward
v2 phạt lateral thế giới. Đây là hạn chế observability/đặt bài toán cần tách.

Module mới `residual_guidance.py` tái dùng follower geometry cũ và bổ sung:

- Typed pose sample với source/receipt time, source/frame/clock/epoch.
- Duplicate không gia hạn pose lease; stale/future/reversal/mismatch fail
  closed; owner stop và corridor/overshoot được báo rõ, không tự recovery.
- Pose estimate tạo baseline v/ω ở tầng follower. `apply_guidance` đưa đúng
  reference vào cả baseline và feature reference, giữ wheel/final/actuator
  readback; thiếu pose vẫn gỡ permission dù sensor khác đang fresh.
- **Không thêm pose/GT/caster vào actor**; ABI vẫn 100D. Oracle GT bị chặn
  mặc định, muốn dùng phải khai báo và có contract/hash khác.
- Một segment thẳng, chưa hỗ trợ ordered turns/loop trong adapter mới.

[Contract và luồng cụ thể](NINO_SIM_GUIDANCE_CONTRACT_2026-11-04.md).

Workflow offline đã chạy năm scripted-pose fixtures × 35 tick: trái/phải
path, heading error, gần goal, pose stale. Cả năm đạt reference/gate semantics.
Đã kiểm handoff với **ResidualPipeline thật**, gồm ramp: yaw correction
không xuất hiện ngay khi cả hai bánh còn cùng tăng tốc theo bound. Không sửa
limiter để tạo authority giả. Đây chưa là wheel/body response trong physics.

## 3. Dữ liệu và kiểm chứng

- Diagnostic: tối đa và thực tế **560 transition**, zero optimizer updates.
  Manifest checkpoint v2 giữ đúng SHA256 đã chốt; kiểm lại **51 file** upstream.
- Hai job mới: **62 file** khớp manifest SHA256; 1.160/1.160 world-control
  requests hoàn tất đúng clock/iteration; zero physics retries, 8/8 readonly
  parameter calls hoàn tất. Offline guidance job không có physics requests.
- Không có C1 contact manifolds. Vẫn có contact bánh/caster với sàn; không
  gọi clear floor là zero-contact dynamics hoặc no-slip ground truth.
- Task-window source gaps/boundary lags được tính riêng startup trong QA;
  counts không là chứng minh loss-free. Metric body dùng native 100 ms từ
  GT nguồn khoảng 50 Hz, không nội suy để tăng độ phân giải.
- 50 test sim/reference/guidance và 9 test GUI đạt; colcon `nino_pi`,
  `nino_rl` được build/repackage. GUI load artifact thực, giữ history v1/v2.
- Không SSH, không thu real data mới, không đổi PI/current/gain hoặc firmware.

Root: `~/nino_research/sim_clear_bias_v1`.

QA: `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_clear_bias_2026-11-04/`.

[Ledger kiểm chứng](NINO_SIM_CLEAR_BIAS_VERIFICATION_2026-11-04.json).

## 4. GUI đã cập nhật

**NHÁNH SIM → Tiếp theo · kiểm bias sàn sạch + reference follower** là view
hiện tại. Hai stage: diagnostic vật lý đã chạy và adapter offline đã kiểm.
Bảng hiển thị mean yaw reference/GT yaw, tracking/lateral, y cuối, stop và
task. Status ghi rõ **ĐẠT OFFLINE · CHƯA NỐI GAZEBO / ROBOT**.

Các stage đã hoàn tất được đóng; nút xem artifact còn dùng được. Dropdown
v1/v2 giữ nguyên nguồn và kết quả cũ. Mở GUI không tự chạy job hoặc nối Pi.

## 5. Việc nên làm tiếp

**[Đ — chưa chạy] V3 baseline trước learning:** nối estimator wheel+IMU
causal → guidance adapter → residual zero → projection → velocity backend.
GT chỉ dùng evaluator/oracle tách riêng; initial pose phải được khai báo.
Kiểm sàn sạch và initial heading error trước contact screen, theo protocol
mới có điều kiện/lặp/deadline và tối đa một correction có căn cứ.

Khi baseline/estimator/reference/stop hợp lệ mới chốt velocity/yaw tracking
reward và zero-initialized residual nếu phù hợp, rồi training budget riêng.
Đây là thay task/baseline, cần checkpoint metadata v3; **cùng ABI không đủ
để resume checkpoint v2** dưới reference mới. Real data phục vụ calibration
song song, không là prerequisite của bước sim này.

Điều khiến đổi khuyến nghị: baseline guidance giữ tuyến và stop ổn định,
reference causal/pose drift có thể đo, residual khởi đầu không tạo steering
bias, rồi có lợi ích chất lượng theo protocol. Chưa có căn cứ chỉ tăng steps,
thêm PPO/history dài hoặc quy toàn bộ lỗi cho contact.
