# Checklist dữ liệu thật và công việc kế tiếp của Nino

**Cập nhật: 03/11/2026.** Đối chiếu báo cáo và artifact đang lưu trên laptop;
dữ liệu robot được xác nhận đến ngày 02/11. Chưa kiểm kê lại Pi trong lần
lập checklist này, nên file mới chỉ nằm trên Pi giữ trạng thái **chưa biết**.
GUI v2, demo, firmware build và 40 software tests không tạo thêm dataset thật.

**GUI v3:** đã thêm hồ sơ data/thông số/to-do và rubric Q0–Q4 theo claim;
[đánh giá lại báo cáo và thay đổi GUI](NINO_REPORT_REASSESSMENT_AND_GUI_2026-11-03.md).
Đây là cập nhật offline, không thay trạng thái đo thật hoặc mở lại ledger.

**GUI v4 / hướng hiện hành:** [thu bằng nút bấm](../src/nino_pi/GUIDED_COLLECTION.md),
[motion contract → SysID → B0/B1 → residual TD3/PPO](NINO_RESEARCH_DIRECTION_2026-11-03.md).
Dữ liệu thật không tăng từ việc chuẩn bị code. D24–D30/T19–T24 bên dưới là
nhu cầu/đầu việc của hướng mới, không thay trạng thái D01–D23.

## 1. Tóm tắt

- **Đã có:** raw IMU, encoder/feedback hai bánh, status, LiDAR, đối chiếu
  bridge, trục IMU thô/dấu gyro Z, TF gần đúng, một capture đứng yên đóng
  sạch và các trace command → reported wheel thật.
- **Có một phần:** enable/disable theo firmware, tiến–dừng từng lượt,
  tracking trái–phải, timestamp/rate và metadata từng phiên.
- **Chưa có bộ đủ để kết luận:** độ lặp chuyển động, body reference độc lập,
  slip, stopping thân xe, nhận dạng actuator/PI, crossing/governor và navigation thật.
- **Ưu tiên:** giải thích lượt encoder tăng nhưng người vận hành báo xe
  không tiến bằng một lượt chẩn đoán có video thấy bánh và mốc thân/sàn.
  Chưa tăng tốc, gain/current hoặc chuyển sang vật cản.

Theo [inventory đã rà soát](NINO_REAL_DATA_STATUS_2026-11-03.md): 15 bag
sessions duy nhất; 10 manifest `captured_not_calibrated`, 3 `incomplete`,
2 `started` bị ngắt. 13 phiên có manifest hash đã được tính lại và khớp
trong lần rà soát đó. Counts này không bao gồm các phép IMU lưu JSONL,
không tính bản copy trùng thành phiên mới, và không có nghĩa 10 thử nghiệm
chuyển động đạt. Checklist này không chạy lại toàn bộ phép kiểm raw/coverage.

## 2. Danh sách dữ liệu cần thu và trạng thái hiện tại

**Ký hiệu:** **Đã có** = đủ cho claim hẹp ghi trong ô; **Một phần** = có raw
hoặc số đo nhưng chưa đủ claim mục tiêu; **Chưa xác nhận** = chưa thấy bằng
chứng đủ trong gói hiện có, không khẳng định ngoài Pi/laptop không có file.

### A. Cảm biến, hình học và nền tảng thu

