# Nino: motion contract từ reference đến backend — 23/10/2026

## 1. Quyết định sau bước tiếp tục

**[S] Ưu tiên tiếp theo vẫn là classical baseline và nhận dạng backend.
Chưa nên bật ROS governor như một bản triển khai của controller frozen.**
Audit source cho thấy các contract khác nhau cả tham số, feature history,
shaping và telemetry; đây không chỉ là thay tên topic. Khác biệt không tự
chứng minh wrapper lỗi hoặc governor không hữu ích, nhưng ngăn chuyển kết
quả sim sang hardware trực tiếp.

**[N] Đã hoàn tất:** đọc source/YAML/launch, trích xuất settings có cả
dataclass defaults, so với frozen v7 và kiểm một ví dụ IMU tổng hợp bằng
`ImuWindow` hiện có. **0 simulator, 0 ROS node, 0 hardware access, 0 controller
update**; không sửa runtime/config, không tạo release/ngân sách. 249 execution
dependencies của v7 vẫn khớp hash. Không chạy thêm software test suite hoặc
gọi ví dụ tổng hợp là traversal.

- [Audit JSON, source hashes và ví dụ](nino_motion_contract_review_2026-10-23/audit.json).
- [Script offline](nino_motion_contract_review_2026-10-23/audit.py).
- [Motion contract **đề xuất**, không phải config để launch](nino_motion_contract_review_2026-10-23/motion_contract.proposed.json).
- [Báo cáo phản biện tổng hợp và roadmap T1–T3](NINO_INDEPENDENT_REVIEW_2026-10-23.md).

Nhãn: **[N]** code/config hoặc dữ liệu Nino; **[T]** nguồn ngoài;
**[S]** suy luận; **[Đ]** đề xuất. Số trong YAML là giá trị cấu hình, chưa
phải số đo/giới hạn phần cứng được chấp nhận.

## 2. Ba kiến trúc cần phân biệt

### A. Command stack mặc định cho robot thật: candidate trong repository

```text
Teleop /cmd_vel_teleop ┐
                     ├→ command_gate → /cmd_vel_selected
Nav2 /cmd_vel_nav     ┘                   ↓
                                 velocity_smoother
                                         ↓ /cmd_vel_smoothed
                                 collision_monitor
                                         ↓ /cmd_vel
                              driver thật CHƯA XÁC NHẬN
                                         ↓
                             wheel target / PI / CyberGear
```

**[N]** Gate khởi động disabled, manual mode, xóa command khi enable/switch,
chỉ giữ lệnh mới và clamp v/ω. YAML: 20 Hz, timeout0,3 s; max forward0,2,
reverse0,1 m/s, yaw0,6 rad/s. Smoother OPEN_LOOP 20 Hz, accel0,25 và
decel0,5 m/s², `scale_velocities=false`. Collision monitor nhận smoothed
và là publisher `/cmd_vel` theo launch/config này.
[Nguồn gate](../src/nino_pi/nino_pi/command_gate.py:17),
[selection](../src/nino_pi/nino_pi/selection.py:5),
[control YAML](../src/nino_pi/config/control.yaml:1).

**[S]** Đây là mô tả source candidate, không phải inventory trên Pi. Không
có telemetry robot xác nhận node/driver/owner nào đang hoạt động. Một
publisher cuối trong thiết kế không chứng minh không có publisher thứ hai
ngoài launch. Nav2 controller và behavior server có thể cùng có endpoint
`/cmd_vel_nav`; cần kiểm quyền active theo workflow, không gọi mọi multiple
endpoint ở topic đầu vào là xung đột motor.

### B. Tùy chọn `governor=true`: thay reference limiter

