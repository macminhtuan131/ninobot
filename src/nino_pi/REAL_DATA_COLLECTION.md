# Thu thập dữ liệu robot thật Nino — Ubuntu 24.04 / ROS 2 Jazzy / Pi 5

**Điều khiển từ laptop khi thu:** xem
[LAPTOP_CONTROL_AND_COLLECTION.md](LAPTOP_CONTROL_AND_COLLECTION.md) cho helper
SSH keyboard, mapping/Nav2/RViz, build trên Pi và quy trình vừa lái vừa ghi.
Collector vẫn chỉ đọc; điều khiển được khởi động/bật riêng bởi người vận hành.

## 1. Bộ này làm gì?

Thu thập **chỉ đọc** từ driver đang có. Không khởi động driver, Nav2, PI,
governor hoặc teleop; không gửi lệnh motor, không sửa parameter hay gain.
Không cần màn hình trên Ubuntu Server. Chạy qua SSH được.

- `hardware_audit.py`: kiểm kê node, package, publisher/subscriber, TF,
  parameter cho phép đọc, timestamp/rate và dấu hiệu undervoltage.
- `state_monitor.py`: xem IMU, encoder, vận tốc ước lượng, torque command và
  dữ liệu motor do bạn khai báo; có thể ghi JSONL từng message.
- **`collect_real_data.py`**: ghi ROS bag nguyên bản bằng tiến trình rosbag2
  riêng; đồng thời chạy audit ở tiến trình khác và chụp power định kỳ.
  Chuyển đổi message trong audit không nằm trên callback ghi bag.
- Config và biểu mẫu ở `config/real_*`; mapping motor ví dụ ở
  `config/motor_telemetry.example.json`.

Đây là công cụ lấy bằng chứng, **chưa xác nhận robot ổn định hoặc governor
có ích**. Chưa được thử trên Pi/driver của bạn. Test tích hợp dùng sensor
giả trong ROS domain localhost riêng, không chạy Gazebo hoặc robot thật.

## 2. Dữ liệu nào cần? Lấy bằng cách nào?

### A. Cần ngay, trước khi thử chuyển động

| Dữ liệu | Cách thu và bằng chứng cần lưu | Có tự lấy được không? |
|---|---|---|
| Model motor/gearbox, firmware, controller mode, interface CAN/USB/serial và ID | Nhãn thiết bị + driver/firmware version, commit, launch command | Package/node là gợi ý; thông tin phần cứng phải điền |
| Driver motor/encoder/IMU/LiDAR nào đã cài và thực sự phát dữ liệu | `hardware_audit`: package, executable, node, endpoint, số mẫu nhận | Có, trong domain/overlay hiện tại; không chứng minh kết nối motor chỉ từ tên node |
| Luồng lệnh và quyền điều khiển | Topic/type, publisher/subscriber từng đoạn, final command → backend | Graph tự thu; cần đọc backend để xác nhận nó thực thi/forward gì |
| Vòng PI nằm ở đâu | Firmware hay Pi; gain P/I và đơn vị, rate, integrator/clamp/reset, motor mode | Chỉ các parameter allowlist đọc được; phần còn lại từ code/firmware, không suy từ topic |
| Giới hạn motor và watchdog | Torque/current/speed, acceleration/deceleration, saturation/fault, timeout, cơ chế dừng | Lưu cấu hình thật và kênh feedback; collector không tự thử watchdog |
| Timestamp, clock, rate, QoS | Source stamp, frame, bag receipt time, audit monotonic/ROS receipt, gap/duplicate/backwards, endpoint QoS | Có phần quan sát; clock origin/filter của driver phải xác nhận |
| IMU ở trạng thái đứng yên | Acceleration XYZ, gyro XYZ, orientation/covariance, frame; bias/noise, gravity, filter/range/rate | Thu raw được; chiều trục/units/mounting cần đối chiếu thực tế |
| Encoder đứng yên | Tên joint, position/velocity/effort nếu có, raw tick nếu driver cung cấp | ROS ghi được; số count/rev, gear ratio, sign và cách tính velocity cần khai báo |
| LiDAR và TF | Full ranges, range/angle limits, scan/time_increment, IMU/LiDAR↔base và odom↔base | Có; TF là cấu hình khai báo, không chứng minh lắp đúng |
| Nguồn điện | Pi rail và motor rail, V/A danh định, dây, topology; điện áp/dòng idle và khi tải; nhiệt độ | ROS battery/motor nếu có + hwmon/kernel/get_throttled nếu truy cập được; cần đồng hồ/logger ngoài khi thiếu |
| Undervoltage đã sửa chưa | Alarm hiện tại, lịch sử từ boot, thời điểm và bằng chứng sau sửa | Không có log **không đồng nghĩa** nguồn tốt; thiếu quyền/tool ghi unavailable |
| Phiên thử | Robot ID, ngày, payload, mặt sàn, pin, cấu hình/firmware, operator, tình trạng bất thường | Điền `real_session.template.json`, giữ unknown = `null` |

