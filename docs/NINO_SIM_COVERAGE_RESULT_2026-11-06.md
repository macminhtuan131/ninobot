# Study critic/coverage V1: đóng do lỗi metadata ở tick đầu

06/11/2026 · Chạy từ nút GUI sau [release](NINO_SIM_COVERAGE_RELEASE_PROTOCOL_2026-11-06.md).

## Kết luận

**Đợt đã đóng, không chạy bù.** Đây là lỗi wiring phần mềm trong wrapper
training: thiếu `qualification_condition` mà validator yêu cầu. Chưa có
learner hoàn tất hoặc phép so sánh TD3 mới; không kết luận coverage/TD3 tốt
hay kém từ lượt này. Classical/B0 vẫn là reference theo comparison trước.

| Hạng mục | Thực tế |
|---|---:|
| Learner khởi động / hoàn tất | 1 / 0 |
| Gazebo launches | 1 / tối đa64 |
| Control attempt / raw trace | 1 / 1 |
| Transition hợp lệ vào replay | 0 |
| Critic / actor optimizer steps | 0 / 0 |
| Evaluation | 0 / 16 |
| Launch slots còn lại | 63, đóng |
| Hardware actions | 0 |

Budget V1 đã tiêu thụ ở mức attempt/launch; không gọi0replay là budget chưa
tiêu thụ. Release hiện đã đóng lại. Năm learner chưa bắt đầu và16evaluation
đều đóng; phần còn lại của learner đầu không được resume.

## Chuỗi lỗi và audit

1. GUI khởi chạy worker; READY/namespace/reset đạt. Arm A, seed11 chọn
   request warmup đầu tiên; shared window vẫn đóng, không probe.
2. Gazebo đã thực hiện một control interval100ms. Wrapper lưu control
   attempt và raw trace trước validation.
3. `verify_transition` đọc `row['qualification_condition']['source_stop_s']`,
   nhưng wrapper V1 không thêm field đó. Lỗi `KeyError('qualification_condition')`
   xảy ra trước khi environment trả transition về SB3.
4. Partial model/replay được lưu; actor bằng initial policy, num_timesteps0,
   n_updates0, replay size0, sampler đã chọn1request. Backend/observer đóng
   đúng lifecycle và ACK; manifest giữ nguyên failure.

Kiểm44file hash đạt. Chín boundary checks đều có support ở hai reader,
joint age tối đa0ms **trong các check này**. Mỗi reader nhận2.470 mẫu,
2.467source stamps chung không lệch payload; counts không chứng minh
loss-free toàn hệ thống.12physics requests gồm setup và control đều ACK,
đúng iterations, retry0;2parameter readbacks được giữ. Đây không là lỗi
measurement đã quan sát hoặc bằng chứng cần đổi QoS/gain/current.

Artifact:
`~/nino_research/sim_coverage_study_v1/20261106T103952320046Z_sim-coverage-study`.
Manifest SHA256:
`3f73d59ddfc5d3381ae202561113e864e75379e4618adba1c42e8ff965df7fab`.
Fingerprint vẫn:
`1cd68b11dea8aee0302094294d89636276df23d6dfc2dc314af1c4a6433d89be`.
Worker và các source trong fingerprint không sửa sau launch.

## Correction riêng, chỉ offline

`coverage_qualification_adapter.py` chuẩn bị proxy cho runner tương lai:
gắn metadata arm/seed/source-stop từ cấu hình **trước action**, rồi chuyển
nguyên request tới backend. Không dùng GT/contact; không đổi observation,
reward, action, PI, limits hoặc gate. Conflict metadata bị từ chối, không
ghi đè. API `prepared_training_environment` tái dùng wrapper V1 qua proxy,
chưa được nối vào một runner/release Gazebo mới.

Regression dùng bản sao raw first-tick có provenance: validator thật tái
hiện đúng KeyError; chỉ thêm metadata thì validator/feasibility giữ nguyên
đều đạt. Test riêng qua wrapper thật với synthetic guidance/support envelope
kiểm tuyến ghép field; envelope tổng hợp không phải dữ liệu sensor thật.

Preflight45tests trước launch kiểm sampler/replay/checkpoint và coordinator,
nhưng chưa phủ đầy đủ đường `training wrapper → row → validator`. Lỗi này
cho thấy số tests đạt không tự chứng minh wiring dưới Gazebo. Gate tiếp theo
phải có regression tuyến này, không chỉ mock validator hoặc test adapter thấp.

GUI đã hiển thị raw attempt khác replay/update, quarantine partial, số liệu
QC có binding manifest và slot chưa chạy đã đóng. Dataset thật vẫn cutoff
02/11; không có thu hardware mới.

Kiểm sau correction: **6 regression tests +48GUI tests đạt (54)**; build
`nino_rl` và `nino_pi` đạt, bản cài adapter/GUI khớp source. Candidate hash:
`6997d055adf70b7ca08d2069c3c4171574a61c884d618ddcdca18ace86bcdaa7`.
Đây là hash adapter/tests/fixture +pin worker lỗi, không phải release V2.
Chi tiết: [verification](NINO_SIM_COVERAGE_VERIFICATION_2026-11-06.json).

## Bước tiếp theo

Chuẩn bị [protocol V2 riêng](NINO_SIM_COVERAGE_V2_NEXT_2026-11-06.md), nối
adapter vào runner có identity/fingerprint mới, kiểm software đủ tuyến.
Chỉ sau release/budget mới mới xem xét Gazebo; không mở lại V1 hoặc dùng
63slot đóng làm slot miễn phí. Chưa cần real bag mới cho correction này.
