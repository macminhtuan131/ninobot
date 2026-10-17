# Thu thập dữ liệu Pi 5 chỉ đọc — 17/10/2026

## Mục đích

Kiểm kê ROS/hardware trước thử chuyển động: phần mềm driver có trong overlay,
node/topic đang hiện diện, dữ liệu thực sự nhận được, luồng publisher–topic–
subscriber, timestamp, cấu hình TF, tham số PI đọc được và cảnh báo nguồn.
Không khởi động driver/Nav2/teleop, không enable controller, không gửi lệnh
vận tốc/effort, không đổi tham số hoặc reset alarm nguồn.

Source: `src/nino_pi/nino_pi/hardware_audit.py`. Chạy standalone bằng Python
ROS của hệ thống; không cần build workspace, Gazebo, PyTorch hoặc venv RL.
Nếu build package mới, có entry point `ros2 run nino_pi hardware_audit`.

## 1. Copy từ laptop tới Pi

Ví dụ dùng tài khoản/IP bạn đã cung cấp; đổi IP nếu Pi đã nhận địa chỉ khác.
Chạy **trên laptop**, không phải trên Pi:

```bash
scp /home/tuanmac/ninorobot/src/nino_pi/nino_pi/hardware_audit.py \
  d@192.168.0.127:~/hardware_audit.py
ssh d@192.168.0.127
```

Không cần chép workspace laptop `build/` hoặc `install/` sang ARM64.
Bundle độc lập cũng được lưu tại
`artifacts/nino_pi_readonly_audit_2026-10-17.zip`; bên trong có script và tài
liệu này. Có thể giải nén bằng `python3 -m zipfile -e FILE.zip DIRECTORY`.

## 2. Chạy trên Pi

Giữ robot đứng yên và không khởi động nguồn lệnh chuyển động. Công cụ không
tự dừng các publisher đang có: nếu có lệnh khác zero, nó chỉ ghi cảnh báo.

```bash
source /opt/ros/jazzy/setup.bash

# Source overlay hardware đang dùng, nếu có. Ví dụ cho bundle nino_pi:
if [ -f "$HOME/nino_pi_ws/install/setup.bash" ]; then
  source "$HOME/nino_pi_ws/install/setup.bash"
fi

# Giữ ROS_DOMAIN_ID và discovery giống terminal driver hiện có.
# Không tự đổi sang domain simulation 80 hoặc domain mới chỉ cho audit.
printenv ROS_DOMAIN_ID ROS_AUTOMATIC_DISCOVERY_RANGE RMW_IMPLEMENTATION

/usr/bin/python3 "$HOME/hardware_audit.py" \
  --duration 60 \
  --output "$HOME/nino_audits/$(date +%Y%m%d_%H%M%S)"
```

Nếu chưa kết nối robot hoặc chưa chạy driver, vẫn dùng được để kiểm kê
package. Kết quả khi đó sẽ ghi **chưa nhận dữ liệu**, không chứng minh driver
chưa cài hay bị hỏng. Chỉ source những workspace đã tồn tại; chưa biết launch
hardware nào đúng thì không tự chọn launch simulation để thay thế.

Mỗi lần dùng một output directory mới; script từ chối ghi đè. `Ctrl+C` lưu
kết quả một phần với trạng thái partial. Sampling dùng wall monotonic clock,
5–300 giây; lấy ROS graph mỗi 2 giây, giới hạn 128 subscriptions và 64 node
đọc tham số. Raw log tối đa 200.000 mẫu, báo rõ số mẫu bị lược nếu chạm trần.
Laser chỉ lưu summary mỗi scan, không lưu toàn bộ ranges.

Nếu feedback là Float64MultiArray trên topic riêng:

```bash
/usr/bin/python3 "$HOME/hardware_audit.py" --duration 60 \
  --topic /TEN_TOPIC_FEEDBACK_THUC_TE \
  --output "$HOME/nino_audits/custom_$(date +%Y%m%d_%H%M%S)"
```

Mặc định có thêm `/nino_drive/diagnostics` và
`/wheel_effort_controller/commands` nếu các topic này tồn tại. Array được
lưu nguyên giá trị, không tự đoán schema/unit. Topic kiểu custom khác vẫn
có endpoint trong graph nhưng không tự decode dữ liệu.

## 3. File đầu ra và cách đọc

| File | Nội dung |
|---|---|
| `REPORT.md` | Tóm tắt driver/node nhận được dữ liệu, cảnh báo, việc còn thiếu |
| `report.json` | Rate, age, duplicate/backward/zero stamps, frame IDs, sample count theo publisher GID nếu rclpy hỗ trợ, dữ liệu invalid |
| `samples.jsonl` | IMU, joint, odom, command, TF và diagnostics rút gọn; header/receipt timestamps; GID hoặc null nếu rclpy không cung cấp |
| `graph.json` | Các snapshot publisher/subscriber, message type và QoS |
| `graph.mmd` | Sơ đồ Mermaid publisher → topic → subscriber; mở bằng Markdown/Mermaid viewer trên laptop |
| `tf.json` | Parent/child, transform cuối quan sát được theo publisher, phát hiện duplicate authority |
| `parameters.json` | Chỉ các tham số thuộc allowlist đã khai báo và đọc được; không dump tham số tùy ý |
| `host.json` | Kiến trúc/kernel/ROS domain, package/executable hints, process-name hints cục bộ |
| `power.json` | hwmon, hai snapshot get_throttled nếu có, kernel power warnings đọc được |
| `status.json`, `sha256.json` | Trạng thái thu thập, lỗi và hash file/source |

