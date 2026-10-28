# Nino trên Raspberry Pi 5 — navigation và teleop

**14/10/2026.** Bundle ROS 2 Jazzy cho Ubuntu 24.04 **64-bit/aarch64**.
Chạy Nav2, keyboard/joystick teleop và SLAM trên thời gian thật. Không cần
Gazebo, PyTorch, CUDA hay checkpoint RL. Đây là tầng navigation phía trên
driver vật lý; bundle **không chứa driver CyberGear/CAN, IMU hoặc LiDAR**.
Repository hiện chưa có backend CyberGear `ros2_control` cho robot thật.

**Hiện trạng 28/10/2026:** đã có dữ liệu sensor/STM32/LiDAR thật được kiểm
ngày 27/10; chưa có motion-response dataset đã xác minh. Xem
[đánh giá tiến độ và công việc kế tiếp](../../../docs/NINO_PROGRESS_AND_NEXT_STEPS_2026-10-28.md)
và [protocol/profile wheel response](WHEEL_RESPONSE_PROTOCOL.md). Profile
wheel-level riêng không yêu cầu full navigation; command path và giới hạn
thật vẫn cần được chốt trước lượt motor.

**Thu thập dữ liệu chỉ đọc:** xem [REAL_DATA_COLLECTION.md](REAL_DATA_COLLECTION.md)
cho danh mục số liệu cần đo, config, live monitor và collector ROS bag có giới
hạn trên Ubuntu Server/Pi qua SSH. Không khởi động motor hoặc gửi lệnh chuyển động.

**Firmware STM32H723 qua USB:** xem
[STM32_USB_INTEGRATION.md](STM32_USB_INTEGRATION.md) cho profile thu raw,
metadata bản firmware và cách kiểm tra agent; USB/IMU có phạm vi riêng với
bộ dữ liệu đầy đủ. Không tự nạp board hoặc enable motor.

**Lái từ laptop và ghi dữ liệu:** xem
[LAPTOP_CONTROL_AND_COLLECTION.md](LAPTOP_CONTROL_AND_COLLECTION.md).
Helper SSH dùng keyboard node trên Pi; navigation/mapping dùng stack có sẵn,
không tự enable. Config tại `config/laptop_control.example.json`.

## 1. Kiểm tra Pi trước

**Xem trạng thái trực tiếp khi robot đang chạy:**
[`PI_LIVE_STATE_MONITOR_2026-10-17.md`](../../../docs/PI_LIVE_STATE_MONITOR_2026-10-17.md).
Copy `nino_pi/state_monitor.py` sang Pi, source ROS/workspace driver rồi chạy
`/usr/bin/python3 ~/state_monitor.py`. Monitor hiển thị IMU, encoder, odom,
torque command/effort nếu có, LiDAR và battery; `--signals` bổ sung current,
torque và nhiệt độ theo interface driver thực. Không phát lệnh motor.
`--record DIRECTORY` ghi đầy đủ message nhận được; command torque không
được trình bày thành torque đo thật.

**Collector chỉ đọc mới:** xem
[`PI_READONLY_DATA_COLLECTION_2026-10-17.md`](../../../docs/PI_READONLY_DATA_COLLECTION_2026-10-17.md).
Copy riêng `nino_pi/hardware_audit.py` sang Pi, không cần build package:

```bash
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 ~/hardware_audit.py --duration 60 \
  --output "$HOME/nino_audits/$(date +%Y%m%d_%H%M%S)"
```

Xuất `REPORT.md`, `report.json`, `samples.jsonl`, `graph.mmd`, tham số PI
đọc được và power warnings. Không phát lệnh motor hoặc đổi tham số.
Trục/dấu encoder và vị trí PI giữ chưa xác minh nếu thiếu bằng chứng;
không coi không có undervoltage log là nguồn đã ổn. Nếu đã build package
mới, có thể dùng `ros2 run nino_pi hardware_audit` với cùng arguments.

Sau khi source ROS và workspace hardware nếu có:

```bash
source /opt/ros/jazzy/setup.bash
bash ~/nino_pi_ws/src/nino_pi/scripts/check_pi.sh | tee ~/nino_pi_check.txt
```

