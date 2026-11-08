> Cập nhật06/11: evaluation-only mới đã đóng, dùng ba checkpoint TD3 có sẵn; không train thêm. Xem [kết quả](../docs/NINO_SIM_RELIABLE_EVAL_ONLY_RESULT_2026-11-06.md) và [protocol](../docs/NINO_SIM_RELIABLE_EVAL_ONLY_PROTOCOL_2026-11-06.md). Chưa promote/hardware.

# Bước kế: evaluation-only cho ba checkpoint đã train xong

06/11/2026 · **Đề xuất đã chuẩn bị code/test, chưa release job hoặc chạy Gazebo.**

## Vì sao không train lại

Pilot RELIABLE đã train đủ seed11/22/33, mỗi seed1.024transition/960critic
updates; checkpoint/replay/targets/optimizers qua kiểm tra. Lỗi xảy ra sau
đó trong evaluator B0: constructor dùng GuidedBackend cũ rồi đọc namespace
của lifecycle mới. BatchV1 đóng25launches; không có eval hợp lệ.

Source và artifactV1 giữ nguyên. Module correction riêng
`residual_reliable_evaluation.py` tạo đúng `EpisodeLifecycle` và kiểm
namespace sau reset, trước control interval đầu. Bốn test offline đã kiểm
B0/classical/TD3 cùng factory và backend sai không được step physics.
Module này không có CLI/job release; GUI chưa có nút mở budget eval mới.

## Protocol mới cần hoàn thiện trước lần chạy kế

1. Pin manifestV1
   `bb6293d9d5e62b1f63646e805e6b67dc9f712fc570ecbe2fa29b75de629ff053`,
   identity/model hashes của cả3final checkpoints và qualification candidate.
   Đọc trạng thái failedV1 đúng lý do integration; không biến cả pilot thành
   completed. Kiểm từng training result đủ1.024, replay/finite/save-load đạt.
2. Một root và identity eval-only mới; **optimizer/training0**, không resume
   partial700, không retrain hoặc chọn seed. Số điều kiện tối đa10,140tick
   mỗi lượt, tổng1.400, đúng thứ tự đã khóa trong protocol learnerV1.
3. Dùng correction evaluator + cùng RELIABLE lifecycle ở mọi arm. READY,
   fresh namespace/partition/context/cache, close/ACK cho từng launch;
   no source/sidecar substitution,40ms và native/header/task/stop giữ nguyên.
4. Chốt wall deadline hữu hạn từ observed startup/eval throughput và margin;
   chưa coi draft là release. Không thêm Gazebo smoke; lượt đầu trong budget.
5. Gate software trước release: regression factory/namespace đã có; bổ sung
   dependency/model hash tamper, failed-parent reason, fixed-order/budget,
   fail-close/cancel và GUI completed/failed/consumed. Chỉ kiểm phần mới.
6. Một lỗi đóng slot còn lại, không retry. Nếu qua đủ10lượt: so mỗi seed/stop
   với B0 và classical ở native100ms, GT20ms/+10ms, path/task/stop. Báo mọi
   ranking đảo chiều; minimum worthwhile effect vẫn null. Chưa promote.

## Điểm dừng

Không cần sửa gain/reward/current/QoS hoặc train thêm để sửa lỗi wiring
evaluator. Nếu checkpoint/dependency không xác minh được: dừng, giữ artifact.
Nếu evaluation hợp lệ nhưng TD3 không hơn classical: giữ baseline và audit
offline action theo phase trước khi đề nghị training khác. Contact/H2,
generalization và hardware là gate riêng; không suy từ clear-box known stop.