### B. Cần để hiệu chỉnh robot–PI và kiểm chứng quyền điều khiển tốc độ

Chỉ thực hiện sau kiểm kê, khi người vận hành đã xác nhận phần cứng và đường
lệnh. Collector vẫn chỉ quan sát; nó không tự phát các bài thử sau.

| Dữ liệu | Cách thu | Điều không được suy diễn |
|---|---|---|
| Kích thước/mass thật | Cân robot + payload; đo wheel radius trái/phải có tải/không tải, khoảng tâm tiếp xúc hai bánh, footprint, clearance và chiều cao | Không dùng CAD như đo thật. Tham chiếu mô phỏng: wheel radius 0.0625 m, effective separation khoảng 0.3427 m; chưa hiệu chuẩn phần cứng |
| Caster | Radius, swivel axis position, trail, bracket clearance, hướng đầu phiên, quay/lăn tự do, phân bố tải; ảnh/video và phương pháp đo | Không mặc định caster nào chạm trước hoặc caster angle có sensor thật |
| Lệnh → wheel target → wheel actual → body response | Ghi từng tầng command, target sau limit, encoder thật, PI output, current/torque, fault/saturation, body reference độc lập trên cùng timeline | `/cmd_vel` không phải wheel target; odom encoder không phải tốc độ thân độc lập |
| Độ trễ và ramp thực thi | Timestamp theo tầng, command change, target change, encoder/body change; đồng bộ clock và báo sai số phát hiện | Age so với clock khác nhau không tự bằng network delay. Không cộng trùng filtering/actuator lag |
| Đáp ứng PI trái/phải | Tracking error, overshoot, settle, saturation, windup/release, torque command/feedback; điều kiện pin/payload | Không tự tuning gain trước khi có dữ liệu và đơn vị |
| Torque/current thật | Torque command; driver-reported torque/estimate; motor current **loại nào** (Iq, phase hay DC bus), V, °C, speed/fault/limits | `JointState.effort` trống là unavailable. Command không là measured torque; tên “applied” cũng chưa phải cảm biến |
| Hiệu chuẩn torque estimate | Nếu dùng Kt×Iq: Kt, convention/units, gear ratio/efficiency, sign, nhiệt độ và đối chứng nếu có | Torque estimate phải gắn nhãn estimate; không biến thành ground truth lực tiếp xúc |
| Body pose/speed độc lập | Video có mốc khoảng cách/thời gian đã hiệu chuẩn, tracker ngoài hoặc localization độc lập có kiểm tra sai số | IMU integration trôi; encoder odom không đủ đo slip tuyệt đối. LiDAR localization còn phụ thuộc hình học/môi trường |
| Slip | Đồng bộ encoder tốc độ tiếp tuyến với body reference độc lập, radius thật và uncertainty; giữ waveform/spike | Wheel tracking error là proxy tracking, không tự bằng slip |
| Axis/sign calibration | Đối chiếu lắp IMU/TF và phép dịch/chuyển hướng đã biết; encoder positive/negative từ driver và quan sát | Không xác nhận dấu chỉ từ robot đứng yên; không tự thay TF/sign bằng code collector |

Đo COM/inertia/phân bố tải chính xác chỉ cần khi sai khác động lực học/contact
còn quyết định kết luận. Có thể bắt đầu từ mass/payload, geometry và kiểm tra
lăn/cản caster có căn cứ; không cần đo mọi tham số mới được kiểm kê ROS.

### C. Cần cho nghiên cứu contact/governor sau đó

