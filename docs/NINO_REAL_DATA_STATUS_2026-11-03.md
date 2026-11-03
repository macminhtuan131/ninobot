# Tiến độ dữ liệu thật Nino — rà soát 03/11/2026

## Kết luận

**Đã có dataset cảm biến và các trace command → reported wheel trên robot thật.
Chưa có bộ độ lặp chuyển động hoàn chỉnh hoặc reference thân độc lập.**
Lượt kiểm startup mới nhất đã failed trước forward, không phải0/1 sẵn sàng.
Không có release motion đang mở trong bằng chứng đã giữ.

Phạm vi: rà soát dữ liệu trên laptop đến session cuối ngày 02/11 và đối chiếu
báo cáo/raw/ledger. SSH d@192.168.0.109 ngày 03/11 trả No route to host; chưa
đọc được danh sách mới trênPi, boot/GID hiện tại hoặc dữ liệu sau mốc này.
Không SSH điều khiển, launch stack, flash hoặc phát command trong lần rà soát.

## 1. Đã thu đến mức nào?

| Nhóm | Bằng chứng đã có | Dùng được cho | Chưa kết luận được |
|---|---|---|---|
| Sensor inventory27/10 | IMU 2.708 mẫu, motor feedback 2.707 mẫu, status 270 mẫu, LiDAR 394 scan; 20 file hash và SQLite đã kiểm | Dữ liệu thật các kênh, raw↔bridge, rate/gap trong cửa sổ | Driver/mode/nguồn ổn định ở mọi phiên |
| IMU axes/mounting | Lượt ứng viên cuối 708 mẫu IMU; yaw +90°; offsets gần đúng đã áp/kiểm live trong lịch sử | Đổi trục thô và TF khai báo | Fine roll/pitch/yaw, mounting uncertainty hoặc calibration đầy đủ |
| GyroZ | 718 mẫu IMU yên/trái/phải; mean −0,000453 / +0,303611 / −0,359153 rad/s | Dấu quayZ theo nhãn thao tác | Gyro scale/drift/góc quay chính xác |
| Recorder đứng yên02/11 | stationary v2: 22 file hash, SQLite đạt, 20.749 messages; đủ dữ liệu cuối 55–60 s | Một capture tự kết thúc/closure đã xác minh | Chịu mất điện hoặc mọi điều kiện tải |
| Command→reported wheel | Hai phiên từng được operator báo tiến/tự dừng; clear-zone cóprimary hợp lệ | Feasibility và waveform riêng từng lượt | Độ lặp, calibrated motor/PI model hoặc ground truth thân xe |
| Repeatability | V3/V1 bịSTOP; V2 có arithmetic primary nhưng operator báo không tiến | Giữ failure và phân biệt input bị chặn với bất đồng feedback/thân | Chưa có ba repeats hợp lệ cùng điều kiện |
| Startup verification | Lượt 17:49 ngày 02/11 failed ở discovery, khôngforward/enable=true | Chẩn đoán check tên endpoint | Chưa kiểm startup fix khi motion |
| Chuyển vị/vận tốc thân và slip | Chưa thấy video/reference độc lập trong artifact workspace đã rà | Chưa có claim định lượng | Slip, body stopping, traction/contact quality |
| Vật cản/governor trên thật | Chưa có dataset hợp lệ trong phạm vi rà soát | Chưa dùng cho đánh giá lợi ích governor | H2/H3, sim-to-real hoặc triển khai |

Rate quan sát inventory: IMU/encoder khoảng47,13Hz; LiDAR6,95Hz. Không coi
đây là rate được bảo đảm hoặc số đo latency realtime. Encoderodom/EKF không
được tính là ground truth thân xe; radius0,060m còn là giá trị khai báo, chưa hiệu chuẩn.

## 2. Các phiên chuyển động quan trọng, giữ riêng

| Session rút gọn ngày 02/11 | Raw | Outcome/giới hạn |
|---|---|---|
| rc_auto_followup_050858953708Z | 23filehash/SQLiteok,24.608messages | Operator từng xác nhận tiến ngắn/tự dừng; feasibility riêng. Không ép pass theo cửa sổ/support của protocol được chọn sau đó |
| wheel_clear_zone_094226594883Z | 25filehash/SQLiteok,23.995messages | Primary deltaMean trái0,834241/phải0,820122rad/s; operator xác nhận tiến/tự dừng. Một lượt, không phải repeatability |
| wheel_repeatability_v3_091339485407Z | 24.882messages, raw đã kiểm | Input bịSTOP trongprimary; người/đồ vật phía sau được xác nhận; stopped1/3 |
| clear_floor_repeatability_100409043176Z | 25filehash/SQLiteok,23.483messages | Source tiến nhưng finalzero toàn đoạn doSTOP; operator không tiến; stopped1/3 |
| clear_floor_repeatability_v2_102247471316Z | 25filehash/SQLiteok,24.349messages | Final0,05m/s vàreported feedback tăng; primary delta0,82244/0,74366rad/s nhưngoperator báo thânkhôngtiến. Giữ sự không khớp, reviewed_unknown1/3 |
| wheel_startup_verification_104845142374Z | 25filehash/SQLiteok,23.632messages | Discovery subscriber fail trướcforward. Source chỉ có zero; cleanup3disablefalse; trialfailed1/1 |

