> **Mới nhất06/11 — coverage V1 đã đóng lỗi wiring:** [kết quả](NINO_SIM_COVERAGE_RESULT_2026-11-06.md):1Gazebo launch/1raw tick,0replay/optimizer/eval,63slot còn lại đóng. Correction metadata riêng kiểm offline; chưa release V2. Các đoạn dưới giữ lịch sử.

# Nhánh Sim: implementation study critic/coverage

06/11/2026 · Tiếp [protocol draft](NINO_SIM_CRITIC_COVERAGE_PROTOCOL_DRAFT_2026-11-06.md).

## Đã xây

- `coverage_sampling.py`: warmup64 chung, Gaussian σ0,1; C thay mỗi open
  decision thứ4 sau warmup bằng probe bốn bin. Eligibility đọc observation
  index101 trước action; counter giữ qua episode, không dùng GT/contact.
- `coverage_td3.py`: sampler nằm ở đường chọn action SB3; cùng actual
  request đi vào environment và replay. Replay có RNG riêng, giữ timeout
  semantics. Đếm trực tiếp `actor.optimizer.step` và `critic.optimizer.step`.
- `residual_coverage_study.py`: sáu fresh learner,16eval theo order draft,
  lifecycle/observer mới mỗi episode, namespace trước control tick, kiểm
  task/support/reset/closure, partial checkpoint và ledger giữ khi lỗi/hủy.
  Không resume hoặc retry study; release chặn trước khi cấp scientific slot.
- Checkpoint có identity riêng arm/seed/ABI/fingerprint; không nhận checkpoint
  V3/Studio/learner cũ. Save/load kiểm targets/optimizer/replay và inference.
- Evaluation deterministic, không gọi sampler/learn; snapshot policy/counters
  và trạng thái exploration trước/sau. Native/GT20ms/+10ms giữ riêng.
- Critic diagnostic dùng20 B0 packets pin từ dữ liệu cũ trước học và20
  own-policy packets mỗi learner; Q1/Q2/min-Q, argmax, disagreement, actor-Q
  gap được ghi riêng. Đây là dự đoán Q, không là counterfactual outcome.
- GUI profile **Critic/coverage · preflight rồi study2arm×3seed** có nút
  kiểm offline, study bị khóa khi chưa release, log/lỗi, progress, bảng
  sáu learner và các evaluation đã hoàn tất. Các profile lịch sử giữ riêng.

## Correction có căn cứ trước release

Đọc source SB3 đang cài cho thấy implementation gốc còn cộng exploration
noise sau uniform action ở warmup. Draft đã ghi uniform warmup64 chung;
sampler mới thực hiện **pure uniform64 cho cả A và C**, không thêm Gaussian
ở64bước đó. A mới vì vậy không phải tái tạo bitwise collector lịch sử.
So sánh nghiên cứu chỉ giữa hai arm mới; không ghép model cũ làm control.
Noise/RNG chung và lịch học mới được khóa bằng source/fingerprint.

Software test cũng khoanh được việc tính lại parent fingerprint trong
control loop. ABI/source được kiểm trước và sau job; ABI được cache trước
vòng điều khiển, không đọc/hash dependency tree ở mỗi100ms tick. Không đổi
gate, controller hoặc QoS để xử lý overhead này.

## Kiểm chứng và giới hạn

**Kết quả thực hiện:** 45 test software của study và 46 test GUI đạt, tổng
**91 tests**; build `nino_rl` và `nino_pi` đạt. Preflight được khởi chạy bằng
chính nút GUI/QProcess, không gọi thay bằng một báo cáo giả.

Artifact preflight:
`~/nino_research/sim_coverage_study_v1/20261106T102458274967Z_sim-coverage-preflight`.
Manifest SHA256:
`43981a39f32afdce9da8803ade22e49dc42b6d476a240896fe52515ca5978e83`.
Implementation fingerprint:
`1cd68b11dea8aee0302094294d89636276df23d6dfc2dc314af1c4a6433d89be`.
20 B0 critic packets đã pin trước scientific learning. File release có
hai pin trên nhưng `released:false`, rule review chưa mở.

Kiểm software gồm: cadence/bin balance và counter qua reset; RNG isolation;
actual request→adapter→reward→replay; timeout/terminal; optimizer counters;
checkpoint identity/parity; factory/namespace cho cả bốn loại arm;
evaluation không probe/update; matrix/budget; failure/cancel/corrupt ledger;
GUI selection không chạy job và chưa release không thể mở study.

Software fixture có optimizer updates riêng để kiểm tích hợp. Chúng không
phải transition Gazebo hoặc bằng chứng learned benefit; không cộng vào
ngân sách scientific6.144train/2.240eval. Chưa xác nhận runner mới dưới tải
Gazebo; chưa có evidence generalization/contact/hardware mới.

Hai fixture của preflight chạy200transition/arm với seed11; kiểm được
136critic/68actor optimizer steps mỗi arm và checkpoint/replay round-trip.
Đây là **400synthetic transitions**, không phải6.144transition Gazebo hoặc
thí nghiệm ba training seeds. Scientific training/eval mới, Gazebo launches
mới và hardware actions đều **0**. Không deploy checkpoint fixture.

## Thao tác GUI và bước tiếp

1. Mở **Xây project → NHÁNH SIM → Critic/coverage**.
2. Bấm **Kiểm coverage offline**, chờ worker kết thúc và manifest được kiểm.
   Xem log và preflight result; bước này không mở Gazebo hoặc nối Pi.
3. Study chỉ mở khi release riêng pin implementation fingerprint và đúng
   preflight manifest, đồng thời rule nghiên cứu được review. File release
   hiện `released:false`; hardware luôn `false`, application effect vẫn null.
4. Sau release mới chạy một attempt:6learner×1.024 và16eval×140, tối đa64
   launches/8.384ticks; lỗi/hủy/deadline đóng các slot còn lại. Không thêm
   Gazebo smoke, tăng timestep, đổi reward hoặc chạy lại batch cũ.

Profile này dùng103D/1D và learner identity riêng. Tab TRAIN TD3 tự do/V3
có ABI khác, không dùng để resume hoặc thay learner của study coverage.

**Bước kế tiếp:** review preflight artifact/source và chốt release study
riêng theo đúng draft. Classical/B0 vẫn là reference hiện tại. Không cần
thu real bag mới cho gate software này.

Verification: [JSON pin nguồn/kết quả](NINO_SIM_COVERAGE_IMPLEMENTATION_VERIFICATION_2026-11-06.json).
Các helper `mode_gui.sh` và `residual_coverage_study.sh` dùng source workspace
qua PYTHONPATH để kiểm provenance của các module Sim frozen. Byte parity
của bản colcon đã kiểm riêng; không sửa path resolver trong các source cũ.