| Dữ liệu | Cách thu |
|---|---|
| Floor/obstacle thật | Vật liệu, độ sạch/ướt/dốc; loại rigid ridge/cáp mềm/groove/pothole, cao/sâu, rộng/dài, profile mép, góc, khoảng cách, cách cố định và biến dạng |
| Điều kiện approach | Pose/speed, steering, caster state nhìn được, payload và pin; nhóm paired trial, thứ tự và lần lặp |
| Chuỗi contact | Video đồng bộ từ góc thấy từng wheel/caster, first/subsequent/exit contact và recovery; contact identity/impulse chỉ có nếu thêm thiết bị đo thích hợp |
| Chất lượng crossing | Raw IMU gyro/accel có mounting/filter rõ; post-contact và toàn tuyến, first impact riêng; thời gian, tracking, arrival, stall/failure, stopping/settling |
| Intervention thực thi | Thời điểm detector → giảm command → giảm wheel/body speed so với contact kế; log state/target/ramp/hold/recovery của governor nếu bật ở giai đoạn được cho phép |
| Repeatability/generalization | Lặp cùng điều kiện, nhiều geometry/góc/payload; tách development/test theo episode và scenario; không tune trên test |
| Đồng bộ ngoài ROS | Video/tracker/đồng hồ điện có timestamp hoặc mốc đồng bộ và uncertainty; không gán thời điểm contact “chính xác” từ video nếu chưa đồng bộ |

Không cần mua cảm biến lực hoặc encoder caster để chạy bộ kiểm kê này. Nếu
không có chúng, ghi rõ contact force/caster angle không đo trực tiếp; dùng
video và đầu ra cơ thể cho câu hỏi phù hợp. Dây mềm/quấn bánh là bài toán
khác cylinder cứng của mô phỏng. LiDAR ngang không được coi là preview chắc
chắn của cáp thấp/hõm sàn. Predictor/PPO/Optuna và ngưỡng ứng dụng chưa được
bộ thu thập này kích hoạt/chấp nhận.

## 3. Cài trên Pi qua SSH (không cần desktop)

Chạy từ laptop để vào Pi; thay IP bằng IP hiện tại của Pi:

```bash
ssh d@192.168.0.127
```

Trên Pi, dùng checkout riêng để tránh đụng workspace/driver đang chạy:

```bash
sudo apt-get install -y git
git clone --depth 1 --filter=blob:none --sparse --single-branch --branch Collecting-datas \
  https://github.com/macminhtuan131/Ninobot_controlled_with_torque.git \
  ~/nino_data_tools
git -C ~/nino_data_tools sparse-checkout set src/nino_pi
bash ~/nino_data_tools/src/nino_pi/scripts/install_collection_dependencies.sh
source /opt/ros/jazzy/setup.bash
# Source thêm install/setup.bash của workspace DRIVER THẬT nếu có.
export PYTHONPATH="$HOME/nino_data_tools/src/nino_pi${PYTHONPATH:+:$PYTHONPATH}"
```

Không cần build để chạy ba module Python. Không activate virtualenv RL
trên Pi. Dùng `/usr/bin/python3` cùng ROS Jazzy và interface packages thật.
Nếu đã có clone, kiểm tra branch/worktree trước khi pull; đừng ghi đè file
driver hiện tại. Installer không cài motor/IMU/LiDAR backend của bạn.

**ROS domain:** mở cùng môi trường/domain/RMW với driver. Không tự đặt domain
80 của Gazebo hoặc thay discovery range khi robot đang dùng domain khác.
Collector không đổi các biến đó. Chưa biết domain thì xem terminal/service
khởi chạy driver; topic list trống không chứng minh driver chưa cài.

## 4. Bắt đầu bằng audit đứng yên

```bash
/usr/bin/python3 -m nino_pi.hardware_audit \
  --duration 30 --output "$HOME/nino_audits/inventory_$(date +%Y%m%d_%H%M%S)"

ros2 topic list -t
# Thay tên bằng topic thực sau kiểm kê:
ros2 topic info /cmd_vel --verbose
ros2 topic info /joint_states --verbose
```

Đọc `REPORT.md`, `graph.mmd`, `parameters.json`, `power.json` và
`report.json`. Inventory không phải lệnh cho phép chạy. Collector không chặn
các publisher khác; giữ robot ở trạng thái được người vận hành kiểm soát.
Nếu nguồn tiếp tục báo undervoltage, xử lý/đo nguồn trước bài thử có tải.

