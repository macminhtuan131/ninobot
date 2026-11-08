# PI screen Sim: software đã kiểm, chưa chạy vật lý

07/11/2026 · Tiếp [dynamics audit](NINO_SIM_DYNAMICS_AUDIT_RESULT_2026-11-07.md)
và [draft screen](NINO_SIM_PI_SCREEN_DRAFT_2026-11-07.md).

## Quyết định

Đã chuẩn bị nhánh riêng để so **Ki 0,10 / 0,15**, giữ **Kp 0,30**, gain-map=1
và B0 residual=0. **Parity offline đạt; chưa có bằng chứng Ki 0,15 cải thiện
đáp ứng robot mô phỏng.** Bước kế tiếp là runner/protocol/release riêng cho
screen có giới hạn, trước khi chạy physics. Không có lý do mở TD3 từ kết quả
software này.

## Đã làm và đã kiểm

| Thành phần | Kết quả | Giới hạn |
|---|---|---|
| Driver/launch riêng | Ki truyền bằng ROS parameter override trước khởi tạo PI; read-only theo driver gốc. Node chỉ chấp nhận domain129, localhost, partition và context Sim riêng | Chưa chứng minh launch tích hợp trong Gazebo |
| Kernel PI | Gọi đúng kernel frozen, giữ watchdog, conditional integrator, ramp, torque/slew, reset và odometry | Chưa nhận dạng plant hoặc ổn định candidate |
| Baseline Ki 0,10 | 1.200 callback có state/effort/diagnostics/odom và gain telemetry đúng bằng driver gain=1 frozen | Synthetic clock/feedback, không phải 1.200 lượt chạy robot |
| Candidate Ki 0,15 | Cùng 1.200 input; effort khác ở 1.199 callback; target và odometry không đổi trên feedback giữ giống nhau | Chứng minh Ki vào kernel; không chứng minh hiệu quả, latency hoặc stopping |
| Wrapper/context | 560 transitions synthetic tổng cộng: hai context cũ/mới × 140 decisions × hai Ki; observation/reward/projection/reference/terminal khớp trên cùng input | Fixture wrapper không mô hình hóa ảnh hưởng Ki lên dynamics |
| Ki/readback/support | Sai Ki/Kp/limits, source lệch stamp, stale/future, nonzero residual, old ABI hoặc source đặc quyền đều bị từ chối trong tests | Source support/closure của launch mới còn phải kiểm trong screen |
| Software tests | **49 đạt**; gồm constructor dùng parameter override, reset, readback thật/khác requested, launch construction và artifact tamper | Không gọi `rclpy.init`, không chạy LaunchService/Gazebo |

Tổng kernel fixture: **3.600 callbacks** (frozen + baseline + candidate).
Chỉ backend nhận dạng mới có Ki metadata; **không thêm Ki hoặc gain vào observation**.
Context vẫn 103D/1D, history5/10Hz nhưng có ABI mới và chặn mọi residual khác0;
shape giống nhau không cho phép dùng checkpoint cũ. Không có actor loader trong nhánh này.

GUI có trạng thái và nút mở hồ sơ PI mới; budget9/9 cũ vẫn khóa, không khởi
chạy job từ trang kết quả. Build `nino_rl`/`nino_pi` đạt; bản cài đặt và entry
được đối chiếu source. QA có screenshot dùng artifact thật. Bộ GUI trực tiếp
đã đạt12 tests; một regression rộng hơn dừng chủ động sau33 tests đạt/60 dự kiến
khi các kiểm tra cần cho thay đổi này đã đủ; không gọi full regression đã đạt.
JUnit của lượt dừng vẫn được giữ trong artifact QA, không xóa để che lỗi.

Một giả định test ban đầu đã được sửa theo source: khi không có wheel feedback,
kernel frozen giữ target/integral và yêu cầu effort zero qua slew limiter;
không có reset target/integral tự động tại nhánh đó. Đây là hành vi được giữ
để làm phép so Ki, không phải kết luận semantics này đã đủ cho robot thật.

