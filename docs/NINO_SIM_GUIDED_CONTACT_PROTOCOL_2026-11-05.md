# Protocol trước chạy — guided baseline clear/gờ 6 mm

05/11/2026. Tiếp tục nhánh sim theo yêu cầu người dùng; không hardware hoặc
optimizer. [Baseline V3 clear ±5° đã đạt gate đề xuất](NINO_SIM_GUIDED_BASELINE_V3_RESULT_2026-11-05.md).

## Câu hỏi và ngân sách đóng

Wheel+IMU estimator và follower có còn đáp ứng tracking/drift/stop khi qua
gờ cứng, đủ để dùng làm baseline cho learning V3 không?

- Guided, residual `[0,0]`, không actor/checkpoint. Cùng causal estimator,
  history/projection/PI/limits V3. Không sửa file parent V1/V2/V3.
- Tối đa **4 fresh launches / 560 transition**, thứ tự: clear 1 → gờ 1 →
  gờ 2 → clear 2. Không exact-state pairing hoặc nhiều training seeds.
- World controlled từ factory hall: solid box và một cylinder Ø6 mm,
  tâm x=0,65 m, y=0, z=0,003 m, roll=π/2, yaw=0. SDF đầy đủ và hash lưu
  trong `worlds.json` trước rollout; không gọi là mixed map/cáp mềm.
- Robot spawn yaw0, tuyến 3 m theo +X, initial estimated pose `[0,0,0]`
  từ metadata tại task epoch; không GT alignment.
- Cruise0,2 m/s; ramp/PI giữ parent; source zero0–0,5 s và từ8 s; task14 s,
  physics1 ms, native/control100 ms,140 tick/lượt. Không thay reward/limits.
- GT/caster/contact chỉ reset/evaluator/audit, không vào estimator/follower.

## Outcome và dừng

Giữ toàn bộ functional gate engineering của V3: progress dọc tuyến ≥0,95 m,
quiet stop liên tục2 s; max cross-track≤40 mm, max estimator position
error≤50 mm, yaw≤0,05 rad. Estimate so GT tại boundary còn lệch source time;
report tuổi estimate, không diễn giải như calibration accuracy.

Primary là chức năng/stop và bound drift/tracking. Secondary: body v/yaw
tracking, raw support/gaps, drift trước/sau contact, requested/accepted/
final/actuator target. Không có slip/impact benefit claim hoặc thay gate98%
của nghiên cứu khác. Contact manifold không là first loaded contact/force.

**Sau mỗi lượt review tự động gate.** Nếu fail functional gate, đóng ngay
các slot chưa dùng, lưu result no-go cùng dữ liệu; không retry/thêm mẫu.
Nếu source/pose-clock/guidance/physics fault hoặc không đủ140 tick, job
fail closed và giữ ledger/raw; không lấp gap bằng nguồn khác.

Qua cả4 chỉ xác nhận baseline ứng viên trong envelope hẹp. Hai lượt không
đủ generalization/CI. Bất đồng hoặc sampling-sensitive giữ unknown; không
hạ bound, loại spike hoặc thêm mẫu. Tối đa một correction có nguyên nhân
cụ thể theo protocol/root mới, không tự chạy correction. Wall deadline1200 s.

## Provenance

Config `residual_guided_contact_v1.yaml`, module/script mới có fingerprint
riêng gồm frozen V3 parent. Dependency lưu manifest/hash của V3 đã qua gate.
Root `~/nino_research/sim_guided_contact_v1`, action `sim-guided-contact`;
root có state đã đóng không được tái sử dụng. Hardware/training/optimizer0.

Kết quả sẽ quyết định giữ contact envelope cho contract TD3 V3 hay giữ
clear floor và giải thích estimator/contact mismatch trước learning.
