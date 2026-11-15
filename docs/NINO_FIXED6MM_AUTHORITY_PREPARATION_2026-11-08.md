# E2 gờ 6 mm — chuẩn bị offline, chưa release

Ngày 08/11/2026. Tiếp sau [E1 integration](NINO_COMMON103_V2_INTEGRATION_RESULT_2026-11-08.md).
**12 lượt đề xuất, 0 lượt được cấp; chưa chạy thêm Gazebo, optimizer hoặc hardware.**

## Quyết định

**[Đ]** Giữ Ki0.10 và chỉ thay common reference **−0,005 / 0 / +0,005 m/s
sau first C1 manifold**. Câu hỏi: wheel rồi body có đổi kịp trước drive-wheel
contact và cải thiện tracking nominal không? Ki0.15, DR, reward/history/LR và
ngân sách TD3 dài giữ ngoài screen. Chưa so TD3 với baseline mới.

Trigger là **oracle first received C1 manifold**, không phải first loaded
contact hoặc detector sensor-only. Oracle thuộc context thí nghiệm riêng;
contact/GT không vào observation của actor triển khai.

## Bằng chứng mới từ dữ liệu đã có

**[N — raw Sim]** Đọc sáu raw evaluation E1 còn giữ, ghi hash raw/trace riêng;
không đọc raw train đã xóa hoặc sửa manifest/verdict cũ.

| E1 arm/stop | First C1 → first drive-wheel C1 manifold, source time |
|---|---:|
| 6/B0 | 1,193 s |
| 6/Classical scheduled | 1,134 s |
| 6/TD3 | 1,167 s |
| 8/B0 | 1,183 s |
| 8/Classical scheduled | 1,131 s |
| 8/TD3 | 1,183 s |

**[N — source]** `FactoryVelocityBackend._contact` chỉ giữ collision names và
số điểm, không có wrench/depth. Raw có source và callback receipt monotonic;
trace chưa có đủ decision monotonic cutoff để chứng minh callback có trước
một quyết định cụ thể. Không dùng source stamp thay receipt causality.

**[S]** Khoảng source-time1,13–1,19s làm cho câu hỏi authority trước drive
contact đáng kiểm; chưa bảo đảm receipt, actuator/body phản ứng kịp hoặc có
lợi ích. Caster còn lại có thể chạm sớm hơn nhiều. Deadline nghiên cứu này
là **first drive-wheel C1 manifold**, không phải mọi contact kế tiếp. Không
suy force/impulse/slip/damage hay latency hardware từ các khoảng này.

## Protocol đã cụ thể hóa

[JSON](../src/nino_rl/config/fixed6mm_postmanifold_authority_draft_v1.json) ·
[Planner offline](../src/nino_rl/nino_rl/obstacle_authority_draft.py).

| Thành phần | Contract đề xuất |
|---|---|
| Map/plant | `box_c1_6mm`, cylinder cứng radius0.003m tại x0.65m, μ1; Kp0.3/Ki0.10/gain1; giữ geometry/limits/follower |
| Lệnh nguồn | 0.2m/s, warmup0.5s, source stop6/8s, horizon14s, native100ms |
| Trước trigger | B0 residual0 ở mọi arm; không bù trước contact như classical E1 |
| Trigger | Đúng model/link/C1 collision; source thuộc epoch và≤decision; callback receipt≤decision cutoff |
| Sau trigger | Common±0.005 hoặc0, source tiến, nominal steady và health hợp lệ; loss health latch tắt |
| Withdrawal | Residual0 từ stop−0.5s; giữ shaping và source-zero priority |
| Matrix | 3 arm ×2 stop ×2 fresh-launch block=12; đảo thứ tự arm/stop ở block sau |
| Cap | Đề xuất1680 task ticks/168 task sim seconds, reset riêng; 0 retry/extra smoke/train |
| Integration | Neutral đầu nằm trong12; review từng slot, không tự chạy hết |

Fresh launch không là exact-state branch; hai block là mô tả, không đủ
power/generalization hoặc hai learner seed độc lập. Scenario đã xem là
development, không phải unseen bank. **Không pool E1 làm B0** vì reference
trước contact khác nhau. Profile này không được coi là classical tối ưu.

