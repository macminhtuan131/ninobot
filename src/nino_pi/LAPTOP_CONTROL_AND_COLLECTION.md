# Điều khiển từ laptop và thu dữ liệu trên Pi

## 1. Kiến trúc và giới hạn

```text
Laptop terminal ── SSH/TTY ──> keyboard_teleop chạy trên Pi ─> /cmd_vel_teleop ┐
Laptop RViz ── ROS network ─> Nav2 goal ─> Nav2 trên Pi ──> /cmd_vel_nav     ├─>
                                              command_gate (disabled lúc khởi động)
                                                  ↓ /cmd_vel_selected
                                              velocity_smoother
                                                  ↓ /cmd_vel_smoothed
                                              collision_monitor ← scan + TF
                                                  ↓ /cmd_vel
                                              driver thật → wheel PI/motor

Collector trên Pi ← IMU, encoder, LiDAR, odom, TF, command stages, motor telemetry
```

Helper SSH mới: `nino_pi/laptop_control.py` và `scripts/laptop_control.sh`.
Laptop chỉ cần Python 3 và SSH để dùng keyboard; không cần ROS hoặc multicast
giữa hai máy cho cách này. RViz trên laptop cần ROS Jazzy/Nav2 và ROS discovery
đến Pi riêng. Nav2/mapping/command stack chạy trên Pi; collector chạy terminal
khác. Không chạy hai command stack hoặc hai nguồn `map → odom` cùng lúc.

Gói đã chứa launch/config navigation, mapping, keyboard/joystick và collection.
Nó **không chứa driver motor/CAN/encoder/IMU/LiDAR của robot thật**. Không khởi
động launch Gazebo để thay driver. Driver nhận final `/cmd_vel` kiểu `Twist`;
backend dùng giao diện khác cần adapter đúng cho thiết bị đó.

Chưa có kiểm chứng chuyển động trên Pi/robot của bạn. Nguồn từng báo không
đủ 5A/undervoltage; cần kiểm tra nguồn trước chạy có tải. Gate mặc định tắt,
giới hạn/ramp trong `control.yaml` là cấu hình khởi đầu, chưa hiệu chuẩn phần
cứng. Collision monitor cần LiDAR/TF còn mới; không tắt nó để vượt lỗi thiếu
sensor. Horizontal scan không bảo đảm nhìn thấy cáp/hõm.

## 2. Cài gói điều khiển trên Pi

Giải nén archive cập nhật vào `~/nino_data_tools` như bộ collection. Chạy
trên Pi (SSH shell `d@d`):

```bash
bash ~/nino_data_tools/src/nino_pi/scripts/install_dependencies.sh
bash ~/nino_data_tools/src/nino_pi/scripts/install_collection_dependencies.sh
source /opt/ros/jazzy/setup.bash
# Source workspace DRIVER THẬT nếu driver/custom message ở overlay khác.
mkdir -p ~/nino_pi_ws
cd ~/nino_pi_ws
python3 -m colcon build --symlink-install \
  --base-paths "$HOME/nino_data_tools/src/nino_pi" --packages-select nino_pi
source ~/nino_pi_ws/install/setup.bash
ros2 pkg prefix nino_pi
```

Không copy `install/build` x86 từ laptop sang Pi ARM. Không cần build cho
collector Python độc lập; cần build package để `ros2 launch/run nino_pi` tìm
được các file/executable điều khiển. Giữ driver thật chạy riêng với config
đã kiểm tra. Đối chiếu audit về nguồn, TF, feedback, PI/watchdog và quyền
command trước chuyển động. Motor driver phải tự timeout khi Pi/process chết;
SSH keepalive và gate không thay watchdog motor hoặc physical stop.

## 3. Chuẩn bị laptop

Trên laptop đang có checkout `~/ninorobot`:

```bash
cp ~/ninorobot/src/nino_pi/config/laptop_control.example.json ~/nino_laptop_control.json
nano ~/nino_laptop_control.json
```

Điền:

- `host`: IP hiện tại của Pi (ví dụ `192.168.0.107`); `user`: `d`; port SSH.
- `ros_domain_id`: **domain của driver thật**, thay `null` bằng số đã kiểm
  tra ở terminal/service khởi chạy driver. Không lấy domain 80 của simulator
  hoặc tự đổi sang 88 khi driver đang dùng số khác.