## 5. Chỉnh config theo driver thật

```bash
mkdir -p ~/nino_collection_config
cp ~/nino_data_tools/src/nino_pi/config/real_collection.json ~/nino_collection_config/topics.json
cp ~/nino_data_tools/src/nino_pi/config/real_collection_qos.yaml ~/nino_collection_config/qos.yaml
cp ~/nino_data_tools/src/nino_pi/config/real_session.template.json ~/nino_collection_config/session.json
nano ~/nino_collection_config/topics.json
nano ~/nino_collection_config/session.json
```

- Đổi topic name thực. `required:true` là cần cho dataset ban đầu; thiếu thì
  session báo incomplete, không bị biến thành giá trị 0. Nếu backend chưa
  có `/joint_states`, thêm topic encoder thật và giữ yêu cầu encoder; không
  bỏ required chỉ để có báo cáo “đẹp”.
- Chỉnh tên/QoS tương ứng trong `qos.yaml` từ endpoint thực; `/tf_static`
  cần nhận dữ liệu latched. Thông báo QoS không tương thích phải giữ lại.
- Thêm **topic thông điệp motor đầy đủ**: actual wheel target, encoder/tick,
  PI output/limits/integrator/saturation, current/Iq, reported torque, bus
  voltage, temperature, faults, watchdog. Không đoán tên/field/units.
- Topic firmware không xuất thì cần bổ sung telemetry ở driver/firmware;
  Python observer không thể tạo phép đo mà phần cứng không cung cấp.
- Đặt `session_id` riêng. Các ô chưa đo giữ `null`; các giá trị nhập là khai
  báo operator, không phải công cụ đã kiểm chứng. Lưu model/firmware/commit
  và file cấu hình driver đã loại credentials cùng phiên nếu cần tái lập.

Live monitor với mapping motor (tùy chọn):

```bash
cp ~/nino_data_tools/src/nino_pi/config/motor_telemetry.example.json ~/nino_collection_config/signals.json
nano ~/nino_collection_config/signals.json
# Chỉ dùng mapping sau khi sửa topic/type/field/unit và phân loại đúng:
/usr/bin/python3 -m nino_pi.state_monitor --duration 30 \
  --signals ~/nino_collection_config/signals.json
```

`field` hỗ trợ `data`, `data[0]`, `motors[0].current`… không dùng `eval`.
`kind`: `command`, `estimate`, `measured`, `reported_unverified`. Mặc định
unverified; nhãn `measured` do bạn cung cấp không được tự động xác minh.
Không cần mapping để bag ghi nguyên message custom. Cần source workspace
chứa message type custom. Với monitor, đổi các `--imu-topic`,
`--joints-topic`, `--command-topic`… nếu driver không dùng mặc định.

## 6. Kiểm tra config rồi ghi một phiên

```bash
/usr/bin/python3 -m nino_pi.collect_real_data \
  --config ~/nino_collection_config/topics.json \
  --session ~/nino_collection_config/session.json \
  --qos ~/nino_collection_config/qos.yaml \
  --output ~/nino_real_data/validation_only --check
```

`--check` không mở ROS node, không tạo thư mục dữ liệu. Nó chưa kiểm tra
driver đang phát hay QoS có kết nối được.

Ghi đứng yên trước; chỉ ghi bài thử có chuyển động khi người vận hành chủ
động khởi chạy bằng stack thật đã kiểm tra:

```bash
/usr/bin/python3 -m nino_pi.collect_real_data \
  --config ~/nino_collection_config/topics.json \
  --session ~/nino_collection_config/session.json \
  --qos ~/nino_collection_config/qos.yaml \
  --output "$HOME/nino_real_data/session_$(date +%Y%m%d_%H%M%S)"
```

Config mặc định 60 giây wall time, tối đa 300 giây/phiên. Giới hạn size
được kiểm tra định kỳ; buffer/shutdown có thể vượt nhẹ mốc, nên có disk
reserve. Ctrl+C đóng các tiến trình thu của phiên, giữ dữ liệu và đánh dấu
partial. Nó **không gửi lệnh dừng robot**. Không retry hoặc ghi đè phiên.
Nếu muốn lưu mapping cùng phiên, thêm `--signals .../signals.json`; mọi
topic trong mapping phải có trong `topics.json`, nếu thiếu sẽ từ chối.

