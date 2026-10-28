# TF IMU đã áp dụng và cách đo mounting — 27/10/2026

**Cập nhật sau phiên 18:59–19:00:** đã lấy và đánh giá raw
`gyro_yaw_20261027T115928157994Z`. Hai file khớp hash, thống kê tính lại khớp
manifest. Mean gyro Z: yên −0,000453; trái +0,303611; phải −0,359153 rad/s
(240/239/239 mẫu). Đạt phép kiểm dấu với nhãn người vận hành; giữ dấu và TF
hiện tại, không cần lặp ba thao tác. Chưa phải hiệu chuẩn scale/góc quay.
Xem [báo cáo gyro Z](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/gyro_yaw_evaluation_2026-10-27/REPORT.md>).

**Cập nhật 18:47 ngày 27/10/2026:** Pi hiện ở `d@192.168.0.104`.
Người dùng đã bổ sung chiều cao tâm trục bánh khoảng 5,6 cm và IMU khoảng
7 cm. Đã áp translation gần đúng, giữ yaw IMU +90° và kiểm TF live:

| Transform | xyz, m |
|---|---|
| `base_footprint → base_link` | `[0, 0, 0.056]` |
| `base_link → imu_link` | `[-0.050, -0.020, 0.014]` |
| `base_link → laser` | `[0.220, 0, 0.189]` |

Tổng chuỗi TF cho IMU cao 0,070 m, LiDAR cao 0,245 m so với sàn. Đây là
số đo người dùng gần đúng, chưa có uncertainty định lượng hoặc xác minh
mounting cứng. Bản sao trước/sau và kiểm tra live ở
`/home/d/nino_runtime/mounting_xyz_20261027_v1`.

Đã thêm tham số Xacro `drive_axle_height`, mặc định giữ bằng wheel_radius
nếu không truyền vào để giữ hành vi cũ. Config hiện truyền 0,056 m cho TF
gốc thân; **wheel_radius của odometry vẫn 0,060 m**, chưa được suy từ số đo
chiều cao trục. Không tự coi chiều cao trục là bán kính lăn hiệu dụng.
Kiểm offline xác nhận chiều cao cộng chuỗi đúng và fallback default không
đổi; kiểm live 12 s nhận đủ các topic, 58 status đều 35, không có header
zero/lùi/trùng ở các stream có header. Agent/bridge/LiDAR đã mở lại sau reboot.

## 1. Đã hoàn tất bước TF

Trên Pi `d@192.168.0.101`, đã cập nhật duy nhất field `robot.imu_rpy` thành
`[0, 0, 1.5707963267948966]` trong config commissioning và config nguồn
`pi5_slam_bringup/config/robot.yaml`. Installed share resolve về source đã
cập nhật. Backup từng file, hash trước/sau và logs nằm tại:

`/home/d/nino_runtime/imu_tf_yaw90_20261027T063145859518Z`.

Đã mở lại bridge, robot_state_publisher và RPLIDAR. Quan sát 12 s nhận đủ
9 topic kiểm tra. TF thực tế `base_link → imu_link` có quaternion xyzw
`[0, 0, 0.7071067811865475, 0.7071067811865476]`, đúng ứng viên yaw +90°.
IMU raw/bridge khoảng 47,26 Hz; header không zero/lùi/trùng trong cửa sổ.
Nhận 80 scan, 57 status đều 35. Không có publisher thực tế trên các topic
velocity/MIT/torque/enable được quan sát; observer không tạo command publisher.

Đây là áp dụng phép đổi trục thô đã được kiểm chứng bằng tư thế. Vị trí
sensor sau đó đã có số đo gần đúng như cập nhật đầu bài; góc roll/pitch
chính xác vẫn chưa đo. Raw `/imu/data` tiếp tục ở
frame `imu_link`; TF cung cấp phép đổi sang thân, không viết lại raw hoặc
xoay thêm trong firmware. Không coi số đo gần đúng là hiệu chuẩn chính xác.

## 2. Đo vị trí IMU và LiDAR

### Chọn mốc chung

Đặt robot trên mặt sàn phẳng và giữ tư thế ổn định. Khi thao tác bằng tay,
xác nhận drive không tạo mô-men theo thiết kế robot.

