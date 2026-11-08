> Cập nhật: screen đã chạy đủ4/4 và release đã đóng. Xem [kết quả/giới hạn/bước tiếp](NINO_SIM_PI_SCREEN_RESULT_2026-11-07.md). Các trạng thái “chưa release/chạy” bên dưới là lúc chuẩn bị protocol trước batch.

# PI screen Sim — runner, ledger và protocol đã chuẩn bị

07/11/2026 · **Chưa release/chạy physics hoặc training.**

## Quyết định và phạm vi

Tiếp [software parity PI](NINO_SIM_PI_SCREEN_OFFLINE_RESULT_2026-11-07.md),
đã tạo runner riêng `pi_screen_runner.py`, protocol JSON và release record.
**44 tests runner đạt**; coordinator đi qua4 cell/560 decisions synthetic,
đóng4 backend fixture. Không sửa driver/context PI đã seal, gain-v1, root9/9,
checkpoint hoặc phần robot thật.

Các kết quả synthetic chỉ chứng minh đường đi phần mềm. Summary, timing và
closure trong fixture được mock, không là kết quả Gazebo. Artifact ghi rõ
`gazebo_launches=0`, `evaluation_transitions=0`, `synthetic_decisions=560`;
4/560 là budget khai báo của runner, được giữ riêng khỏi execution thật.

## Ma trận cố định — chưa cấp slot

| Cell | Block | Ki | Kp | Arm / gain | Reset |
|---|---|---|---|---|---|
| 0 | 0 | 0,10 | 0,30 | B0zero / 1 | Fresh owned launch |
| 1 | 0 | 0,15 | 0,30 | B0zero / 1 | Fresh owned launch |
| 2 | 1 | 0,15 | 0,30 | B0zero / 1 | Fresh owned launch |
| 3 | 1 | 0,10 | 0,30 | B0zero / 1 | Fresh owned launch |

Hai cặp so sánh là cell0/1 và cell3/2 (baseline/candidate). Tất cả dùng reset
seed701 để giữ config cũ; không coi đó là hai training seeds hoặc exact-state
branching. Fresh reset có thể khác caster/contact/numerics; hai block chỉ
là pilot mô tả, không reliability/generalization hoặc xác nhận thống kê.

Giữ clear-box factory lab, nominal0,2m/s, source stop8s, horizon14s,
140 native decisions/lượt ở100ms. PI500Hz, physics1ms, torque4Nm,
effort slew10Nm/s, target acceleration12rad/s²; không governor/estimator
adaptation/TD3 action. Reset ACK+quiet0,5s trong cap5s giữ nguyên. Setup
physics ngoài560 evaluation ticks vẫn bị cap reset; **560 không phải tổng
physics iterations**. Integration đầu nằm trong4 lượt, không có smoke riêng.

Budget dự kiến tối đa4 launches/560 evaluation ticks, wall deadline1800s
là cap vận hành đề xuất, không phải thời gian chạy được đo. Training,
actor loads, optimizer, exploration/probes, retries và hardware đều0.

## Lifecycle và ledger

1. Kiểm release, fingerprint, protocol hash, canonical root, JUnit và offline
   proof. Release bị từ chối trước khi tạo root/slot; không launch để thử.
2. Giữ shared factory lock và job lock nonblocking. Kiểm ledger lần nữa
   dưới lock để tránh hai process cùng lấy budget.
3. Ghi `state.json` trước execution; ghi từng attempted condition trước cell.
   Mỗi lượt tạo namespace/partition mới, observer ready rồi mới reset.
4. Trước từng action kiểm permission/source; ghi attempted request và raw row
   trước validation. Ki/readback/audit sai, task/measurement/closure lỗi thì
   giữ failure và đóng mọi slot chưa attempted. Không tái sử dụng backend.
5. Ctrl+C và wall deadline đi qua cleanup/final seal. Ledger failed,
   cancelled, completed, running còn sót hoặc hỏng đều chặn re-entry.
   Hard kill/mất máy không được coi là graceful closure: ledger còn lại vẫn
   chặn retry; phải audit tiến trình owned và artifact trước quyết định mới.
