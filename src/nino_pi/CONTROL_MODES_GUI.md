# GUI chuyển quyền điều khiển Nino — 03/11/2026

**Mới v3.1: lệnh thu trong To-do.** Chọn T07 → **Lệnh thu / Copy** (hoặc
double-click dòng). Chọn bước và copy lệnh cho đúng terminal. Bộ lệnh có
inventory, thu yên, diagnostic firmware RC hiện có, review/fetch và draft
các bước sau; GUI không tự thực thi. Xem
[hướng dẫn commands](../../docs/NINO_COLLECTION_COMMANDS_2026-11-03.md).
Mở thẳng bằng `bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh --commands diagnostic`.

**Mới: v3 — Tiến độ / kết quả / to-do.** Mở
`bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh --project` để xem hồ sơ local,
23 nhóm dữ liệu, 26 thông số và quality theo claim. Chi tiết ở phần v3 cuối
tài liệu và [đánh giá lại](../../docs/NINO_REPORT_REASSESSMENT_AND_GUI_2026-11-03.md).

## Bổ sung v2: chế độ thu dữ liệu và teleop

Tab **Thu dữ liệu / teleop** đã bổ sung quy trình thực tế bên cạnh tab quyền
điều khiển. Đã kiểm offline/demo, chưa được kiểm với ROS stack và robot thật.
Firmware authority wire contract vẫn là v1; không phát sinh một firmware
khác trong lần bổ sung GUI này. Gói v1 trước đó là snapshot lịch sử.

### TBS Mambo có những “chế độ” nào?