### Primary và điểm dừng

**[Đ — chưa chấp nhận như yêu cầu nhà máy]** Primary: GT-header ISE của body
velocity so với nominal shaped reference độc lập, **m²/s**, trong `tc..tc+3s`
(tc=first C1 source manifold từng run). Hai grid causal20ms/dịch+10ms báo
riêng, native100ms giữ riêng và phải cùng chiều. Tích phân theo dt có support;
không nội suy tương lai, bỏ spike hoặc đổi cửa sổ sau kết quả.

- Measurement: boundary/clock/nominal đủ support, coverage thời lượng≥98%,
  GT gap≤40ms; native replay, command/driver/readback và lifecycle hợp lệ.
- Caliper: RMS **chênh body velocity candidate−B0**, căn theo tc riêng,
  ≤0.001m/s trong0.5s trước tc; báo cả approach và caster audit. Không nới
  gate chỉ vì prestop đã fail caliper; đây không là ngưỡng vận tốc tuyệt đối.
- Authority: driver nhận, actual hai bánh đổi cùng chiều common; body
  contrast≥0.001m/s kéo dài≥0.2s so B0, observed interval hoàn toàn trước
  first drive contact. Publication/target riêng không đủ. First contact đã
  là drive thì không có horizon cho claim này; interval chồng deadline→unknown.
- Go: **cùng một sign** giảm primary≥5% cả hai block/hai stop/hai GT grid,
  native cùng chiều; full-route vRMSE tăng≤2%, quiet onset chậm≤0.1s, marker
  ≥0.95m, path max≤0.04m và stop liên tục2s.
- Estimand: từng sign/stop, trung bình bằng trọng số hai tỷ lệ candidate/B0
  theo block trừ1; kèm absolute delta và mọi block. B0 denominator0→unknown.
- No-go: dữ liệu hợp lệ nhưng không authority/lợi ích hoặc fail constraints:
  giữ classical cho action/horizon/envelope này; không kết luận mọi governor bất khả thi.
- Unknown: caliper/coverage/receipt/grid/block không rõ thì đóng screen,
  không tăng mẫu. Tối đa một correction có căn cứ; đóng release hiện tại,
  giữ slot đã dùng, cần version/release riêng; không chạy bù slot.

Go chỉ đề cử classical để xác nhận tiếp. **Tracking tốt không chứng minh
giảm contact risk**. Acceleration body-Z RMS chỉ là secondary với kiểm frame/
gravity; không là force/impulse. Claim loaded phase cần instrumentation riêng.

## Đã làm và bước kế tiếp

**[N — software]** Module mới kiểm pins/specification/budget, lập lịch oracle
receipt-causal và tạo sáu reference preview qua shaper thật. Test old epoch,
future source, late receipt/backdating, zero arm, health latch và withdrawal/
zero-source. Preview dùng contact tổng hợp3.2s/receipt3.3s, không là body model
hoặc replay trigger nhân quả của E1. GUI kiểm hash protocol và hiển thị
**chuẩn bị offline, 0/12 allocated**; không có nút chạy runner chưa tồn tại.

**Tiếp theo:** xây adapter/runner E2 biệt lập, ghi decision sim/monotonic,
ánh xạ physical common qua projection, giữ independent joint/GT và actual
driver target/feedback. Không dùng wrapper PI B0-only cho nonzero action hoặc
load checkpoint chỉ vì cùng vector shape. Kiểm neutral parity, fault/clock/
stop/lifecycle, disk, source/install và release riêng trước slot neutral đầu.

Sau E2 hợp lệ mới chốt baseline và validation/test bank; nếu còn residual need
vượt cách cố định mới chuẩn bị pilot research12k. Chưa mở3×50k hoặc hardware.

Kiểm phần mềm cuối: **131 test được chọn đạt**, build `nino_rl`/`nino_pi`
đạt; ba cặp source/install khớp và loader bản cài đọc được draft. Kiểm lại
**54 file bảo vệ** và **197 file gốc E1 giữ lại** đều khớp hash; 66 file raw
thiếu đều thuộc retention đã ghi trước. Đây không phải 131 rollout hoặc
nghiệm thu runtime E2.

Audit:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/fixed6mm_authority_preparation_2026-11-08/`.
