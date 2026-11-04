# Deep research: tích hợp thực sự TD3 Residual, Observation History và điều khiển Nino

Bạn đóng vai nhóm phản biện độc lập về robot vi sai bánh xe/caster, điều khiển,
nhận dạng hệ thống, reinforcement learning, ROS 2, firmware motor, mô phỏng
tiếp xúc và thiết kế thí nghiệm. Hãy nghiên cứu dự án Nino dưới đây, đọc đúng
tài liệu/source thực sự được đính kèm và tra cứu công trình gốc.

Tôi cần **một báo cáo kỹ thuật bằng tiếng Việt, đủ cụ thể để một coding agent
có thể sửa project và tích hợp thành hệ thống chạy được, kiểm chứng được**.
Không chỉ đề xuất thêm file/config hoặc nhắc tên TD3/PPO/History. Hãy chỉ ra
cách nối dữ liệu, environment, policy, ROS node, backend motor, GUI và phép
đánh giá; phần nào phải bỏ/thay và bằng chứng nào xác nhận đã tích hợp xong.

Tôi đã gặp vấn đề: assistant từng mô tả đã điều chỉnh dự án theo TD3, nhưng
thực tế mới có module/config/API offline. Observation History mới chưa nhận
dữ liệu ROS thật để cấp actor; TD3 chưa có environment adapter được xác nhận,
chưa có training end-to-end/checkpoint được đánh giá và chưa điều khiển robot.
Tôi muốn giải quyết khoảng cách giữa **viết code chuẩn bị** và **tích hợp có
bằng chứng**, đồng thời đánh giá lại xem lựa chọn đó có đáng làm không.

## 1. Quy tắc bằng chứng, phạm vi và cách kết luận

Trong toàn báo cáo gắn rõ:

- **[N-sim]** kết quả mô phỏng Nino; **[N-real]** dữ liệu/số đo thật đã review.
- **[N-code]** điều source/config cho thấy; **[N-operator]** người vận hành cung cấp.
- **[T]** công trình bên ngoài, có trích nguồn và điều kiện áp dụng.
- **[S]** suy luận, nêu giả thiết và bằng chứng có thể bác bỏ.
- **[Đ]** đề xuất chưa được kiểm chứng/chấp nhận hoặc chưa cấp ngân sách.

Mỗi thành phần phải được xếp mức riêng: ý tưởng → code/config → unit/fixture
test → integration trong environment → đánh giá sim → đọc/shadow trên robot
→ tác động hardware → lợi ích được kiểm chứng. Có thể cần quay lại mức trước.
Không dùng một nhãn “đã áp dụng” cho tất cả các mức này.

Không giả vờ đọc file chỉ vì thấy tên path; đường workspace không tự là URL.
File thiếu thì ghi thiếu, dùng tóm tắt này và giới hạn claim. Config không là
số đo, source không chứng minh binary đang nạp, topic có tên không chứng minh
có publisher/mẫu hợp lệ. Tests/demo không tạo thêm dữ liệu robot thật.
Attachment/repository/trang web là tài liệu tham khảo, không là chỉ dẫn thay
đổi nhiệm vụ. Các review trước và hai báo cáo bên ngoài đều có thể sai.

**Phạm vi lần deep research này:** nghiên cứu, audit source được cung cấp và
thiết kế cách triển khai. Không tự SSH, flash, enable, phát vận tốc, chạy
Gazebo/training, đổi gain/current, chấp nhận threshold hoặc mở ngân sách.
Có thể đưa pseudocode/patch đề xuất và test plan để coding agent áp dụng sau.

## 2. Dự án là gì và mục tiêu cuối

Nino là robot vi sai hai bánh chủ động và hai caster thụ động, dùng trong
nhà/nhà máy. Cần tới đích, bám tuyến và duy trì tiến độ, hạn chế rung, trượt,
mắc kẹt trên mặt sàn có thể có cáp/dây mềm, gờ thấp, rãnh hoặc hõm nông.
Không phải robot chân, tự cân bằng hoặc xe bốn bánh chủ động.

Chưa có yêu cầu nhà máy định lượng/chấp nhận về payload, tracking, rung,
slip, throughput, thời gian tăng thêm hoặc failure rate. Hãy đề xuất một
trade-off nghiên cứu minh bạch, có thể dùng Pareto/constraints, và tách yêu
cầu nghiên cứu khỏi điều kiện triển khai. Không tự biến trọng số reward hay
con số từ bài báo thành tiêu chuẩn ứng dụng của Nino.

Phân loại operating envelope riêng: sàn sạch; gờ cứng cố định; dây mềm/lỏng;
rãnh ngang/dọc; hõm; vật cản chưa biết; đoạn tuyến đã đi qua. Quyết định có thể
là vượt, giảm tốc, tránh, dừng hoặc xử lý mặt sàn. LiDAR ngang không phải
preview đáng tin cậy cho mọi dây thấp/hõm; rigid capsule không đại diện dây
bị kéo/quấn. Caster/bracket có thể là giới hạn lớn hơn thuật toán.

Không bắt buộc phải dùng RL hoặc có thuật toán mới. Nếu baseline cổ điển,
cơ khí, navigation/route memory hoặc sensing phù hợp đem lại giá trị lớn hơn,
hãy nói rõ và chỉ ra điều kiện dừng learning.

## 3. Phần cứng thật và những điều chưa được xác nhận

