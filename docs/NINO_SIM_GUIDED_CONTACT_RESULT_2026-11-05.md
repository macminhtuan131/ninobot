# Guided baseline clear/gờ 6 mm — kết quả 05/11/2026

## Quyết định

**Giữ guided baseline làm đối chứng ứng viên cho TD3 V3 trong envelope sim
hẹp đã kiểm.** Screen đã đóng đủ **4/4 lượt, 560 transition**; cả bốn đạt
marker tiến độ và quiet stop, không actor/optimizer. Bước tiếp là triển khai
contract TD3 V3 reward/baseline/zero-init trước một pilot learning mới;
checkpoint V2 giữ lịch sử, không resume theo ABI đơn thuần.

Đây là kết quả Nino mô phỏng. Không có dữ liệu thật, hardware deployment,
learned benefit hoặc chứng minh H2 post-contact từ screen zero-residual này.

## Protocol đã khóa trước chạy

[Protocol](NINO_SIM_GUIDED_CONTACT_PROTOCOL_2026-11-05.md), YAML
`src/nino_rl/config/residual_guided_contact_v1.yaml`.

- Estimator wheel+gyro-Z → follower → residual zero → projection/ramp → PI.
  Source/clock/epoch và limits giữ [V3 parent](NINO_SIM_GUIDED_BASELINE_V3_RESULT_2026-11-05.md).
- Clear / gờ / gờ / clear; robot và tuyến yaw0, đường 3 m. Single rigid
  cylinder Ø6 mm, x0,65 m, z0,003 m, nằm ngang. Không mixed map hoặc dây mềm.
- Cruise0,2 m/s; source0,5–8 s; task14 s, physics1 ms/control100 ms.
  RMSE toàn task gồm stop. Marker0,95 m không là arrival goal3 m.
- Nếu gate chức năng fail, đóng các slot còn lại; source/guidance/physics
  fault fail closed; không retry. Batch này không cần correction.

## Kết quả từng lượt

| Thứ tự | Điều kiện | RMSE path (mm) | Max path (mm) | Max estimate position error (mm) | Max estimate yaw error (rad) | RMSE v theo nominal (m/s) | Marker + stop |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | Clear 1 | 0,332 | 0,527 | 3,291 | 0,000752 | 0,005053 | Đạt |
| 2 | Gờ 1 | 4,283 | 6,631 | 8,100 | 0,001382 | 0,018755 | Đạt |
| 3 | Gờ 2 | 3,091 | 4,808 | 10,234 | 0,001345 | 0,015426 | Đạt |
| 4 | Clear 2 | 0,087 | 0,129 | 22,329 | 0,000446 | 0,004942 | Đạt |

Tất cả qua bound đề xuất trước chạy: max path40 mm, estimate position50 mm,
yaw0,05 rad và quiet stop liên tục2 s. Quiet cuối cả bốn khoảng4,0 s;
progress cuối clear1,448–1,467 m, gờ1,457–1,458 m. Không đổi bound sau dữ liệu.

**Không diễn giải error estimate của clear2 là bằng chứng gờ giúp
localization tốt hơn.** Initial truth x của clear2 khoảng−20,394 mm so
initial estimate0; ba lượt kia khoảng−1,485 đến−2,105 mm. Đây là offset sau
settling được protocol giữ nguyên, không GT alignment. Max error22,329 mm
gồm offset này và tuổi estimate tại boundary, không phải drift tăng22 mm.

### Phase contact — mô tả

Hai lượt gờ có first C1 manifold tại3,653 /3,663 s và last manifold
5,170 /5,164 s theo task clock. Max estimate position error trước manifold
là3,268 /3,935 mm, từ manifold tới cuối task là8,100 /10,234 mm.
Cross-track tăng sau tiếp xúc trong hai trajectory này.

Đó là association theo manifold, chưa tách wheel slip, rolling pitch,
contact/PI numerics hoặc tích phân thành nguyên nhân độc lập. Không có
first-loaded-contact/force proof hoặc đối chứng action để suy useful control
authority. Estimate so GT tại boundary có thể cũ tới10 ms; không nội suy
để tuyên bố độ phân giải body timing cao hơn GT50 Hz.

## QC và provenance

Root mới:
`/home/tuanmac/nino_research/sim_guided_contact_v1/20261105T020403516683Z_sim-guided-contact`.

| Kiểm | Kết quả |
|---|---|
| Manifest raw/config/trace/job/worlds | 64/64 file khớp SHA256 |
| Physics requests | 1.160/1.160 hoàn tất; đúng iteration/clock; retry0 |
| Parameter read-only calls | 8/8 hoàn tất |
| Estimator updates | 2.800; đủ causal support/dt/age/receipt checks |
| Actor / optimizer / hardware | 0 / 0 / 0 |
| Unused slots / correction | 0 / 0 |

Manifest SHA256:
`8f15e5f12bf5ebb40b7930e37956bde71fd5e5da7dc3534a3936cc1c3b68efe5`.

Source age tại control boundary tối đa19 ms; estimate age tối đa10 ms.
Max dt gyro/support bound40 ms được kiểm trên từng update. Counts/gaps
không là một chứng nhận coverage98% theo contract cũ, cũng không chứng minh
logger loss-free cho mọi load. Native/control100 ms, GT/IMU50 Hz và wheel
nguồn khoảng500 Hz giữ riêng khi dùng dữ liệu.

Module, protocol, script mới có fingerprint gồm V3 parent; dependency lưu
path/hash manifest parent. Source cũ và checkpoint V2 không bị chỉnh.
Tests, build, GUI và source snapshot ghi tại
[verification](NINO_SIM_GUIDED_CONTACT_VERIFICATION_2026-11-05.json).

QA analysis/plot/screenshot:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_guided_contact_2026-11-05`.

## GUI và hướng tiếp theo

**Xây project → NHÁNH SIM → Tiếp xúc · guided clear/gờ 6 mm** hiển thị
bốn lượt, metric có đơn vị và trạng thái đợt đã đóng. Nút chạy lại bị khóa;
V3 clear ±5°, clear-bias, V2 và V1 vẫn xem riêng. Nếu batch sau fail gate,
GUI phải hiển thị no-go và số slot đã đóng, không coi artifact hợp lệ là
outcome đạt.

**Việc kế tiếp:** triển khai phần2 của
[thiết kế TD3 V3](NINO_SIM_V3_NEXT_DESIGN_2026-11-05.md): cùng guided B0,
velocity/yaw nominal reward, đầu actor zero-init/target đồng bộ, replay
semantics và checkpoint identity mới. Giữ h5, chưa đồng thời tune history/
hyperparameter/physics. Sau checks offline mới mở pilot learning hữu hạn.

Hai lượt mỗi điều kiện chỉ đủ quyết định bước tích hợp tiếp, chưa chứng
minh benefit/generalization hoặc đủ power. Nếu pilot không hơn guided B0,
giữ baseline; không tự tăng budget để theo đuổi return.
