# Nino: tích hợp và thu dữ liệu cảm biến thật — 27/10/2026

**Gyro Z đã kiểm sau phiên 18:59–19:00:**
`gyro_yaw_20261027T115928157994Z` đủ ba nhãn, 718 mẫu IMU; 2/2 file khớp
hash và thống kê tính lại khớp manifest. Mean yên/trái/phải lần lượt
−0,000453 / +0,303611 / −0,359153 rad/s. Dấu phù hợp thao tác có nhãn,
giữ sign/TF, không yêu cầu thu lại. Chưa hiệu chuẩn scale hoặc đo actuator.
[Kết quả và bước tiếp theo](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/gyro_yaw_evaluation_2026-10-27/REPORT.md>).

**Mounting mới nhất, 18:47:** đã áp số đo gần đúng của người dùng trên Pi
`192.168.0.104`: IMU xyz `[-0.05,-0.02,0.014]` m, LiDAR xyz
`[0.22,0,0.189]` m, gốc thân cao 0,056 m so sàn, yaw IMU +90°.
TF live xác nhận đúng; IMU/LiDAR lần lượt cao 0,070/0,245 m so sàn.
Góc chính xác và uncertainty chưa kiểm chứng; gyro yaw sign đã kiểm như trên.
Xem [hướng dẫn và bằng chứng áp mounting](IMU_TF_APPLIED_AND_MOUNTING_GUIDE_2026-10-27.md).

## Kết luận hiện tại

**Đã có phiên thu cảm biến kết hợp và lượt xác minh IMU ba tư thế mới.**
Phiên `imu_axes_20261027T062331920164Z` tái hiện dấu/trục dự đoán bởi ứng viên
**yaw IMU +90°** chọn trước đó. Đã áp cấu hình sau yêu cầu người dùng và xác
nhận quaternion đúng trong TF live; bridge/LiDAR đã chạy lại. Không cần
thu lại ba tư thế giống hệt. Offset sau đó đã áp số đo gần đúng người dùng;
chưa hiệu chuẩn góc lắp chính xác. Xem [kết quả áp TF và hướng dẫn bước 2](IMU_TF_APPLIED_AND_MOUNTING_GUIDE_2026-10-27.md).

Người dùng báo đã kiểm tra và lấy được feedback bánh trái. Ghi nhận là
`operator_report`; không yêu cầu làm lại kiểm tra đó. Phiên mới bổ sung
bằng chứng status có freshness hai bánh theo schema source tham khảo.
Chiều dương, đơn vị/góc bánh so với chuyển động vật lý chưa được kiểm toán
độc lập từ phiên thụ động này.

Phạm vi đã thực hiện: mở các node cảm biến/adapter và ghi bag. Không sửa
firmware/controller, không gọi enable, không phát velocity/torque, không
launch Nav2/SLAM. Vấn đề nguồn nằm ngoài bước này theo yêu cầu người dùng.

## 1. Phiên và kết quả đo

- Pi: `d@192.168.0.113`, ROS domain 0, env
  `/home/d/pi5-stm32-slam-main/scripts/env.sh`.
- Phiên: `/home/d/nino_real_data/sensor_inventory_20261027T040428773075Z`.
- Bắt đầu UTC `04:04:29.636009`, kết thúc `04:05:31.086082`, ngày 27/10/2026.
  Thời gian supervisor gồm startup/closure; không gọi là 60 s coverage từng kênh.
- Manifest: `captured_not_calibrated`, `duration_reached`, issues rỗng;
  recorder/audit đều exit 0, không forced shutdown.
- Bản sao laptop: **20/20 file khớp SHA256**, SQLite integrity `ok`.
  Hai hash code collector/audit được giữ riêng, không tính là file dữ liệu
  đã đối chiếu trong thư mục phiên.