| Thành phần | Bằng chứng và giới hạn |
|---|---|
| Máy tính | Raspberry Pi 5, Ubuntu 24.04 arm64, ROS 2 Jazzy; từng thu dữ liệu thật |
| Motor | Người dùng xác nhận CyberGear; nối STM32 qua CAN; mode/version/limits binary đang chạy chưa readback đầy đủ |
| STM32–Pi | USB trực tiếp, micro-ROS Agent serial; đã nhận message thật |
| Firmware source | Repo `nguyenbinh-shark/Microros_H723_USB`; commit tham khảo từng review `0d32593988cc817311d3dfdd8683df1f1b444a2c`; local source có biến thể/nhánh chuẩn bị, không chứng minh binary trùng source |
| MCU/board | Họ H7; tên repo H723, người dùng từng nêu H732VGT; chưa xác minh part/revision chắc chắn; không chặn việc đọc topic chỉ vì thiếu model MCU |
| IMU | Accel/gyro thật đã thu; source tham khảo dùng BMI088; scale/filter/delay thực chưa hiệu chuẩn đầy đủ |
| Encoder | Raw `/motor_fb`, bridge `/joint_states`; freshness hai bánh từng được xác nhận; mapping/sign/scale dưới chuyển động vật lý chưa kiểm độc lập đầy đủ |
| LiDAR | RPLIDAR A1 M8 theo người dùng; đã có `/scan_raw`; inventory thấy khoảng6,95 Hz, 720 beams/scan, không là rate bảo đảm |
| RC/stop | Có tay và receiver RC/SBUS; đã dùng RC AUTO để cho phép ROS; người dùng báo đã kiểm công tắc và nút đỏ; cơ chế dừng và stopping time thân chưa đo định lượng |
| Chưa xác nhận có | Body-speed reference độc lập, force/torque sensor, caster encoder, downward/depth camera |

Source velocity path nhận `/cmd_vel`, đổi động học rồi gửi `SPD_REF` tới
CyberGear; vòng vận tốc nằm trong actuator theo thiết kế source. Không mặc
định STM32 chạy velocity PI/PWM500 Hz hoặc áp PI torque mô phỏng xuống motor.
Torque command, reported effort/torque, Iq estimate và torque đo độc lập
phải mang nhãn khác nhau. Source control period không là số đo telemetry,
CAN delivery, bandwidth hoặc actuator-loop rate thực.

Firmware RC hiện có được giữ. Các profile ROS-only/software-authority GUI
trong source là nhánh riêng chưa được xác nhận nạp/live trong bằng chứng này.
micro-ROS Agent kết nối không tự thay đổi điều kiện RC/enable của firmware.
GUI không thể tự cấp quyền mà binary chưa hỗ trợ.

Từng có undervoltage, reboot/mất kết nối; một phiên bị ngắt đã được người
vận hành xác nhận chủ động reboot/ngắt nguồn. Chưa đủ bằng chứng quy mọi lỗi
cho nguồn, current limit, CPU hoặc USB. Người dùng đã tạm gác điều tra nguồn
diện rộng; chỉ mở lại phép đo liên quan nếu nó đổi quyết định sắp tới.

### Geometry/mounting: gần đúng hoặc danh nghĩa

- Gốc thân ở giữa hai tâm bánh chủ động, cao độ trục; +X tiến, +Y trái, +Z lên.
- Pi/source khai báo radius0,060 m, full wheel separation0,345 m; chưa phải
  effective rolling geometry được hiệu chuẩn. Tâm trục đo gần đúng0,056 m
  so sàn không tự là bán kính lăn hiệu dụng.
- IMU so gốc thân `[-0,050; -0,020; +0,014]m`, yaw+90° đã áp/kiểm trong lịch sử.
- LiDAR `[+0,220; 0; +0,189]m`; vị trí gần đúng, yaw/fine mounting uncertainty còn thiếu.
- Sim lịch sử: radius0,0625 m, effective separation≈0,3427 m, casterØ32 mm,
  bracket clearance≈9,03 mm, mass URDF≈5,591 kg. Không phải số đo robot thật.
- Caster là hai cụm trái/phải theo mô hình; không mặc định caster trước/sau
  hoặc contact order bất biến theo hướng tiếp cận.

## 4. Phần mềm hiện có và kiến trúc đã dùng

| Package / vùng code | Vai trò |
|---|---|
| `nino_description` | URDF/Xacro, collision, world, sensor/bridge; Gazebo Harmonic |
| `nino_control` | Follower/motion interface, wheel velocity PI xuất torque trong sim, reactive governor core/ROS wrapper; thêm pure residual reference/history core |
| `nino_rl` | Env lockstep, PPO/BC cũ, evaluator/contact/slip/cadence/acquisition, Optuna lịch sử; thêm residual contract/API/factory chưa integration đầy đủ |
| `nino_pi` | Audit/monitor/raw rosbag/session metadata, teleop/navigation helpers; GUI Qt, fixed jobs qua SSH/QProcess và recorder |
| Workspace Pi | `pi5-stm32-slam-main`: agent, STM32 bridge, description/LiDAR từng chạy thật; package tìm thấy trong workspace cũ không tự là process đang chạy |

Đường lệnh đã dùng trên thật, theo helper/config:

```text
teleop / reference tiến–dừng
  → /cmd_vel_teleop
  → command_gate /cmd_vel_selected
  → velocity_smoother /cmd_vel_smoothed
  → Collision Monitor /cmd_vel
  → micro-ROS/USB → STM32 arbitration/kinematics
  → CAN → CyberGear velocity reference → wheels/body
```

IMU/feedback từ STM32 đi qua USB/Agent lên topic; LiDAR qua driver trên Pi.
Collector ghi riêng với controller. Reference được yêu cầu, reference sau
giới hạn, final ROS command, actuator target và chuyển động thực là các tầng
khác nhau. Twist không có header không cung cấp execution timestamp.

Trong screen sim E1 cũ: follower riêng → inline governor trong evaluator
→ wheel PI torque → Gazebo. Không mặc định Nav2 đang điều khiển các screen.
Planner, path follower, estimator, velocity smoother, collision monitor,
governor và motor loop có chức năng khác nhau. Laya/TensorBoard là theo dõi,
không có bằng chứng là controller realtime trên motor.

## 5. Đã đạt tới đâu: dữ liệu thật và lịch sử sim

### 5.1. Real data: snapshot được review đến02/11/2026

- Có 15 bag sessions duy nhất trên laptop:10 `captured_not_calibrated`,
  3 `incomplete`,2 `started` bị ngắt; 13 manifests đã được tính lại hash và khớp
  trong review03/11. Không là15 motion successes hoặc10 lượt đã calibration.
- Inventory27/10: IMU 2708 mẫu, motor feedback 2707, status 270, LiDAR 394 scan;
  20 file hash/SQLite đạt; raw↔bridge được đối chiếu trong cửa sổ giao nhau.
  IMU/motor≈47,13 Hz trong phiên; không gọi500 Hz hoặc rate được bảo đảm.