**[N]** `command_owner()` chỉ tạo **governor hoặc smoother**, không cả hai.
Governor đọc `/cmd_vel_selected`, phát `/cmd_vel_smoothed`; collision monitor
vẫn ở sau. Gate và governor đều mặc định disabled. Điều này đã có trong
README; không cần thiết kế lại một chuỗi với hai smoother chồng nhau.
[Launch branch](../src/nino_pi/launch/command_stack.launch.py:12),
[README](../src/nino_pi/README.md:255).

**[N]** Launch lấy giới hạn v/ω từ gate, accel/decel từ smoother YAML,
và yaw acceleration là `min(abs(accel_yaw),abs(decel_yaw))` =1,0 rad/s²
ở cấu hình đang đọc. Vì vậy governor YAML riêng ghi yaw accel1,5 không
phải effective value của branch mặc định này. Đây chỉ là source projection;
launch arguments/installed overlay thực tế chưa được dump.

### C. Screen v7 trong evaluator lockstep

**[N]** Follower/native scoring100 ms; inline governor100 hoặc20 ms; drive
PI torque qua `/cmd_vel`; fixed100 ms IMU/target-acceleration window trong
fast arm. Không mặc định Nav2, command_gate hoặc ROS `SpeedGovernor` node
đang điều khiển screen. Chưa chạy v7 live; source freeze vẫn nguyên.
[Frozen fast YAML](governor_isolated_cadence_contract_v7_2026-10-23/inputs/reactive_20ms.yaml:622),
[cadence adapter](../src/nino_rl/nino_rl/governor_cadence.py:85).

**[S]** A→B là thay cả reference processing branch. C→B là chuyển architecture,
không chỉ đổi tốc độ cập nhật. So A/B trên robot thật sau này phải kiểm soát
shaping/stop semantics trước khi gán toàn bộ delta cho adaptive detection.

## 3. Các phát hiện cụ thể và quyết định

### M1. YAML governor chưa tương đương cấu hình frozen

**[N]** Audit hợp nhất field của `GovernorSettings` với YAML wrapper trước
khi so frozen parameters; tránh bỏ sót defaults không hiện trong YAML.

| Field | Wrapper candidate mặc định | Inline frozen v7 | Ý nghĩa [S] |
|---|---:|---:|---|
| `target_scale` | 0,70 | 0,90 | Biên độ giảm tốc khác, không phải cùng treatment |
| `vertical_only_trigger_enabled` | **true** từ dataclass default | **false** | Nhánh trigger vertical-only đã ablate trong screen có thể lại được bật khi dùng wrapper defaults |
| `maximum_hold_seconds` | 2,5 | 1,0 | Release/holding khác; vẫn tính mỗi trigger, không là hard cap toàn chuỗi |
| `pulse_seconds` | 0,8 | 1,0 | Khác setting nhưng chỉ dùng cho profile pulse; không quy thành effect của reactive profile |

[Dataclass defaults](../src/nino_control/nino_control/governor_core.py:11),
[wrapper YAML](../src/nino_control/config/speed_governor.yaml:1).

**[Đ] Quyết định:** lưu hai contract riêng; chưa đồng bộ bằng cách copy0,90
hoặc tắt vertical-only trong source. Cần chọn mục tiêu hardware rồi review
effective parameters. Không sửa controller để làm audit “tương đương”.

### M2. Feature history khác dù dùng cùng core

**[N]** Wrapper tính RMS/peak trên các mẫu mới có `stamp > last_imu_used`;
RMS là trung bình bình phương theo số mẫu. Fast inline dùng trailing100 ms,
RMS từ `square_integral/duration`; `ImuWindow` giữ zero-order hold theo
timestamp và report coverage. Wrapper gọi core không truyền override
`target_acceleration_m_s2`, nên core dùng previous-update/dt; fast inline
truyền target-acceleration summary cửa sổ100 ms.
[Wrapper tick](../src/nino_control/nino_control/speed_governor.py:197),
[core acceleration](../src/nino_control/nino_control/governor_core.py:162),
[ImuWindow](../src/nino_rl/nino_rl/control_v2.py:268).

