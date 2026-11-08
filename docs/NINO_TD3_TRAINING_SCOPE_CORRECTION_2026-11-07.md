# Đính chính phạm vi kết luận về training TD3

07/11/2026. Không chạy training, Gazebo hoặc hardware trong lần đính chính này.

## Đã train bao nhiêu?

| Learner | Transition vào replay | Critic updates | Actor updates | Phạm vi |
|---|---:|---:|---:|---|
| A Gaussian seed11 | 1.024 | 960 | 480 | Hoàn thành ngân sách pilot ngắn; cuối episode censored44bước |
| C stratified seed11 | 840 | 776 | 388 | Partial; study dừng do readiness đầu episode |

Không gộp hai learner thành một checkpoint có1.864steps hoặc nhiều training
seeds. A được đối chiếu trực tiếp với `training_result.json` và hash trong
manifest đã seal. C là số được báo trong báo cáo study partial.

- [Artifact A — số bước và optimizer updates](/home/tuanmac/nino_research/sim_coverage_study_v2/20261106T111842753138Z_sim-coverage-v2-study/A_gaussian_seed_11/training_result.json).
- [Báo cáo study V2](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md).
- [Eval-only checkpoint A](NINO_SIM_READY_EVAL_ONLY_RESULT_2026-11-06.md).

`initial_policy.num_timesteps=0` trong file kết quả là trạng thái khởi đầu,
không có nghĩa quá trình sau đó không train. Số transition được nhận và
optimizer updates phải đọc từ các trường tương ứng của kết quả cuối.

## Điều được và chưa được kết luận

Checkpoint A sớm có velocity RMSE cao hơn baseline trong phép eval đã ghi.
Đó là kết quả thực của **checkpoint đó**, không chứng minh TD3 đã được train
đủ, đã hội tụ, thất bại về thuật toán hoặc không thể thắng baseline.

1.024steps không tự cho biết thiếu bao nhiêu bước để hội tụ. Số bước lớn
hơn cũng không bảo đảm học tốt. Cần protocol training, action coverage,
learning curves, checkpoint evaluations và seed phù hợp trước khi kết luận.
Tests phần mềm, synthetic decisions và eval-only ticks không được cộng vào
số bước TD3 train.

Cách diễn đạt trước đã đặt quá nhiều trọng lượng lên kết quả checkpoint
sớm và đẩy công việc sang nhiều vòng baseline audit. Cần sửa thứ tự đầu tư.

## Hướng tiếp cận đã sửa

1. Dùng baseline Ki0,10 frozen đã có làm đối chứng cho thiết kế pilot TD3.
   Validation Ki0,15 stop6s phục vụ quyết định promote PI, là nhánh riêng;
   không bắt buộc trước pilot dùng baseline cũ.
2. Chốt contract/ABI, environment, warmup/exploration/action coverage,
   ngân sách training và eval cadence trước khi chạy. Không tự mở lại
   root đã đóng hoặc load checkpoint khác ABI để resume.
3. Train trong ngân sách được review, lưu curves/checkpoints và đánh giá
   định kỳ. Đánh giá sớm dùng chẩn đoán; không yêu cầu learner thắng ngay.
4. Đánh giá cuối có baseline cùng điều kiện, quy tắc chọn checkpoint và
   holdout tách biệt. Một seed/pilot không đủ cho claim tổng quát.
5. Gate thắng baseline dành cho promote/deployment. Readiness và contract
   hợp lệ là gate để xem xét training; không dùng kết quả chưa train đủ
   làm lý do chặn mọi training tiếp theo.

Chưa cấp ngân sách mới hoặc tự chọn số timesteps trong lần đính chính này.
GUI và outline hiển thị số train thật cùng giới hạn kết luận; artifact,
checkpoint, các release đã đóng và thông số controller được giữ nguyên.