6. Chỉ job completed có latest pointer. Manifest pin file hashes, nguồn,
   dependency, release và protocol; không promote candidate từ việc job hoàn tất.

## Metric và quyết định đã viết vào comparator

- **Primary:** whole14s native nominal-body velocity RMSE.
- **Sensitivity:** GT20ms và GT dịch+10ms, giữ riêng; không chọn grid thuận lợi.
- **Constraints:** marker/task, physical path RMSE≤0,04m và quiet stop2s trước
  horizon14s; support/observer closure và timestamp diagnostic phải đạt.
- Pass screening mô tả: native giảm≥5% ở cả hai block và cả hai GT grids
  giảm ở cả hai block; mọi task/measurement/closure gate đạt.
- Tệ hơn nhất quán: no-go candidate, giữ Ki0,10. Effect nhỏ, khác chiều theo
  block hoặc grid, nonfinite/zero denominator: unknown. Không auto thêm lặp,
  thêm Ki, đổi window/metric hoặc loại failures/spikes.
- Failure đo lường không được diễn giải thành candidate kém hơn về dynamics.
  So sánh chỉ nhận đúng4 cell hoàn chỉnh, đúng thứ tự và outcome hợp lệ.
- 5% vẫn là rule nghiên cứu đề xuất; chưa là yêu cầu nhà máy được chấp nhận.
  Pass không tự mở learner, contact/generalization hoặc robot thật.

## Phần mềm và gate kiểm được

`pi_screen_runner.py` dùng EpisodeLifecycle/observer/reset/source-support
cũ và PiScreenBackend mới đã đạt parity; không thay controller math.
Source gate đối chiếu entry thực tế, installed driver/backend/launch và motor
source/YAML. Ki đã đọc được phải khớp condition; requested không thay actual.

44 tests kiểm full140-decision wrapper/validator cho hai Ki, failure trước
command, sai Ki ở tick đầu, cleanup lỗi, đủ matrix, thứ tự hai cặp, small/
grid/block-dependent/invalid metrics, first fault ở từng cell, world-prep
failure, locks, ledger/seal/re-entry và release/test-report/proof mutation.
Fixture không kiểm được actual launch, timing hoặc observer closure mới.

## Artifact và release

- Protocol: `src/nino_rl/config/sim_pi_screen_protocol_v1.json`.
- Release: `src/nino_rl/config/pi_screen_release_v1.json` — **released=false,
  allocated_physics_slots=0**, training/hardware=false.
- Root physics riêng: `/home/tuanmac/nino_research/sim_pi_screen_v1`;
  chưa được tạo/consume trong bước này.
- Proof offline: `/home/tuanmac/nino_research/sim_pi_screen_runner_preflight_v1/offline_2026_11_07`.
- QA/JUnit/install/GUI: workspace artifact `artifacts/sim_pi_runner_2026-11-07`.
  Fingerprint/manifest/protocol pins được ghi trong proof, release record và GUI snapshot.

Pins đã seal:

- Runner fingerprint: `86db564afa9e1a7980b16351db4cf466869c9b6c08c4f9bae27843cde326014f`.
- Protocol SHA256: `7a150aef70ecbb70d06a09476c7b082d82c577d4a49a60dee13bc775c04fb6a6`.
- Offline manifest SHA256: `01b7ecf4ff30a48bf746f30730254445b782e4cd1b756bff28ef41d9787ab36f`.

GUI hiện chỉ hiển thị progress/proof và mở protocol. **Không có nút chạy
screen mới từ trang kết quả**, không tự mở lại profile/budget cũ. Data thật
vẫn cutoff02/11, hardware residual authority0; không SSH/flash/motor command.

## Một bước tiếp theo

Review và chốt **release riêng cho đúng protocol/source/root này**, rồi mới
thực hiện tối đa4 cell Gazebo; cell đầu là integration trong budget. Kết quả
sẽ quyết định giữ Ki0,10, xem xét Ki0,15 cho validation riêng hoặc unknown.
Không train TD3 trước khi biết baseline và useful authority còn gap nào.