Theo [manual chính thức TBS Mambo](https://www.team-blacksheep.com/media/files/tbs-mambo-manual.pdf),
Mode 1–4 liên quan bố trí chức năng trên cần điều khiển; FM0–FM8 là các slot
profile có thể đặt tên/gán switch, trim và chuyển tiếp. Mixer, logical
switches và special functions cho phép người dùng cấu hình kênh. Các mục
này không tự định nghĩa chức năng chạy của Nino. Nguồn chính thức đã tra
ngày 03/11/2026: phần stick mode/mixer bypass và Flight modes qua chỉ mục
tìm kiếm; fetch toàn PDF bằng web tool bị giới hạn kích thước (~31 MB).

Ánh xạ **từ source Nino đã đọc**, chưa phải dump model đang lưu trên remote:

| Phần nguồn RC | Ý nghĩa trên Nino / GUI |
|---|---|
| A / CH5 (`RC_CH_MODE=4`) | ROS AUTO hoặc lái cần RC; GUI chọn nguồn ROS / TAY RC |
| E / CH9 (`RC_CH_ARM=8`) | ARM / DISARM |
| F / CH10 (`RC_CH_ESTOP=9`) | Stop latch; GUI có STOP và xóa khóa riêng |
| CH1 / CH2 trong source | Tham chiếu tiến/lùi và quay; GUI có pad giữ-nút v/omega |
| B / C | Source hiện không sử dụng; không tự gán thành mode thu mới |
| LOST / failsafe | Trạng thái mất link, không phải một nút chọn để ép “đã kết nối” |

Không suy vị trí gạt/cấu hình model hiện tại từ ảnh. GUI phát reference ROS,
không giả mạo SBUS. Profile authority mới có quy tắc RC override riêng nêu
bên dưới; không đồng nhất nó với arbiter RC cũ.

### Các chế độ thu đã thêm

| Chế độ | Thao tác | Dữ liệu / giới hạn |
|---|---|---|
| Đứng yên | Chỉ recorder 60 s; không tự ARM hoặc phát lệnh tiến | IMU, feedback/status, scan_raw, authority; command không bắt buộc có mẫu |
| Zero–ARM–DISARM | Sau recorder ready + kiểm vùng trống: yêu cầu ARM, giữ reference zero 4 s, DISARM | Kiểm request/ACK; không chứng minh torque/current hoặc stop-time |
| Tiến–dừng | Source +0,05 m/s trong mục tiêu 2 s, rồi zero/DISARM; smoother phải khai báo ramp 0,10 m/s² | Truy vết đủ source/selected/smoothed/final và feedback; thời lượng thực ghi event, không hứa chính xác tuyệt đối |
| Teleop giữ nút | Giữ pad tiến/lùi/quay; hết refresh 200 ms về zero; segment tối đa 2 s sau ARM, rồi DISARM | Tiến ≤0,05; lùi ≤0,01 m/s; quay ≤0,10 rad/s; không tự tăng tốc/gain/current |
| ROS ngoài / Nav2 | Chỉ ghi nhận; không khởi động Nav2, gửi goal hoặc tự ARM | Có mục để ghi dataset từ nguồn ngoài; navigation thực vẫn cần được commissioning riêng |

Mỗi phiên ghi 60 s chỉ cho **một chuỗi thao tác do workflow**. Không chạy
theo batch, không lấy thêm slot trong pilot cũ, không tự retry/resume. Điều
khiển từ publisher ROS khác vẫn là rủi ro của mạng tin cậy; GUI kiểm publisher
teleop xung đột và chủ sở hữu các tầng trước workflow. Đây là công cụ vận
hành, không phải tự động phê duyệt một protocol hoặc một campaign nghiên cứu.

### Thứ tự sử dụng sau khi triển khai firmware/bridge đúng

1. Driver/agent/sensor hoạt động. Dùng command stack hiện có nếu nó khớp
   cấu hình; không khởi động trùng. Khi chưa có stack, **STM32 phải DISARM**,
   chạy terminal Pi riêng:

   ```bash
   bash ~/nino_runtime/mode_gui_v1/start_gui_data_stack.sh
   ```

   Helper mới dùng `gui_data_control.yaml`, khởi tạo gate disabled + smoother
   + Collision Monitor. Nó không gọi runner/ledger cũ, không ARM và không
   phóng trial. Cần workspace `~/nino_pi_ws/install/setup.bash` đã dùng trước
   đó. Nếu thiếu workspace/package hoặc stack đã có, dừng và báo lỗi.

2. Mở GUI, kết nối, lấy quyền. Với quy trình có command: chọn nguồn ROS,
   chọn mode thu, bấm **Chuẩn bị đường lệnh · zero**. Nút này chỉ chuẩn bị
   Pi gate MANUAL/enabled và stream zero qua `/cmd_vel_teleop`; không ARM
   STM32. Có nút **Reset STOP tầng Pi** riêng, chỉ được gọi khi STM32 DISARM;
   sau reset gate vẫn disabled. STOP firmware và STOP gate là hai latch khác.
3. Ghi pose/caster và sàn/tải (`unknown` được phép); bắt đầu recorder. Nút
   chạy thao tác chỉ mở khi **file SQLite đã có mẫu của các kênh required**,
   không chỉ khi có node recorder.
4. Kiểm vùng trống, chọn profile và xác nhận trên GUI. Chạy một thao tác.
   Workflow chờ state mới xác nhận ARM + permission trước khi gửi nonzero.
   Có STOP, mất scan/TF/readiness/feedback/quyền/recorder thì zero + STOP,
   giữ nguyên failure; không tự chạy tiếp khi trạng thái tốt trở lại.
5. Chờ recorder đóng tự nhiên ở 60 s. Hủy sớm được ghi là incomplete theo
   collector. Khi đóng GUI giữa phiên, app yêu cầu stop và chờ cleanup;
   nếu mất SSH/tiến trình, status còn `started_not_closed` là chưa xác nhận
   hoàn tất, không được coi là captured. Ghi quan sát thân xe, lưu và review
   trước khi mở phiên mới.

Đứng yên / ghi nhận nguồn ngoài không cần chuẩn bị đường teleop GUI. Nếu
đường này còn enabled từ mode trước, bấm DISARM để tắt trước phiên chỉ ghi.
Phần ROS ngoài hiện là observer; GUI không cung cấp điều khiển navigation
để thay quy trình commissioning Nav2 còn thiếu.

### Readiness và dữ liệu

- Kiểm cấu hình gate, max/min velocity, accel/decel của smoother; lifecycle
  ACTIVE; một publisher đúng chủ cho selected/smoothed/final; final zero mới.
- Kiểm 5 s scan mới, TF LiDAR → base_footprint, StopZone giữ nguyên
  `x=[-0,40;0,46], y=[-0,34;0,34]`, min_points=3. Monitor chưa phát trạng
  thái là unknown và sẽ khóa workflow; không giả định UNKNOWN là CLEAR.
  Các geometry/readiness rule này cần kiểm live khi tích hợp, chưa là chứng
  nhận không có vật cản hoặc không có vùng mù.
- Các kênh chính: raw IMU, motor_fb, motor_status, scan_raw, control_state;
  các mode phát command thêm teleop/selected/smoothed/final. control_request
  và motor_enable là event/optional; không phát giả để lấp schema. TF, bridge,
  encoder odom, Collision Monitor, ROS nav và MIT/torque được giữ nếu có.
- Raw giữ source headers/frame/units trong message và bag receipt clock.
  `events.jsonl` thêm wall/monotonic anchors, metadata và phase/request labels;
  không biến chúng thành thời điểm actuator thực thi.
- Dùng lại `collect_real_data.py` với rosbag2 process và audit riêng. Không
  bỏ check SQLite integrity/metadata/hash của collector. GUI kiểm lại raw
  hashes sau khi collector đóng, rồi ghi `gui_result.json`, `sidecar_sha256.json`.
- Thư mục mới: `~/nino_real_data/gui_sessions/gui_<UTC>/capture/`. Raw hashes
  không bị sửa khi thêm quan sát; ghi quan sát vào sidecar có hash riêng.
  `captured_not_calibrated` chỉ là trạng thái thu; `workflow_status` và quan
  sát thân xe được giữ riêng, không suy arrival/slip từ encoder quay.

Backend thêm dependency `nav2_msgs`, `lifecycle_msgs`, `tf2_ros`, cùng bộ
collector ROS đã có. Nếu thiếu, phần data không được báo là sẵn sàng. Chế
độ demo mô phỏng recorder và luôn ghi `DEMO_ONLY_NO_DATA`, không tạo bag thật.

## Trạng thái bàn giao

**Đã có code GUI/bridge, firmware opt-in và kiểm tra offline. Chưa nạp board,
chưa kiểm trên robot, chưa cấp một lượt motion mới.** Pi `.109` không truy cập
được trong lần kiểm này (`No route to host`). Menu laptop đã có **Nino Control Modes**.

Firmware đang chạy trên robot trước đây buộc qua RC/SBUS. Chỉ thêm nút Python
không đổi được điều kiện đó. GUI này sử dụng một contract STM32 mới; firmware
cũ không phát `/nino/control_state` thì GUI khóa các nút, không giả lập AUTO/ARM.

Ảnh tay điều khiển giúp nhận biết thiết bị đang dùng; cấu hình kênh/switch
được quyết định bởi transmitter và firmware, không được suy từ ảnh.

## 1. Mở trên laptop

```bash
# Demo có nhãn rõ ràng, không SSH, không ROS, không nối motor:
bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh --demo

# Giao diện thật: mở ở trạng thái chưa kết nối / chưa lấy quyền:
bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh
```

GUI cần `/usr/bin/python3` và `python3-pyqt5`. Laptop hiện đã có dependency.
GUI không cần ROS trên laptop khi dùng SSH; bridge ROS chạy trên Pi. Chế độ
demo chỉ minh họa UI, không chứng minh firmware/hardware hoạt động.

Cài lại mục menu nếu đổi vị trí checkout:

```bash
bash ~/ninorobot/src/nino_pi/scripts/install_mode_gui.sh
```

Trong **Thiết lập SSH**, chỉnh key, đường dẫn `env.sh`, thư mục backend và
domain đúng với driver thật. Mặc định là `d@192.168.0.109`, domain `0` theo
phiên đã ghi trước đây; IP/domain cần khớp phiên hiện tại. SSH dùng key,
kiểm host key thông thường, không hỏi hoặc lưu mật khẩu trong GUI.

## 2. Các nút thực sự làm gì?

| Chọn/nút | Tác động và điều kiện |
|---|---|
| Lấy quyền GUI | Claim một owner mới hoặc claim lại owner hiện tại; luôn DISARM và chọn DỪNG |
| DỪNG | Chọn nguồn STOP, DISARM; không phải một lệnh tiến với vận tốc 0 |
| ROS / GUI | Tương ứng nhận reference ROS thay vì cần RC; RC offline không chặn nguồn này |
| TAY RC | Dùng cần RC thật; cần receiver online, RC arm, không RC stop và cần ở giữa khi ARM |
| ARM | Yêu cầu riêng, không tự phát vận tốc; cần owner, lease, feedback hai bánh mới, nguồn hợp lệ, không khóa stop |
| DISARM | Thu hồi cho phép, xóa lệnh cũ; ARM lại cần điều kiện zero mới |
| STOP phần mềm | DISARM + khóa STOP; không phải nút emergency stop vật lý |
| Xóa khóa STOP | Không ARM. Với ROS cần lệnh zero mới; với RC cần RC hợp lệ và cần ở giữa |
| Trả quyền | DISARM, chọn DỪNG và bỏ owner |

**Đổi nguồn luôn DISARM**; command có trước lúc đổi nguồn không đủ để ARM.
Với ROS, phải có `/cmd_vel` zero mới ở đầu vào STM32 rồi mới ARM. GUI không
phát `/cmd_vel` để tạo điều kiện zero thay cho teleop/stack. GUI cũng không
bật Pi command gate, smoother hay Collision Monitor. Hai tầng quyền này
khác nhau: quyền nguồn STM32 và chọn teleop/navigation trên Pi.

Khi nguồn ROS được chọn và tay RC tắt/mất tín hiệu, GUI không cần RC để ARM.
Nếu receiver đang online, **RC DISARM hoặc RC stop vẫn chặn**. Không giả mạo
frame SBUS và không sửa chức năng của receiver. Switch chọn nguồn vật lý
không tự thay nguồn mà GUI đã chọn trong profile mới; RC arm/stop là override
như trên. Nguồn TAY RC trong profile này cũng cần GUI lease; đây không phải
chế độ RC độc lập khi laptop đã tắt.

Các trạng thái ARM/permission là trạng thái chính sách/đường thực thi firmware,
**không phải readback enable/current hoặc bằng chứng xe đã chuyển động**.
Đường emergency stop vật lý hiện có cần được giữ và kiểm riêng; GUI không
xác nhận cách nút đỏ đang được đấu dây.

## 3. Firmware cần thiết

Source ở workspace firmware `Microros_H723_USB`, nền commit
`0d32593988cc817311d3dfdd8683df1f1b444a2c` cộng các thay đổi được lưu trong
gói bàn giao. Build với **`NINO_SOFTWARE_AUTHORITY=1`**. Mặc định `0` giữ
nhánh RC cũ; không được bật đồng thời `NINO_ROS_ONLY_TELEOP=1`.

Tại workspace triển khai:

```bash
bash build_gui_control_firmware.sh
```

Artifact: `artifacts/software_authority_2026-11-03/build/microros_H7.{elf,bin,hex}`.
**Target build là STM32H723xx / linker STM32H723XG_FLASH.ld. Part/revision
board thực chưa được xác nhận độc lập. Không chọn binary chỉ từ ảnh hoặc
tên repo; chưa thực hiện flash trong nhiệm vụ này.**

Profile mới:

- Boot ở STOP/DISARM. Command hoặc kết nối agent không tự ARM.
- Chỉ velocity mode; chặn MIT/torque chuyển mode; không đổi gain/current.
- `|v| ≤ 0,05 m/s`, `|omega| ≤ 0,10 rad/s`, áp cho cả nguồn ROS và RC trong
  profile này. Đây là giới hạn khởi đầu của code, không là chứng nhận an toàn.
- `/motor_enable=true` cũ không ARM được. `/motor_enable=false` vẫn DISARM.
- Lease GUI 500 ms; watchdog ROS command 500 ms. Hết hạn sẽ DISARM/khóa STOP,
  không tự tiếp tục khi link quay lại. Đây là timeout cấu hình, không là
  stopping time hoặc deadline đã đo trên robot.
- Khi agent bị disconnect, thu hồi owner và khóa stop. Mất feedback hoặc
  RC chặn khi ARM cũng khóa stop.

**Không chạy nguyên helper pilot cũ sau khi đổi firmware:** chúng có enable
contract khác và budget/ledger đã khóa. Khi triển khai thật cần protocol mới.

## 4. Đưa backend lên Pi khi Pi kết nối lại

Lệnh sau chỉ copy Python, không mở agent, ARM, flash hoặc chạy thử xe:

```bash
bash ~/ninorobot/src/nino_pi/scripts/deploy_mode_bridge.sh d@192.168.0.109
```

Sau đó GUI có thể mở bridge qua SSH. Pi cần ROS Jazzy, `rclpy`, `std_msgs`
và env driver đúng. Agent và STM32 vẫn phải kết nối như trước. Backend nằm
ở `~/nino_runtime/mode_gui_v1/nino_pi/`, độc lập với runtime/ledger cũ.

Ở tab chọn nguồn, bridge publish `/nino/control_request`. Tab data sau thao
tác chuẩn bị có thể publish `/cmd_vel_teleop` và gọi dịch vụ gate như mô tả
ở trên; **không publish trực tiếp `/cmd_vel` hoặc `/motor_enable`**. GUI phải
gửi pulse liên tục mới gia hạn lease. Bridge tự
chạy mà GUI đã chết không được duy trì ARM vô hạn. Đóng app gửi STOP/release
best effort; nếu link mất, firmware lease là lớp xử lý độc lập. Không có
cam kết ROS/SSH là đường realtime hoặc safety-rated.

## 5. Wire contract v1

Hai topic `std_msgs/msg/UInt32MultiArray`, reliable/volatile, layout rỗng:

| Topic | Nội dung |
|---|---|
| `/nino/control_request` | Đúng 5 uint32: `[version=1, client_id, sequence, opcode, argument]` |
| `/nino/control_state` | Đúng 20 uint32 theo bảng dưới; khoảng 5 Hz theo lịch publication firmware |

Opcode: `1 CLAIM`, `2 HEARTBEAT`, `3 SELECT`, `4 ARM`, `5 DISARM`, `6 STOP`,
`7 CLEAR_STOP`, `8 RELEASE`. Argument chỉ khác 0 cho SELECT: `0 STOP`,
`1 RC`, `2 ROS`. Client và sequence không được 0. Owner có sequence tăng;
yêu cầu cũ bị từ chối. STOP/DISARM từ client khác vẫn được phép dừng.
Heartbeat không ghi đè ACK thao tác. Một yêu cầu vận hành chờ ACK tại một
thời điểm; không tự retry sau timeout.

| Index state | Field |
|---|---|
| 0–1 | version `1`, magic `0x4E494E4F` |
| 2–4 | owner client, last owner sequence, source |
| 5–7 | policy armed, stop latched, reason |
| 8–11 | RC online, RC armed, RC stop, feedback mask (trái=1, phải=2) |
| 12–13 | command age ms, GUI lease age ms; chưa có = `UINT32_MAX` |
| 14–16 | ACK client, ACK sequence, ACK result |
| 17–19 | firmware permission, applied firmware actuator-mode variable (`0 velocity`), HAL uptime ms |

Mã result/reason là nguồn chung trong `mode_protocol.py` và
`User/Config/software_authority.h`. GUI kiểm capability/độ dài/miền giá trị,
ACK client+sequence, và trạng thái mới. Timestamp uptime không tăng không
được dùng để gia hạn freshness. Firmware reboot làm phiên GUI bị khóa;
phải chủ động lấy quyền lại. State quá 450 ms hoặc UI pulse quá 400 ms làm
bridge ngừng heartbeat; đây là ngưỡng code chưa benchmark dưới tải Pi thật.

Owner token chống tranh quyền vô ý, **không xác thực bảo mật publisher DDS**.
Chỉ dùng trong mạng ROS tin cậy; SSH không biến mọi DDS publisher thành client
được xác thực. Không replay bag chứa control_request trên robot nối motor.

## 6. Bước triển khai thật tiếp theo — chưa thực hiện

1. Kết nối lại Pi, xác nhận part/flash method và firmware hiện tại để giữ
   bản rollback; sau đó mới cài đúng binary hỗ trợ contract mới.
2. Kiểm trạng thái/ACK với nguồn công suất motor đã ngắt: boot DISARM,
   claim/chọn nguồn không ARM, thiếu feedback từ chối ARM, lỗi link không
   tự hồi phục. Việc này không chứng minh motor stop.
3. Khi có điều kiện feedback hợp lệ, thực hiện lượt zero/ARM/DISARM có người
   vận hành; kiểm cả mất GUI và nút dừng vật lý theo protocol riêng.
4. Chỉ sau bước đó mới review một lượt motion 0,05 m/s với recorder, vùng
   trống, Collision Monitor và reference phù hợp. Không tự mở slot pilot cũ.

Các kiểm tra offline hiện có được ghi trong `artifacts/software_authority_2026-11-03/REPORT.md`
của workspace triển khai. Không cộng tests hoặc demo UI thành lượt robot.

## Cập nhật GUI v3 — 03/11/2026

Thêm tab **Tiến độ / kết quả / to-do**, xem được khi chưa nối Pi:

```bash
bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh --project
```

Gồm 23 nhóm data cần/đã/chưa; 26 thông số/kết quả có nguồn và giới hạn;
11 phiên được chọn để review; 22 mục to-do (4 mục đã đủ/chuẩn bị, 18 việc
kế tiếp). Đây là snapshot local, không phải inventory live hay tất cả 15 bag.
Có lọc, xem/mở nguồn, export JSON và đọc lại catalog.

Thang Q0–Q4 chấm **theo claim**, tách raw integrity, measurement/window,
command/confound, body reference và độ lặp. Mức phiên mới tự động tối đa Q2;
coverage, body motion/slip và repeatability còn cần review riêng. Demo Q0,
không gán cho dữ liệu thật. Các ngưỡng CV/asymmetry/stop trong báo cáo ngoài
chưa được chấp nhận và không thay runtime limits/STOP.

Khi backend mới đóng một phiên GUI, `gui_quality_report.json` được giữ bên
cạnh `gui_result.json`, hash trong sidecar riêng; raw manifest không sửa.
Cần copy backend mới bằng deploy helper để có report này trên Pi. Backend
cũ không đủ evidence để chấm Q2 chỉ từ một status string. Chưa deploy/flash
hoặc kiểm hardware trong lần cập nhật GUI này.

Catalog `nino_pi/project_evidence.json` đóng gói cùng Python package. Mỗi
nguồn có ngày/path/hash; nếu chuyển sang máy khác, nguồn local có thể không
còn ở path đó. Không tự hoàn tất task hoặc thêm phiên vào lịch sử từ
workflow done hay checkbox; review mới cần cập nhật catalog có nguồn.

Xem [đánh giá lại báo cáo](../../docs/NINO_REPORT_REASSESSMENT_AND_GUI_2026-11-03.md)
và [checklist real data](../../docs/NINO_REAL_DATA_CHECKLIST_2026-11-03.md).