Hai lượt được báo tiến trước đó không phủ nhận báo cáo không tiến ở V2.
Độ lớn encoder-distance danh nghĩa khoảng9–10cm trong một sốtrace không
phải chuyển vị thân được đo. Không gộp các layout/profile/phase/quality khác
nhau thành3 repeats và không dùng chúng để tuninggain/current.

## 3. Tổng kiểm kê file hiện lưu trên laptop

`inventory.json` liệt kê15 bag sessions duy nhất (không tính folder audit,
preflight hoặc bản copy trùng là phiên mới):

- 10 manifest `captured_not_calibrated`,3`incomplete`,2`started` bị ngắt.
- 13 session cósha256manifest: vừa tính lại toàn bộfile được kê, không mismatch.
  Hai entries hashsourcecollector/audit không được tính như file raw.
- Hai interrupted sessions thiếu closure/metadata/hash hoàn chỉnh giữ trạng thái
  không hợp lệ; hash khớp của một phiên incomplete không làm nó hợp lệ.
- Các phépIMU tư thế/gyro lưuJSONL, không nằm trong15 bag kể trên.
- Không thấyvideo .mp4/.mov/.mkv/.avi/.webm trong artifact workspace đã tìm.
  Không suy ra người vận hành chưa quay hoặcPi không còn file khác.

Đây là inventory/checksum; không tuyên bố vừa lặp toàn bộSQLite/clock/coverage
cho mọibag. Các verdictSQLite/window dẫn từ review tương ứng, raw giữ nguyên.

## 4. Lỗi cuối và trạng thái bản sửa

`/motor_enable` subscriber vẫn có nhưng ROS graph gắn BARE_DDS label; GID
khớp chính xác endpoint trước đây được ghi stm32h7_node. Recorder cũng có
subscriber. Helper yêu cầu đúngnode_name nên fail trước yêu cầu chạy; không
phải lỗi được xác định từ RC AUTO hoặc LiDAR ở lượt này.

Candidate `artifacts/wheel_endpoint_fix_2026-11-02/` đã có exactGID/type pins,
kiểmrecorder source/enable cùngparticipant, DDSmatchedsubscriptions và giữ
telemetryfresh. Publisher được advertise sớm nhưng không phátmessages;
kiểm trướcclaim, không bỏ yêu cầu STM32/recorder hoặc STOP. 52tests/19mockcases
đã được quan sát đạt khi chuẩn bị. Ngày02/11 cũng đã quan sát một phép kiểm
DDS thực với0enable/velocitymessages; raw của phép probe này vẫn ởPi, chưa
copy/kiểm lại được trong lần rà soát03/11. Không tính probe thành motiontest.

Candidate prepared_not_released, không có lượt motion sau bản sửa được xác
nhận. Hardware startup disabled→enabled fix vẫn chưa có dữ liệu kiểm thực
vì lượtkiểm cuối chưa qua discovery. Nếu reboot/reconnect thayGID thì pins
phải được revalidate read-only, không tự chấp nhận mọi anonymous endpoint.

## 5. Việc tiếp theo duy nhất nên ưu tiên

Khôi phục kết nốiPi và xác nhậnboot/GID/endpoint read-only cho candidate đã
sửa; sau đó chỉ khi có release riêng mới thu một lượt profile cũ0,05m/s,
ramp0,10m/s²,source2s,bag60s với **video thấy bánh và mốc thân/sàn**.
Mục tiêu là đối chiếu startup ACK + final command + reportedfeedback với
chuyển động vật lý. Không mở ngay một đợt3 repeats, không tăng tốc hoặc bỏ
LiDAR để làm xe chạy. Giữ các slotđãđóng; lầnràsoátnày không cấp ngân sách.

Không cần thu lại IMU sign/standing inventory giống hệt. Chưa nên chuyển
sang vật cản/PPO/predictor hoặc tuyên bố governor có ích trên robot thật.

## 6. Nguồn nội bộ đã đọc

- docs/REAL_SENSOR_INTEGRATION_2026-10-27.md; IMU_TF_APPLIED_AND_MOUNTING_GUIDE_2026-10-27.md.
- artifacts/imu_axes_validation_2026-10-27/REPORT.md; gyro_yaw_evaluation_2026-10-27/REPORT.md.
- artifacts/stationary_closure_v2_evaluation_2026-11-02/REPORT.md.
- artifacts/rc_auto_followup_evaluation_2026-11-02/REPORT.md; clear_zone_motion_evaluation_2026-11-02/REPORT.md.
- artifacts/clear_floor_repeatability_evaluation_2026-11-02/slot1/REPORT.md; clear_floor_repeatability_v2_evaluation_2026-11-02/slot1/REPORT.md.
- artifacts/wheel_startup_verification_evaluation_2026-11-02/derived/analysis.json, endpoint_names.json vàledger_closed.json.
- Candidate endpoint_identity.py, endpoint_pins.json, run_trial.py và bút tíchtooloutput trước đó cho probe thực.

Không tra cứu bên ngoài, không thayraw/controller/firmware hoặc chạyrobot.
