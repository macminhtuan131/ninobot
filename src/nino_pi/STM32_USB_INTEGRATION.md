# Nino + firmware STM32H723 qua USB

**27/10/2026.** Source tham khảo được ghim tại
[`0d32593988cc817311d3dfdd8683df1f1b444a2c`](https://github.com/nguyenbinh-shark/Microros_H723_USB/tree/0d32593988cc817311d3dfdd8683df1f1b444a2c).
Đây là integration thu dữ liệu và chuẩn bị build, chưa xác nhận bản đã nạp
trên board. Không cấu hình motor, flash hoặc launch driver từ collector.

**Kết quả live mới nhất, 27/10/2026:** người dùng đã kiểm tra feedback trái.
Phiên sensor inventory riêng đã ghi raw IMU/motor/status, RPLIDAR A1 M8,
bridge và TF. Raw/bridge khớp header/payload trong cửa sổ giao nhau; mounting
vẫn là model khai báo, chưa kiểm chuẩn. Xem
[báo cáo kết quả và bước tiếp theo](../../docs/REAL_SENSOR_INTEGRATION_2026-10-27.md).
Profile full bên dưới giữ nguyên; phiên sensor inventory không thay gate motion.

## 1. Thành phần và contract

```text
IMU / motor CAN → STM32 firmware → USB CDC → micro-ROS Agent trên Pi
                                               ↓ raw ROS topics
                                    collector / audit / bridge
```

Agent là cầu nối hai chiều; node khác trong cùng graph có thể gửi lệnh qua
agent. Collector chỉ quan sát. `allow_motor_enable=false` ở Pi bridge chỉ
chặn service của bridge, không khóa ROS topic trực tiếp, firmware hoặc RC.

| Topic | Firmware tại commit tham khảo | Cách sử dụng |
|---|---|---|
| `/motor_fb` | JointState, best effort, target 50 Hz | Giữ tên joint, header và toàn bộ arrays; không chuyển thành body GT |
| `/motor_status` | UInt8, reliable, target 5 Hz | Giữ raw bitmask; diễn giải theo đúng bản đã nạp |
| `/imu/data` | Imu, best effort, target 50 Hz | Bản gốc trước Pi bridge, gồm gravity theo source contract |
| `/imu/debug` | Float64MultiArray, best effort | Chẩn đoán khi output IMU bị chặn bởi calibration/time sync/validity |
| `/cmd_vel`, `/cmd_mit`, `/cmd_torque`, `/motor_enable` | Command inputs | Ghi nếu có; không phát hoặc replay để điền topic thiếu |
| `/imu/bridge`, `/odom/unfiltered`, `/joint_states` | Do Pi bridge nếu chạy | Dữ liệu dẫn xuất, không thay raw firmware channels |
| `/scan_raw`, `/scan` | Driver LiDAR / deskew phía Pi | Cần driver LiDAR riêng; firmware này không tạo LaserScan |

Các rate trên là mục tiêu source, chưa là rate đo trên robot. Effort từ motor
là reported/unverified torque, không phải cảm biến torque độc lập. Khi thiếu
feedback CAN, vẫn có thể nhận JointState không đại diện phép đo mới; counts
không chứng minh freshness. Không diễn giải giá trị 0 là encoder đứng yên
nếu status tương ứng chưa xác nhận. Status 5 Hz cũng không xác nhận freshness
từng mẫu 50 Hz hoặc tự phát hiện mọi gián đoạn giữa hai status.

Bit 0/1 là freshness trái/phải; bit 2/3 là CAN bus-off; bit 4 lấy từ biến
enable của firmware; bit 5 là timeout; bit 6 là mode MIT. Bit enable không
là phép đo nguồn công suất hoặc xác nhận torque đang tác động. Chưa có kênh
đã xác nhận cho wheel target sau mọi limiter/current/PI internals của Nino:
không suy chúng từ `/cmd_vel`, không coi profile full là đủ chứng minh H2.

## 2. Hai profile, hai phạm vi kết luận

| File | Required channels | Kết luận được phép |
|---|---|---|
| `config/stm32_usb_imu_collection.json` | `/imu/data`, `/motor_status` | Chỉ kiểm kê USB/IMU; motor power ngắt, không cần Nav2/bridge/LiDAR |
| `config/stm32_usb_collection.json` | Toàn bộ required của `real_collection.json`, cộng `/motor_fb`, `/motor_status` | Bộ dữ liệu sensor/command đầy đủ; vẫn cần kiểm tra tính hợp lệ vật lý |

Profile IMU là contract giai đoạn đầu riêng, không phải kết quả full dataset
được cứu bằng cách bỏ required. Không dùng nó để công bố slip, motor response,
arrival, navigation hoặc governor. Nếu thiếu `/imu/data`, giữ incomplete;
`/imu/debug` hỗ trợ tìm nguyên nhân, không thay kênh IMU hợp lệ.

Profile full giữ nguyên gate required trước đây. Ví dụ chỉ launch `bench`
không tạo `/odom` fused, `/scan` hay command stream: full session sẽ thiếu
channel; không tự publish zero hoặc bật navigation để làm đầy counts.

## 3. Chuẩn bị config trên Pi

Copy package mới từ laptop sang một thư mục mới trên Pi; không chép build
x86 sang Pi và không ghi đè `~/nino_collection_config` hiện có. Ví dụ giải
nén bundle vào `~/nino_stm32_usb_tools` rồi dùng:

```bash
nino_pkg="$HOME/nino_stm32_usb_tools/src/nino_pi"
nino_cfg="$HOME/nino_collection_config/stm32_usb"
mkdir -p "$nino_cfg"
cp --update=none "$nino_pkg/config/stm32_usb_imu_collection.json" "$nino_cfg/imu_topics.json"
cp --update=none "$nino_pkg/config/stm32_usb_collection.json" "$nino_cfg/full_topics.json"
cp --update=none "$nino_pkg/config/stm32_usb_collection_qos.yaml" "$nino_cfg/qos.yaml"
cp --update=none "$nino_pkg/config/stm32_usb_session.template.json" "$nino_cfg/session.json"
```

Trong session, điền ID duy nhất, profile đang dùng và phạm vi kết luận.
`reviewed_source_commit` đã có nguồn tham khảo; bản flashed, binary hash,
board revision, motor compatibility, boot/RC và số đo vẫn để `null` tới khi
có bằng chứng. Không coi metadata trong template là cấu hình controller.

Kiểm tra offline, chưa cần driver hoặc agent:

```bash
export PYTHONPATH="$nino_pkg${PYTHONPATH:+:$PYTHONPATH}"
/usr/bin/python3 -m nino_pi.collect_real_data \
  --config "$nino_cfg/imu_topics.json" --session "$nino_cfg/session.json" \
  --qos "$nino_cfg/qos.yaml" --output "$HOME/nino_real_data/stm32_validation_only" --check
```

`--check` chỉ kiểm tra cấu trúc/plan. Session ID `EDIT_*` vẫn được collector
hiện tại chấp nhận về cú pháp; phải thay trước khi thu thật. Không diễn giải
check thành kết nối agent, endpoint QoS hay storage backend đã được thử.

## 4. Kiểm kê đứng yên sau khi xác nhận phần cứng

Log người dùng đã gửi cho thấy STM32 Virtual ComPort `0483:5740`, serial
`317136523233`, được gán `/dev/ttyACM0` lúc cắm lại. Đây là bằng chứng USB
trong log đó; cần kiểm tra đường dẫn/quyền ở phiên mới, không gán nhầm CP2102.

Đợt đầu ngắt nguồn công suất motor theo thiết kế nguồn thực, giữ nguồn logic
board phù hợp. Chưa xác nhận flashed firmware/boot/RC nên không dựa vào gate
trên Pi để bảo đảm motor bị disable. Giữ board đứng yên lúc IMU hiệu chuẩn.

Trong terminal A trên Pi, sau khi kiểm tra package/quyền và không có agent
khác chiếm cổng, có thể mở một agent thủ công:

```bash
source "$HOME/pi5-stm32-slam-main/scripts/env.sh"
export ROS_DOMAIN_ID=0
ros2 pkg executables micro_ros_agent
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 --baudrate 921600 -v 3
```

Domain 0 là giá trị host khởi đầu được chọn minh bạch theo script Pi hiện có;
phải đối chiếu client/static-library và discovery thực tế nếu không thấy node.
Source cùng env/domain cho terminal B. Không chạy thêm launch `bench` mặc
định mở agent thứ hai. Muốn dùng bridge sau đó, launch phải đặt
`start_agent:=false`; chưa cần bridge để nhận raw topics.

Trong terminal B, kiểm tra đúng publisher, mẫu thật và QoS:

```bash
source "$HOME/pi5-stm32-slam-main/scripts/env.sh"
export ROS_DOMAIN_ID=0
ros2 node list
ros2 topic info /imu/data --verbose
ros2 topic info /motor_status --verbose
ros2 topic echo /imu/data --once --qos-reliability best_effort
ros2 topic echo /motor_status --once
```

Giới hạn chờ mỗi echo bằng Ctrl+C nếu không có mẫu; giữ log thiếu dữ liệu.
Nếu mất CAN freshness khi motor power ngắt, đó không phải bằng chứng encoder
đứng yên hợp lệ. Không bật motor để làm biến mất warning trong phiên IMU.

Khi nhận được mẫu đúng nguồn, chỉnh session/profile rồi ghi riêng phiên mới:

```bash
export PYTHONPATH="$HOME/nino_stm32_usb_tools/src/nino_pi${PYTHONPATH:+:$PYTHONPATH}"
/usr/bin/python3 -m nino_pi.collect_real_data \
  --config "$HOME/nino_collection_config/stm32_usb/imu_topics.json" \
  --session "$HOME/nino_collection_config/stm32_usb/session.json" \
  --qos "$HOME/nino_collection_config/stm32_usb/qos.yaml" \
  --output "$HOME/nino_real_data/stm32_imu_$(date -u +%Y%m%dT%H%M%SZ)"
```

Kiểm tra manifest, bag metadata/counts, source stamps, audit và các warnings
sau đóng bag. Collector hiện kiểm tra completeness bằng cấu trúc/counts và
audit, chưa tự enforce firmware-version, status bits, sample freshness hay
claim scope trong profile. Cần đọc những điều đó trước khi kết luận.

## 5. Build/nạp và giới hạn tương thích

Source firmware được chuẩn bị riêng trên laptop cùng `build_firmware.sh`
và `prepare_toolchain.sh`; xem README của thư mục làm việc firmware. Build
thành công không xác nhận wiring, motor protocol hoặc binary đang trên board.

Tại commit ghim: motor task dùng `rs_ext_*` của RobStride qua FDCAN1/FDCAN3,
hai ID 1 trên hai bus riêng. Có file CyberGear không có nghĩa driver đó đang
được gọi. Nino được người dùng xác nhận CyberGear; compatibility vẫn unknown.
Không thay gain, sign, CAN IDs, current/torque limits theo ví dụ source.

`/cmd_vel` chọn actuator velocity mode; `/cmd_mit` và `/cmd_torque` chọn
operation-control/MIT. Không phát xen kẽ và không chồng external velocity PI
lên motor velocity PI. Pinout/IMU/clock phải phù hợp CtrBoard-H7/H723 thực.

README còn mô tả boot auto-enable/100 Hz trong khi code ghim gọi disable ở
startup và đặt motor task 2 ms. Đây là khác biệt tài liệu/source, không phải
bằng chứng board đang chạy bản nào. RC có thể tác động quyền điều khiển.
Collector không thay đổi arbitration hoặc thử watchdog.

### Nguồn ghim

- [Firmware ROS entities/status/headers](https://github.com/nguyenbinh-shark/Microros_H723_USB/blob/0d32593988cc817311d3dfdd8683df1f1b444a2c/Core/Src/freertos.c).
- [Motor task và boot/mode](https://github.com/nguyenbinh-shark/Microros_H723_USB/blob/0d32593988cc817311d3dfdd8683df1f1b444a2c/User/APP/motor_task.c).
- [Porting](https://github.com/nguyenbinh-shark/Microros_H723_USB/blob/0d32593988cc817311d3dfdd8683df1f1b444a2c/docs/porting.md).
- [Cấu hình firmware](https://github.com/nguyenbinh-shark/Microros_H723_USB/blob/0d32593988cc817311d3dfdd8683df1f1b444a2c/User/Config/robot_config.h).
