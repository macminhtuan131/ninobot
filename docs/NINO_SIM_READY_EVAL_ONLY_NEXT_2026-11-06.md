> **Đã triển khai và đóng 6/6 ngày 06/11:** xem [kết quả](NINO_SIM_READY_EVAL_ONLY_RESULT_2026-11-06.md) và [protocol đã chạy](NINO_SIM_READY_EVAL_ONLY_PROTOCOL_2026-11-06.md). Draft bên dưới giữ lịch sử; release đã đóng, không chạy lại.

# Kế tiếp: eval-only A seed11 / B0 / cổ điển cùng reset readiness

06/11/2026 · **Draft, chưa runner/release hoặc budget eval mới.**

## Lý do và tài nguyên

Qualification reset/zero đã đạt2/2 nhưng chưa có outcome motion. A seed11 của
V2 có1.024valid training transitions/replay vàcheckpoint parity; C chỉ840,
studyV2đãđóng. Dùng A để screening eval-only có information gain/chi phí tốt
hơn train lại6learner trước khi biết checkpoint hoàn tất có ích không.
Chọn A vì nó hoàn tất, không vì thấy reward/eval tốt.

Checkpoint được giữ:
`~/nino_research/sim_coverage_study_v2/20261106T111842753138Z_sim-coverage-v2-study/A_gaussian_seed_11/model.zip`.

SHA256 `40f676c7464a94440d57cda34c6eb277ba67d6fb7a87760f8bc363af253a6166`.
Identity/model fingerprint vẫn V2; không convert ABI hoặc resume optimizer.

## Ma trận đề xuất riêng

- A seed11/B0/Classical_scheduled × stop6/8 =**6fresh launches ×140ticks**,
  tối đa840eval ticks;0train/optimizer/probes/retry/hardware.
- Thứ tự đề xuất: B0–6,A–6,Classical–6,Classical–8,A–8,B0–8.
- Tất cả dùng cùng `DriveReadinessBackend`, cap5s/quiet0,5s/driveACK trước
  task epoch; actor103D/1D/history5,10Hz,common±0,005m/s và cùng preview/window.
- Factory clear-box nominal0,2m/s; chưa gờ/mixed course hoặc unseen layout.
- Không load C partial làm candidate, không thay projection/reward/gain/QoS.

## Các bước triển khai trước physics

1. Runner/root/identity/fingerprint riêng; pin qualification manifest/source,
   A checkpoint/V2 identity và runtime. Không sửa frozen modules đã chạy.
2. Kiểm deterministic predict không đổi policy/targets/optimizer/counters,
   sampler RNG hoặc checkpoint. Guard input bị inhibit trước success validator;
   raw/failure giữ lại, không thay null thànhzero.
3. Kiểm path reset→first decision→row→validator→summary bằng fixture; source
   không dùngGT/contact cho actor/guidance. Tách baseline/actual/GT scoring.
4. Review release đúng6launches/840ticks, một attempt; first rollout tích hợp
   nằm trongbudget, không smoke ngoài. Một failure đóng phần còn lại.

## Outcome và điểm dừng

Giữ whole14s native vRMSE làm primary, GT20ms/dịch10ms riêng, arrival/tracking/
stop/estimator/support constraints như parent. Báo paired descriptive deltas
theo stop plan, không CI hoặc power giả từ một seed/một run mỗi condition.
Reset mới có thể đổi trạng thái ban đầu; paired conditions không là exact-state
branching. Không gộp ranking với eval cũ dùngreset khác.

- Chỉ gọi **descriptive candidate** nếu task/measurement đạt và A tốt hơnB0/
  cổ điển nhất quán trên các grids;5% vẫn chỉ là rule nghiên cứu được review.
- Nếu A không tốt hơn cổ điển: không mở train dài/ma trận mới cho checkpoint
  này theo mặc định. Giữ classical và cân nhắc giá trị bài toán tiếp theo.
- Failure, effect nhỏ hoặc đổi dấu theo grid: UNKNOWN, không tăngN/hạgate.
- Một seed không trả lời lợi ích probe C, hội tụ TD3, generalization hoặc
  sim-to-real. Không suy qualification/arrival thành giảm contact risk.

**Việc ngay:** triển khai eval-only runner cùng software parity/release pins;
chưa cần thêm real data, observation history dài hơn hoặc tune hyperparameter.
