# Dọn episode Sim sau đánh giá — 14/11/2026

## 1. Đã làm

Đã giải phóng **3.372 GiB** theo kích thước file ròng. Dung lượng trống sau dọn và kiểm tra khoảng **25.88 GiB**. Không chạy thêm training, simulation hoặc thao tác robot thật.

| Phần dữ liệu | Xử lý |
|---|---|
| Raw của 12 lượt evaluation thành công, đã QC/đối chiếu outcome | Xóa 36 file raw lớn; giữ toàn bộ native decision trace, reset, outcome, QC, log và metadata |
| Raw thành công đại diện của B0 và 20k trên ba layout | Giữ sáu lượt: slot 1, 2, 5, 6, 10, 17 |
| Năm task failures và một startup unknown của evaluation | Giữ nguyên toàn bộ dữ liệu |
| Common103 lịch sử: raw chẩn đoán và environment trace | Nén lossless 206 file sang `.jsonl.gz`; giải nén kiểm SHA256 trước khi xóa bản chưa nén |
| Training trace, TensorBoard, checkpoint của các run cũ | Giữ nguyên |
| Goal100 train20k, checkpoint 10k/15k/20k và replay | Giữ nguyên toàn bộ phần đang có sau retention 12/11 |
| Goal100 short qualification, dữ liệu thật, source/config | Giữ nguyên |

Giữ các checkpoint 10k/15k/20k để còn tái hiện so sánh và tiếp tục có kiểm soát khi cần. Không xóa model dựa riêng vào một pilot nhỏ. Nhóm raw còn lại là tập chẩn đoán được chọn, không phải tập ngẫu nhiên để tính lại tỷ lệ thành công.

## 2. Đánh giá episode trước khi dọn

Đã đọc lại **88,859 transition**, gồm **632 episode hoàn chỉnh** của năm job Common lịch sử. Kiểm timestep tăng nghiêm ngặt, reward hữu hạn và tổng reward components khớp reward. Giữ cả các đoạn cuối chưa hoàn tất.

| Job lịch sử | Transition trong trace | Episode hoàn chỉnh | Task success theo contract cũ | Task fail | Đoạn cuối chưa hoàn tất (transition) |
|---|---:|---:|---:|---:|---:|
| `20261109T095403402007Z_common_v2_seed11_train` | 20,860 | 149 | 139 | 10 | 0 |
| `20261110T003411337787Z_common_v2_seed11_train` | 10,000 | 71 | 62 | 9 | 60 |
| `20261107T054154365880Z_common_train` | 20,000 | 142 | 142 | 0 | 120 |
| `20261107T080414816378Z_common_train` | 10,000 | 71 | 71 | 0 | 60 |
| `20261109T040100212808Z_common_v2_seed11_train` | 27,999 | 199 | 176 | 23 | 139 |

Các hàng là job/đoạn tiếp tục học, có thể cùng seed và checkpoint cha; không phải năm training seed độc lập. Số transition trong trace không bảo đảm checkpoint cuối chứa toàn bộ số đó. Đây là mô tả policy thay đổi khi train, không phải benchmark frozen. Success của task Common cũ có lịch dừng biết trước không thay thế success của Goal100 qua gờ không biết. Job failed vẫn giữ failed, kể cả khi kiểm reward/trace ở đây đạt.

Đợt evaluation Goal100: tính lại **3,648 decision** trên **23 lượt hợp lệ**, kiểm path RMSE/max, heading RMSE, return và outcome khớp ledger. Slot startup không có decision được giữ unknown. Trước dọn, 789/789 file của manifest evaluation khớp hash. Kết quả đối chiếu action deterministic từ checkpoint và phân tích gap trước đó vẫn được lưu nguyên.

| Controller | Success | Task fail | Unknown |
|---|---:|---:|---:|
| B0 | 5/6 | 1 | 0 |
| TD3 10k | 5/6 | 1 | 0 |
| TD3 15k | 4/6 | 2 | 0 |
| TD3 20k | 4/6 allocated | 1 | 1 |

**Quyết định nghiên cứu giữ nguyên:** giữ B0 làm tham chiếu; chưa đầu tư thêm train dài. Ưu tiên review goal-stop/odometry và startup freshness. Không có thí nghiệm controller mới trong lượt dọn.

## 3. Kiểm chứng sau dọn và giới hạn

- **3,974 file được bảo vệ khớp hash** sau dọn; checkpoint/replay và training trace không thay đổi.
- Evaluation còn **753 file thuộc manifest gốc** khớp hash; **36 file thiếu có chủ đích**, được liệt kê từng đường dẫn/bytes/hash/slot trong receipt. Không có file thiếu ngoài danh sách.
- 206 archive khớp hash; trước khi unlink đã giải nén toàn bộ và kiểm hash/byte count bằng bản gốc.
- GUI catalog và Sim review vẫn load; qualification và preflight đánh giá 10k/15k/20k vẫn đạt readiness.
- Manifest, ledger, trạng thái job và báo cáo thực nghiệm gốc không sửa để hợp thức hóa retention.
- Raw của 12 lượt thành công đã xóa không thể đọc lại toàn bộ. Vẫn có native observations/actions/reward/outcome của 23 lượt hợp lệ, log lỗi startup của lượt unknown và báo cáo QC trước dọn; không dùng native trace để giả lập lại nguồn sensor 500 Hz.
- Công cụ audit cũ yêu cầu tất cả raw sẽ báo missing sau retention. Dùng `verify_retained.py` để kiểm manifest cùng receipt; đó là kiểm tập giữ lại, không phải pass cho toàn kho raw gốc.
- Raw/environment trace Common cũ có thể khôi phục không mất dữ liệu từ file `.jsonl.gz` cùng thư mục bằng `gzip -dk <file.jsonl.gz>` khi đủ dung lượng. Training trace thường dùng trong GUI vẫn ở dạng gốc.
- Phạm vi dọn được chốt trước khi xóa, chỉ bốn tên stream chẩn đoán; không xóa thư mục run, code, dependencies hoặc dữ liệu robot thật.

## 4. Artifact

- [Kết quả trước dọn theo từng slot](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_episode_retention_2026-11-14/evaluation_before_retention.json).
- [Review toàn bộ training trace lịch sử](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_episode_retention_2026-11-14/legacy_trace_review.json).
- [Danh sách và hash từng file xử lý](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_episode_retention_2026-11-14/retention_result.json).
- [Kiểm chứng sau dọn](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_episode_retention_2026-11-14/retention_verification.json).
- [Kiểm readiness sau dọn](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_episode_retention_2026-11-14/readiness_after.json).
- [Báo cáo so sánh frozen đầy đủ](NINO_GOAL100_GAP_AND_FROZEN_CHECKPOINT_EVALUATION_2026-11-14.md).
