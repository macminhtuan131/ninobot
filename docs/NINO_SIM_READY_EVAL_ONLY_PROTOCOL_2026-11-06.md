# Eval-only A seed11 với reset có drive ACK

06/11/2026 · Protocol riêng, một attempt; không mở lại Coverage V1/V2.

## Release đã kiểm trước physics

- Runner `residual_ready_eval_only.py`, GUI profile 19; 78 kiểm tra phần mềm/GUI đạt.
- Fingerprint: `d75036f1a15431c16fc92eb82e34319652b17e05483a81ea86455c26f08eec3d`.
- Root riêng: `~/nino_research/sim_ready_eval_only_v1`.
- A Gaussian seed11 hoàn tất 1.024 transitions, 960 critic / 480 actor updates;
  checkpoint SHA `40f676c7464a94440d57cda34c6eb277ba67d6fb7a87760f8bc363af253a6166`.
- Qualification manifest `0c569728eb935dd2d6f6bd3ac1b1a0ca92fbfda313fff553e894473e57564aeb`.
- Load/predict deterministic đã kiểm không đổi policy, targets, optimizer,
  counters và sampler. Không load C chưa hoàn tất.

## Ma trận và giới hạn

| Thứ tự | Arm | Source stop | Ticks tối đa |
|---|---|---:|---:|
| 1 | B0 | 6 s | 140 |
| 2 | A Gaussian seed11 | 6 s | 140 |
| 3 | Classical scheduled | 6 s | 140 |
| 4 | Classical scheduled | 8 s | 140 |
| 5 | A Gaussian seed11 | 8 s | 140 |
| 6 | B0 | 8 s | 140 |

Tổng 6 fresh launches / 840 ticks, deadline 1.800 s; 0 train, optimizer,
probe, retry, smoke ngoài budget hoặc hardware. Một lỗi đóng mọi slot còn lại.
Mọi arm dùng DriveReadinessBackend đã qualification, quiet liên tục 0,5 s
và drive ACK mới trước task epoch; cap settling 5 simulation seconds.

Giữ nguyên clear-box factory lab, nominal 0,2 m/s, common residual ±0,005 m/s,
10 Hz, ABI 103D/1D/history5, task/measurement gates. Không thử vật cản hoặc
factory mixed map. Raw inhibited row được giữ và fail trước success validator;
không biến proposal thiếu thành zero.

## Estimand và cách quyết định

Primary: whole-14s native velocity RMSE; GT-header 20 ms và dịch +10 ms báo
riêng. So A/B0 và A/classical theo từng stop plan, không gộp với eval cũ dùng
reset khác. Một seed và một run/condition chỉ cho screening mô tả, không CI,
power, equivalence, generalization hoặc kết luận TD3 đã hội tụ.

- A tốt hơn cả hai baseline ≥5% ở cả stop plans và ba grids: candidate mô tả,
  còn cần holdout riêng; 5% là rule nghiên cứu đề xuất, chưa là yêu cầu ứng dụng.
- A không tốt hơn classical trên mọi grid/stop: không mặc định mở train dài
  cho checkpoint và bài thử này; giữ classical, xem lại giá trị bài toán.
- Đổi dấu theo grid, effect nhỏ hoặc phụ thuộc điều kiện: unknown; không tự tăng N.
- Failure task/measurement: đóng study, giữ artifact; không tính partial thành outcome.

Kết thúc phải kiểm manifest/hash, source age, observer overlap, physics ACK,
closure và actor/optimizer/sampler/checkpoint bất biến; sau đó đóng release.
GUI chỉ trình bày số đo đã seal như kết quả nghiệm thu.
