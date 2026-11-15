# Rà soát dữ liệu train và dọn dung lượng — 12/11/2026

## 1. Kết luận hiện tại

Lượt **Goal100 research20k ngày 11/11 đã chạy đủ 20.000 transition** và kết thúc khoảng 11:57, trước hạn 14:00. Có **10.000 cập nhật critic, 5.000 cập nhật actor**, replay chứa đủ 20.000 transition. Đây là lượt học thực sự trên Gazebo, một training seed 11.

Job giữ trạng thái **failed** vì kiểm raw cuối phiên tìm thấy **một khoảng trống drive 54 ms ở episode 57**, vượt giới hạn 40 ms. Đánh giá frozen B0/TD3 chưa chạy. Chưa có kết quả so sánh chứng minh checkpoint này tốt hơn classical.

Đã dọn thêm **3,779 GiB**, còn khoảng **25,35 GiB trống** tại thời điểm kết thúc dọn. Giữ các mốc học cần đối chiếu, đầy đủ trace/replay và bằng chứng lỗi.

## 2. Đã xóa gì, giữ gì?

| Phần | Quyết định | Lý do |
|---|---|---|
| Goal100: raw của 99 episode thành công, QC đạt | Xóa 297 file raw lớn, khoảng 3,293 GiB | Đã kiểm offline trước khi dọn; trace vẫn giữ mọi observation/action/reward/outcome |
| Goal100: 28 episode còn lại | Giữ nguyên raw | Gồm 13 task failures, episode 57 lỗi QC, đoạn cuối chưa hoàn tất, mẫu đầu/cuối và mẫu từng layout tại các giai đoạn 0–5k/5–10k/10–15k/15–20k |
| Goal100 checkpoint 5k | Xóa bundle; lưu metadata và hash trong biên bản | Chưa có optimizer update; policy và optimizer state giống 10k. Giữ mốc 10k làm đối chứng trước học |
| Goal100 checkpoint 20k interrupted | Xóa bundle trùng; giữ 20k final | Nội dung model, optimizer và replay giống final; file ZIP có thể khác metadata đóng gói |
| Goal100 checkpoint 10k, 15k, 20k final | Giữ cả model, replay, identity và manifest | Lần lượt là trước học, giữa học, sau học; 20k có thể dùng để tiếp tục hoặc đánh giá sau khi review QC |
| Common103 v2 cũ: 10k warmup, 30k periodic, 45k periodic | Xóa bundle; lưu metadata/hash | Nhánh lịch sử đã có các mốc 20k, 40k, 40.860 và 50k cần giữ |
| Common103 v2: 50k interrupted | Xóa bản trùng model/replay với 50k final | Giữ final và bằng chứng evaluation thất bại |
| Checkpoint 20k/25k/30k của nghiên cứu common cũ ngày 07/11 | Giữ nguyên | Thuộc đợt phân tích offline khác, có kết quả so sánh riêng |
| Trace, TensorBoard, reset, world/URDF, error, evaluation, metadata | Giữ nguyên | Cần quan sát lịch sử, phân biệt lỗi dữ liệu với lỗi điều khiển |
| Short qualification Goal100 và dữ liệu robot thật | Giữ nguyên | 238/238 file qualification tiếp tục khớp hash; dữ liệu thật ngoài phạm vi dọn |

Tổng cộng **327 file**, gồm raw và **6 checkpoint bundle**, được xóa có danh sách. Giới hạn dọn chỉ gồm bốn job được ghi trong `retention_plan.json`; môi trường Python, build/install và các dữ liệu ngoài bốn job giữ nguyên.

Manifest gốc và trạng thái job **không sửa**. Sau retention, manifest không còn xác minh đầy đủ kho raw ban đầu. Trong job Goal100 có `storage_retention.json`; các job cũ có `storage_retention_checkpoints_20261112.json`, bổ sung cho receipt ngày 11/11. Không dùng tập raw còn lại để ước lượng success rate: nó cố ý giữ nhiều lượt lỗi. Thống kê dưới đây được tính từ **toàn bộ trace trước dọn**, gồm mọi failure và đoạn censored.

## 3. Quan sát lịch sử train