| ID | Dữ liệu cần | Trạng thái / bằng chứng đã có | Phần còn thiếu / khi nào cần |
|---|---|---|---|
| D01 | Raw IMU: accel XYZ, gyro XYZ, orientation/covariance, frame/header | **Đã có.** Inventory 27/10: 2.708 mẫu; còn có các phiên sau | Không cần lặp inventory giống hệt. Noise/filter/range/scale/delay chỉ xác minh thêm khi ảnh hưởng metric hoặc detector |
| D02 | Trục IMU và dấu quay Z | **Đã có ở mức thô.** 708 mẫu xác minh ứng viên yaw +90°; 718 mẫu yên/trái/phải kiểm dấu Z | Chưa là calibration scale, gyro drift dài hạn hoặc góc chính xác; không thu lại cùng phép sign nếu không đổi mounting/driver |
| D03 | Vị trí/hướng lắp IMU và LiDAR, TF so thân | **Một phần.** Số đo người dùng gần đúng đã áp và từng kiểm TF live | Fine roll/pitch, LiDAR yaw, độ cứng gá và uncertainty chưa định lượng. Kiểm lại nếu tháo/lắp hoặc định lượng body/contact cần độ chính xác đó |
| D04 | Raw feedback hai bánh: tên, góc rad, vận tốc rad/s, reported effort nếu có | **Đã có raw; calibration một phần.** Inventory 2.707 mẫu và nhiều motion traces; status freshness hai bánh đã quan sát | Mapping trái/phải, sign/scale dưới chuyển động vật lý và effective rolling geometry chưa được xác minh độc lập đầy đủ |
| D05 | LiDAR: ranges, góc, range limits, scan/time_increment, header/frame | **Đã có.** Inventory 394 scan, 720 beams/scan; có scan trong motion sessions | Chưa kiểm chuẩn khoảng cách/per-beam timing hoặc body-speed estimator. Có raw scan không chứng minh phát hiện mọi dây thấp/hõm |
| D06 | Raw ↔ bridge, `/joint_states`, `/imu/bridge`, `/odom/unfiltered` | **Đã có đối chiếu trong phiên.** Payload/header đã so trên cửa sổ giao nhau | Encoder odometry không là body ground truth; chưa có localization/navigation được kiểm chuẩn |
| D07 | Timestamp, clock, rates, gap, QoS, coverage từng cửa sổ | **Một phần.** Inventory IMU/feedback ~47,13 Hz, LiDAR ~6,95 Hz; có audit và review riêng từng lượt | Đánh giá lại trên lượt mới có motion/GUI. Rate quan sát không là deadline, transport latency hoặc coverage bảo đảm |
| D08 | File raw, SQLite/metadata, manifest/hash, dữ liệu cuối phiên | **Đã có cho các capture được review.** Stationary v2: 20.749 messages, 22 file hash, đủ cửa sổ 55–60 s | Kiểm mỗi phiên mới; phiên interrupted/incomplete vẫn giữ nguyên. Mang cả WAL/SHM nếu có, không chỉ `.db3` |
| D09 | Session metadata: pose, caster, sàn, tải, nguồn/pin, firmware/config, operator | **Một phần.** Đã có session forms và ghi chú từng lượt | Cần ghi nhất quán từng lượt; hướng caster chưa biết ghi unknown, không tự điền 0 hoặc gọi paired seeds là cùng trạng thái vật lý |

### B. Điều khiển, chuyển động và đối chiếu vật lý

