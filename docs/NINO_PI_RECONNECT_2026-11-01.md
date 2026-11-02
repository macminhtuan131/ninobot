# Pi nối lại và chuẩn bị phần mềm — 01/11/2026

> **Cập nhật tiếp cùng ngày:** đã thêm EKF/odom TF, cấu hình monitor dùng
> `/scan_raw`, kiểm chuỗi command trên topic riêng và chuẩn bị profile một
> lượt tiến–zero được người dùng chọn. [Trạng thái mới và lệnh thu](NINO_WHEEL_COLLECTION_READY_2026-11-01.md).
> Các mục “gate còn mở” bên dưới mô tả thời điểm trước cập nhật này.

## Kết quả

SSH tới `d@192.168.0.109` đã xác thực thành công bằng khóa hiện có; SSH mặc
định từ laptop cũng vào được. Không cần cài lại public key. Boot ID mới:
`efa9e5ea-00fc-42f1-a5d0-006a8196be38`. Pi nhận STM32 VCP tại
`/dev/stm32_robot → ttyACM0` và CP2102 LiDAR tại ttyUSB0/by-id cũ.

Ban đầu sau reboot không thấy các tiến trình ROS đang chạy. Đã khôi phục
ba wrapper sensor-only đã review: micro-ROS agent, bridge + state publisher,
RPLIDAR A1 raw. Không launch command stack/keyboard/Nav2/governor, không
gọi enable/disable hoặc phát velocity/torque. Bridge enable vẫn cô lập ở
tên `unused_*`; đây không phải khóa RC hoặc đo trạng thái công suất motor.

Runtime/logs mới: `/home/d/nino_runtime/reconnect_20261101_v1`.
Launcher process groups agent/sensors/LiDAR lần lượt 1605/1606/1607.
Không thêm service autostart. Source firmware và config mounting không đổi
bởi lượt này.

## Quan sát live 12 giây sau khôi phục

| Kênh | Số mẫu nhận |
|---|---:|
| Raw IMU / motor feedback | 568 / 568 |
| IMU bridge / joint states / encoder odom | 469 / 470 / 470 |
| Raw scan | 79 |
| Motor status | 56, tất cả bằng 35 |
| TF động / tĩnh | 164 / 1 message |

Nhận đủ 9 topic dự kiến. Các stream có header được kiểm không có timestamp
zero/lùi/trùng trong cửa sổ. IMU raw khoảng 47,23 Hz, scan khoảng 6,59 Hz;
counts/rate của các consumer có discovery boundaries khác nhau nên không
gọi chênh count là loss. Đây là kiểm sức khỏe cửa sổ ngắn, không là dataset
response, một coverage guarantee hoặc chứng minh mode/power từ status bit.

TF tiếp tục đúng config gần đúng đã áp trước đó: base cao 0,056 m, IMU
xyz `[-0.05,-0.02,0.014]` m/yaw +90°, laser xyz `[0.22,0,0.189]` m.
Không lặp lại các phép kiểm gravity/gyro sign.

## Chuẩn bị teleop và collector

Overlay driver ban đầu chưa tìm thấy `nino_pi`; `/home/d/nino_pi_ws` chưa
có setup. Đã chuyển 43 file source được hash và build riêng bằng colcon
vào `/home/d/nino_pi_ws`, symlink install; build thành công một package.
Có command_gate, keyboard_teleop, collect_real_data, laptop_control và các
profile/session/protocol mới. Chỉ cài phần mềm, không thực thi các node command.

Đã cập nhật `/home/tuanmac/nino_laptop_control.json` có backup:

- host `192.168.0.109`, ROS domain `0`;
- driver setup `~/pi5-stm32-slam-main/scripts/env.sh` để giữ DDS profile;
- robot setup `~/nino_pi_ws/install/setup.bash`;
- control/navigation YAML từ package share của overlay mới.

Helper laptop `--dry-run teleop` đạt, script in ra được lưu mà không chạy.
Collector trên Pi `--check` đạt với profile wheel-response và session draft;
không tạo directory ghi bag. Các giá trị tốc độ/ramp/stop chưa được chấp
nhận vẫn null trong form. `--check` không là motion release.

## Gate còn mở

Graph sau chuẩn bị vẫn có `/scan_raw`, `/odom/unfiltered`; chưa có publisher
`/scan` hoặc `/odom`. TF quan sát chưa có odom→base. Full teleop monitor
YAML đang cần scan/odom TF, nên chưa coi chuỗi đó ready. Cần giải quyết
theo command contract, không bypass monitor chỉ để làm robot chạy.

Không thấy publisher trên `/cmd_vel`, `/cmd_mit`, `/cmd_torque`,
`/motor_enable` trong snapshot. Chưa chứng minh quyền RC hoặc trạng thái
physical stop bằng graph. Còn phải chốt mapping/trạng thái RC, semantics
nút đỏ, owner enable và profile/limits trước slot commissioning.

Bước kế tiếp theo [roadmap](NINO_PROGRESS_AND_NEXT_STEPS_2026-10-28.md) vẫn
là P1 contract, sau đó E1 sàn sạch. Chưa có kết quả motor-driven mới hoặc
căn cứ promote governor từ lần nối lại này.

## Artifact

Bản sao laptop:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/pi_reconnect_2026-11-01/`.
Gồm source manifest, launcher/log paths, live_verification, dependency
snapshot, package/collector preparation verification, config backup và
dry-run script. Raw sessions cũ được giữ nguyên.