| Topic | Số mẫu bag | Rate nhận, Hz | Gap nhận lớn nhất, ms |
|---|---:|---:|---:|
| `/imu/data` | 2708 | 47,132 | 26,008 |
| `/motor_fb` | 2707 | 47,132 | 26,060 |
| `/motor_status` | 270 | 4,713 | 216,026 |
| `/imu/debug` | 270 | 4,713 | 215,989 |
| `/imu/bridge` | 2678 | 47,133 | 26,902 |
| `/joint_states` | 2679 | 47,134 | 26,873 |
| `/odom/unfiltered` | 2679 | 47,134 | 26,283 |
| `/scan_raw` | 394 | 6,953 | 149,421 |
| `/tf` | 900 | 15,710 | 69,349 |
| `/tf_static` | 1 message, 3 transforms | không áp dụng | không áp dụng |

Các topic có source header trong bảng không có header zero/lùi/trùng;
IMU/motor/joint/odom có source-header gap lớn nhất 26 ms. Đây là kết quả
cửa sổ quan sát, không phải bảo đảm rate, loss-free hoặc latency realtime.
Status 270/270 mẫu bằng **35**: nếu schema khớp source đã ghim thì cả hai
freshness bit đặt, command timeout đặt, enable-variable bit không đặt.
Bit enable không đo nguồn motor hoặc xác nhận trạng thái vật lý actuator.

## 2. Đối chiếu raw và bridge

- 2678/2678 IMU qua bridge khớp acceleration/gyro/quaternion **và source
  header** với IMU gốc được ghi trong phiên.
- 2679/2679 joint states khớp position/velocity/effort arrays **và source
  header** với raw motor feedback, theo cấu hình signs `+1/+1` hiện tại.
- Trong cửa sổ header giao nhau, hai cặp raw/derived có cùng tập header;
  không có header raw-only hoặc derived-only. Số mẫu tổng khác nhau do
  cửa sổ bắt đầu/kết thúc nhận mỗi topic; không lấy chênh counts làm tỷ lệ
  mất packet hay kết luận bridge bỏ mẫu.
- Source bridge có logic sanitize timestamp khi header ngoài tolerance.
  Phiên này không quan sát header bị thay trong các mẫu IMU đã đối chiếu.
  Luôn giữ raw khi phân tích timing về sau.
- `/odom/unfiltered` chỉ là phép tích phân encoder theo geometry khai báo;
  không phải ground truth vận tốc thân, slip hoặc kết quả localization đã kiểm chuẩn.

## 3. LiDAR và TF

**Người dùng báo:** RPLIDAR A1 M8. **Driver trả:** serial
`ABC2ECF0C3E09ED2A0EA98F3381A4110`, firmware 1.29, hardware rev 7,
SDK 1.12.0, health 0, scan mode **Sensitivity**. Driver chạy 115200 baud
theo ví dụ A1/A2 đã cài; không tự ép mode Standard. Cổng dùng đường dẫn
`/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`.

394 scan đều có 720 beams. Tổng 254114 range hữu hạn trong giới hạn driver
khai báo và 29566 `+inf`; không có NaN, `-inf` hoặc finite ngoài giới hạn.
`+inf` có thể biểu diễn no-return, không loại scan vì lý do này.
Range khai báo 0,15–12 m chưa phải kiểm chuẩn khoảng cách thực tế.
`scan_time` trung bình 0,143355 s; per-beam timing do driver khai báo, chưa
được xác minh độc lập. Chỉ lưu `/scan_raw`, chưa deskew/republish thành `/scan`.

TF tĩnh trong bag:

| Parent → child | xyz, m | Rotation | Phân loại |
|---|---|---|---|
| `base_footprint → base_link` | 0 / 0 / 0,060 | identity | model khai báo |
| `base_link → imu_link` | 0 / 0 / 0 | identity | model khai báo, chưa đo mounting |
| `base_link → laser` | 0,223 / 0 / 0,1915 | identity | model khai báo, chưa đo mounting |

Có TF động từ base_link tới hai wheel links. Chưa có `odom → base_footprint`
TF từ estimator vì bước này chưa chạy EKF; field `child_frame_id` trong
Odometry không tự tạo TF. Chưa chấp nhận cây frame cho navigation.