Factory reset được so AST với bản frozen: chỉ khác launch, đối số Ki và
expected Ki trong readback. Guided reset dùng cùng callable; settle vẫn yêu
cầu drive ACK + quiet liên tục0,5s trong cap5s. Telemetry `/nino_drive/pi_screen`
báo **giá trị cached thực sự kernel dùng**, đồng stamp với drive/gain; requested
condition không được dùng để thay readback. Các bản ghi này là telemetry Sim,
không là torque đo độc lập.

## Artifact và provenance

Artifact:
`/home/tuanmac/nino_research/sim_pi_screen_preflight_v1/offline_2026_11_07`

- Fingerprint: `026014c6034e8294a9f187e0a4a8d23d9825bfe0d9225c1208fab92f5f600e22`.
- Manifest SHA256: `ac8d24eb535e418189d3aea4b93f1163b9a1d710bbddf51b4adce6a09c865766`.
- ABI: `48f2c9883a36a6afa3d8caf6c6f302fd9ebf46392703d0d10f0f307475fde1f4`.
- Parent là gain-context frozen, motor source và parameter YAML được pin.
  Dependency là dynamics V2 manifest `da0c20ff6deb089e52353c9d984f1c4c4178b302f23ffc48bbc58c079b22a2ab`.
- Manifest kiểm exact inventory, hashes, source fingerprint, identity và
  dependency; mất trace/thay trace hoặc claim có runtime đều bị từ chối.
- Source mới: `pi_screen_contract.py`, `pi_screen_effort_drive.py`,
  `pi_screen_backend.py`, `pi_screen_context.py`, `pi_screen_preflight.py`,
  `training_sim_pi_screen.launch.py`, `sim_pi_screen_preparation_v1.json`.
  Không sửa frozen gain driver/kernel/context/runner hoặc root9/9.

`physics_released=false`, `allocated_physics_slots=0`. **0 Gazebo launch,
0 physics step, 0 actor load, 0 training/optimizer, 0 hardware action** trong
bước này. Real-data cutoff vẫn02/11; không SSH hoặc thu thêm dữ liệu thật.

## Việc còn lại theo thứ tự

1. **Chuẩn bị runner có ledger riêng và protocol/release được hash:** dự kiến
   thứ tự Ki0,10 →0,15 →0,15 →0,10, mỗi lượt140ticks; integration đầu nằm
   trong tối đa4launches/560ticks. Chưa cấp slot ở bước software này. Không
   retry/smoke ngoài budget; failure đóng các slot còn lại, giữ raw.
2. **Khi screen được release:** fresh launch/reset, kiểm installed entry,
   readback Ki và mọi invariant, reset ACK/quiet, observer/support/closure
   trước khi chấp nhận outcome. Giữ source stop8s/horizon14s/nominal0,2m/s,
   clear-box, torque4Nm/slew10Nm/s/target accel12rad/s².
3. **Quyết định từ outcome:** primary whole14s native nominal-body velocity
   RMSE; GT20ms và +10ms riêng. Giữ marker/path≤40mm/quiet stop2s.
   Rule đề xuất là giảm≥5% ở cả hai cặp và GT cùng chiều; hai lặp chỉ pilot
   mô tả, chưa xác nhận thống kê. Effect nhỏ/khác chiều/grid-sensitive là
   unknown; không tự tăng Ki/số lặp hoặc đổi metric.
4. **Sau quyết định mới xét baseline/envelope:** candidate đạt cũng chưa tự
   promote, mở contact/gain generalization hoặc train TD3. Candidate thất
   bại thì giữ Ki0,10 và xem lại câu hỏi; không mở một vòng tuning vô hạn.

**Một việc tiếp theo:** viết bounded runner/protocol cho screen này. Đầu ra
phải là hồ sơ review được với các gate/slot/release rõ ràng; parity software
không thay thế phép thử physical feasibility hoặc ích lợi hệ thống.
