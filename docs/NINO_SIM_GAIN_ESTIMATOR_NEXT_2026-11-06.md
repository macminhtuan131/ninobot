> **Cập nhật 07/11:** correction này đã hoàn tất kiểm offline: 44 tests, 143 quyết định synthetic và 1.260 shadow. Gain-ID/motion benefit còn unknown; không có physics/training mới. [Kết quả và outline hiện tại](NINO_SIM_STATUS_AND_TODO_2026-11-07.md). Nội dung dưới là thiết kế tại ngày 06/11.

# Bước kế tiếp: một correction estimator cổ điển, chỉ offline

06/11/2026 · **Chưa release physics v2, training, holdout hoặc hardware.**
Đầu vào là [qualification9/9 đã đóng](NINO_SIM_GAIN_BASELINE_RESULT_2026-11-06.md).
Không sửa family gain v1, runner/test frozen, checkpoint hoặc sealed raw.

## Câu hỏi

Có thể tách **điều kiện cập nhật estimate** khỏi **lệnh bù đang được giữ** để
tránh bù tự làm history mất steady rồi quay về zero, mà vẫn tôn trọng
window, freshness và quyền stop? Đây là một correction classical candidate;
chưa giả định giải quyết bias/lag hoặc có lợi ích motion.

## Outline hữu hạn

1. Dùng9trace hiện có, tái tính action/validity/fallback và phase-cost;
   giữ primary toàn14s. Phần này đã audit ở kết quả, không thêm rollout.
2. Chốt spec một candidate stateful riêng: cập nhật chỉ khi reference và
   encoder hỗ trợ giả thiết steady; invalid estimate update không tự làm
   mất estimate hợp lệ cũ. Thời hạn giữ, decay và tiêu chí steady cần lý do
   từ trace/plant; chưa đặt số tùy ý hoặc coi đã được chấp nhận.
3. Phân biệt rõ: **window đóng, stale sensor, owner/fault/stop** vẫn phải
   đưa residual vềzero theo contract; “hold estimate” không cho phép vượt
   stop, gate, ramp hoặc bounds. Reset/new epoch xóa trạng thái.
4. Fixture tối thiểu: gain tĩnh, actuator lag khi reference vẫn steady,
   correction-induced change, missing/stale/reordered samples, reset,
   window close và stop. Input đúng103D causal; không biết gain/GT.
5. Replay trace chỉ kiểm decision/validity/state machine. Không chấm các
   trajectory cũ như outcome của candidate mới; không reuse chúng thành
   counterfactual hoặc TD3 replay. Không chọn metric/tune theo test sau đó.
6. Quyết định một lần: nếu hold/update không giữ semantics hoặc không
   phân biệt được lag/bias, báounknown/no-go và giữ baseline/envelope đơn
   giản. Nếu software đạt và có cơ chế hữu ích, viết protocol/root/budget
   qualification riêng trước physics. Một correction, không vòng sửa/thử vô hạn.

## Đầu ra và giới hạn

Đầu ra: spec có phiên bản, source candidate riêng, fixture report và bảng
requested/update/held/executed semantics. Chưa có kết quả motion hoặc benefit.
Không cần real dataset cho bước phần mềm này; thiếu SysID thật vẫn giới hạn
sim-to-real. Static gain có lời giải classical; chưa có bằng chứng cần TD3.
Không tự tăng residual để bù cả dynamics/body bias hoặc mở DR/PPO/Optuna.
