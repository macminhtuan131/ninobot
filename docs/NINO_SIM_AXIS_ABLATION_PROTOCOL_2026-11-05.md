# Protocol trước chạy — frozen V3 full/common-only/B0

05/11/2026. Tiếp tục nhánh Sim theo yêu cầu người dùng, dựa trên
[pilot TD3 V3](NINO_SIM_GUIDED_TD3_V3_RESULT_2026-11-05.md).
Không training, optimizer, hardware, tuning hoặc thêm seed.

## Câu hỏi và can thiệp

Mask differential residual của frozen actor có loại được phần lớn lệch
tuyến quan sát trên sàn sạch, với thay đổi velocity tracking/progress nào?

- **B0:** guided baseline, proposal `[0,0]`; không gọi actor.
- **TD3_full:** deterministic actor V3, giữ hai proposal common/differential.
- **TD3_common_only:** cùng actor/weights, đặt **chỉ proposal differential=0**
  trước projection. Giữ common output, baseline yaw của follower, shaping,
  limits và wheel PI. Không ép tổng yaw reference thành zero.
- Mask làm feedback/history và các output tương lai thay đổi theo trajectory;
  không tuyên bố giữ nguyên common-command trajectory hoặc exact-state branch.
- Giữ `actor_raw_proposal` và `controller_proposal` riêng; `policy_proposal`
  từ environment là proposal thực tế sau mask. Không ghi đè output gốc hoặc
  xuất các rollout này thành replay học thông thường. Reward kế thừa tính
  action cost trên controller proposal; **return không dùng để chọn/promote**.

## Điều kiện và ngân sách đã khóa

Chỉ controlled **clear solid-box factory hall**, không gờ/mixed map. Robot
yaw0, path3m yaw0. Cùng estimator wheel+gyro-Z causal, geometry/PI/caster,
h5/100D/normalization và bounds parent. Initial estimate0 từ metadata,
không GT alignment. GT chỉ reset/reward/evaluation.

Cruise0,2m/s, source0,5–8s, task14s; physics1ms, native/scoring100ms,
140tick/lượt,6 fresh launches: **B0/full/common/common/full/B0**. Tối đa
**840 evaluation transitions**, optimizer/training0. Wall deadline1800s.
Reset wrapper seed701 không chứng minh mọi RNG của Gazebo đã kiểm soát;
hai launches mỗi arm là mẫu mô tả nhỏ, không nhiều training seed.

Checkpoint frozen `20261105T022329071579Z_sim-v3-train`:

- manifest SHA256 `8cc9cbeafeea220074638185535d7a23d6a84156424b2e2a8f656414c6e71578`;
- task fingerprint `861290d674c5dd7a9aa0cd8690896b1f59ceaf3cd6a4e9bcd34e8e2f07c482d9`.

Kiểm task/baseline/estimator/reward identity và ABI trước load. Không tự
chọn checkpoint mới. Module/YAML/script ablation có fingerprint riêng gồm
parent; không sửa nguồn/cấu hình hoặc artifacts của các batch trước.

## Metric, diễn giải và dừng

Primary: GT cross-track RMSE trên toàn task14s, gồm stop. Secondary:
nominal velocity/yaw RMSE, max/final cross-track, progress/time, estimate
error/age, raw/masked/accepted common/differential, quiet stop2s.

Giữ gate engineering parent: marker≥0,95m, stop2s, maxpath≤40mm,
maxestimate position≤50mm/yaw≤0,05rad. Chưa là acceptance nhà máy.
Marker không là arrival tại goal3m; wheel odometry không là body GT.

Ghi separation mô tả nếu maxRMSEpath(common-only)<minRMSEpath(full) trong
hai lượt mỗi arm. Đây là bằng chứng hỗ trợ ablation trong setup này, **không
là minimum effect được chấp nhận hoặc system-benefit gate**. Báo riêng
velocity/progress costs và so B0; không promote chỉ từ separation/return.

Physical/source/guidance fault hoặc thiếu140tick → đóng job, giữ raw/ledger,
không retry hoặc chạy bù. Quality miss giữ trong bảng, đánh giá đủ các slot
đã khóa nếu không có hard fault. Không đổi gate, bỏ spike hoặc mở thêm mẫu.
Nếu kết quả không tách được giả thuyết thì unknown/dừng nhánh giả thuyết,
không tăng train để che lỗi. Chưa mở rộng contact do B0 gờ còn biến thiên.

Root mới `~/nino_research/sim_axis_ablation_v1`, action`sim-axis-ablation`;
root có state đã tiêu thụ không chạy lại, kể cả failure. Raw sensor/GT/drive/
caster và estimator/guidance audit giữ đầy đủ; không tự gán coverage98%
của contract khác. Counts/hash không là proof loss-free mọi điều kiện.