| Giai đoạn | Kết quả đã ghi | Ý nghĩa và giới hạn |
|---|---|---|
| Common ngày 07/11: 20k → 25k → 30k | Có checkpoint, trace và đánh giá riêng; phân tích offline đã chốt giữ classical cho sàn sạch/lịch dừng biết trước | Xem `NINO_TD3_OFFLINE_PHASE_REVIEW_2026-11-07.md`; không chuyển kết luận sang task gờ không biết |
| Common103 v2 integration ngày 08/11 | 280 transition, 264 critic, 132 actor; integration completed | Kiểm phần mềm và bộ đánh giá, quy mô nhỏ |
| Campaign common103 v2 ngày 09/11 | Startup episode 200 timeout; giữ checkpoint 20k | Budget 50k không có nghĩa đã học đủ 50k. Seed 22/33 chưa được coi là đã train |
| Recovery từ 20k | Có checkpoint 40k và 40.860; lỗi wheel source age 56 ms | Lỗi timing/data được giữ riêng |
| Common103 v2 tiếp đến 50k | Hoàn tất phần train; job failed vì feasibility/task gate khi evaluation | Có thêm dữ liệu evaluation sau job nằm ngoài manifest gốc, đã được ghi provenance trong review 10/11. Không gộp thành một benchmark mới |
| Goal100 short ngày 10/11 | 384 transition, 368 critic, 184 actor; B0 thành công 2/3; một development eval smoke thành công | Qualification, giữ cả B0 path failure; chưa là lợi ích nghiên cứu |
| Goal100 research ngày 11/11 | 20k transition, 10k critic, 5k actor; raw QC failed; evaluation chưa chạy | Task hiện tại, đủ để phân tích hành vi và thiết kế đánh giá tiếp |

Inventory `legacy_job_inventory.json` liệt kê 77 file job metadata (62 completed, 15 failed). Nó gồm cả bản sao metadata trong input bundle; **không phải 77 thí nghiệm độc lập** và không thay thế fresh raw audit của mọi run lịch sử.

## 4. Kết quả chi tiết Goal100 research20k

### Cấu hình thực thi

- Goal100: observation 100 chiều = 20 feature × history 5, policy 10 Hz.
- Action thực của engine: một common residual vận tốc, giới hạn danh nghĩa ±0,02 m/s; qua projection và backend velocity PI. Tên schema action trong profile kế thừa không thay đổi số chiều action thực của engine.
- MLP 256×256; learning rate actor/critic 0,0003; batch 256; replay capacity 100.000; warmup 10.000; policy delay 2.
- Tuyến thẳng 2 m, cruise danh nghĩa 0,20 m/s; bank development gồm sàn sạch, gờ cứng Ø6 mm tại 0,65 m và 1,05 m, luân phiên cố định. Vị trí gờ không vào observation.
- Validation 1,25 m/test 1,50 m được giữ riêng, chưa sử dụng. Cấu hình liệt kê seed 11/22/33 không phải bằng chứng đã chạy ba seed: lượt này chỉ seed 11.

### Outcome khi đang train

126 episode hoàn chỉnh: **113 thành công (89,68%)**, **6 path violation**, **7 stall**. Đoạn episode 126 còn 134 transition là đoạn **chưa hoàn tất**, không tính vào mẫu số success/failure. Các action lúc train có exploration và policy thay đổi theo thời gian.

| Layout | Success / complete | Tỷ lệ train | Trung bình RMSE đường, mọi episode hoàn chỉnh | Thời gian trung bình, chỉ episode thành công |
|---|---:|---:|---:|---:|
| Sàn sạch | 42/42 | 100% | 0,377 mm | 16,55 s |
| Gờ 0,65 m | 34/42 | 80,95% | 6,423 mm | 16,44 s |
| Gờ 1,05 m | 37/42 | 88,10% | 4,225 mm | 16,39 s |

RMSE là trung bình bằng trọng số từng episode; thời gian chỉ trên successful episodes, phải đọc cùng số failure. Không diễn giải episode thất bại kết thúc sớm là throughput tốt hơn.

| Nhóm theo bước kết thúc episode | Success / complete | Return trung bình |
|---|---:|---:|
| 0–5k | 28/30 | 5,321 |
| 5–10k | 28/31 | 4,839 |
| 10–15k | 29/34 | 4,057 |
| 15–20k | 28/31 | 4,868 |

Chưa có xu hướng success/return tăng đều khi bắt đầu optimizer. Các nhóm này khác policy, exploration và thời điểm reset; chưa phải đối chứng nhân quả hoặc đánh giá frozen checkpoint.

### Lỗi QC được xác định đến đâu?

Đọc lại 127 raw episode tái lập đúng kết quả QC gốc. Chỉ episode **57**, layout `dev_early`, có drive source stamp từ **2,562 → 2,616 s**, gap **54 ms**, tại khoảng **0,256 s sau đầu task**. Các lệnh reference ghi ở năm bước đầu episode vẫn zero trong warmup nguồn. Episode này cuối cùng đạt task.