**[N] Ví dụ tổng hợp, không robot data:** các timestamp0/20/40/60/80/100 ms,
vertical tại20 ms bằng10 m/s², còn lại0. Tại100 ms, nếu wrapper đã dùng mẫu
đến40 ms thì RMS/peak của các mẫu mới =0/0; production `ImuWindow` trên
0..100 ms cho RMS4,4721 m/s², peak10. Ví dụ chỉ chứng minh summary không
giống nhau; core có memory nên chưa suy ra trigger/outcome sẽ khác thế nào.

**[Đ] Quyết định:** trước transfer cần chọn semantics theo giây và coverage,
rồi offline replay cùng raw input giữa adapters. Chưa implement việc đó
trong nhiệm vụ nghiên cứu này. Không gọi việc dùng chung dataclass/core là
bằng chứng observation contract đã giống nhau.

### M3. Thay branch đổi cả shaping và zero-reference behavior

**[N]** Wrapper clamp rồi nhân scale, interpolate Δv/Δω bằng một fraction
chung và có nhánh `reference==(0,0)` phát zero trực tiếp ở tick. Smoother
YAML mặc định không coupling proportional scaling giữa các trục.

**[T]** Source Nav2 Jazzy áp acceleration/deceleration constraints cả khi
reference đã zero; timeout cũng chuyển command về zero rồi đi qua đường
deceleration. Đây là source branch được truy cập23/10, chưa đối chiếu binary
Nav2 đã cài trên Pi.
[Velocity smoother source](https://raw.githubusercontent.com/ros-navigation/navigation2/jazzy/nav2_velocity_smoother/src/velocity_smoother.cpp).

**[S]** Gate stop/disable phát zero không đồng nghĩa torque hoặc body dừng
ngay. Minh họa reference-only trên sàn không xét backend: từ0,2 về0 ở
decel0,5 cần khoảng0,4 s nếu ramp lý tưởng; đây **không phải stopping bound
hoặc độ trễ đã đo**. Collision-monitor stop ở tầng sau là một đường khác;
software stop upstream không được gọi là physical emergency stop.

**[Đ] Quyết định:** dùng baseline A khi inventory/ID được mở sau này;
không so A/B rồi quy toàn bộ khác biệt cho governor. Dùng cùng stop contract
và cùng nominal shaping trong một comparative protocol riêng nếu mở B.
Không sửa bypass stop hoặc acceleration trong vòng review này.

### M4. Diagnostics schema không tự có từ CyberGear

**[N]** Wrapper subscribe `Float64MultiArray`, tên field từ
`layout.dim[0].label` phân tách dấu phẩy, yêu cầu:

```text
sim_time_s, executed_linear_m_s,
left_actual_rad_s, right_actual_rad_s,
left_target_rad_s, right_target_rad_s,
have_wheel_state, cmd_fresh
```

[Schema consumer](../src/nino_control/nino_control/speed_governor.py:107).
Trong packages đã review, producer là `effort_drive` dùng với Gazebo;
`nino_pi` không chứa STM32/CyberGear backend producer đã xác nhận.

**[S]** Đặt một array đúng tên/topic không chứng minh values có đúng nghĩa.
`executed_linear_m_s` ở simulated drive là reference đã xử lý, không body
velocity. Actual wheel values cần từ encoder, target cần từ sau backend
limits. Không điền target=requested chỉ để đủ field nếu firmware còn ramp.
Tên `sim_time_s` là compatibility field của schema hiện có; adapter thật
nếu xây cần nêu clock domain, không lấy receipt time rồi gọi source time.

**[Đ] Quyết định:** initial raw bag không yêu cầu chế tạo schema này. Chỉ
review adapter sau khi biết interface thật và nhu cầu bật governor. Không
khởi chạy `effort_drive`/Gazebo để làm topic hiện ra trên robot thật.

### M5. Container freshness khác freshness của encoder

**[N]** `on_feedback` kiểm field presence và finite; `tick` kiểm freshness
theo `sim_time_s` + local receipt và `have_wheel_state`. Không có required
source timestamp riêng từng wheel trong schema trên; `cmd_fresh` được
kiểm có/finite, không có check bắt buộc giá trị true tại đường tick này.
`effort_drive` giữ `have_wheel_state` sau callback; age có diagnostic nhưng
không có age rejection tường minh trong `_control_update` đã đọc.
[Freshness wrapper](../src/nino_control/nino_control/speed_governor.py:153),
[wheel callback](../src/nino_control/nino_control/effort_drive.py:431),
[control update](../src/nino_control/nino_control/effort_drive.py:449).

**[S]** Producer phát container stamp mới với encoder cũ có thể làm wrapper
thấy message fresh. Đây là khoảng trống contract khi chuyển backend, chưa
phải fault đã xảy ra trên robot thật hoặc lời kết luận simulation mất feedback.

**[Đ] Quyết định:** driver/adapter phải chứng minh tuổi source, mapping và
semantics các flags, qua raw encoder timeline độc lập. Không coi publisher
rate cao hoặc heartbeat mới là thay thế freshness từng kênh. Chưa sửa
guard runtime, không thêm instrumentation trước khi có driver evidence.

### M6. Velocity PI trên Pi và velocity PI trong motor là hai lựa chọn

**[N]** `effort_drive` biến base v/ω thành wheel targets, giới hạn wheel
acceleration, PI vận tốc xuất torque, thêm residual khi được enable rồi
effort/slew/speed limiting. Nó phát effort-controller commands; đây không
phải CyberGear speed-mode driver.
[PI/limiter path](../src/nino_control/nino_control/effort_drive.py:530).

**[S]** Nhiều limiter không tự là lỗi: command shaping và bảo vệ actuator
có vai trò riêng. Nhưng tổng response cần được đo, không cộng/deduplicate
lag bằng phỏng đoán. Chạy external velocity PI đồng thời với speed-mode PI
khác việc current inner loop nằm dưới một velocity loop.

**[Đ] Quyết định:** speed mode đã xác nhận → một velocity loop của firmware,
Pi gửi wheel reference; current/torque mode đã xác nhận → một external
velocity controller có contract rõ, current inner-loop vẫn riêng. Chưa chọn
nhánh, chưa chuyển sim gains/4 Nm/500 Hz xuống phần cứng.

### M7. Command timeout đang là tuổi receipt, không source age

**[N]** Gate nhận `Twist` không header và stamp bằng local monotonic khi
callback chạy. Expiry0,3 s kiểm từ receipt đó. Mode/enable xóa command cũ,
nhưng không thể suy tuổi publication gốc từ Twist không timestamp.
[Callback gate](../src/nino_pi/nino_pi/command_gate.py:33).

**[S]** Nếu backlog/network delay tồn tại, một command cũ vừa được callback
nhận không tự bị phát hiện là cũ từ upstream. Chưa có bằng chứng backlog
thật ở robot; không sửa stack sang TwistStamped chỉ vì khả năng này.

**[Đ] Quyết định:** ghi source/receipt clock và ownership theo interface thật
trước latency claim. Watchdog/backend-stop cần xác minh riêng, không lấy
gate timeout làm end-to-end stopping guarantee.

### M8. Collector có thể dùng ngay khi inventory được mở; không đo mọi latency

**[N]** `collect_real_data.py` đã ghi rõ: bag giữ header/receipt, supervisor
có wall/monotonic anchors, **không có per-message monotonic timestamp trong
bag**. Config diagnostics là optional; real-session unknown giữ null.
[Manifest semantics](../src/nino_pi/nino_pi/collect_real_data.py:263),
[collection config](../src/nino_pi/config/real_collection.json:1).

**[Đ] Quyết định:** tái dùng collector; không viết logger nữa. Có thể thu
encoder/IMU dù MCU model hoặc body reference chưa biết. Muốn tách network/
driver latency phải có clock uncertainty và stamps ở đúng tầng; nếu thiếu
thì chỉ report interval/gap tương ứng, không bịa decomposition.

## 4. Motion contract tối thiểu đã chuẩn bị

**[Đ]** JSON kèm theo là proposal, không là launch YAML, firmware config,
runtime release hoặc tuyên bố trạng thái thật. Các trường hardware chưa
xác nhận vẫn null. Nó làm rõ ba mức claim:

| Mức | Dữ liệu tối thiểu | Kết luận được / chưa được |
|---|---|---|
| Inventory đứng yên | Topic/type/endpoint + valid raw encoder/IMU; command owner và các kênh fault/power sẵn có; version/clock metadata | Có gì đang phát; chưa xác nhận sign khi chuyển động, response/slip hoặc readiness motor |
| Wheel response cổ điển | Sau khi backend/owner/power/limits được xác nhận: selected/final command, requested/limited wheel target, encoder source age, flags | Command→target→wheel intervals và limiter behavior; chưa đo body slip |
| Body response/slip | Thêm effective radius có tải + independent body reference + đồng bộ/uncertainty | Body/wheel mismatch trong scope đo; encoder odom không là reference độc lập |

IMU orientation/mount/gravity và telemetry schema là điều kiện bật wrapper,
không là điều kiện để bắt đầu ghi raw IMU. `JointState.effort` trống không
ngăn inventory; nó ngăn torque claim. Dùng đúng measured/reported/estimate/
command labels thay vì điền zero cho unknown.

**[Đ]** T3 trong roadmap cũ được giữ: session đứng yên trước; nếu hardware
motion được mở riêng, hold/matched-ramp ×3 lần, một payload/mặt sàn/backend,
giữ nguyên lần ngoài fit. Biên độ/speed thật chưa chốt, không tự dùng max0,2
trong YAML hoặc cruise0,4 trong sim làm lệnh đo. Đây là refinement T3,
**không thêm thí nghiệm thứ tư hoặc cấp lượt chạy mới**.

## 5. Hệ quả đối với quyết định toàn dự án

1. **[S] H2 vẫn unknown.** Audit này không thêm actual response hoặc crossing
   outcome; v7 vẫn chưa chạy. Nó phát hiện một rào transfer riêng, không
   thay lý do hard stop v6 hoặc mở lại batch cũ.
2. **[Đ] Ưu tiên A được cụ thể hóa:** xác nhận command/backend rồi đo response
   cổ điển; chưa bật governor. Cần đúng interface evidence, không cần toàn bộ
   thông số STM32 hoặc calibrated full dynamics trước inventory.
3. **[Đ] Trước mọi hardware governor comparison:** chốt identity settings,
   feature semantics, shaping/zero behavior và per-channel freshness.
   Tối đa một thay đổi có căn cứ qua protocol riêng nếu sau này quyết định
   sửa; không tự sửa cả bốn trong một lượt rồi gọi sim-to-real thành công.
4. **[Đ] Điểm dừng offline hiện tại:** source contract và proposal đã đủ cho
   bước quyết định sắp tới. Không đào thêm logging/launch audit nếu chưa có
   driver/session thật hoặc một câu hỏi cụ thể có khả năng đổi kết luận.

**Một việc nên làm ngay khi mở lại hardware:** một phiên inventory đứng
yên bằng collector hiện có để xác định backend thực sự đang chạy và các
target/encoder channels. Hardware hiện vẫn giữ lại; review này không mở
phiên đó. Tôi thay đổi khuyến nghị hoãn wrapper khi có driver/config/clock
evidence khớp một contract được chọn và replay feature/shaping đạt tương
đương mong muốn; một topic đúng tên hoặc thêm software tests không đủ.