Script chỉ đọc platform, packages, nodes, topics, rates và TF; không phát
lệnh motor. `timeout` sau 4 giây lấy mẫu rate là bình thường. Gửi file
`~/nino_pi_check.txt` để xác định thành phần còn thiếu.

| Trạng thái | Ý nghĩa |
|---|---|
| Có package driver | Đã cài phần mềm, chưa chứng minh nối được phần cứng |
| Có node và publisher | Driver đã khởi động; vẫn cần kiểm tra dữ liệu |
| Topic có rate và dữ liệu đúng | Sensor/backend đang hoạt động trên ROS |
| Không có topic | Có thể chưa chạy/source driver; chưa đủ kết luận chưa cài |

Không có `ros2_control` không tự động là lỗi: một driver motor khác có thể
nhận `/cmd_vel` trực tiếp. Với backend effort của Nino, phải có
`joint_state_broadcaster` và `wheel_effort_controller` active, cùng adapter
PI `nino_control effort_drive` đã cấu hình/hiệu chuẩn cho motor thật.

## 2. Cài bundle

Pi cần Ubuntu 24.04, ROS 2 Jazzy đã cài theo
[hướng dẫn chính thức](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html).
Giải nén archive vào `src/` của workspace:

```bash
mkdir -p ~/nino_pi_ws/src
unzip ~/Downloads/nino_pi5_navigation_teleop_2026-10-14.zip -d ~/nino_pi_ws/src
bash ~/nino_pi_ws/src/nino_pi/scripts/install_dependencies.sh
cd ~/nino_pi_ws
source /opt/ros/jazzy/setup.bash
python3 -m colcon build --symlink-install --packages-select nino_pi
source install/setup.bash
```

Nếu dùng checkout đầy đủ `~/ninorobot`, build riêng `nino_pi` trong workspace
đó thay vì giải nén. Đừng copy `build/` hoặc `install/` từ laptop x86 sang Pi.

Mỗi terminal Pi/laptop dùng chung:

```bash
source /opt/ros/jazzy/setup.bash
source ~/nino_pi_ws/install/setup.bash
export ROS_DOMAIN_ID=88
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
```

Source workspace driver hardware trước overlay `nino_pi` nếu driver nằm
trong workspace khác. Pi/laptop cần cùng ROS domain và kết nối mạng; không
dùng `LOCALHOST` khi điều khiển từ máy khác. Không dùng domain simulator 80
cho deployment này.

## 3. Giao diện phần cứng bắt buộc

Khởi động driver motor, encoder, IMU và LiDAR bằng launch thực tế của bạn
trước; chưa thể đưa lệnh driver cụ thể khi chưa biết driver đã cài.

| Giao diện | Yêu cầu |
|---|---|
| `/cmd_vel` | Backend nhận `geometry_msgs/msg/Twist`, đơn vị m/s và rad/s |
| `/odom` | `nav_msgs/msg/Odometry`, từ encoder hoặc estimator thực |
| `/scan` | `sensor_msgs/msg/LaserScan`, LiDAR ngang thật |
| `/imu/data` | IMU cho estimator/giám sát; Nav2 hiện không fuse trực tiếp |
| `/joint_states` | Encoder cho wheel PI/RSP khi backend dùng ROS joints |
| TF | `odom → base_footprint → base_link → laser`; sensor mount đo trên robot |
| `map → odom` | AMCL khi navigation; SLAM Toolbox khi mapping |

Chỉ một node được sở hữu mỗi TF. Không dựng TF odom giả hoặc phát sensor
giả để làm navigation chạy. Driver motor phải tự zero command khi đầu vào
mất, ngay cả khi Pi/process mạng chết; gate phần mềm không thay hardware stop.
Không launch file simulation của `nino_description` để chạy motor thật.

Nếu dùng adapter effort hiện có: `/joint_states` phải có vị trí/vận tốc
`left_wheel_joint`, `right_wheel_joint`; output effort nhận N·m trái/phải.
Hiệu chuẩn giới hạn torque/gains và chiều encoder trên phần cứng. Bundle
không tự chọn torque limit hoặc bật residual torque RL.

## 4. Luồng lệnh