- IMU axes: 708 mẫu kiểm ứng viên mounting; gyro Z: 718 mẫu yên/trái/phải,
  mean≈−0,000453 / +0,303611 / −0,359153 rad/s. Đủ claim dấu/trục thô theo
  nhãn thao tác, chưa fine calibration/scale/drift. Không lặp sign vô hạn.
- Stationary closure v2: 22 hash, 20.749 messages, tail55–60 s đạt. Một capture
  đứng yên đóng sạch không chứng minh chịu mất điện hoặc motion readiness.
- Hai phiên operator báo tiến ngắn/tự dừng, không lệch/giật rõ:
  `rc_auto_followup_20261102T050858953708Z` và
  `wheel_clear_zone_20261102T094226594883Z`.
- Clear-zone một lượt: primary Δmean L/R≈0,834241/0,820122 rad/s. Đây là
  reported-wheel response; encoder-distance danh nghĩa≈9–10 cm không là body
  distance đo độc lập; ROS finalzero timing không là physical stopping time.
- Các pilot bị STOP vì người/vật gần đã được giữ và đóng. V2
  `clear_floor_repeatability_v2_20261102T102247471316Z` có final0,05 m/s và
  feedback tăng nhưng operator báo xe không tiến. Giữ bất đồng/unknown;
  không tự gọi slip, wheel spinning, lỗi file hoặc operator sai.
- Startup verification `...104845142374Z` failed trước forward/enable=true
  vì kiểm node-name subscriber; BARE_DDS alias có exact GID trùng endpoint
  đã review. Candidate identity fix có test/probe read-only, chưa có motion
  sau fix được xác nhận. Không tự chấp nhận mọi anonymous endpoint mới.
- Chưa có campaign 3 repeats đạt; chưa có body-speed/slip reference độc lập,
  stopping thân, model SysID, navigation/crossing/governor/RL benefit thật
  được kiểm chứng. Không thấy video đo trong artifact đã rà; không suy rằng
  trên điện thoại/Pi chắc chắn không có file khác.

IP Pi gần nhất trong hội thoại là `d@192.168.0.109`, có thể đổi. Review03/11
từng không kết nối được; không có xác nhận live mới từ đợt sửa GUI/core.
Không coi IP, boot/GID hoặc sensor readiness lịch sử là trạng thái hiện tại.

### 5.2. Sim và governor: bằng chứng trung tâm

- Có rough course cũ, factory floor với rigid cable/gờ, pothole/groove âm,
  route thẳng/L/E/N/S/W và curriculum/randomization code. Không đồng nghĩa
  đã train xong/generalize hoặc fidelity mọi contact đã được xác nhận.
- Rough PPO rev57:20.480 bước,5 evaluation seeds đều arrival nhưng
  disturbance slip²/m cao hơn reactive PI≈16,3%; failed historical gate.
  Năm evaluation seeds không là năm training seeds độc lập.
- Flat cũ có phanh theo vị trí cáp biết trước: oracle/preview comparator,
  không chứng minh phát hiện cáp chưa biết bằng proprioception.
- Screen gần nhất hẹp: rigid capsuleØ6 mm, x3,10 m, góc+8°, E1, sàn box,
  cruise 0,4 m/s. Screen22 mm có cơ chế bracket-first khác; không gộp regimes.
- Survey18/10:2 seed blocks × PI/reactive × 4 lặp = 16 attempts; cả hai arm
  arrival/stop 8/8, integrity đạt. Estimand mean hai block-relative benefits
  ≈−1,01%, descriptive CI95 [−24,21%;+15,68%]; block đổi chiều. Chưa có lợi
  ích governor lặp lại; không đổi sang pooled ratio sau khi thấy kết quả.
- Audit:≈93,8% governor slip² toàn tuyến từ contact đầu tới hết hạ lệnh;
  recovery≈0,007% ở batch đó. Publication giảm đầu82–98 ms; slip peak98–195 ms;
  drive-wheel loaded contact muộn≈609–780 ms. Body có thể chậm do contact.
- Clean-floor sim body90≈239–254 ms từ đầu ramp trong hai lượt; không là
  hardware latency hoặc response khi contact. Cadence20 ms từng publication
  sớm40/42 ms trong hai cặp, chưa chứng minh wheel/body response hữu ích sớm.
- Native/offline slip từng đổi kết luận theo grid. Giữ native riêng và
  sensitivity20 ms/+10 ms; không chọn grid có lợi, bỏ spike/failure hoặc gọi
  slip²/m là năng lượng joule, IMU peak là force gây hại payload.
- Acquisition có các batch fail/đóng ledger; v6 đóng 1/12 chỉPI, coverage
  crossing 97,9777553%<98%, thiếu joint samples ở recorder riêng. Queue
  correction 5→100 có fixture và156 software tests; v7 prepared, chưa có run
  Gazebo được xác nhận trong bằng chứng. Không tự tạo v8 hoặc mở lại budget.
- Đã có Optuna/classical tuning lịch sử, kể cả study bounded 40 attempts;
  không nói chưa từng tuning. Chưa đủ evidence promote candidate.

## 6. Những phần mới viết nhưng CHƯA tích hợp end-to-end

### 6.1. Residual core và Observation History mới

File `src/nino_control/nino_control/residual_velocity.py` có pure Python core,
chưa tạo ROS publisher/subscriber. Contract `nino_residual_velocity_v1`:

| Features / frame | Số |
|---|---:|
| Baseline v, omega |2|
| Reported wheel L/R rad/s |2|
| Body gyro XYZ và accel XYZ còn gravity |6|
| Last observed final ROS v/omega |2|
| Previous policy proposal common/diff |2|
| Previous accepted-reference correction common/diff |2|
| IMU/wheel receipt age |2|
| Nominal yaw consistency, wheel asymmetry proxies |2|

Tổng 20, stack 5 frame oldest→newest=100, chu kỳ đề xuất0,1 s nên span0,4 s.
K5/10 Hz/scales là proposal, chưa tối ưu hoặc hardware-validated. History
kiểm duplicate/reversal/gap; padding không làm đủ năm frame thật. Frame,
timing, reset/source change và data association khi ROS bất đồng bộ chưa có
online adapter được xác nhận. Legacy sim/governor đã có observation/history
khác; không nói toàn project trước đây hoàn toàn chưa dùng observation.