| ID | Dữ liệu cần | Trạng thái / bằng chứng đã có | Phần còn thiếu / khi nào cần |
|---|---|---|---|
| D10 | Source → selected → smoothed → final command, ownership và trạng thái Collision Monitor | **Đã có trong các phiên.** Có cả input bị STOP và một clear-zone profile đi qua final | Xác nhận endpoint/owner/config/live readiness ở phiên mới. Không dùng source có lệnh tiến làm bằng chứng STM32 nhận hoặc thực thi lệnh đó |
| D11 | Zero → enable → disable, freshness/mode/fault theo firmware | **Một phần trên firmware cũ.** Probe `043000235565Z` giữ raw zero, Bool true/false và status đổi tương ứng; operator báo không giật | Manifest gốc vẫn incomplete do lỗi audit khi đó; không promote. ACK theo status không là readback motor hoặc stopping time. GUI authority mới chưa có kiểm thực |
| D12 | Tiến–dừng và đáp ứng riêng bánh trái/phải | **Một phần.** Hai phiên từng được operator xác nhận tiến/tự dừng; clear-zone có primary hợp lệ | Chưa có bộ system ID/độ lặp; một lượt V2 final/feedback tăng nhưng operator báo thân không tiến. Giữ outcome unknown và cần đối chứng vật lý |
| D13 | Độ lặp cùng profile, sàn/tải/pose/caster và điều kiện pin | **Chưa có campaign hoàn chỉnh.** Các pilot cũ dừng hoặc unknown, không đủ ba repeats hợp lệ | Sau lượt chẩn đoán đạt mới chốt campaign mới có giới hạn, review từng lượt; không gộp các lượt khác điều kiện hoặc dùng lại slot đã đóng |
| D14 | Video/reference độc lập thấy bánh và thân so mốc sàn | **Chưa xác nhận trong artifact đã rà.** Chưa thấy video/reference độc lập | **Cần ngay cho lượt chẩn đoán kế tiếp.** Video đủ góc nhìn/mốc trước mắt giải quyết có tiến hay không; chưa đủ hiệu chuẩn thì chỉ kết luận định tính |
| D15 | Bán kính lăn hiệu dụng L/R, separation, mass/payload, caster/clearance thật | **Một phần.** Có kích thước mounting gần đúng; Pi khai báo R=0,060 m, track=0,345 m | Chưa là effective rolling calibration. Đo geometry/mass/caster theo claim cần dùng; không lấy cao trục 0,056 m làm bán kính lăn hoặc dùng URDF làm cân thật |
| D16 | Target bánh sau limit/ramp, actuator mode/readback, limits, current/voltage/temperature/fault nếu backend có | **Chưa xác nhận đủ telemetry độc lập.** Có raw status/feedback và source tham khảo | Kiểm interface hiện hữu, bổ sung đúng kênh khi cần. Không tạo target bằng cách đổi `/cmd_vel` rồi coi là target thực; phân biệt effort/torque report, Iq estimate và torque đo độc lập |
| D17 | Command → wheel → body onset/ramp/settling và stopping thân xe | **Một phần ở đường ROS→reported wheel.** Có waveform và mốc input/receipt; chưa có body reference | Kết hợp video/reference, clock và uncertainty. Nếu thiếu target/readback thì chỉ nhận dạng đường tổng hợp; không gọi wheel mean gần zero là body stopping |
| D18 | Body displacement/speed định lượng và slip | **Chưa có bộ đã kiểm chứng.** Encoder odom/EKF không thay reference độc lập | Sau khi xác nhận chuyển động: hiệu chuẩn mốc/clock của video/tracker hoặc LiDAR estimator có đối chứng, kết hợp rolling radius và uncertainty trước khi tính slip |
| D19 | Nguồn Pi/motor dưới tải, điện áp/dòng/fault liên quan reset | **Một phần.** Có log/power snapshots và lịch sử undervoltage; một phiên ngắt do operator đã được xác nhận | Chưa có bằng chứng “đã sửa nguồn” hoặc current-limit readback chống reboot. Lưu trạng thái từng phiên; chỉ mở điều tra sâu khi lỗi lặp/ảnh hưởng phép đo, không tự đổi dòng |

### C. Nhóm giai đoạn sau

| ID | Dữ liệu cần | Hiện trạng | Điều kiện để bắt đầu |
|---|---|---|---|
| D20 | Navigation thật: goal/path, localization/TF, tracking, arrival, thời gian/throughput | **Chưa có bộ đánh giá đã kiểm chứng.** GUI Nav2 hiện chỉ observer | Motion backend đủ tin cậy; commissioning estimator/TF và Nav2 riêng. Full navigation không là điều kiện để tiếp tục wheel-response |
| D21 | Operating envelope, geometry/material của gờ/rãnh/hõm/dây mềm; approach và contact order | **Chưa có dataset crossing thật được kiểm chứng** | Chốt envelope cơ khí, mục tiêu ứng dụng và phép đo; tách từng cơ chế, không lấy rigid capsule sim đại diện dây mềm/rãnh |
| D22 | Baseline/can thiệp governor, executed response, quality/arrival/stall/tracking/time | **Chưa có lợi ích governor được chứng minh trên robot thật** | Có baseline lặp và cửa sổ actuator tác động hữu ích; H2 trước predictor/H3. Không dùng arrival hoặc command giảm để suy giảm contact risk |
| D23 | Payload, điều kiện sàn, nhiều route/obstacle/session và test bank độc lập | **Chưa có bộ generalization** | Sau feasibility/measurement và lợi ích baseline rõ; group toàn run/layout/session, giữ failures; chưa đầu tư RL/BC chỉ để tăng số bước |