Mở báo cáo trên Pi:

```bash
ls -1 "$HOME/nino_audits"
cat "$HOME/nino_audits/TEN_LAN_CHAY/REPORT.md"
tar -C "$HOME/nino_audits" -czf "$HOME/nino_audit_result.tar.gz" TEN_LAN_CHAY
```

Từ laptop lấy về:

```bash
scp d@192.168.0.127:~/nino_audit_result.tar.gz .
```

## 4. Những gì có thể và chưa thể kết luận

1. **Driver:** package tồn tại ≠ node chạy ≠ có mẫu ≠ sensor vật lý đã được
   xác minh. Graph chỉ có phạm vi domain/discovery đang dùng. Node có thể ở
   máy khác; không suy ra nơi chạy từ tên node. Process hints không chứng minh
   ánh xạ executable ↔ ROS node, nhất là composable nodes hoặc Python.
2. **Luồng lệnh:** sơ đồ là kết nối khai báo. Một node subscribe rồi publish
   không chứng minh nó đang forward, giới hạn hay thực thi lệnh. Nhiều
   publisher là nguy cơ tranh quyền, chưa tự chứng minh có xung đột thực tế.
   Samples có publisher GID để đối chiếu khi rclpy cung cấp. Một số build
   Jazzy chỉ có timestamp trong MessageInfo; khi đó GID từng mẫu ghi null,
   không đoán publisher từ graph và không xác nhận duplicate TF authority
   từ sample. Endpoint GID vẫn được lưu trong graph. Twist không có header thì
   không biết tuổi lệnh tại nguồn.
3. **Timestamp/rate:** receipt rate dùng monotonic clock; header rate và
   age báo riêng. Age là ROS time collector trừ header; clock không đồng bộ
   hoặc simulation time có thể làm age sai. Ngưỡng 0,5 s và future 50 ms chỉ
   là cảnh báo chẩn đoán, không phải gate an toàn/đúng sensor. Chưa có yêu
   cầu rate từng driver thì không tự chấm đạt. Header tăng không chứng minh
   nội dung không bị replay hoặc sensor không bị đứng.
4. **Trục:** ghi XYZ IMU, quaternion/covariance và TF. Không tự chứng minh
   IMU lắp đúng trục, encoder trái/phải đúng dấu, hoặc joint đơn vị thực đúng
   từ lúc robot đứng yên. Cần đối chiếu mounting/driver/firmware. Không tích
   phân IMU rồi gọi đó là vận tốc thật hoặc slip tuyệt đối.
5. **PI:** list/get parameter chỉ đọc các tên allowlist. Thấy velocity_kp/ki
   là bằng chứng cấu hình, chưa chứng minh PI đang thực thi trên Pi hoặc MCU.
   Không có tham số đó cũng không chứng minh không có PI: firmware có thể
   đóng vòng hoặc driver dùng tên khác. Chốt vị trí cần xem code/firmware
   và mapping motor interface. Không tự gán vị trí PI.
6. **Nguồn:** `under_voltage_now` khác `under_voltage_since_boot`. Log chỉ
   lấy 1.000 dòng kernel cuối trong boot hiện tại; có thể thiếu lịch sử.
   Thiếu quyền/journal/vcgencmd được ghi unavailable, không chấm nguồn tốt.
   Không có cảnh báo trong cửa sổ đứng yên không chứng minh nguồn ổn khi
   motor chịu tải. Công cụ không chạy sudo, không cài package và không xóa bit.

ROS/rclpy tự có metadata DDS và `/parameter_events` của collector; không có
publisher command motor do công cụ tạo. Các service được gọi duy nhất là
ListParameters/GetParameters, không gọi SetParameters hoặc enable/reset.

## 5. Phạm vi kiểm tra trước bàn giao

- Unit tests dùng dữ liệu tổng hợp cho timestamp/rate, missing/invalid,
  scan +inf/NaN, bit undervoltage hiện tại/lịch sử, JSON, callback/GID và
  kiểm tra không tạo command publisher hoặc service ghi.
- Integration Jazzy chỉ dùng một publisher **IMU tổng hợp** và tham số mẫu
  trong domain localhost riêng; kiểm tra nhận mẫu, GID hoặc unavailable và đọc gain. Không
  chạy Gazebo, motor, driver thật hoặc batch H2.
- Chưa chạy trên Pi ARM64 hoặc phần cứng Nino. Báo cáo thực cần được thu
  trên Pi rồi đối chiếu; tests laptop không thay xác nhận đó.

Không thay đổi governor, PI, detector, scoring, tiêu chí đề xuất hoặc ngân
sách H2 16 attempts trong công việc này.
