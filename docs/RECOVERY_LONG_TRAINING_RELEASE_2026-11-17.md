# Đã mở campaign TD3 recovery 20k trong Gazebo

> Cập nhật sau release. Campaign đầu đã dừng sạch tại 1.082 steps để sửa phân loại truncation. Xem [bản rà soát mới](RECOVERY_LONG_TRAINING_RECHECK_2026-11-17.md). Các trạng thái đang chạy bên dưới là snapshot lịch sử.

Mục tiêu là xử lý các lỗi chặn training dài và khởi chạy một campaign thực. Campaign hiện chạy qua dịch vụ user systemd `nino-td3-recovery20k-20261117-01.service`. Đây là nghiên cứu mô phỏng stage 0, không phải triển khai robot thật hoặc kết luận TD3 thắng classical.

## Những gì đã kiểm chứng

- 252 tests liên quan đạt trong lượt kiểm cuối. Log ở [tests_final.log](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery_longtrain_2026-11-17/tests_final.log).
- Readiness mới đạt cả năm nhóm, gồm 1358 transition mô phỏng toàn nhiệm vụ. Mỗi nhóm có một lượt stage 0, không phải phép chứng minh độ tin cậy thống kê.
- Source QC đạt, PI dt tối đa 2 ms. Gate PI vẫn 4 ms, source vẫn 40 ms, physical goal vẫn 5 cm.
- Fixture TD3 1.200 bước qua warmup có 200 critic và 100 actor updates. Chạy liền và ngắt tại 1.040 rồi tiếp tục khớp policy, optimizer, replay và RNG. Đây là kiểm phần mềm, không phải tái lập vật lý bit exact.
- Snapshot ban đầu của campaign thực đã xác minh 205 replay rows. Warmup 1.000 bước có thể chưa tạo optimizer updates tại thời điểm snapshot này. [Tiến độ trực tiếp](/home/tuanmac/nino_research/recovery100_train20k_20261117_01/progress.json) là nguồn hiện trạng.

| Nhóm stage 0 | Bước probe | Sai số đích, mm | Moving speed RMSE, m/s | Task và QC |
|---|---:|---:|---:|---|
| clean | 272 | 8.37 | 0.005388 | Đạt |
| short_obstacle | 272 | 5.71 | 0.008116 | Đạt |
| pothole | 271 | 6.13 | 0.006156 | Đạt |
| mixed | 271 | 8.57 | 0.008886 | Đạt |
| slope | 272 | 21.96 | 0.010417 | Đạt |

## Kiểm campaign thực sau khởi chạy

Episode đầu đã đóng và ghi checkpoint `/home/tuanmac/nino_research/recovery100_train20k_20261117_01/checkpoints/step_000272_d9063f5e`. Đã kiểm độc lập hashes của 8 file trong bundle, nạp model và replay, kiểm toàn bộ giá trị hữu hạn, và chạy inference observation 100D cho action 1D hợp lệ. Bundle chứa 272 transition. Chưa thực hiện resume vật lý trên bundle này.

Snapshot kế tiếp ghi 378 bước đã xác minh, service vẫn active. Actor/critic có thể vẫn bằng zero trong warmup 1.000 bước. Đây là campaign đang chạy, chưa phải kết quả hoàn tất 20.000 bước. [Audit checkpoint thực](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery_longtrain_2026-11-17/live_checkpoint_audit.json).

## Sửa các lỗi chặn training

1. Loại đường ghép sàn nhân tạo xuyên qua vệt bánh trái. Gộp các rectangle phẳng theo Y trước rồi X. Hõm, gờ, friction và gain giữ nguyên. Raw contact xác nhận bánh đi trên mảng phẳng chung ở vùng từng kẹt. Xem [kiểm runtime độc lập](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery_longtrain_2026-11-17/TERRAIN_RUNTIME_REVIEW.md).
2. Đồng bộ stop radius ở follower với cấu hình. Khoảng dừng ước lượng hiện 1 cm là tuning cổ điển, không phải hạ gate đích vật lý.
3. Tách readiness đo lường khỏi thắng bài. Thất bại vật lý có phân loại và dữ liệu hợp lệ được dùng cho RL. Lỗi nguồn, clock, owner, driver hoặc terminal không phân loại vẫn chặn.
4. Thêm runner campaign riêng. Không đổi ngân sách và ý nghĩa của smoke 384 hoặc 640 bước.
5. Replay chứa đủ tổng ngân sách, tránh tràn buffer 2.048 mẫu của smoke. Episode đầy đủ tối đa 400 bước. Campaign luân phiên cả năm nhóm và không tự lên stage chưa được kiểm.
6. Checkpoint lưu sau update optimizer, tại ranh giới episode. Giữ latest mỗi episode cùng các milestone 5k. Model, optimizer, replay, RNG, scheduler, source identity và QC được kiểm khi tiếp tục.
7. Nén raw và kiểm SHA của nội dung archive trước khi bỏ bản chưa nén. Giữ failures. Chỉ giảm raw thành công thuộc campaign mới với receipt có hash. Resume kiểm evidence còn giữ và các receipt giảm lưu trữ hợp lệ.
8. Có progress JSON, TensorBoard, xử lý dừng tại ranh giới episode và báo trạng thái lỗi đúng. Dịch vụ nền độc lập với terminal.

## Campaign đang chạy

- Output ở `/home/tuanmac/nino_research/recovery100_train20k_20261117_01`.
- Ngân sách tổng 20.000 transition, tối đa 200 launches và 24 giờ. Không reset ngân sách khi resume.
- Profile có warmup 1.000, batch 256, learning rate 0,0003, mạng hai tầng ẩn, mỗi tầng 256 neuron, noise 0,1. Cấu hình này chưa tune.
- Actor dùng 100D history và residual vận tốc chung 1D. Follower giữ quyền yaw. Truth và geometry không vào actor.
- Giữ tối thiểu 2 GiB trống, cap raw retention 4 GiB và tối đa 6 bundles theo request đã kiểm.
- Request ở [request.json](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery_longtrain_2026-11-17/request.json), log ở [train.log](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery_longtrain_2026-11-17/train.log).

```bash
systemctl --user status nino-td3-recovery20k-20261117-01
cat /home/tuanmac/nino_research/recovery100_train20k_20261117_01/progress.json
```

Dừng có checkpoint bằng file `STOP` trong output hoặc gửi SIGTERM tới service. Runner hoàn tất episode hiện tại rồi lưu. Không sửa source trong lúc campaign dùng source đã đóng băng.

## Nguyên tắc và giới hạn

Fix Root Causes đặt sửa đổi ở đường ghép sàn và cấu hình follower. Attack the Premise buộc kiểm raw trước khi coi một lượt thành công là đủ lặp lại. Model the Domain tách request, readiness, scheduler và trạng thái checkpoint. Sequence Work into Verifiable Units giữ test trước khi đóng source và chạy probe. Prove It Works yêu cầu actual Gazebo, actual replay và dịch vụ đang hoạt động.

Chưa kết luận policy học tốt hơn baseline, đã hội tụ, tổng quát hóa vị trí vật cản mới hoặc dùng được trên robot thật. Những giới hạn đó không chặn campaign nghiên cứu hiện tại.
