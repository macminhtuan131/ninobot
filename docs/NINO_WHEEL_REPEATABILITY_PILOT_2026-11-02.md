# Pilot lặp đáp ứng bánh — sẵn sàng cho lượt 1/3

> **Cập nhật mới nhất 02/11: pilot v2 đã được đồng ý và chuẩn bị, 0/3 lượt.**
> V1 vẫn đóng ở 1/3, hai slot cũ không tái sử dụng. Readiness mới kiểm live
> trước cấp slot; zero-only preflight đạt, chưa chạy motion pilot.
> [Lệnh thu lượt 1 và điểm dừng](NINO_WHEEL_REPEATABILITY_PILOT_V2_2026-11-02.md).
> Các cập nhật cũ bên dưới là lịch sử.


## ĐÃ DỪNG ở slot1 — không dùng lệnh bên dưới để chạy lại

Slot1 `053608` bị chặn trước enable/forward. Smoother configure response
timeout, manager kẹt và monitor chưa active; không phải lỗi firmware/RC
đã được chứng minh. Raw/ledger giữ nguyên;2slot còn lại đã đóng theo stop
rule. Một correction startup/preallocation readiness đã chuẩn bị và kiểm
zero riêng; candidate v2 pending budget mới, chưa mở lại pilot. Workspace
report `artifacts/pilot_readiness_failure_2026-11-02/REPORT.md`.

Ngày:02/11/2026. Người dùng đã yêu cầu thực hiện NEXT_PILOT_DRAFT.md.
Contract đã khóa trước pilot;0/3attempts. Runtime Pi:
`~/nino_runtime/wheel_repeatability_pilot_20261102_v1/`.
Firmware/PI/current/geometry giữ nguyên, RC AUTO, sàn trống và tải giữ nguyên.
Profile0,05m/s, reference accel/decel0,10m/s², source tiến mục tiêu2s, zero/
disable rồi quan sát3s, bag60s. Baseline zero tối thiểu2s trước source tiến.

## Người vận hành thu lượt 1

Ba terminal trên Pi chạy đồng thời:

1. `bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v1/start_stack.sh`
2. `bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v1/record_wheel.sh`
3. Ngay khi terminal2 hiện Output, chạy
   `bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v1/run_trial.sh`

Terminal2 hỏi: gõ AUTO khi xe đứng yên, RC AUTO, cùng sàn/tải; ghi chú
vị trí/hướng xe và caster (unknown nếu chưa biết). Chưa bấm/chạy terminal3
trước khi Output/session được tạo. Đợi terminal2 đóng bag, Ctrl+C terminal1,
gửi output và quan sát tiến/dừng/lệch/giật/can thiệp. Giữ Pi bật.

## Quản lý ba slot

- Recorder bắt đầu một slot và lưu session/conditions/boot; nếu chỉ ghi mà
  không chạy trial, dữ liệu vẫn giữ và pilot dừng, không coi là motion pass.
- Motion helper chỉ claim một lần/session, không chạy lặp. Owner/status/
  feedback/finalzero/recorder readiness checks giữ nguyên, signal cleanup
  zero/disable, không bypass Collision Monitor hoặc firmware RC guards.
- Collector lỗi/trial lỗi/missing trace → slot failed, đóng các slot còn lại.
- Capture đủ → awaiting_review. Assistant kiểm raw và operator outcome, ghi
  review evidence riêng ngoài raw, rồi mới cho slot kế tiếp.
- `ledger.json` có lịch sử immutable snapshots, atomic+fsync; contract/frozen
  inputs đổi hoặc boot đổi → chặn. Sau3reviewed passes tự đóng pilot. Không
  reset/xóa ledger/claims hoặc chạy bù.

## Phép đo khóa trước

Primary từng bánh: mean raw velocity trong source+1,25..1,75s trừ mean
baseline source-2..0s, báo L-R. Final reference primary0,05±1e-6m/s; nếu
không có plateau/support thì unknown. Không đổi window, xóa spike, chọn
peak hoặc random-split frames. Báo mỗi lượt và range/median, không CI/power
hoặc generalization từ3lượt.

Wheel header/receipt/boundary support100ms là lựa chọn bảo thủ cho metric;
final command support200ms khớp guard freshness hiện có. Không là physical
safety bound, không là hạ coverage sim98%. Trong chuẩn bị chưa có pilot data,
đã sửa phạm vi100ms từ mọi trace sang wheel source; giữ contract prerelease
r1 riêng. Historical commissioning có final command gap367ms ở baseline
nên metric primary mới là unknown trên trace đó; không nới rule để làm nó
pass, không thay kết luận feasibility đã có. Pilot mới có baseline zero2s
được guard liên tục và metric vẫn cần kiểm từ bag thực.

## Kiểm chứng phần mềm/triển khai

6 mocked handoff cases;13 ledger+metric unit cases đạt. Test bao gồm từ
chối duplicate/advance-before-review/fourth-attempt, fail/unknown closes
remaining, changed boot/input, command plateau/gap và giữ spike.
17 frozen runtime file hashes khớp trên Pi; collector file-only check đạt.
Zero preflight cùng boot:225 selected/209 smoothed/208 final đều zero,
smoother/monitor active, launch thoát0; không gửi source/enable, không motion.
Ledger hiện chưa tạo/0slots; không đồng nhất tests với trials thật.

## Phân tích sau mỗi lượt (assistant, read-only)

1. Đợi manifest closure trước copy SQLite/raw; verify checksum/integrity/
   metadata, required channels, source/final/profile, status/freshness.
2. Dùng analyze_commissioning.py và export_trace.py giữ original CDR/samples;
   primary_metrics.evaluate(trace.csv rows) theo cửa sổ khóa, không resample.
3. Lưu review_data_pass cùng session vào analysis ngoài raw chỉ khi raw,
   command plateau, windows/source support hợp lệ; giữ peak/gap/failures.
4. Thu operator report rc_auto, forward, stopped_without_intervention,
   no_obvious_yaw_jerk,same_surface_load. Unknown hoặc failure → dừng slots
   còn lại. Không có numeric application acceptance để tự nhận quality pass.
5. review_attempt.py chỉ ghi quyết định vào ledger với evidence/hash; không
   tạo ROS interfaces hoặc chạy motor. Sau3lượt mới tổng hợp repeatability.

## Contract

Protocol:wheel_response_repeatability_3x_20261102_v1

SHA256:750b0b37ef9077cb6cc8e2535f54d326378645dd1964807dda37d699dbbac170

Workspace artifacts: `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/wheel_repeatability_pilot_2026-11-02/`.