Maximum source gap toàn phiên: wheel **9 ms**, IMU/truth **20 ms**, drive **54 ms**. Maximum tuổi dữ liệu drive tại các policy decision là **28 ms**. Kiểm khoảng trống raw và kiểm freshness tại decision trả lời hai câu hỏi khác nhau. Chưa xác định gap đến từ nhịp publish, vận chuyển hay đường ghi; số đo này chưa chứng minh motor mất điều khiển.

Ngưỡng 40 ms của job vẫn giữ nguyên và job vẫn failed. Không loại episode 57 hoặc cắt warmup sau khi thấy kết quả để đổi job thành pass. Nếu muốn một hợp đồng QC khác, cần đặc tả và kiểm chứng riêng.

### Độ đúng của pipeline học

Offline kiểm **20.000/20.000** replay rows: observation, next observation, requested action, reward, done/timeout đều khớp trace trong sai số số thực 2e-6. Reward bằng tổng các thành phần; không có NaN/Inf ở các array đã kiểm. Không phát hiện privileged truth đi vào guidance trong 20k trace.

Requested action khác accepted action ở **81,07%** bước theo tolerance 1e-5; con số này gồm warmup, ramp và lọc/projection, không có nghĩa 81,07% action bị chặn. **14,455%** requested action có |a| ≥0,99; gồm exploration. PI torque limit xuất hiện ở **3,605%** policy samples; đây là diagnostic mô phỏng.

## 5. Những thông số đánh giá chất lượng train

### A. Chất lượng dữ liệu và thực thi — kiểm trước

| Chỉ số | Dùng để quyết định gì? | Hiện trạng |
|---|---|---|
| Hash, đóng phiên, manifest/provenance | File có thay đổi hoặc thiếu ngoài retention có chủ đích không? | Đã đối chiếu file chọn xóa và file giữ; có receipt, manifest gốc bất biến |
| Source rate/gap, timestamp tăng, tuổi dữ liệu tại decision | Replay/outcome có dựa vào mẫu hợp lệ đúng thời điểm không? | Gap drive 54 ms làm raw QC failed; source age tại policy vẫn dưới 40 ms |
| Observation/action ABI, causal history | Train và inference có cùng feature/action, có dùng tương lai/GT sai chỗ không? | Trace 100D/1D, không scheduled stop feature, replay khớp đầy đủ |
| Requested → projected → executed reference | Actor yêu cầu gì, hệ thống chấp nhận gì, backend đã nhận reference nào? | Ghi riêng; executed reference mô phỏng chưa là xác nhận thực thi motor thật |
| NaN/Inf, replay count và optimizer counters | Có thật sự học và buffer có đúng transition không? | 20k rows, 10k critic, 5k actor, full replay check đạt |

### B. Chất lượng hoàn thành nhiệm vụ — nhóm chính

| Chỉ số | Cách đọc |
|---|---|
| Success rate của **frozen policy**, phân theo layout | Cần đến goal, toàn robot qua gờ, bám giới hạn và dừng liên tục; báo số lượt và failures, không chỉ % |
| Path RMSE và **maximum cross-track error** (m/mm) | RMSE cho sai số điển hình; max phát hiện một lần vượt giới hạn mà RMSE trung bình che mất |
| Heading RMSE/max, sai số goal | Phân biệt đi tới gần goal với đến đúng tư thế/vị trí |
| Thời gian hoàn thành, tiến độ và stall | Đọc cùng success rate; so sánh controllers trên cùng task, thời gian và tracking constraint |
| Clearance và stopping | Kiểm cả caster/bracket/chassis qua gờ; đạt điều kiện quiet liên tục, không chỉ encoder zero |
| Owner/fault/intervention/tilt/path violation | Giữ số sự kiện và outcome. Không dùng penalty reward để thay cơ chế kết thúc task |
| Rung/slip nếu là mục tiêu phụ | Nêu sensor/GT, bandwidth và cửa sổ. IMU peak không tự là tải hư hại; encoder tracking error không tự là slip |

Gate engineering đang có của Goal100: cross-track tối đa **40 mm**, goal distance **50 mm**, heading goal **15°**, dừng liên tục **2 s**, task deadline **25 s**. Đây là hợp đồng thí nghiệm mô phỏng, chưa phải yêu cầu nhà máy được chấp nhận. Bộ đánh giá frozen Goal100 research20k **chưa chạy**.

### C. Chỉ số học và chi phí — dùng chẩn đoán