### D. Dữ liệu cho SysID và residual velocity

| ID | Dữ liệu | Trạng thái / kết quả | Phần cần tiếp |
|---|---|---|---|
| D24 | SysID command→reported wheel→body | Chưa có model được kiểm held-out | Nhận dạng combined path nếu thiếu actuator target; không fit radius/slip/lag đồng thời |
| D25 | Baseline B0/B1 công bằng và time/quality Pareto | Chưa có benchmark real đủ | Cùng shaping/limits/information, development tuning và fixed held-out |
| D26 | Feature/history ABI 20×5 và checkpoint schema | Đã chuẩn bị offline; chưa có real dataset | Frame body/normalization/epoch/gap validity, không privileged actor |
| D27 | Policy proposal / accepted / final / actuator readback | Chưa có real residual traces | Không thay missing target bằng command; log reason/clock riêng |
| D28 | Reward/evaluation labels và failures/censoring | Chưa có bộ residual benchmark | Body/contact/slip cần independent truth; native metrics giữ riêng |
| D29 | Grouped train/validation/test, action coverage | Chưa có corpus theo ABI mới | Không random overlapping frames; không counterfactual từ một behavior |
| D30 | Latency/compute và shadow zero authority | Chưa đo deployment budget | Đo dưới tải Pi thật; không suy deadline hoặc stop từ GUI/tests |

## 3. Bộ dữ liệu tối thiểu của lượt kế tiếp

**Mục tiêu duy nhất:** lệnh thực sự đi qua và reported feedback có khớp
chuyển động vật lý hay không. Chưa phải slip, obstacle hoặc repeatability test.

| Nhóm | Cần giữ |
|---|---|
| Bắt buộc | `/cmd_vel_teleop`, `/cmd_vel_selected`, `/cmd_vel_smoothed`, `/cmd_vel`; raw `/motor_fb`, `/motor_status`, `/imu/data`; `/scan_raw`, TF đã dùng, trạng thái/scene readiness |
| Đối chứng vật lý | Video thấy hai bánh nếu bố trí cho phép, toàn thân và mốc cố định trên sàn; ghi file và cách đồng bộ/độ không chắc chắn |
| Theo backend thực dùng | Firmware cũ: các enable/disable requests và RC trạng thái phù hợp. GUI authority: `/nino/control_state`, `/nino/control_request` theo event và ACK thực. Không yêu cầu topic không thuộc contract hoặc phát giả cho đủ count |
| Metadata | Session ID/UTC, boot/endpoint, firmware/config, người vận hành, pose/caster, sàn/tải/pin, profile và phạm vi claim; unknown giữ null/unknown |
| Kết thúc | Raw bag nguyên thư mục, SQLite/metadata, source/config/hash, event labels; quan sát xe tiến/không tiến, tự dừng/can thiệp, lệch/giật/bất thường |

Profile đề xuất giữ: **+0,05 m/s, ramp 0,10 m/s², source mục tiêu 2 s,
zero/DISARM, recorder 60 s**. Đây là kế hoạch cho protocol mới, không là
lệnh chạy hoặc cấp thêm slot. Ghi duration/ramp thực đo, không mặc định từ config.

## 4. To-do theo thứ tự

### P0 — Làm trước lượt chuyển động mới

