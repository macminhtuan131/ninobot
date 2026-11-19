# Campaign TD3 50k và đánh giá chất lượng

## Trạng thái và phạm vi

Đã khởi động campaign mới 50.000 transition trong Sim. Source, reward, history, action scale và các gate dữ liệu giữ nguyên so với bản đã qua năm probe Gazebo. Observation 100D, residual vận tốc chung 1D, cùng causal follower và wheel PI. Chỉ chạy development stage 0 của sàn sạch, gờ, hõm, mixed và dốc. Không tự tăng stage và chưa kiểm tổng quát hóa qua mọi vị trí vật cản.

Lượt 20k trước đã dừng sạch ở 2.702 transition, 1.702 cập nhật critic và 851 cập nhật actor. Checkpoint cũ đã kiểm hash, load model/replay và inference. Contract resume khóa request nên lượt 50k bắt đầu từ đầu với identity riêng, không đổi nhãn checkpoint cũ thành checkpoint 50k.

## Hai công việc song song

1. Training Gazebo dùng service `nino-td3-recovery50k-20261117-01.service` và output `/home/tuanmac/nino_research/recovery100_train50k_20261117_01`.
2. Phân tích offline dùng dữ liệu đã đóng của lượt trước, chạy song song với training. Công việc này đã hoàn tất, không chạy thêm Gazebo và không sửa source training.

[Tiến độ training](/home/tuanmac/nino_research/recovery100_train50k_20261117_01/progress.json). [Báo cáo offline](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery50k_2026-11-17/offline_quality/REPORT.md).

## Request và tài nguyên

- Tổng 50.000 transition, replay chứa đủ ngân sách.
- Warmup 1.000 bước, learning rate 0,0003, batch 256, mạng hai tầng 256 neuron.
- Tối đa 400 launches và 24 giờ theo request. Giới hạn episode 400 bước.
- Checkpoint tại ranh giới episode, giữ milestone theo các mốc 5k và hai bundle mới nhất, giới hạn 12 bundle.
- Giữ tối thiểu 2 GiB trống. Cap raw retention 4 GiB, giữ failures và summary/hash. Không xóa dataset cũ.
- Source phải giữ nguyên khi campaign đang chạy.

[Request thực tế](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery50k_2026-11-17/request.json). [Training log](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery50k_2026-11-17/train.log).

## Chất lượng hiện biết

Phân tích độc lập giữ đủ 10 episode đã đóng của lượt 2.702 bước. Cả 10 thành công và source QC đạt. Mỗi nhóm có hai lượt, dùng cùng seed/layout development và action exploration khác nhau.

Goal error trong khoảng 3,08 đến 39,19 mm. Cross-track RMS trong khoảng 1,27 đến 12,57 mm. Moving speed RMS trong khoảng 0,0123 đến 0,0239 m/s. Đây là kết quả training, chưa là so sánh deterministic với classical.

Có action saturation và projection sửa residual trong các phase nhất định. Diagnostic này là câu hỏi cho evaluation, chưa là lỗi thuật toán đã được chứng minh. Không đổi nhiều tham số cùng lúc để đuổi theo reward.

## Đánh giá tự động sau 50k

Đã xếp hàng service `nino-td3-recovery50k-eval-20261117-01.service`. Watcher chỉ bắt đầu evaluation sau khi đủ 50.000 bước, replay/QC/source đạt, job đóng sạch, manifest đã ghi và service training kết thúc thành công. Nếu training lỗi hoặc dừng sớm, watcher báo lỗi và không gọi đó là kết quả 50k.

Protocol chọn sẵn checkpoint cuối 50k, không chọn theo reward validation. Chạy năm nhóm validation stage 0 với classical zero residual và TD3 deterministic, tổng 10 lượt. Hai arm dùng cùng world/config/start/seed và đổi thứ tự giữa các nhóm. Fresh launch cùng điều kiện không phải snapshot vật lý giống hệt nhau. Không có update optimizer hoặc exploration trong evaluation.

Các lượt Gazebo chạy tuần tự theo global lock. Phân tích offline mới là việc được chạy song song với training. Không chạy hai Gazebo cạnh tranh control timing.

Báo cáo số lượt thành công, lý do thất bại, source QC, goal error, path/heading RMSE, speed RMSE và thời gian từng cặp. Giữ failure vật lý. Lỗi nguồn hoặc lifecycle làm kết quả unknown và dừng batch. Không thay bằng zero hoặc chạy bù âm thầm.

Output dự kiến là `/home/tuanmac/nino_research/recovery100_eval50k_20261117_01/results.json`. Nó chưa tồn tại trước khi evaluation chạy. [Trạng thái hàng đợi](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery50k_2026-11-17/evaluation_queue.json).

## Kiểm thử và giới hạn

Handoff tests đã kiểm đủ ngân sách, clean closure, replay/source QC và chặn paused/failed/thiếu cập nhật. Evaluator đã qua self-test action ABI, deterministic inference, rollout fixture và phân loại terminal. Chưa chạy evaluation 10 lượt khi training còn đang chạy.

Một seed training và một cặp mỗi nhóm validation chỉ cho đánh giá thăm dò. Clean/slope có thể lặp geometry development; không gọi đó là kiểm vật cản mới. Không khẳng định TD3 tốt hơn classical từ reward hoặc số bước. Giữ classical nếu TD3 mất task success hoặc trade-off bám đường/tốc độ/thời gian không có lợi. Không tự gia hạn ngân sách hoặc đưa policy lên hardware.
