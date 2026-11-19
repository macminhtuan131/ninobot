# Rà soát và sửa training dài ngày 17/11/2026

> Cập nhật. Campaign 20k đã dừng sạch ở 2.702 bước theo yêu cầu chuyển sang [campaign 50k mới](RECOVERY_TD3_50K_CAMPAIGN_2026-11-17.md). Các trạng thái khởi chạy 20k bên dưới là snapshot lịch sử.

## Mục tiêu và thay đổi

Chuẩn bị các file để campaign TD3 dài nhận đúng transition và lưu checkpoint có thể kiểm chứng.

Review độc lập tái hiện lỗi tại `CampaignEnv.step`. Điều kiện cũ chỉ kiểm lý do fault khi `terminated=True`. Adapter trả `truncated=True` với lý do owner intervention, driver fault hoặc không rõ vẫn có thể ghi vào replay dưới dạng timeout. Đây là lỗi tại boundary của campaign. Chưa có bằng chứng campaign thực vừa chạy chứa các transition lỗi đó.

Điều kiện mới chỉ nhận truncation từ backend khi task ghi `external_cutoff` và backend ghi `time_limit`. Điều kiện chạy trước khi tăng counter, ghi trace hoặc đưa transition vào replay. Giới hạn episode do campaign tự tạo và failure vật lý hợp lệ giữ nguyên. Timeout hợp lệ vẫn bootstrap khi SB3 lấy mẫu replay.

Không thay đổi reward, gain, history, action scale hoặc hyperparameter TD3 trong lần sửa này.

## Checkpoint trước sửa

Campaign `recovery100_train20k_20261117_01` đã dừng tại ranh giới episode. Có 1.082 transition, 82 cập nhật critic và 41 cập nhật actor. Source QC đạt ở cả bốn episode đã đóng. Service thoát mã 0.

Đã kiểm hash tám file trong bundle, nạp model và replay bằng SB3, kiểm giá trị hữu hạn và inference 100D sang action 1D. Chưa resume vật lý checkpoint này. Không tự chuyển checkpoint cũ sang source mới vì identity khác.

## Kiểm thử phần mềm

- Trước sửa có `6 failed, 1 passed` trong regression mới.
- Sau sửa có `45 passed` trong campaign và review tests.
- Bộ mở rộng có `244 passed in 42.95s`.
- Reviewer độc lập chạy lại bảy regression mới và đều đạt.
- CLI wrapper qua `bash -n` và thực thi được `--help`.
- Knowledge graph đã cập nhật sau thay đổi code.

Log và patch ở [artifact kiểm chứng](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/longtrain_recheck_2026-11-17).

## Kiểm chứng Gazebo và trạng thái campaign

Cả năm probe Gazebo với source mới đều hoàn thành nhiệm vụ và đạt source QC. Có 1.358 transition và 165 file hash đã kiểm độc lập. Mỗi nhóm chỉ có một lượt development stage 0.

| Nhóm | Bước | Goal error, m | Speed RMSE, m/s | Cross-track RMSE, m |
|---|---:|---:|---:|---:|
| clean | 272 | 0.003101 | 0.005696 | 0.003524 |
| short_obstacle | 272 | 0.017606 | 0.008055 | 0.013272 |
| pothole | 271 | 0.001755 | 0.006005 | 0.003245 |
| mixed | 271 | 0.007850 | 0.008381 | 0.001122 |
| slope | 272 | 0.021371 | 0.012512 | 0.006453 |

Bank mới ở `/home/tuanmac/nino_research/recovery100_training_inputs_20261117_03`. Readiness mới ở `/home/tuanmac/nino_research/recovery100_training_readiness_20261117_02`. CLI `check-ready` trả về `readiness_pass=true`.

Đã khởi động campaign mới 20.000 bước từ đầu với service `nino-td3-recovery20k-20261117-02.service`. Lượt cũ dừng ở 1.082 bước được giữ riêng và không cộng vào replay mới. Chưa hoàn tất ngân sách training. Source mới có identity khác nên không tự resume checkpoint cũ.

[Tiến độ trực tiếp](/home/tuanmac/nino_research/recovery100_train20k_20261117_02/progress.json). [Request đã dùng](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/longtrain_recheck_2026-11-17/request.json). [Audit năm probe](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/longtrain_recheck_2026-11-17/readiness_audit.json).

Campaign mới giữ giới hạn đã chọn trong request. Warmup 1.000 bước, actor 100D sang residual chung 1D, tối đa 200 launches và 24 giờ. Giữ 2 GiB trống, giới hạn raw 4 GiB và checkpoint sáu bundle. Source phải giữ nguyên trong lúc chạy.

## Giới hạn

Readiness chỉ kiểm một layout development stage 0 mỗi nhóm. Không chứng minh tổng quát hóa hoặc TD3 thắng classical. Campaign vẫn chỉ chạy Sim.

Áp dụng Fix Root Causes để sửa ngay nơi nhận transition. Áp dụng Prove It Works bằng regression RED/GREEN, checkpoint SB3 thực và Gazebo thực.

## Attention

Review dùng cùng họ model được kế thừa vì các họ model trong cấu hình skill không có ở phiên này. Reviewer không phát hiện lỗi chặn trong bản sửa có phạm vi nêu trên. Đây không phải đồng thuận giữa nhiều họ model.