Geometry đang dùng: radius 0,060 m, separation 0,345 m, signs `+1/+1`, từ
config Pi cũ. Giữ toàn bộ trường số đo vật lý chưa biết là null; không
thay chúng bằng các giá trị model chỉ vì có odometry/TF.

### Bổ sung từ ảnh có chú thích của người dùng

Người dùng đánh dấu mũi tên đỏ hướng tiến về phía trái ảnh và chỉ rõ
**STM32 cùng IMU nằm ngay dưới quạt**. Ghi nhận hướng tiến này là +x thân;
+y sang trái robot khi nhìn theo hướng tiến, +z lên trên. Vị trí dưới quạt
là bằng chứng định tính, chưa xác định offset so với gốc thân hoặc hướng
trục chip. Nắp/quạt che bo nên chưa đọc được ký hiệu trục từ ảnh.

Đã đối chiếu source ghim `User/APP/INS_task.c`: luồng INS giữ thứ tự trục
acceleration BMI088 và trừ gyro bias trên cùng trục trước khi xuất snapshot.
Luồng này không tự chứng minh IMU đã được xoay về frame thân; commit trên
board chưa được xác nhận. Không đặt identity rotation hoặc xyz bằng 0 chỉ
từ việc IMU ở dưới quạt. TF đang chạy chưa được thay bằng suy đoán từ ảnh.
Evidence được giữ riêng tại `mounting_evidence.json` trong bộ artifact bước
cảm biến; raw session và metadata của các phiên đã thu giữ nguyên.

Ảnh cận bo tiếp theo cho thấy mặt linh kiện, USB ở cạnh dưới ảnh và đầu
nguồn vàng ở bên phải; người dùng tiếp tục đánh dấu hướng tiến về trái ảnh.
Chưa đọc được mũi tên X/Y/Z của cảm biến từ ảnh, và repo không có sơ đồ PCB
đủ để xác nhận phép xoay chỉ từ hướng cổng USB. Chuyển sang phép kiểm trục
bằng dữ liệu có nhãn; không yêu cầu thêm ảnh cùng góc nhìn.

Helper đã chuẩn bị trên Pi:

```bash
bash /home/d/nino_runtime/sensor_observation_20261027_v1/check_imu_axes.sh
```

Helper chỉ thu `/imu/data` và status, không thay TF hay điều khiển motor.
Trước thao tác, người vận hành phải xác nhận drive không tạo mô-men và có
thể đỡ robot chắc chắn; không coi enable nhưng đứng yên là drive disable.
Sau xác nhận tại terminal, ba tư thế lần lượt là **ngang / đầu xe nâng nhẹ /
bên trái robot nâng nhẹ**, mỗi tư thế giữ yên rồi Enter để thu 5 s. Nếu
không thể thực hiện phù hợp, thoát và giữ hướng trục unknown. Script không
đòi góc nghiêng chính xác và không gọi đó là calibration chính xác; giữ
raw samples cùng nhãn thao tác để đối chiếu hướng gravity, độ ổn định và
tính độc lập của các tư thế. Không tự áp phép xoay từ các số đo này.

Output mới có dạng `/home/d/nino_real_data/imu_axes_<UTC>/`. Khi chuẩn bị,
helper đã qua kiểm cú pháp/import offline; kết quả phép kiểm sau đó nằm dưới.

### Kết quả phép kiểm IMU ba tư thế, 11:24–11:26 ngày 27/10/2026

Đã tìm thấy và đọc phiên
`/home/d/nino_real_data/imu_axes_20261027T042455655133Z`. Manifest ghi
`recorded_requires_axis_review`, errors rỗng; người vận hành xác nhận drive
disabled tại prompt. Đây là operator report, không phải phép đo trạng thái
torque độc lập. Hai file manifest/samples khớp SHA256. Có **708 mẫu IMU**
(236 mỗi tư thế), **123 status đều 35**, không header zero/lùi/trùng. Giữ
toàn bộ mẫu, không loại rung hoặc chọn lại cửa sổ.