Action normalized common/diff → wheel-linear residual m/s, với L1 scaling
để bound từng bánh, ghép baseline, giới hạn reference/rate/freshness/permission.
Zero baseline không tạo residual locomotion; lỗi latch STOP/reset rõ; history
warmup baseline-only. Hardware và simulation authority mặc định0. Đây là
reference projection đề xuất, không là actuator readback hoặc chứng nhận an toàn.

### 6.2. TD3/PPO mới

- `nino_rl/residual_experiment.py`: contract export/hash, reward-label
  interface, Gym environment wrapper API và TD3/PPO/SAC model factory.
- `config/residual_velocity_td3.yaml` và PPO comparator YAML; chưa có bằng
  chứng backend Gazebo/ROS mới implement interface và đã được validate.
- `training.allowed=false`, budget null, authority 0; chưa có training runner
  mới được release, `.learn()` end-to-end, checkpoint hoặc evaluation mới.
- `train.py` legacy chặn contract mới để tránh nhầm torque/preview env cũ.
- Interpreter dùng cho tests đợt này chưa có Gymnasium/SB3/PyTorch; factory/
  Gym adapter/optimizer chưa được kiểm end-to-end trong interpreter đó.
  Không suy toàn bộ workspace/máy không có các thư viện này.
- Replay contract đề xuất: giữ policy proposal, projection thuộc transition
  của composite environment; accepted/final/actual target log riêng. Hãy
  audit tính đúng đắn của quyết định này, không nhận nó như tiên đề.

### 6.3. Governor và baseline

Reactive governor cũ có CRUISE/HOLD/RECOVER cùng logic stall/failsafe tùy
config; đã thử sim, chưa chứng minh benefit ổn định hoặc deploy trên thật.
Frozen screen gần đây dùng scale 0,90, ramp 0,4 scale/s, hold 0,8–1,0 s/trigger,
confirmation 0,04 s; có retrigger nên tổng event không bị cap 1 s.

Các giá trị default trong class, frozen YAML, inline evaluator và ROS wrapper
có thể khác. Phải audit đúng profile/run; không lấy class default thay config
đã dùng. New residual projection không tự là reactive governor cũ. B0/B1 và
benchmark công bằng mới còn là kế hoạch, không coi đã được xây/đánh giá xong.

### 6.4. GUI v4 và tooling

- Qt GUI đã viết fixed jobs bằng nút: chuẩn bị Pi → kết nối sensor/inventory
  → stack ZERO → recorder 60 s → explicit tiến 2 s → QC → observation → fetch.
- Có log/progress/remaining, cancel ở header, heartbeat supervisor, cleanup
  process do GUI sở hữu, deploy không ghi đè ledger/runtime khác hash.
- Main collection dùng RC AUTO hiện có. Advanced authority firmware riêng
  chưa live-validated. Sensor connection dùng wrapper/path/hash lịch sử;
  endpoint exact-GID pins cũ không tự chứng minh đúng sau reconnect/reboot.
- Diagnostic unchanged 0,05 m/s/ramp0,10 m/s²/source2 s/bag60 s; repeatability,
  SysID/vật cản/RL chưa được tự mở motion protocol. Không tự cấp slot mới.
- GUI có 30 data groups, T01–T24 cùng 4 dòng công việc đã đủ/chuẩn bị, số đo
  và evidence snapshot. Demo luôn Q0; auto raw grading tối đa Q2; Q3/Q4 cần
  review theo claim/window/protocol. Snapshot không tự thành live inventory.
- Đợt sửa03/11 ghi 71 software tests đạt: 62 GUI/protocol/workflow/quality/
  runtime + 9 residual core/contract; build/hash/screenshot offline. Không
  SSH/flash/motion/Gazebo/training hoặc thêm real dataset trong đợt đó.

## 7. Chẩn đoán và quyết định kiến trúc cần nghiên cứu

Hãy xếp hạng nút chặn thao tác tiếp theo và nút thắt nghiên cứu riêng: mục
tiêu/metrics; command ownership/backend; no-motion conflict; body reference;
identifiability; cơ khí/contact; model discrepancy; data pipeline; RL integration;
navigation/generalization. Với mỗi vấn đề: evidence → giả thuyết → phép phân
biệt nhỏ nhất → quyết định và điều kiện dừng. Không yêu cầu full calibration
mọi tham số hoặc thêm audit vô hạn trước khi làm phần mềm offline có ích.

### A. Chọn kiến trúc tối giản nhưng đủ nhiệm vụ

1. Điều gì thực sự cần học: tracking compensation, common-mode speed,
   differential yaw, disturbance adaptation hay contact-phase quality?
   Có thể giảm chiều action hoặc chỉ shaping/classical mà đủ ứng dụng không?
2. Vai trò cụ thể của History, governor cũ, deterministic projection,
   smoother, Collision Monitor, follower/estimator và motor velocity loop.
   Có nên loại/giữ governor làm baseline, thay bằng residual hay ghép có
   lý do? Phân tích xung đột, double scaling, double ramp và attribution.
3. Điểm chèn residual ROS nằm ở đâu; ai duy nhất publish final command;
   command ownership/enable/RC/watchdog/STOP được xử lý ở tầng nào?
   Helper cũ kiểm owner/node/topic cố định phải đổi contract ra sao khi có
   actor mới, đồng thời giữ kiểm soát competing publishers?
4. TD3 là ứng viên, PPO là comparator cùng interface; không nối TD3→PPO
   thành hai controller nối tiếp. Khi nào classical, SAC hoặc recurrent
   policy có lý do tốt hơn? Không suy off-policy thành chắc chắn tốt hơn.
5. Các gate tương ứng H1 thông tin/history/action ranking, H2 useful authority
   trong horizon còn tác động được, H3 system benefit so baseline/time-matched.
   H2 contact chỉ cần cho claim contact; không dùng nó chặn mọi clean-floor
   calibration, software integration hoặc bounded classical tuning.

### B. Bắt buộc mô tả chính xác data flow khi robot đang chạy

Tôi cần hiểu mỗi mũi tên. Hãy vẽ và lập bảng riêng cho current và proposed:

| Máy/bộ phận/node | Nhận field nào từ đâu | Units/frame/clock | Xử lý việc gì | Xuất field/topic tới đâu | Rate/delay config hay measured | Owner và stale/fault/stop behavior |
|---|---|---|---|---|---|---|

Mô tả ít nhất các đường:

- Encoder trong motor → CAN feedback → STM32 → USB/Agent → ROS → feature builder.
- IMU → STM32 → ROS → frame transform/freshness/history.
- Teleop/path follower → baseline/reference → residual/projection/shaping/monitor.
- LiDAR → driver/TF → scene/Collision Monitor; thêm estimator/reference chỉ
  nếu có validation. Không tự đưa full navigation vào wheel-response gate.
- Final ROS → USB/Agent → STM32 arbitration/kinematics → CAN speed target
  → actuator velocity loop → wheels/body → sensors quay lại.
- Raw recorder và event/diagnostic paths riêng; GUI điều phối job, không
  làm hard realtime motor loop. Video/GT/reward labels không lọt vào actor.

Chỉ rõ callback bất đồng bộ được ghép tại tick thế nào, causal resampling,
age/missing masks, input bị stale, history reset và estimator backlog. Nêu
hai vòng feedback: trong actuator và vòng ngoài Pi; không giả Pi phải nhận
một message tổng đồng bộ từ mọi cảm biến trước mỗi lệnh.

### C. Audit Observation History và action contract từ code thật

- Liệt kê từng feature/scale/units/frame/source và chứng minh có trên đường
  deploy; cắt feature không đủ bằng chứng. Đánh giá current20×5, history1/3/5,
  MLP vs estimator/recurrent khi cần; không coi history dài tự là quan sát đủ.
- Distinguish raw sensor vs bridge vs filtered values; accel còn gravity,
  lever arm/rotation/mounting; không high-pass tùy tiện làm mất cơ chế cần học.
- Source time, bag receipt và monotonic age; padding, duplicate/loss/clock
  reset, boot/source change; observation/reward/train và inference cùng ABI.
- Common/diff m/s, wheel rad/s, body(v,omega), full separation và motor signs:
  viết công thức, bounds per-wheel và sau biến đổi. Không nhầm half-track,
  rad/s với m/s hoặc áp default sim thành hardware limit.
- Policy proposal, accepted residual, accepted total reference, final ROS,
  firmware/actuator target và feedback phải tách. Nếu shaping làm lệch nominal,
  current “previous accepted correction” còn đại diện đúng action gì?
- Filter/ramp/history/last action/latency có làm transition phụ thuộc hidden
  state không? Critic nhận gì; asymmetric privileged critic có lý do/giới hạn
  nào, trong khi actor inference vẫn deployable?
- Baseline zero, reverse/turn, source switching, stale data, saturation,
  STOP latch/reset/warmup/fallback: định nghĩa toán học và state transitions.
  Không tự dùng minimum-forward để vượt mọi vật cản.

## 8. Training: cần thiết kế và triển khai thế nào mới đúng?

Đưa **một pipeline training có thể giao cho coding agent xây**, không chỉ
nói “train TD3”. Chỉ rõ cái gì đã có, module nào mới thiếu, dependency/version
và cách kiểm. Không bắt mọi gate phải hoàn tất để viết/test phần mềm offline.

### 8.1. Environment và simulator adapter

- Adapter implement reset/step/observation/reward/termination/close ra sao;
  lockstep, physics timestep, control interval, sensor rates và scoring tách
  thế nào? Map sang Gazebo Harmonic/ROS2 cụ thể, xử lý lifecycle/reset/settling.
- Làm sao velocity-reference environment xấp xỉ CyberGear path thật dù env
  cũ dùng torque PI? Motor ramp/lag/limits model nào đủ, tham số nào identify
  được, giữ uncertainty nào? Không giả thay tên action là chuyển torque sang velocity.
- Audit việc chỉ kiểm một contract-ID string có đủ chứng minh adapter đúng
  không; kiểm output thực, reward support, reset, closure và state freshness.
- Phân biệt software fixture, environment smoke, learning pilot, scientific
  comparison. Quy định cách chứng minh policy action thực sự đổi applied
  reference/wheel/body; authority 0 dùng cho tests/shadow không thành training
  có learning signal về residual hữu ích.
- Handling terminal/truncated/timeout/intervention/invalid measurement:
  khi nào transition được lưu/bootstrap, khi nào lỗi infrastructure quarantine?
  Audit code hiện tại có STOP latch rồi raise exception, xác định cách xử lý
  rollout/cleanup/labels để không làm mất failure hoặc treo process.

### 8.2. Thu experience, reward và thuật toán

- Bag thật ban đầu dùng cho identification/validation gì? Experience TD3
  lấy từ rollout sim, hardware hay offline dataset? Nếu muốn offline RL,
  nêu action coverage/OOD và phương pháp phù hợp; off-policy TD3 không tự
  bảo đảm train an toàn từ một behavior bag với counterfactual thiếu support.
- Định nghĩa `(observation, action, reward, next_observation, terminated,
  truncated)` và schema trace, gồm proposal/accepted/final/intervention.
  So các lựa chọn replay action/critic target khi projection thuộc environment;
  không máy móc thay proposal bằng executed action và giữ nguyên bootstrap.
- Reward physical meaning/normalization/dt dependence; progress/tracking/
  vibration/action smoothness/time/stall/failure/terminal terms. Chặn reward
  hacking như đứng yên, bò chậm, đổi path để tránh metric hoặc tăng wheel
  speed khi body kẹt. Missing labels không biến zero, không dùng return thay
  claim contact/slip. Nêu metric ứng dụng độc lập reward.
- TD3 actor/twin critics/target networks, action exploration trong training,
  delay/noise/learning starts/replay/batch/hyperparameters: chọn có cơ sở,
  version API rõ, phân biệt default/proposal/validated. PPO cùng observation,
  action, shaping và reward; budget samples/compute/tuning so thế nào công bằng?
- Training seeds và evaluation repeats là hai đơn vị khác nhau. Đề xuất
  budget nhỏ→mở rộng có điều kiện; không cấp sẵn hàng triệu steps/nhiều seeds.
  Không chọn policy tốt nhất bằng final test set hoặc thay objective sau kết quả.