```text
Keyboard hoặc joystick → /cmd_vel_teleop ┐
Nav2                  → /cmd_vel_nav    ├→ command_gate
                                       ┘  → /cmd_vel_selected
                                          → velocity_smoother
                                          → /cmd_vel_smoothed
                                          → collision_monitor
                                          → /cmd_vel → driver → wheel PI/motor
```

Gate mặc định **disabled, manual mode**. Giới hạn đầu ra khởi đầu 0.20 m/s
tiến, 0.10 m/s lùi, 0.60 rad/s quay; command quá 0.3 giây trả zero. Đổi mode
hoặc enable xóa lệnh cũ. Manual không tự chuyển lại Nav2 khi keyboard mất
kết nối. Tất cả topic vận tốc dùng **Twist**, cấu hình Jazzy
`enable_stamped_cmd_vel: false` nhất quán.

Smoother giới hạn accel/decel ở `config/control.yaml`; collision monitor nằm
sau cả hai nguồn để kiểm tra LiDAR. Mất scan/TF làm monitor dừng. Scan ngang
không phát hiện tin cậy cáp/groove thấp; stack này chưa có governor contact
hoặc policy RL đã xác nhận trên robot thật.

## 5. Keyboard teleop

Terminal A, sau khi hardware drivers đã chạy:

```bash
ros2 launch nino_pi teleop.launch.py
```

Terminal B, bật luồng manual sau kiểm tra driver:

```bash
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: true}'
bash "$(ros2 pkg prefix --share nino_pi)/scripts/keyboard_teleop.sh"
```

Dùng `i` tiến, `,` lùi, `j/l` quay, `k` dừng. Giữ phím; sau 0.6 giây không
nhận phím teleop gửi zero. SSH dùng `ssh -t USER@PI_IP`; keyboard cần TTY.
Keyboard node đi kèm tự publish 20 Hz và kiểm tra timeout bằng monotonic
clock. Không dựa vào `repeat_rate/key_timeout` của package keyboard ROS 1;
package ROS 2 Jazzy cài trên máy phát triển không triển khai hai tham số đó.
Không dùng một keyboard publisher khác phát thẳng `/cmd_vel` vì sẽ bỏ qua gate.

Joystick thay keyboard:

```bash
ros2 launch nino_pi teleop.launch.py joystick:=true
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: true}'
```

Giữ LB (button 4) để chạy; layout ban đầu kiểu Xbox. Kiểm tra `/joy` và sửa
`config/joystick.yaml` cho controller thực. Chọn keyboard **hoặc** joystick,
không chạy cả hai publisher cùng lúc trên `/cmd_vel_teleop`.

## 6. Tạo map thật

Dừng teleop launch cũ rồi chạy (mapping đã chứa command stack):

```bash
ros2 launch nino_pi mapping.launch.py
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: true}'
bash "$(ros2 pkg prefix --share nino_pi)/scripts/keyboard_teleop.sh"
```

Quan sát bằng RViz trên laptop cùng domain 88. Sau khi map đủ vùng:

```bash
mkdir -p ~/maps
ros2 run nav2_map_server map_saver_cli -f ~/maps/factory
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: false}'
```

`factory.yaml` và `factory.pgm` là occupancy map; world `.sdf` không phải
map navigation. Dừng SLAM trước AMCL để không có hai nguồn `map → odom`.

## 7. Navigation

Dừng mapping/teleop launch cũ, giữ hardware drivers:

```bash
ros2 launch nino_pi navigation.launch.py map:=$HOME/maps/factory.yaml
```

RViz trên laptop: `ros2 launch nav2_bringup rviz_launch.py use_sim_time:=false`.
Đặt **2D Pose Estimate** đúng vị trí/hướng hiện tại; không giả định robot ở
gốc map. Kiểm tra map/laser/footprint/TF trước khi đặt goal.

```bash
ros2 service call /nino_command_gate/navigation_mode std_srvs/srv/SetBool '{data: true}'
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: true}'
```

Gửi **Nav2 Goal** từ RViz. Controller dùng Regulated Pure Pursuit, planner
NavFn A*, costmap 2D từ scan; không dùng cấu hình tốc độ 1.2–1.5 m/s của
simulation cũ. RViz trên Pi là tùy chọn `rviz:=true`, mặc định tắt.