| Nhãn người vận hành | Mean acceleration sensor X/Y/Z, m/s² |
|---|---|
| LEVEL | −0,203 / −0,496 / 9,678 |
| NOSE_UP | −0,198 / −2,910 / 9,307 |
| LEFT_SIDE_UP | 1,505 / 0,007 / 9,536 |

Chênh so với LEVEL: NOSE_UP đổi chủ yếu **−sensor Y** (−2,414 m/s²);
LEFT_SIDE_UP đổi chủ yếu **+sensor X** (+1,708 m/s²). Dưới giả thiết nhãn
tư thế đúng và gia tốc chủ yếu là gravity khi giữ tư thế, phép đổi trục thô
được ủng hộ là:

```text
body X = −sensor Y
body Y = +sensor X
body Z = +sensor Z

base_link → imu_link: rpy ứng viên [0, 0, +π/2]
R_body_sensor = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
```

Trong bốn giả thuyết yaw 0/90/180/270°, +90° phù hợp dấu/trục chủ đạo nhất.
Đây là so sánh hình học theo nhãn thao tác, không phải xác suất độ đúng hoặc
calibration chính xác. Năm block liên tiếp trong mỗi tư thế đều giữ dấu
chủ đạo tương ứng; không gọi các block là năm phép thử độc lập.

**Giới hạn:** LEFT_SIDE_UP vẫn đổi sensor Y khoảng +0,503 m/s²; tư thế này
có drift trong lúc giữ. NOSE_UP có std Z khoảng 0,490 m/s². Góc nghiêng và
mặt phẳng ngang không được đo bằng reference ngoài. Vì thế chưa suy góc
roll/pitch/yaw chính xác, covariance mounting, gyro yaw sign hoặc lever arm
từ bộ này. Identity IMU hiện tại không còn là giả thiết phù hợp nhất, nhưng
chưa tuyên bố +90° là calibration hoàn chỉnh.

Đã tạo [config ứng viên, chưa áp dụng](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/imu_axes_evaluation_2026-10-27/robot.imu_yaw_candidate.yaml>)
chỉ đổi `imu_rpy` trong model khai báo; radius/track/offset giữ nguyên trạng
thái chưa đo. Không xoay rồi ghi đè raw IMU, không đồng thời sửa firmware
và TF để tránh áp phép xoay hai lần. Xem [phân tích đầy đủ](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/imu_axes_evaluation_2026-10-27/results.json>).

### Kết quả lượt xác minh tiếp theo

Đã đọc phiên `imu_axes_20261027T062331920164Z`: 236 mẫu mỗi tư thế, tổng
708 IMU; hai file raw/manifest khớp hash, không header zero/lùi/trùng.
Dùng **ứng viên +90° cố định**, không fit lại, chênh acceleration body so
với LEVEL là NOSE_UP `[+2.410, -0.012, -0.371]` và LEFT_SIDE_UP
`[+0.382, +2.063, -0.242]` m/s². Cả hai giữ dấu/trục chủ đạo trong năm block
liên tiếp của từng tư thế. Lượt này phù hợp phép đổi trục thô; chưa chứng
minh góc chính xác, gyro yaw sign hoặc offset.

Lượt `061906781917Z` thiếu IMU và lượt `062159589854Z` có hai tư thế nghiêng
cho tín hiệu gần giống nhau vẫn được giữ, báo riêng; không suy chúng thành
kết quả đạt, không xóa hay gộp có lợi. Xem [báo cáo xác minh](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/imu_axes_validation_2026-10-27/REPORT.md>)
và [kết quả từng lượt](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/imu_axes_validation_2026-10-27/results.json>).

## 4. Khác biệt giữa các observer được giữ lại

Audit rút gọn không nhận `/tf_static`, trong khi subscriber kiểm tra riêng
RELIABLE/TRANSIENT_LOCAL và recorder CDR đều nhận đủ 3 transforms. Lần thử
CLI tự khám phá type cũng không xác định được type trong cửa sổ đó; không
quy đây là publisher mất TF. Chưa tách nguyên nhân discovery/QoS của audit;
giữ cảnh báo gốc, không sửa raw hoặc gọi audit đã nhận TF tĩnh.