- [x] Kiểm kê local dataset và lập bảng claim/giới hạn từ báo cáo đã có.
- [x] Giữ raw/failures; xác nhận trục IMU thô và dấu Z, không lặp vô hạn.
- [x] Có capture đứng yên đóng sạch; dừng audit đứng yên giống hệt nếu không có lỗi mới.
- [x] Chuẩn bị GUI nguồn + năm mode thu, metadata/recorder/review; đạt 40 tests **offline**.
- [ ] **T01:** Kết nối lại Pi, kiểm kê file mới/chưa copy; lưu raw probe endpoint còn trên Pi nếu có, không đếm bản copy trùng thành session mới.
- [ ] **T02:** Xác nhận read-only phiên live: domain/agent, raw sensor/feedback, boot/GID/endpoint, command owner, Collision Monitor và cấu hình profile.
- [ ] **T03:** Chốt backend sẽ dùng. Firmware RC hiện có và firmware GUI authority có contract enable khác nhau; không trộn helper/protocol.
- [ ] **T04, nếu dùng GUI không cần RC:** Xác nhận đúng MCU/board và rollback, triển khai firmware tương thích/bridge; kiểm boot DISARM, source/ACK, mất link và recorder. Chưa có bằng chứng đã flash/kiểm live. Không cần flash chỉ để tiếp tục đọc raw bằng công cụ đang có.
- [ ] **T05:** Chốt protocol mới cho **một lượt chẩn đoán có video**, tiêu chí data/stop/unknown và thao tác người vận hành. Giữ mọi ledger/slot cũ đã đóng.
- [ ] **T06:** Chuẩn bị camera/mốc sàn và nhãn đồng bộ; ghi pose/caster/sàn/tải. Đảm bảo góc nhìn phân biệt được bánh quay, thân tiến, quay tại chỗ hoặc bị giữ.

### P1 — Thu và quyết định từ lượt chẩn đoán

- [ ] **T07:** Người vận hành thực hiện lượt mới khi readiness/stop/control contract đạt; thu bag 60 s và video theo D10–D14. Assistant không tự chạy từ checklist này.
- [ ] **T08:** Kiểm integrity/closure/hash và samples/gap/coverage từng cửa sổ; đối chiếu source→final→hai bánh→video, giữ spike/failure.
- [ ] **T09:** Kết luận theo bằng chứng: input bị STOP / không có response / có wheel nhưng chưa thấy body / có tiến và tự dừng. Nếu bất đồng còn tồn tại, dừng trước tuning và repeatability; không tự gán là slip.
- [ ] **T10:** Nếu lượt đầu giải quyết được bất đồng và data hợp lệ, chốt một đợt độ lặp mới tối đa ba lượt cùng điều kiện, review trước lượt kế. Không tự bù slot/tăng sample size hoặc gọi ba lượt là đủ generalization.
- [ ] **T11:** Báo từng bánh, chênh trái–phải, biến thiên từng lượt và failures; chưa tự chỉnh gain/current từ một mean hoặc một phiên.

### P2 — Định lượng sau khi chuyển động nền tảng được xác nhận

- [ ] **T12:** Hiệu chuẩn body reference/đồng bộ và rolling geometry ở mức đủ cho displacement/speed/slip; nêu uncertainty. Video định tính ở T07 không tự hoàn tất bước này.
- [ ] **T13:** Xác nhận target/mode/limits/telemetry thực sự có; đo command→wheel/body ramp/settling trong phạm vi được chọn. Thiếu target thì giữ claim tổng hợp.
- [ ] **T14:** Chọn trade-off ứng dụng tạm thời: payload, tracking, thời gian tăng thêm, rung/failure cần quan tâm; ngưỡng chưa được chấp nhận phải ghi là đề xuất.

### P3 — Chỉ mở khi P1/P2 trả lời được câu hỏi liên quan