| Chỉ số | Hiện trạng và giới hạn |
|---|---|
| Episode return và từng reward component | Có progress, path, heading, time, accepted action, change và outcome bonus/penalty. Bonus success +5/failure −10 làm return phân cụm rõ. Return không thay được outcome vật lý |
| Critic loss | TensorBoard ghi khoảng 0,366 →0,133, 16 điểm từ bước 10.412 tới 19.544. Giảm loss cho biết fit target của critic tốt hơn trên sample đã học; không chứng minh controller tốt hơn |
| Actor loss / Q | Actor loss khoảng −0,045 →−0,585 trong các điểm log. Actor tối ưu Q do critic ước lượng; giá trị âm hơn có thể đi cùng Q lạc quan. Muốn tin ranking cần kiểm với rollout return thực |
| Action magnitude/change, projection, torque limit | Quan sát residual có quyền tác động không, có thường xuyên bị giới hạn hoặc tạo dao động không |
| Sample efficiency | Outcome đánh giá frozen theo tổng transition và số update; 20k transition không đồng nghĩa 20k optimizer update do warmup |
| Wall time, fps, RAM và dung lượng | Lượt vừa rồi khoảng 7.413 s (~2 giờ 3 phút); TensorBoard log 2–3 transition/s. Đây là chi phí, không phải thước đo learned benefit |
| Độ biến thiên seed/layout, checkpoint | Cần training seed độc lập và dữ liệu test không dùng tune; lượt này một seed, ba development layouts |

Learning rate, gamma, tau, batch size, history length và action scale là **tham số cấu hình**. Chúng ảnh hưởng kết quả nhưng không phải điểm chất lượng để nghiệm thu train.

### Cách chấm hiện tại

| Trục đánh giá | Kết luận |
|---|---|
| Train loop/optimizer/replay | **Đã thực thi và kiểm đủ 20k** |
| Raw telemetry QC toàn job | **FAIL** |
| Outcome lúc train | **Có số mô tả, 113/126**, gồm exploration và policy thay đổi |
| Frozen policy tốt hơn baseline | **Chưa biết — chưa chạy evaluation** |
| Tổng quát hóa và sim-to-real | **Chưa kiểm** |

Không gộp các trục thành một điểm “train tốt 90/100”. 89,68% ở đây là tỷ lệ thành công khi train, không phải chất lượng dataset hay độ tin cậy triển khai.

## 6. Việc tiếp theo có giá trị thông tin cao

1. **Review đường publish/ghi drive quanh gap episode 57**, đối chiếu source/receipt, lệnh zero và control diagnostics trong raw đã giữ; xác định câu hỏi mà gate raw 40 ms cần bảo vệ. Nếu cần đổi measurement contract, làm một phiên bản độc lập có fault fixture, giữ kết quả cũ failed.
2. Sau khi measurement readiness được xác minh, **đánh giá frozen checkpoint 20k và B0 trên ba development layouts** theo protocol đã chuẩn bị; giữ mọi task failure. Checkpoint 10k/15k vẫn có để làm ablation/chọn checkpoint nếu cần một protocol riêng.
3. Chỉ cân nhắc training bổ sung/tune hoặc thêm seed khi evaluation chỉ ra nút thắt cụ thể. Báo cả effect và uncertainty giữa các run; không đổi đồng thời reward/history/learning rate/action scale vì một đường loss đẹp.

Lượt rà soát này không khởi động thêm Gazebo/training. Artifact phần mềm mới chỉ đọc dữ liệu offline và thực hiện retention có danh sách.

## 7. Artifact để quan sát và kiểm lại

- [Biểu đồ training](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/training_review_retention_2026-11-12/training_overview.png>): return, path RMSE, duration, loss, gap theo episode và success theo 5k bước.
- [Assessment có cấu trúc](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/training_review_retention_2026-11-12/assessment.json>).
- [Full trace review](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/training_review_retention_2026-11-12/training_trace_review.json>): toàn bộ episode, reward components và layout/window summaries.
- [Raw QC review](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/training_review_retention_2026-11-12/raw_qc_review.json>): counts/gaps của 127 episode trước retention.
- [Retention plan và kết quả](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/training_review_retention_2026-11-12/retention_plan.json>): file, hash, metadata checkpoint, canonical ZIP member comparison, bytes và thời gian dọn.

Nguồn nhận định là file Nino đã đọc và tính lại: `job.json`, `training_result.json`, `source_qc.json`, `training_trace.jsonl`, checkpoint final20k/replay, raw episode và TensorBoard. Các mức ưu tiên bước tiếp là đề xuất dựa trên bằng chứng này; chưa bổ sung kết quả thực nghiệm mới.