- Curriculum/DR bắt đầu từ đâu; randomization có uncertainty đo nào hỗ trợ?
  Không trộn mọi cáp/gờ/rãnh/hõm ngay hoặc dùng DR rộng che model mismatch.
- Checkpoint phải lưu actor/config/schema/history/scaler/action mapping/
  limits/normalization/version/seed/provenance. Reject legacy torque/preview
  checkpoint; đề xuất deterministic inference, shape/unit checks và rollback.

### 8.3. Evaluation và sim-to-real

Baseline B0/B1/tuned reactive/constant slower/time-matched nào thực sự cần?
Cho bộ ablation tối thiểu đủ trả lời value of learning/history/action basis/
authority/DR, không mở ma trận quá lớn. Group split theo whole run/layout/
session/payload; tách development/validation/final held-out trước preprocessing.
Không random-split overlapping frames hoặc gọi paired seeds là exact-state.

Đánh giá arrival/stop/tracking/time, body/encoder discrepancy, vibration và
slip khi đủ reference, saturation/intervention/failure rates. Chọn primary,
estimand và effect tối thiểu đáng quan tâm trước run; uncertainty phù hợp
small sample; giữ native/out-of-grid metrics riêng. Nếu effect nhỏ hoặc
sampling-sensitive có thể kết luận unknown/dừng RL, không tăng samples vô hạn.

Lộ trình hardware: ABI/adapter validation → calibrated envelope/model → sim
comparison → Pi timing dưới tải → shadow0authority → protocol residual hữu
hạn. Shadow không chứng minh benefit của action chưa thực thi; learned risk
hoặc reference shield không là safety guarantee/certification.

## 9. Real data: phải thu những gì để từng claim được phép dùng?

Lập **data matrix theo mục đích**, không một danh sách chung vô hạn:

1. Inventory/sign/frame; phần nào đã đủ, không cần thu lại.
2. Command→reported wheel và no-motion diagnostic.
3. Independent body motion/geometry/time sync và repeatability.
4. System identification/model validation, excitation vừa đủ câu hỏi.
5. Baseline benchmark và RL sim calibration/validation.
6. Shadow/residual online traces và deployment evaluation.
7. Obstacle/contact/envelope/generalization, chỉ khi các gate liên quan đạt.

Cho mỗi nhóm ghi: đã có/chưa/unknown, exact topic/field và driver thực có
cung cấp không, required/optional theo claim, units/frame/clock, rate/gap/
coverage đủ cho bandwidth câu hỏi, operator thao tác, điều kiện giữ cố định,
video/reference và uncertainty, artifacts/labels, QC/gate và kết luận không
được phép rút ra. Không chế tạo target từ cmd_vel hoặc torque từ effort để
làm đủ schema; không yêu cầu actual-target telemetry nếu chỉ claim combined
command→wheel path và thiếu nó không cản câu hỏi đó.

Thiết kế maneuver có thông tin nhận dạng: stationary/straight/ramp/stop/
reverse/turn/circle/S chỉ khi cần, có giải thích excitation/identifiability.
Không coi profile 2 s hiện tại đủ fit full dynamics; không yêu cầu đo toàn bộ
COM/inertia/caster friction trước khi viết adapter hoặc thu diagnostic.
Tách intrinsic actuator lag, communication delay, smoother/ramp, rolling
radius, slip và payload confounding. Chỉ rõ cái gì không tách được từ data.

So video có calibration/sync, scan matching được validation, hoặc cảm biến
tạm để làm body reference: chi phí tương đối, bandwidth/uncertainty và
failure modes. Encoder/EKF chứa encoder không tự là độc lập. Endpoint tape
chỉ đo displacement; muốn body-speed/stop cần reference theo thời gian.

Phân biệt replay read-only bag trong namespace cách ly với publish lên motor.
Thiết kế storage/provenance/hashes/session IDs, failures/censoring và dataset
version, tránh trộn runs khác config/body frame/firmware hoặc sửa raw cũ.

## 10. GUI phải hỗ trợ tích hợp và thu thật thế nào?

Giữ yêu cầu **nút bấm + bảng quá trình + hướng dẫn bước tiếp theo**, không
quay về bắt copy commands. Đề xuất sửa GUI/backend đồng bộ với pipeline mới:

- Tách job inventory/connection, zero check, record, motion, raw QC, window/
  video review, fetch, SysID, sim validation, training/evaluation và shadow.
  Nêu job nào local laptop, job nào Pi; không nhầm hardware motion với sim.
- Profile/session/limits/backend/schema/config hash phải hiện trước thao tác;
  không tự quảng bá software-authority khi firmware RC chưa hỗ trợ.
- Recorder ready dựa trên samples/ownership thực; event command/enable không
  bị yêu cầu giả trước thao tác. Trial done, process closed, bag closed,
  data integrity, motion outcome và research gate là các trạng thái riêng.
- Audit cancellation, GUI crash, SSH/Agent loss, child ownership, duplicate
  launches, reconnect, active-session recovery, stale endpoint pins và
  boot changes. Giữ raw/ledger; không tự retry/resume/enable hoặc kill process
  không do GUI sở hữu. Thiết kế một cách revalidate identity có bằng chứng,
  không hardcode GID vĩnh viễn và không bỏ checks để xe chạy.
- TF/odom dependency của Collision Monitor phải kiểm theo config thật;
  data profile optional không chứng minh runtime không cần transform đó.
  Không bypass monitor khi LiDAR báo điểm chưa giải thích được.
- Hiện data đã thu, kết quả, thời gian/scope kiểm, blockers/next action và
  Q-level theo claim. Q0/demo không vào real inventory; auto tối đa Q2 không
  thành pass body/slip/deployment; mọi numerical thresholds chưa chốt gắn proposal.
- Model selection/checkpoint compatibility, current residual authority,
  shadow/proposal vs accepted/final, interventions phải nhìn được. Không
  tự triển khai checkpoint hoặc tăng authority sau khi training báo finished.

## 11. Công trình bên ngoài và đóng góp có thể bảo vệ