- `robot_setup`: overlay vừa build trên Pi.
- `driver_setup`: đường dẫn setup driver trên Pi nếu cần; chưa có thì `null`.
- `control_params`, `navigation_params`: các file thật trên Pi, chỉnh
  footprint/frame/topic/limits theo phần cứng. Không sửa PI/ramp qua helper.

Helper từ chối config ví dụ còn domain `null`.

Nếu cả `--dry-run`, `check` và `teleop` báo `ros_domain_id`, chúng đang dừng
ở bước đọc cấu hình trên laptop, trước khi kết nối SSH. File mặc định là
`~/nino_laptop_control.json`; nếu đặt `NINO_LAPTOP_CONFIG` thì helper đọc
file được biến đó chỉ định. Không copy lại example đè lên cấu hình đã sửa.

Trong **chính terminal trên Pi dùng để khởi chạy driver thật**, kiểm tra:

```bash
printf 'ROS_DOMAIN_ID=%s\n' "${ROS_DOMAIN_ID:-<chưa đặt trong terminal này>}"
```

Nếu có số, đối chiếu lệnh/launch driver có ghi đè domain hay không, rồi điền
domain thực vào JSON dưới dạng số nguyên, không có dấu nháy. Nếu chưa đặt
hoặc driver chạy bằng service, cần kiểm tra lệnh khởi chạy/service; môi
trường của một SSH shell mới chưa xác nhận domain của process đang chạy.
Không chọn số domain mô phỏng chỉ để bỏ qua lỗi.

Sau khi điền domain đã xác nhận, kiểm tra script mà chưa kết nối:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh --dry-run teleop
```

Kiểm kê qua SSH, chỉ đọc:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh check
```

Không cần đặt ROS domain trên laptop cho helper SSH, vì node điều khiển chạy
trên Pi và helper export domain đã khai báo tại đó. Helper giữ nguyên discovery
settings; nó không thay cấu hình mạng của driver đang chạy.

## 4. Keyboard từ laptop, đồng thời ghi dữ liệu

**Laptop terminal A:** chạy command stack trên Pi; để terminal này mở:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh teleop
```

Stack khởi động disabled. Helper từ chối nếu đã thấy command stack; khi mở
mapping/navigation còn kiểm tra localization đang có để tránh trùng authority.
Teleop riêng có thể dùng localization đang chạy. Helper không kill node nào.
Kiểm tra này là quan sát tại thời điểm launch,
không phải khóa phân tán chống mọi race/duplicate publisher. Audit `/cmd_vel`
và command stages vẫn cần kiểm tra quyền sở hữu thực.

**Pi/SSH terminal B:** chuẩn bị collector theo `REAL_DATA_COLLECTION.md`, sửa
topic và session theo driver, rồi chạy:

```bash
source /opt/ros/jazzy/setup.bash
source ~/nino_pi_ws/install/setup.bash
# Cùng ROS_DOMAIN_ID với driver và laptop_control.json.
# Source driver workspace nếu cần custom message types.
/usr/bin/python3 -m nino_pi.collect_real_data \
  --config ~/nino_collection_config/topics.json \
  --session ~/nino_collection_config/session.json \
  --qos ~/nino_collection_config/qos.yaml \
  --output "$HOME/nino_real_data/manual_$(date +%Y%m%d_%H%M%S)"
```

Collector chỉ ghi dữ liệu, không bật gate. Mỗi terminal phải có domain đúng;
helper không đổi môi trường của terminal collector. Ghi `manual` trong
`controller.control_source_manual_or_navigation` của session. Mọi topic mới
trong file `real_collection.json` là optional: thêm vào bản `topics.json` đã
copy trước đây nếu cần, không ghi đè mapping riêng của driver.

**Laptop terminal C:** khi người vận hành đã kiểm tra robot và cho phép chạy:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh manual
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh enable
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh keyboard
```

- Giữ `i`: tiến; `,`: lùi; `j/l`: quay; `u/o/m/.`: cung rẽ.
- `k` hoặc space: zero command; Ctrl+C thoát keyboard.
- Keyboard có key expiry 0.6 s; gate command timeout 0.3 s. Mất SSH/phím
  sẽ được xử lý qua các watchdog hiện có; phải kiểm tra dừng thật trước ứng dụng.
- Không chạy joystick và keyboard cùng `/cmd_vel_teleop`; không dùng teleop
  khác publish trực tiếp `/cmd_vel`.

Kết thúc driving **trước** khi kết thúc recording để có đoạn stopping/settling:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh disable
```

Để collector ghi thêm đoạn đứng yên cần thiết rồi mới Ctrl+C/đợi hết budget.
Ngắt collector không dừng robot. Ctrl+C phiên launch khi không dùng nữa.

Lệnh dừng phần mềm latched (terminal laptop khác):

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh stop
```

