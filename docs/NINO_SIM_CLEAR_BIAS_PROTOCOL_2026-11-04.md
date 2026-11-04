# Protocol trước chạy — frozen v2 trên sàn sạch

04/11/2026, tiếp tục nhánh sim theo yêu cầu người dùng. Không yêu cầu real
dataset, không SSH/robot/firmware, không train hoặc sửa checkpoint.

## Một câu hỏi

Bias yaw của checkpoint v2 có xuất hiện khi **không có obstacle/contact với
gờ** không? Sàn vẫn có contact bánh/caster bình thường. Không coi đây là
phép thử learning benefit, hội tụ hoặc generalization.

- Checkpoint: `sim_task_v2/20261104T084149528335Z_sim-v2-train`.
- Manifest SHA256: `634c4bd3de416d73da20aeb7bb5a3f7e5177346a1908a98b1c24aa229776179b`.
- Task fingerprint giữ: `7025cd96dc133cd41d99c00068f56728e9014b4e8f908e2839fec26a95ce7dae`.
- Actor ABI, v2 reward/task 14 s và stop rule, PI, geometry, physics/ramp,
  source 0,2 m/s / zero sau 8 s giữ nguyên. Không resume hoặc optimizer.
- World `clear_box` đúng generator v2; hall factory + solid box, không gờ.
- Bốn fresh launches: **B0, TD3_h5, TD3_h5, B0**, mỗi arm hai lượt,
  tối đa 560 transition, zero training, 1.200 s wall. Một seed learner từ
  checkpoint cũ; reset seed không là exact-state branching/noise seed đã kiểm.
- Không chạy lại batch hoặc bổ sung slot khi đã có ledger; failure giữ
  incomplete/unknown. Correction nếu thực sự cần phải có protocol/root mới.

## Metric và cách diễn giải đã chốt

Primary: signed mean accepted yaw reference ở task time 3–8 s. Báo riêng
proposal common/diff, final ROS yaw reference, GT yaw rate, y/yaw cuối và
RMSE v/y, stop/task. Dùng nguyên native grid 100 ms, không nội suy hoặc
chọn time grid thuận lợi. Raw sensor/GT/caster/drive giữ riêng.

Numerical floor 1e−6 rad/s chỉ để phân biệt zero số học. Nếu cả hai TD3 có
mean accepted yaw cùng dấu, vượt max |B0| + floor, ghi **reference bias quan
sát trên sàn sạch**. Đây không là ngưỡng chất lượng/safety được chấp nhận.
Quan sát body yaw/lateral cùng dấu là bằng chứng hỗ trợ, không biến fresh
launches thành counterfactual cùng state. Nếu kết quả trái chiều hoặc thiếu
cửa sổ, kết luận unknown, không tự tăng mẫu.

Nếu có bias trên sàn sạch: không quy toàn bộ lỗi cho gờ/caster, ưu tiên
objective/action/baseline trước contact learning. Nếu chỉ có sau contact:
giữ giả thuyết cơ chế contact để kiểm riêng. Cả hai nhánh không tự mở train
lớn hoặc đưa GT pose vào actor.

## Artifact và bước thiết kế song song

Root mới `~/nino_research/sim_clear_bias_v1`; action `sim-bias-clear`.
Dependencies giữ manifest checkpoint, config/protocol/source/runtime hash,
traces/raw, từng lượt và verdict mô tả. V1/v2 không sửa, không gộp batch.

Song song: audit follower cũ và chuẩn bị adapter pose-estimate → baseline
reference → residual → projection → velocity backend. Adapter mới chỉ kiểm
offline, chưa coi đã nối Gazebo/ROS/hardware; pose source/frame/clock phải
khai báo rõ, GT chỉ trong mode oracle tách riêng.