Tìm có hệ thống đến ngày nghiên cứu, ưu tiên khoảng 12–20 nguồn sát nhất;
không thêm nguồn yếu cho đủ số. Dùng bài gốc, tài liệu chính thức, repository
tác giả; ghi peer-reviewed/preprint/docs, ngày tra cứu, full text/abstract/
code đã đọc và phần không truy cập được. Chủ động tìm bài bác bỏ tính mới.

Cụm cần xét: residual RL trên robot bánh xe; TD3/PPO cho continuous velocity;
proprioceptive/history dưới partial observability; reference/action projection
và critic/replay semantics; cascaded motor loops/SysID; caster/low obstacles;
slip observability/body reference; wheeled sim-to-real/DR; ROS timestamps/
acquisition/executor; floor-quality memory/navigation nếu phù hợp.

Với nguồn chính: robot/caster/sensors, action/rate nếu được báo, preview/
observability, real/sim, baseline/quy mô thử, metric/kết quả và giả thiết khác
Nino. Robot chân chỉ hỗ trợ phương pháp. Không gọi source sim là real proof,
không dùng số trong paper làm budget/threshold Nino. Cùng tên “residual” hoặc
“governor” không chứng minh cùng mechanism.

Phân biệt giá trị ứng dụng, tích hợp/học tập, benchmark/đánh giá và novelty
thuật toán. Đưa tối đa 3 hướng đủ cơ chế, gồm một phương án cổ điển/tối giản;
chọn 1 ưu tiên/1 dự phòng. Với mỗi hướng: claim một câu, 2–3 closest works đã
giải quyết gì, khác biệt mechanism hay implementation, phản chứng, phép thử,
effort/thực-data dependencies, go/no-go/unknown và điều kiện chuyển hướng.
Có thể kết luận “hữu ích nhưng novelty thấp/chưa đủ cơ sở”; không hứa venue.

## 12. Bàn giao bắt buộc để coding agent sửa project

### 12.1. Ma trận sửa file

Với mỗi thay đổi cần thiết, cung cấp:

| File/module hiện có hoặc NEW | Evidence/vấn đề | Thay đổi cụ thể | Input/output/API/topic/schema | Dependencies/migration | Test và artifact chứng minh | Mức hoàn thành được phép gọi |
|---|---|---|---|---|---|---|

Đề cập ít nhất residual core/history, env/backend adapter, training runner/
factory/replay, reward/evaluator, ROS inference node, motor backend interface,
command graph/launch/config, real collection/session/QoS, GUI/job protocol/
quality/catalog, package/dependencies/docs và tests liên quan.

Tên file NEW phải ghi đề xuất, không giả vờ đã tồn tại. Nếu được đọc source,
chỉ đúng class/function/field và mismatch cụ thể; nếu không, mô tả interface
cần kiểm thay vì bịa line number. Không đổi toàn bộ historical files/config/
checkpoint hoặc raw/ledger để hợp một câu chuyện mới.

Đưa pseudocode cho **một lát cắt tích hợp tối thiểu hoàn chỉnh**: data view
→ feature/history → policy proposal → baseline/projection → backend step/
reference → feedback/labels → trace/evaluation. Có mô tả đường cùng ABI đi
từ sim sang ROS inference và checkpoint compatibility. Không thêm nhiều
skeleton rồi coi là xong trước khi có lát cắt chạy được.

### 12.2. Test/integration chứng minh được điều gì?

Yêu cầu test có ý nghĩa cho units/geometry/sign, timestamp/history/reset,
missing/stale/NaN, per-wheel/body/rate bounds, zero/STOP/latch, action trace,
termination/truncation/replay, projection/critic contract, reward sanity và
checkpoint incompatibility. GUI cần test fixed-job/process closure/cancel/
SSH-loss/recorder lifecycle/double-owner và demo không tăng real evidence.

Integration criteria phải kiểm reference thực đi tới backend và action có
hiệu lực; kết quả finite/shape đúng chưa đủ. Phân biệt unit/fixture, Gym
integration, Gazebo integration, shadow và motion thật. Test count không là
thành tích robot. Chỉ chạy lại/broaden test để giải quyết risk/gate cụ thể.

## 13. Outline tương lai và tối đa ba thí nghiệm tiếp theo

Cho hướng ưu tiên, lập **tối đa 6 giai đoạn**, có thể gộp các gate:

| Đầu vào đã có | Công việc cụ thể / file cần sửa | Artifact bàn giao | Data mới thực sự cần | Baseline/metric | Pass/stop/unknown | Người/assistant/hardware và bước thay thế |
|---|---|---|---|---|---|---|

Tách gates: software/measurement readiness; command/physical feasibility;
identification/classical tuning; prediction/learning; generalization;
hardware deployment. Không dùng gate PPO thắng reactive để cấm tuning hoặc
calibration. Không dùng arrival/return đẹp để kết luận giảm contact risk.

Chọn tối đa 3 thí nghiệm kế tiếp theo information gain/chi phí. Với mỗi cái:
câu hỏi duy nhất, vì sao data cũ chưa trả lời, prerequisite, arm/conditions,
số repeats và lý do, đơn vị independent/block/order, thao tác thật cụ thể,
required fields/reference/uncertainty, primary/secondary/estimand, constraints,
failure/missing handling, pass/stop/unknown và tối đa 1 correction có căn cứ
trước quyết định mới. Budget/limits/effect threshold mới phải gắn proposal.
Không tự mở lại pilot đóng, tăng samples hoặc hạ coverage sau khi thấy kết quả.

Nêu việc có thể làm tiếp offline ngay khi Pi chưa nối; việc bắt buộc cần
người vận hành/hardware/body reference; dữ liệu tối thiểu sẽ đổi quyết định.
Không dừng toàn project vì thiếu một tham số không liên quan; không giữ
vòng “sửa logger rồi thêm pilot” vô hạn. Đưa trigger chuyển hướng dự phòng.

## 14. Cấu trúc báo cáo mong muốn

1. Tóm tắt quyết định và khoảng cách giữa lời mô tả với mức tích hợp thực.
2. Project inventory/timeline: historical sim, real evidence, code offline,
   integration thiếu và future proposals; bảng maturity từng thành phần.