Audit ban đầu có receipt gap lớn hơn bag; không dùng audit compact thay
bag hoặc đồng nhất hai cửa sổ. Audit cũng cảnh báo `empty_frame_id` ở
JointState dẫn xuất: tên joint đối chiếu được với URDF, chưa có bằng chứng
cần chèn frame giả để vượt cảnh báo. Không mở vòng sửa logger mới từ các
cảnh báo này khi raw cần cho quyết định hiện tại đã được ghi và đối chiếu.

## 5. Runtime và tái thu

Các process mở cho bước này trên Pi nằm dưới
`/home/d/nino_runtime/sensor_observation_20261027_v1`:

- `run_observe_sensors.sh`: bridge + robot_state_publisher, launcher group 2061.
- `run_lidar_a1.sh`: driver scan thô, launcher group 2384.
- Agent hiện có dùng riêng, không launch agent thứ hai.
- Bridge enable output/service được remap sang các tên `unused_*` riêng của
  bước commissioning; không có lời gọi service được yêu cầu hoặc thực hiện.
  Điều này không khóa RC hay các node ROS khác.
- Recorder đã kết thúc. Adapter và LiDAR được giữ chạy; chưa cài autostart.

Khi cần một phiên mới với điều kiện đã ghi rõ, helper đã có trên Pi:

```bash
bash /home/d/nino_runtime/sensor_observation_20261027_v1/record_sensor_inventory.sh --check
bash /home/d/nino_runtime/sensor_observation_20261027_v1/record_sensor_inventory.sh
```

Mỗi lần gọi tạo ID mới; helper không khởi động lại driver hoặc phát lệnh.
Không lặp thu nếu không có thay đổi điều kiện/câu hỏi cần kiểm chứng.
Đây là contract `nino_passive_sensor_inventory_v1`, có 9 required channels.
Không thay hoặc hạ required của profile full; `/cmd_vel`, `/scan`, `/odom`
fused và các kênh actuator cần cho motion/H2 chưa được chứng minh.

## 6. Việc tiếp theo có điểm dừng

1. **Commissioning cảm biến đã đủ cho bước kế tiếp:** +90° tái hiện qua
   gravity poses, đã áp TF và XYZ gần đúng; gyro Z đã đạt kiểm trái/phải có
   nhãn. Không lặp các phép này khi chưa có câu hỏi mới. Giữ unknown cho
   góc chính xác, uncertainty, mounting rigidity và LiDAR yaw.
2. **Chốt contract motion trước lượt chạy:** một nguồn lệnh cuối, mode motor,
   mapping/sign đã kiểm tra, giới hạn người vận hành chấp nhận và hành vi
   dừng. Chưa tự phát lệnh khi những mục này còn thiếu. Không áp PI simulation
   lên velocity PI trong motor.
3. **Một protocol đáp ứng trên sàn sạch:** sau khi contract trên rõ, ghi các
   tầng command/target thực thi/encoder cùng reference thân độc lập. Đo
   command→wheel và wheel→body theo uncertainty của phép đo; không lấy
   encoder odom làm body GT. Chưa thêm gờ, train PPO hoặc predictor ở bước này.

Không tuyên bố đã xác minh trục chỉ từ IMU đứng yên, hoặc đã giảm risk từ
arrival/return. Kết quả đủ để kết thúc bước tích hợp thu cảm biến hiện tại.

## Bằng chứng

- [Kết quả offline đầy đủ](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/pi_sensor_stage_2026-10-27/results.json>).
- [Raw session bản sao laptop](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/real_sessions/sensor_inventory_20261027T040428773075Z>).
- [Config, helper, audit và source snapshot](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/pi_sensor_stage_2026-10-27>).

Các file raw/ledger của phiên trước giữ nguyên. Phân tích SQLite chỉ đọc,
không replay bag lên robot, không resample/loại spike hoặc viết lại header.
