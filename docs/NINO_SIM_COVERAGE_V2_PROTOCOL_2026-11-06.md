# Coverage V2 — correction metadata và preflight tích hợp

> **Cập nhật:** [release riêng](NINO_SIM_COVERAGE_V2_RELEASE_2026-11-06.md) đã
> được thực thi, sau đó đóng do initial drive-readiness failure.
> [Kết quả](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md). Không retry hoặc dùng
> lại49slot chưa chạy. Các đoạn dưới là protocol trước release.

06/11/2026 · Phạm vi: Sim/software. **Release physics hiện tắt.**

## Câu hỏi giữ nguyên

Khi giữ actor, observation, history, reward, projection và số optimizer updates
như nhau, probe phân tầng có cải thiện coverage/action learning so với Gaussian
và kết quả cuối có cạnh tranh được với common controller cổ điển không?

V1 đóng sau một control attempt vì trace thiếu `qualification_condition`.
Không có transition TD3 hợp lệ hoặc optimizer update. V2 là runner/root/identity
riêng; 63 slot V1 chưa chạy vẫn đóng. Không resume partial hoặc chuyển ngân sách.

## Thay đổi kỹ thuật

- `residual_coverage_study_v2.py` nối `QualifiedBackend` ngay trong factory
  **được `train_learner` thật sử dụng**, trước khi tạo environment/controller.
- Adapter gắn arm, seed và source stop từ protocol đã khai báo. Backend vẫn
  nhận nguyên command/config/lifecycle. Metadata xung đột bị từ chối; không
  dùng GT/contact để dựng đầu vào actor hoặc metadata điều kiện.
- Validator transition và feasibility của parent giữ nguyên. Ghi raw trước
  validation; transition sai không vào replay. Failure vẫn giữ partial.
- Identity V2 có protocol/fingerprint riêng; checkpoint V1/ABI khác bị từ chối.
- Kiểm nguồn đóng băng V1 và SHA của toàn bộ artifact failure. Root có ledger
  khác version bị từ chối trước preflight/release/physics.

Đây là correction dữ liệu trace, chưa là sửa controller hoặc chứng minh
training trên Gazebo đã hoạt động. Mã V1 đã pin giữ nguyên byte.

## Kiểm tích hợp phần mềm bắt buộc

Đường thật: `train_learner → CoverageTD3 collector → training wrapper →
QualifiedBackend → row → validator thật → SB3 replay → checkpoint/reload`.

Hai arm đều chạy 1.024 bước trên plant synthetic: 8 reset với stop 6/8 giây
xen kẽ; 7 terminal đủ 140 bước và đoạn cuối 44 bước right-censored; counter
sampler tiếp tục qua reset; 960 critic / 480 actor updates mỗi arm. Audit toàn
bộ replay, requested action và save/load optimizer/target/identity.

Fault injection condition xung đột và clock sai phải giữ replay rỗng, zero
optimizer update, giữ partial và đóng backend. Validator thật không bị mock.
Recorded-row regression riêng tái hiện raw lỗi V1 và kiểm metadata-only fix.

**Giới hạn fixture:** plant cân bằng hai bánh; interface guidance/support là
synthetic; summary/diagnostic terminal được thay bằng kết quả giả định có nhãn.
Các test không xác nhận physics, QoS, ROS acquisition hoặc quality gate Gazebo.

## Ma trận đề xuất mới, chưa release

| Thành phần | Giới hạn |
|---|---|
| Train | A Gaussian / C stratified probes × seed 11/22/33 × 1.024 |
| Eval | 16 điều kiện B0 / cổ điển / 6 TD3 tại stop 6/8 giây × 140 |
| Control | 103D/1D, history 5, 10 Hz, common residual ±0,005 m/s |
| Scenario | Factory clear-box, nominal 0,2 m/s; chưa gờ/mixed map |
| Train/eval transitions tối đa | 6.144 / 2.240 |
| Critic/actor updates tối đa | 5.760 / 2.880 |
| Launches / wall | 64 / 10.800 giây |
| Retry / extra smoke / hardware | 0 / 0 / 0 |

Thứ tự, warmup 64, RNG riêng, probe mỗi 4 eligible decisions, replay semantics
và 20 fixed B0 critic packets giữ như V1. First episode tích hợp nằm trong
budget nếu được release; không thêm smoke ngoài. Một failure đóng slot còn lại.

Primary vẫn whole-14s native vRMSE, báo GT20ms / dịch10ms riêng, giữ constraints
và missing/failure. Không đổi reward/gain/physics/QoS hoặc sampling sau kết quả.
Rule 5% là đề xuất nghiên cứu, **không là mức ứng dụng đã được chấp nhận**.
Coverage yếu, effect nhỏ hoặc đổi dấu theo grid có thể kết luận unknown.

## Artifact và GUI

- Root V2: `~/nino_research/sim_coverage_study_v2`.
- Config: `src/nino_rl/config/residual_coverage_study_v2.json`.
- Release overlay: `src/nino_rl/config/residual_coverage_release_v2.json`.
- GUI profile: **Coverage V2 · metadata correction / preflight / study riêng**.
- Nút 1 chạy offline preflight bằng QProcess và lưu manifest/tests/20 packets.
- Nút 2 chỉ mở khi release riêng pin đúng fingerprint + preflight manifest.
- Nút hủy giữ artifact; job đã tiêu thụ không mở lại. V1 còn trong profile lịch sử.

**Bước sau preflight:** review manifest, source pins và ma trận mới rồi mới
chốt release V2. Chưa cần thêm real data, train dài, predictor hoặc đổi thuật toán
để xử lý lỗi field trace này. Classical/B0 vẫn là reference; chưa promote TD3.