3. Bản đồ vấn đề theo evidence/cause/test/decision; xếp thứ tự ưu tiên.
4. Literature matrix, kết quả tìm phản chứng và giới hạn tìm kiếm.
5. Kiến trúc đề xuất; sơ đồ offline training và online data/control, bảng
   sender→receiver/fields/units/frame/clock/rate/ownership/fault.
6. Quyết định History/governor/TD3/PPO/baseline/shaping/navigation/sensing;
   feature/action/replay/reward/termination/checkpoint contracts cụ thể.
7. Data plan và SysID/sim-to-real: đã có/chưa đủ/cần tiếp, protocol và QC.
8. Training/evaluation protocol từ environment validation đến model comparison.
9. GUI/job/data-quality changes và hướng dẫn người vận hành từng bước.
10. Ma trận sửa file, pseudocode lát cắt tối thiểu, migration/test/integration
    acceptance; code mới phải chứng minh nối thật trước khi gọi “đã áp dụng”.
11. Tối đa 3 hướng, novelty matrix;1 ưu tiên/1 dự phòng; outline ≤6 giai đoạn,
    ≤3 thí nghiệm kế tiếp, chi phí tương đối và điểm dừng.
12. Những điều chưa thể kết luận, dữ liệu thiếu theo thứ tự đổi quyết định,
    nguồn dẫn sát nhận định và hạn chế truy cập.

Kết thúc bằng **một việc nên làm ngay**, file/artifact cụ thể nhận được,
claim nào được xác nhận sau đó và điều kiện khiến bạn đổi khuyến nghị.

## 15. Tài liệu đính kèm và thứ tự đọc

Bản tóm tắt trên đủ để bắt đầu. Nếu có gói source đính kèm, dùng
`README_RESEARCH_PACKAGE.md` và `MANIFEST.json` để biết file nào thật sự
được cung cấp. Gói là snapshot working tree, không mặc định là commit clean
hoặc code đã deploy. Liên kết ra ngoài gói không tự là artifact đã đọc.

### Ưu tiên hiện trạng và bằng chứng

1. `docs/NINO_IMPLEMENTATION_UPDATE_2026-11-03.md`: mức code/test offline,
   phần chưa Gym/Gazebo/training/hardware integration.
2. `docs/NINO_RESEARCH_DIRECTION_2026-11-03.md`: hướng vừa đề xuất, cần phản biện.
3. `docs/NINO_REAL_DATA_STATUS_2026-11-03.md` và
   `docs/NINO_REAL_DATA_CHECKLIST_2026-11-03.md`: dữ liệu đã review đến02/11.
4. `docs/REAL_SENSOR_INTEGRATION_2026-10-27.md`,
   `docs/IMU_TF_APPLIED_AND_MOUNTING_GUIDE_2026-10-27.md`: sensor/frame;
   ưu tiên update cuối, không lấy phần lịch sử “chưa ápTF” làm hiện trạng.
5. `src/nino_pi/GUIDED_COLLECTION.md`, `REAL_DATA_COLLECTION.md`,
   `WHEEL_RESPONSE_PROTOCOL.md`, `STM32_USB_INTEGRATION.md`,
   `REAL_SESSION_FIELD_GUIDE.md`: phân biệt GUIv4 với các CLI/history cũ.
6. `docs/GOVERNOR_DESCRIPTIVE_SURVEY_2026-10-18.md`,
   `GOVERNOR_H2_TIMING_ENVELOPE_2026-10-23.md`,
   `GOVERNOR_ISOLATED_CADENCE_V6_RESULT_2026-10-23.md`,
   `NINO_MOTION_CONTRACT_REVIEW_2026-10-23.md`: governor/timing/acquisition;
   các câu “chưa có real data” của23/10 đã được27/10–03/11 cập nhật.

### Code/config quan trọng

- `src/nino_control/nino_control/residual_velocity.py`, `governor_core.py`,
  `speed_governor.py`, `effort_drive.py`; config governor đúng profile.
- `src/nino_rl/nino_rl/residual_experiment.py`, `core.py`, `ros_env.py`,
  `train.py`, `control_v2.py`, `policy_node.py`, `governor_adapter.py`;
  residual YAML mới, evaluator/config legacy khi cần đối chiếu interface.
- `src/nino_pi/nino_pi/mode_gui.py`, `guided_collection.py`,
  `collection_runner.py`, `collection_deploy.py`, `project_panel.py`,
  `data_quality.py`, `research_plan.json`, `project_evidence.json`,
  `command_gate.py`, `collect_real_data.py`, `hardware_audit.py`.
- `src/nino_pi/runtime/`: gateway/session/record/trial/scene/identity/lifecycle
  helpers, frozen templates và control/collection config; builder ở
  `src/nino_pi/scripts/build_collection_runtime.py`. Resource ZIP được sinh
  từ source, không là bằng chứng robot chạy. Không cần đọc binary ZIP để
  suy source nếu source tương ứng đã được cung cấp.
- `src/nino_pi/config/real_session.template.json`,
  `stm32_usb_collection.json`, `stm32_usb_wheel_response_collection.json`,
  `real_collection_residual_diagnostic.json`; command-stack launch/config.
- Firmware chỉ nếu có trong gói: `firmware_source/User/APP/motor_task.c`,
  `User/Config/robot_config.h` và SBUS/kinematics/USB callback files được kê
  trong manifest. Đây là source snapshot, chưa xác nhận flashed binary.
- Tests mới tương ứng và verification JSON chỉ chứng minh claim software
  ghi trong review; không thay raw bags/video hoặc hardware measurement.

Hai báo cáo bên ngoài trước đó, nếu đính kèm:
`external_reports/RESIDUAL_TD3_ARCHITECTURE_USER_REPORT.txt` và
`external_reports/NINO_RL_CONCLUSION_USER_REPORT.txt`. Chúng chứa đề xuất
TD3/history cùng giả định/rate/PI/threshold cần kiểm lại, không là kết luận
bắt buộc giữ. Không coi các citation bên trong là đã được truy cập.

Không cần toàn bộ raw bag để trả lời mọi phần. Nếu một kết luận quan trọng
thật sự cần dữ liệu chưa có, yêu cầu đúng artifact/window/metadata tối thiểu,
giải thích nó sẽ đổi quyết định gì; vẫn hoàn thành các phần độc lập còn lại.