- [ ] **T15:** Commissioning navigation nếu mục tiêu ưu tiên là tự tới đích; đánh giá estimator/TF/path/time riêng.
- [ ] **T16:** Đo envelope cơ khí/caster và thử một loại vật cản đã chốt với baseline cổ điển, body/contact reference phù hợp.
- [ ] **T17:** Kiểm H2 quyền điều khiển hữu ích trước khi đầu tư predictor; chỉ so H3/governor khi phép đo và baseline đủ.
- [ ] **T18:** Mở payload/layout/route/session held-out và learning khi có lợi thế cần thiết; chưa chạy PPO/BC/Optuna mở rộng trong checklist này.

### Hướng mới — R1 đến R7

- [ ] **T19 (R1 · ngay; Chờ hardware):** Qua GUI: inventory → ZERO → bag/video → explicit2s motion → QC/observation/fetch. Gate: Chỉ một diagnostic, giữ profile; fail/unknown không retry.
- [ ] **T20 (R2–R3; Chưa mở):** Body reference có calibration/sync và SysID combined backend. Gate: E1 giải thích được; protocol độ lặp/maneuver riêng.
- [ ] **T21 (R4; Chưa mở):** B0/B1 development tuning và Pareto tracking/time/quality. Gate: Cùng input/limits; classical đủ thì dừng learning.
- [ ] **T22 (R5; API offline):** Implement/validate backend adapter mới và PPO/TD3 comparison cùng ABI. Gate: Training false; budget null; legacy checkpoint không tương thích.
- [ ] **T23 (R6; Chưa mở):** History/authority/DR ablation, OOD và shadow trên Pi. Gate: H2 useful horizon; no body reference thì không slip claim.
- [ ] **T24 (R7; Chưa mở):** Đánh giá residual hardware giới hạn theo protocol mới. Gate: Không tự tăng alpha/tốc độ; reference/owner/stop phải đo.

## 5. Điều không cần làm lại hoặc chưa nên làm

- Không thu lại ba tư thế IMU/dấu Z chỉ vì mở thêm GUI; chỉ kiểm lại khi
  có thay mounting/driver hoặc failure cụ thể.
- Không xem `captured_not_calibrated`, hash khớp, encoder quay hoặc helper
  hoàn thành là bằng chứng xe tiến, dừng vật lý, giảm slip hoặc governor tốt.
- Không coi torque cap/ramp/current limit mô phỏng là giá trị motor thật.
- Không bỏ Collision Monitor/LiDAR, sửa ngưỡng sau kết quả, loại spike,
  sửa manifest thất bại hoặc mở lại các budget đã đóng để lấy một lượt đẹp.
- Không đòi đo COM/inertia/caster friction đầy đủ trước khi làm lượt
  command/body chẩn đoán; chỉ bổ sung tham số có thể thay đổi quyết định kế tiếp.

## 6. Nguồn nội bộ

1. [Tiến độ và inventory dữ liệu thật](NINO_REAL_DATA_STATUS_2026-11-03.md).
2. [Sensor integration](REAL_SENSOR_INTEGRATION_2026-10-27.md) và
   [mounting/gyro](IMU_TF_APPLIED_AND_MOUNTING_GUIDE_2026-10-27.md).
3. [Zero enable/disable: raw có qualification, manifest vẫn incomplete](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/zero_feedback_probe_2026-11-02/evaluation_043000/REPORT.md>).
4. [Stationary closure v2](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/stationary_closure_v2_evaluation_2026-11-02/REPORT.md>).
5. [Clear-zone motion](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/clear_zone_motion_evaluation_2026-11-02/REPORT.md>).
6. [Công cụ thu](../src/nino_pi/REAL_DATA_COLLECTION.md),
   [wheel protocol](../src/nino_pi/WHEEL_RESPONSE_PROTOCOL.md),
   [GUI modes và giới hạn triển khai](../src/nino_pi/CONTROL_MODES_GUI.md).

**Việc nên làm ngay:** hoàn tất T01–T03 để biết chính xác phiên live và
contract điều khiển; đầu ra là inventory/readiness cùng lựa chọn backend.
Lượt thu chuyển động tiếp theo nên có video đối chứng, thay vì thêm trace
encoder đơn độc hoặc mở ngay ba lượt repeatability.