Lệnh này cần mạng/ROS hoạt động, không thay nút dừng vật lý. Sau đó gate phải
disable rồi reset stop bằng service hiện có, vẫn chưa tự enable:

```bash
# Trên Pi, cùng domain/overlay:
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: false}'
ros2 service call /nino_command_gate/reset_stop std_srvs/srv/Trigger '{}'
```

## 5. Mapping và navigation từ laptop

### Chưa có occupancy map thật

Dừng teleop launch ở terminal A bằng Ctrl+C; giữ driver và collector nếu còn
phù hợp budget/session. Sau đó từ laptop:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh mapping
```

Mapping đã chứa command stack; không mở teleop launch nữa. Dùng terminal C
`manual` → `enable` → `keyboard` như trên. Khi map đủ, trên Pi:

```bash
mkdir -p ~/maps
ros2 run nav2_map_server map_saver_cli -f ~/maps/factory
ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: false}'
```

Lưu cả YAML và image map. Dừng mapping/SLAM trước AMCL/navigation. Không dùng
world SDF hoặc map simulator thay occupancy map được đo tại nơi robot chạy.

### Đã có map thật và localization/TF đúng

Dừng launch mapping/teleop cũ. Từ laptop terminal A:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh navigation --map '~/maps/factory.yaml'
```

Map path ở **Pi**; giữ dấu nháy để `~` không bị laptop expand. Helper không
tự enable hoặc gửi goal. Có thể dùng keyboard trong navigation launch bằng
chọn `manual`; không mở thêm teleop launch.

### RViz trên laptop (tùy chọn, cần ROS networking)

Đây là cách xem map và gửi Nav2 Goal. Laptop cần ROS Jazzy/Nav2/RViz. Pi và
laptop cần cùng domain, discovery range hỗ trợ mạng và Wi-Fi không client
isolation. Nếu driver đã dùng `LOCALHOST`, muốn xem RViz từ laptop cần chủ
động cấu hình/restart các tiến trình liên quan với discovery phù hợp. Không
đổi môi trường một terminal rồi mặc định các node đã chạy cũng đổi theo.

Ví dụ dưới dùng **88 chỉ để minh họa**; thay bằng domain thật trên cả hai máy.
Chạy khi cấu hình driver/network đã thống nhất, trên laptop:

```bash
# Cài nếu laptop đã có ROS Jazzy nhưng chưa có RViz/Nav2 bringup:
sudo apt-get install -y ros-jazzy-rviz2 ros-jazzy-nav2-bringup
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=88
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
unset ROS_LOCALHOST_ONLY
ros2 node list
ros2 launch nav2_bringup rviz_launch.py use_sim_time:=false
```

Nếu chưa thấy node/sensor Pi, xử lý kết nối/domain trước. Không tắt firewall
toàn bộ theo hướng dẫn phỏng đoán. Trong RViz chọn map/TF/laser, đặt **2D Pose
Estimate**, kiểm tra alignment/footprint/localization. Khi cho phép navigation:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh navigation-mode
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh enable
```

Gửi **Nav2 Goal** từ RViz. Bắt đầu collector phiên navigation trước khi enable,
khai báo goal/route trong session; `/plan`, `/amcl_pose`, `/map` và collision
state đã được thêm optional vào config thu mới. `/goal_pose` không được coi
là log đầy đủ mọi action goal; lưu goal/điều kiện thực trong metadata.

Chuyển manual:

```bash
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh manual
bash ~/ninorobot/src/nino_pi/scripts/laptop_control.sh keyboard
```

Mode switch xóa lệnh cũ theo gate hiện có. Muốn hủy nhiệm vụ Nav2, dùng Cancel
trong RViz; chuyển mode không tự hủy action. `disable` dừng cấp lệnh qua gate,
không bảo đảm physical stop nếu có publisher khác bypass pipeline.

## 6. Giới hạn kiểm chứng

Test offline kiểm tra config, shell/SSH quoting, map path trên Pi, không tự
enable, bảo toàn timeout/limits của gate và forwarding profile mapping. Test
không mở SSH sang robot, không chạy motor hoặc Nav2 trên hardware. Không có
bằng chứng điều khiển thực chỉ từ các test này. Collector/driver audit còn là
bước đầu để xác nhận phần nào hiện có và phần nào thiếu.