Muốn chuyển manual trong cùng navigation launch:

```bash
ros2 service call /nino_command_gate/navigation_mode std_srvs/srv/SetBool '{data: false}'
bash "$(ros2 pkg prefix --share nino_pi)/scripts/keyboard_teleop.sh"
```

Hủy goal Nav2 đang chạy trước khi quay lại navigation mode. Không mở thêm
`teleop.launch.py` song song với navigation vì cả hai đã chứa command stack.

## 8. Dừng

```bash
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: false}'
```

Software stop có latch:

```bash
ros2 topic pub --once /nino/emergency_stop std_msgs/msg/Bool '{data: true}'
```

Để clear: giữ disabled, gọi `/nino_command_gate/reset_stop` bằng
`std_srvs/srv/Trigger '{}'`, rồi enable lại khi đã xác định nguyên nhân.
False trên topic stop không tự clear. Đây không phải E-stop vật lý hay hệ
thống an toàn nhà máy đã chứng nhận.
Software stop đưa zero vào smoother; deceleration vẫn bị giới hạn bởi
smoother. Hardware E-stop phải hoạt động độc lập.

## 9. Trạng thái kiểm chứng

### Governor phản ứng tùy chọn

Sau khi cài/build cả `nino_control` và driver đã cung cấp feedback đo được:

```bash
ros2 launch nino_pi teleop.launch.py governor:=true
```

Cùng tùy chọn dùng được với mapping/navigation. Mode này thay velocity
smoother bằng governor, vẫn đi qua Collision Monitor. Gate và governor
mặc định disabled. Cần kiểm tra IMU mount/gravity semantics và schema
`/nino_drive/diagnostics` trước; driver hardware không tự có topic này.
Sau khi feedback được kiểm chứng:

```bash
ros2 service call /nino_speed_governor/enable std_srvs/srv/SetBool '{data: true}'
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: true}'
```

Đây là tùy chọn experimental, chưa xác nhận trên Pi/motor thật. Xem
`docs/NINO_REACTIVE_GOVERNOR_V1_2026-10-14.md` trong repo để chạy thí nghiệm
Gazebo/H2 trước. Bundle navigation ZIP cũ không chứa `nino_control`; cần copy
package mới và build trên Pi. Không chạy thêm một speed_governor riêng vì
command stack đã sở hữu pipeline này.

Các file chính: `launch/navigation.launch.py`, `launch/teleop.launch.py`,
`launch/mapping.launch.py`, `config/navigation.yaml`, `config/control.yaml`,
`config/joystick.yaml`, `scripts/check_pi.sh`, `scripts/keyboard_teleop.sh`.

Bundle được kiểm tra trên laptop ROS Jazzy: build, launch arguments, logic
command ownership/expiry/latch và file map. Test ROS domain riêng với sensor
giả xác nhận manual/nav đi qua smoother và collision monitor, command hết
hạn/mất scan/stop latch trả output zero và vận tốc nằm trong giới hạn.
Sensor/TF giả chỉ dùng trong test này, không thuộc deployment.
Navigation launch có đủ 10 lifecycle nodes active trên map/TF/scan/odom
giả, không gửi goal. 10 unit tests pass. Chưa có phép thử dẫn đường thực tế.
Test TTY thật xác nhận một lần nhấn phím phát vận tốc, hết hạn phím trả
zero và Ctrl-C thoát sạch. Không có motor driver trong các test này.
Chưa thử trên Pi 5, driver
CyberGear thật hay robot thật. Footprint và StopZone là starting envelope
theo CAD Nino; đo lại robot/payload, mounting và quãng phanh để hiệu chỉnh.
Tốc độ/gains và độ chính xác AMCL phải được xác nhận trên phần cứng.

Nguồn thiết kế: [Nav2 velocity smoother Jazzy](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/configuring_velocity_smoother/),
[Nav2 collision monitor](https://docs.nav2.org/jazzy/tutorials/general_tutorials/using_collision_monitor/using_collision_monitor/),
[teleop_twist_keyboard ROS 2](https://github.com/ros-teleop/teleop_twist_keyboard/tree/ros2).
Thông số và launch đã đối chiếu với package Jazzy cài trong workspace máy phát triển.