## 7. Đọc output và gửi về laptop

```text
session_.../
  manifest.json             trạng thái, lỗi, counts, missing, môi trường/command
  session.json              điều kiện, số đo thủ công và unknown
  collection_config.json    topic/budget thực dùng
  qos.yaml                  QoS thực dùng
  motor_signals.json        nếu khai báo --signals
  bag/metadata.yaml         chỉ có khi rosbag đóng metadata thành công
  bag/*.db3                 nguyên message CDR và recorder timestamp
  bag.log, audit.log        giữ lỗi, warning và lost-message warning nếu có
  audit/REPORT.md           driver/sensor đang nhận, phần thiếu, nguồn
  audit/graph.mmd           sơ đồ command/sensor theo endpoint quan sát
  audit/parameters.json     allowlist đọc được, không sửa tham số
  audit/samples.jsonl       mẫu rút gọn + monotonic/ROS receipt và source header
  power_timeline.json       chụp nguồn định kỳ best effort (không phải ADC nhanh)
  sha256.json               hash file gốc và source collectors
```

```bash
ros2 bag info ~/nino_real_data/session_YYYYMMDD_HHMMSS/bag
cat ~/nino_real_data/session_YYYYMMDD_HHMMSS/manifest.json
```

**Không dùng `ros2 bag play` khi đang nối motor**: playback có thể phát lại
command. Offline inspection/export không cần playback vào mạng robot.

Từ laptop:

```bash
scp -r d@192.168.0.127:~/nino_real_data/session_YYYYMMDD_HHMMSS ./
```

Gửi toàn thư mục, gồm failures/spike/raw logs và mẫu session; không chỉ gửi
ảnh màn hình hay mean. Xem lại nội dung trước chia sẻ: raw diagnostic/custom
messages có thể chứa chuỗi riêng của driver. Không commit bag vào Git.

## 8. Diễn giải đúng tính đầy đủ

- `captured_not_calibrated`: các tiến trình kết thúc đúng, bag có metadata/
  SQLite đọc được, required topics có mẫu, audit kết thúc; **không phải**
  sensor đúng, sample coverage ≥98%, timing chính xác hay robot an toàn.
- `incomplete` / exit 1: thiếu required, storage/process/closure lỗi, gián
  đoạn hoặc chạm budget. Giữ mọi file; không loại failure khỏi dataset.
- Count bag không bằng count sensor sản xuất. Không tự tính loss/coverage
  bằng rate danh nghĩa; cần driver sequence/counter hoặc reference capture.
  Audit và bag là hai subscriber, counts có thể khác vì startup/QoS/load.
- Bag lưu receipt timestamp + message gốc. Source header vẫn nguyên trong
  CDR; Twist không có source stamp. Audit có monotonic timestamp riêng,
  không có monotonic trên từng bag message. Trên nhiều host cần ghi clock
  origin/sync/offset; không gọi age là latency đã hiệu chuẩn.
- Không lọc outlier, đổi timestamp, điền torque trống hoặc sửa scoring.
  Missing motor current/limits/body reference vẫn là thiếu dữ liệu, kể cả
  session thu IMU thành công. Unknown trong form không biến thành đo thật.
- Ghi telemetry có overhead. Xác nhận rate/gap/CPU/power ở Pi trước dùng
  dữ liệu đánh giá điều khiển. Không đảm bảo loss-free hoặc realtime.

## 9. Thứ tự gửi dữ liệu có ích nhất

1. **Ngay:** audit đứng yên + một bag đứng yên + session khai báo; giải quyết
   nguồn và tìm đúng driver/command/feedback trước.
2. **Khi phần cứng đủ điều kiện:** số đo geometry/mass/caster, cấu hình PI/
   limits và một dataset đáp ứng lệnh trên sàn sạch có body reference độc
   lập. Chưa cần crossing hay governor để đo được bước này.
3. **Sau đó:** crossing một vật cản đã đo, video đồng bộ và repeats có kiểm
   soát. Dùng thông tin này để hiệu chỉnh sim và kiểm tra H2 trước predictor.

Chưa có driver/topic thực nên chưa thể cung cấp adapter CAN/CyberGear hoặc
torque sensor giả định cho robot của bạn. Bộ này cho biết dữ liệu nào có,
trống hoặc cần bổ sung thay vì che phần thiếu đó.