- Gốc O: chính giữa tâm hai bánh chủ động, ở cao độ trục bánh.
- +X: hướng tiến đã đánh dấu trên ảnh.
- +Y: bên trái robot khi nhìn theo hướng tiến.
- +Z: lên trên.

Quy ước trục và đơn vị theo [ROS REP-103](https://github.com/ros-infrastructure/rep/blob/master/rep-0103.rst).
Gốc được chọn ở đây phù hợp với model đang đặt hai tâm bánh tại x=z=0
trong base_link; không lấy kích thước danh nghĩa của vỏ làm số đo.

### Đo bằng thước theo ba phương

Với từng sensor:

| Đại lượng | Cách đo | Dấu |
|---|---|---|
| x | Khoảng cách dọc xe từ đường nối tâm hai bánh tới tâm tham chiếu sensor | Trước O dương, sau O âm |
| y | Khoảng cách ngang từ mặt phẳng giữa hai bánh tới tâm sensor | Trái dương, phải âm |
| z | Cao độ tâm sensor trừ cao độ tâm trục bánh | Trên O dương |

Đo riêng `h_trục` từ sàn tới tâm bánh. Khi dễ đo từ sàn, dùng:

```text
z_IMU   = h_IMU   − h_trục
z_LiDAR = h_LiDAR − h_trục
```

IMU: dùng tâm tham chiếu cảm biến trên bo. Nếu chưa xác định chính xác vị
trí chip, ghi rõ mốc ước lượng và sai số do chọn mốc; không gọi tâm bo là
tâm IMU đã xác định. LiDAR: dùng tâm tham chiếu/quét của sensor, đối chiếu
bản vẽ nếu có; đo cao độ mặt phẳng quét và ghi mốc đã dùng, không lấy đỉnh nắp.

Gửi số theo **mm**, kèm cách đo và mức không chắc chắn. Tôi sẽ đổi sang m
để điền config. Mục chưa đo để trống/null. Không đoán offset từ ảnh.

Mẫu trả lời:

```text
Cao tâm trục bánh so với sàn: ... mm
IMU:   x=... mm; y=... mm; cao tâm so sàn=... mm
LiDAR: x=... mm; y=... mm; cao tâm so sàn=... mm
Mốc đo IMU/LiDAR và sai số ước lượng: ...
```

Form JSON riêng đã chuẩn bị tại:
`/home/d/nino_runtime/sensor_observation_20261027_v1/mounting_measurements.template.json`.
Form chưa điền không tự thay config và không thay generic session template.

### Số đo người dùng đã cung cấp

Người dùng báo khoảng cách gần đúng theo cm: LiDAR trước trục bánh 22 cm,
không lệch trái/phải, cao tâm so sàn 24,5 cm; IMU sau trục bánh 5 cm,
lệch phải 2 cm. Quy đổi theo gốc O đã chọn:

| Sensor | x, m | y, m | z, m |
|---|---:|---:|---|
| LiDAR | +0,220 | 0 | `0,245 − h_trục` |
| IMU | −0,050 | −0,020 | `h_IMU − h_trục` |

`h_trục` và `h_IMU` đều là chiều cao từ sàn, tính bằng m. Ban đầu hai chiều
cao chưa được cung cấp; cập nhật sau đó là 0,056 m và 0,070 m, nên Z IMU
= 0,014 m, Z LiDAR = 0,189 m. Không lấy radius model 0,060 m làm chiều cao
trục đo thật, không đưa trực tiếp 0,245 m vào laser z của base_link.
Lateral 0 và các khoảng cách đều là operator report gần đúng; phương pháp
và uncertainty chưa được định lượng.

Đã lưu số đo và công thức trong
`mounting_measurements.operator_report_2026-10-27.json`, đưa vào form của
phiên sau. Lượt đồng bộ ban đầu tới `.101` timeout; sau khi người dùng cung
cấp `.104`, đã đồng bộ và áp/kiểm TF với đủ mốc cao độ như cập nhật đầu bài.
Yaw +90° đã áp vẫn giữ. Các phiên raw cũ không được sửa metadata hồi tố.

## 3. Kiểm riêng dấu gyro Z

### Bộ thu có nhãn đã chạy và được đánh giá

Phiên mới đã hoàn tất và đạt kiểm dấu như cập nhật đầu bài. Các lệnh dưới
đây là hướng dẫn tái sử dụng khi có câu hỏi mới, không yêu cầu thu lại.

Trên Pi hiện tại `192.168.0.104`, chạy:

```bash
bash ~/nino_runtime/sensor_observation_20261027_v1/check_gyro_yaw.sh
```

Sau khi xác nhận drive không tạo mô-men, công cụ chờ dữ liệu IMU trước khi
bắt đầu. Có ba bước, mỗi bước 5 s: **YEN / TRAI / PHAI**. Gõ đúng tên bước
khi đã sẵn sàng, chờ đếm ngược 3–2–1 rồi thực hiện thao tác lúc báo
**BẮT ĐẦU**. Khi báo xong, dừng xoay và giữ yên chờ bước sau. Operator cung
cấp hướng quay vật lý; phần mềm tự thu `/imu/data`, status và timestamp.
Không thể suy hướng vật lý độc lập chỉ từ chính dấu gyro đang kiểm tra.

Raw samples, manifest, hash và kết quả sơ bộ nằm trong phiên mới
`/home/d/nino_real_data/gyro_yaw_<UTC>/`. Báo hoàn tất để assistant tự lấy và
đánh giá file; người dùng không cần chép từng số trên màn hình. Công cụ
không phát command, không sửa TF/firmware/sign. Phiên chưa chạy không được
coi là đã xác minh gyro yaw sign.

Quy tắc sàng lọc được chốt trong code trước lượt thu: so mean mỗi lượt quay
với baseline, yêu cầu đúng hướng vượt 3 lần std mẫu baseline và ít nhất
20% mẫu vượt cùng phía dải đó ở cả hai hướng. Đây là dải nhiễu thực nghiệm
mang tính mô tả, không phải CI, giới hạn an toàn hoặc độ chính xác hiệu
chuẩn. Trường hợp thiếu phase, header bất thường, không rõ hướng hoặc chỉ
quay một hướng được báo unknown; toàn bộ mẫu và failures giữ lại. Script
đã qua `--check` trên Pi và fixture software đúng dấu/ngược dấu/không quay/
hai nhãn cùng chiều; phiên hardware có nhãn mới đã được kiểm raw và đạt.

### Cách xem trực tiếp nếu cần

Chỉ làm khi drive đã được xác nhận không tạo mô-men và có thể xoay robot
bằng tay phù hợp. Giữ nguyên lắp đặt bo. Đây là quan sát dấu, không chạy
motor, không phải calibration tốc độ/góc quay.

Trong terminal Pi:

```bash
source ~/pi5-stm32-slam-main/scripts/env.sh
export ROS_DOMAIN_ID=0
ros2 topic echo /imu/data sensor_msgs/msg/Imu --field angular_velocity.z --qos-reliability best_effort
```

- Giữ yên: xem baseline và nhiễu, không đòi mọi mẫu bằng 0.
- Quay trái đều vài giây, ngược chiều kim đồng hồ nhìn từ trên: kỳ vọng
  gyro Z chủ yếu dương và phân biệt được với baseline.
- Quay phải: kỳ vọng chủ yếu âm.
- Ctrl+C để dừng đọc. Nếu hướng không rõ so với nhiễu, ghi unknown; nếu
  dấu ngược, kiểm nguyên nhân trước khi đảo sign.

Phép xoay mounting hiện chỉ quanh Z nên raw gyro Z và body gyro Z cùng dấu
trong xấp xỉ đang dùng. Phép thử này không phân biệt mounting yaw 0° với
90°; X/Y đã có bằng chứng từ phép kiểm gravity trước đó.

## Bằng chứng và giới hạn

- [Manifest thay đổi và backup](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/imu_tf_applied_2026-10-27/runtime_evidence/change_manifest.json>).
- [Kiểm tra live TF/topic](</home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/imu_tf_applied_2026-10-27/runtime_evidence/verification.json>).
- Các raw session cũ giữ nguyên. Không có flash, enable hoặc command motor.
- Offset đã áp từ số đo gần đúng; gyro Z đạt phép kiểm có nhãn. Chưa đo
  đáp ứng actuator/body, slip hoặc governor benefit; fine calibration còn thiếu.

