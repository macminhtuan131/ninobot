# Command → wheel response trên sàn sạch — bản chuẩn bị

Ngày soạn: 28/10/2026. **Draft, chưa release một lượt chuyển động.**

Mục tiêu là đo quan hệ giữa velocity command cuối nhìn thấy trên ROS và
feedback hai bánh. Trục IMU thô, dấu gyro Z và sensor inventory đã có bằng
chứng; không cần thu lại chỉ để mở bước này. Dataset này chưa đủ kết luận
vận tốc thân, slip, vượt gờ hoặc lợi ích governor.

## 1. Artifact và phạm vi

- `config/stm32_usb_wheel_response_collection.json`: ba kênh required
  `/cmd_vel`, `/motor_fb`, `/motor_status`. IMU, trace command trung gian,
  bridge, LiDAR và TF là optional cho claim tối thiểu.
- `config/wheel_response_session.template.json`: bản generic session giữ
  unknown=`null`, bổ sung command contract, thiết kế thử và clock/event.
- `config/stm32_usb_collection_qos.yaml`: QoS đang có cho raw STM32,
  IMU/bridge và TF. Vẫn cần kiểm endpoint của phiên thực.

`duration_s=60` là ngân sách ghi đề xuất trong config, không phải thời gian
xe được phép chạy. Profile mới là contract riêng theo câu hỏi nghiên cứu;
profile full/navigation trước đó vẫn có phạm vi và required channels riêng.

Khi claim truy dấu cả chuỗi, copy profile ra file riêng và đặt required cho
**mọi tầng thực sự dùng**: source `/cmd_vel_teleop` hoặc source khác, selected,
smoothed và final. Ghi tên/path/hash của profile đã chốt. Profile tối thiểu
không tự chứng minh các tầng optional có dữ liệu đầy đủ. Nếu thay tên topic,
đổi cấu hình theo endpoint thật, không tạo publisher để lấp kênh thiếu.

## 2. Chuẩn bị offline và lệnh kiểm tra

Chạy dưới đây trong workspace source đã có Python/yaml; sửa `nino_pkg`
thành đường dẫn thực của package ở máy đang dùng. Lệnh không SSH và không
launch ROS node, recorder hoặc controller:

```bash
nino_pkg="$HOME/ninorobot/src/nino_pi"
export PYTHONPATH="$nino_pkg${PYTHONPATH:+:$PYTHONPATH}"
/usr/bin/python3 -m nino_pi.collect_real_data \
  --config "$nino_pkg/config/stm32_usb_wheel_response_collection.json" \
  --session "$nino_pkg/config/wheel_response_session.template.json" \
  --qos "$nino_pkg/config/stm32_usb_collection_qos.yaml" \
  --output "$HOME/nino_real_data/validation_only_wheel_response" \
  --check
```

`--check` chỉ xác nhận cấu trúc/plan. Nó không tạo output directory, không
kiểm motor, limits, RC, timestamp thực hay khả năng dừng. Collector hiện
chấp nhận session ID dạng `EDIT_*` và không enforce release gate của form.
Thay ID và hoàn tất protocol trước lần ghi thực; không bỏ `--check` chỉ vì
validation thành công. Dùng bản session/config mới cho từng lượt, giữ raw
và bản protocol đã ký trước lượt đó.

## 3. Chốt command contract trước chuyển động

Assistant có thể điền nguồn bằng chứng/config và kiểm syntax offline.
Người vận hành cần xác nhận mapping RC, đường emergency stop và các giá trị
vận hành cụ thể. Gate này chỉ gắn với lượt motion; không yêu cầu metadata
generic phải đủ mọi thông số để tiếp tục phân tích dữ liệu cũ.

| Nội dung cần chốt | Bằng chứng cần lưu |
|---|---|
| Nguồn ROS, owner final `/cmd_vel`, owner enable | Node/topic thực, graph/launch/config; không có owner cạnh tranh trong cửa sổ thử |
| RC online, ROS được chọn, arm và stop latch | Mapping tay thật và cách quan sát; source mapping chưa xác nhận binary đang nạp |
| Mode motor/backend | Source, readback nếu có và mức bất định; velocity mode không chồng PI vận tốc thứ hai trên Pi |
| Zero, gate disable, ROS motor disable, watchdog, RC/F, nút đỏ | Semantics riêng, thao tác và bằng chứng; kiểm dừng có chuyển động nằm trong protocol thực được chốt |
| Profile và giới hạn thử | Vận tốc, yaw, ramp, thời gian, khoảng trống, tải/sàn và điều kiện abort; giá trị chưa chốt giữ null |
| Dữ liệu và clock | Topic/type/frame/units, feedback freshness, thời điểm source/receipt, cách gắn nhãn trial và uncertainty |

Theo source tham khảo `Microros_H723_USB` commit
`0d32593988cc817311d3dfdd8683df1f1b444a2c`, chưa xác nhận binary khớp:

- `/cmd_vel` chọn velocity mode, `/cmd_mit` và `/cmd_torque` có thể đổi mode.
  Chốt một đường command cho protocol và ghi command cạnh tranh nếu xuất hiện.
- Motor watchdog cấu hình 500 ms. Giá trị này không phải stopping time đã đo.
  Velocity stop gửi speed zero; MIT stop dùng damping. ROS disable đi qua
  pending enable request; RC/F hoặc mất RC có thể chỉ làm `effective_enable=0`
  rồi gửi stop theo mode. Cơ chế nút đỏ vật lý phải ghi riêng.
- `/motor_status` bit 4 là `g_system_enabled` trước RC arbitration, có thể
  khác `effective_enable`; bit mode là trạng thái firmware, không readback
  trực tiếp của motor. Status không thay bằng chứng nguồn/torque hoặc RC.
- Target bánh sau limiter và current/voltage/temperature chưa có telemetry
  được xác nhận. Không điền target=requested hoặc suy current/torque thật
  từ `/cmd_vel` hay tên trường effort.
- `keyboard.py` hiện hard-code tiến 0,20 m/s, lùi 0,10 m/s, yaw 0,60 rad/s,
  key expiry 0,6 s. Đây là source settings, chưa là mức thử được chấp nhận.
  YAML gate chỉ clamp output; không tự đổi mức bàn phím yêu cầu.
- Gate disabled vẫn phát zero định kỳ. Launch command stack có thể phát
  final zero và refresh watchdog/chọn mode; không dùng launch để thay kiểm
  read-only. Sensor-stage bridge đang cô lập enable không phải khóa RC.
- Chuỗi command stack đầy đủ hiện cấu hình collision monitor dùng `/scan`
  và odom TF, trong khi sensor stage mới xác nhận `/scan_raw` và thiếu
  odom→base TF. Giải quyết source/TF theo contract trước khi launch chuỗi
  đó. Không bypass monitor để làm đầy dữ liệu.

Ghi **đường dẫn source thực và commit/config hash**, không dùng tên repo
hoặc path ví dụ như bằng chứng phiên. Source firmware local đã review nằm
ở `Microros_H723_USB/User/APP/motor_task.c`, `User/Config/robot_config.h`,
`User/Bsp/bsp_sbus.*`, `Core/Src/freertos.c`; source Pi/runtime phải được
đối chiếu riêng. Không cần flash lại để dùng collector này.

## 4. Thiết kế thử đề xuất, chưa release

Đề xuất một slot commissioning/feasibility được định nghĩa trước, sau đó
pilot hẹp **hai profile × ba trial = sáu trial**, tổng tối đa **bảy slots**
cho E1 trên một cấu hình tải/sàn. Stop contract phải được chốt trước khi
mở slot commissioning. Hai profile chỉ
khác reference shaping để tìm hiểu đáp ứng tổng; giá trị cụ thể và thứ tự
block cần ghi trước thử. Mỗi trial bắt đầu từ trạng thái yên theo tiêu chí
đã chọn, có baseline, đoạn tiến/giữ tham chiếu và stop, rồi cửa sổ hậu stop.
Ba trial mỗi profile chỉ mô tả độ lặp sơ bộ, không đủ chứng minh tổng quát
hoặc power. Không tăng số mẫu tự động khi kết quả không rõ.

Lượt tiến thẳng kiểm dấu tiến/zero và freshness, **không tự phân biệt hai
kênh trái/phải bị đổi chỗ** khi hai bánh nhận cùng reference. Danh tính kênh
cần evidence đối chiếu bánh vật lý riêng (có thể dùng bằng chứng kiểm bánh
trái đã có nếu đủ) hoặc một differential maneuver được chốt rõ trong slot
commissioning. Không tự thêm lùi/quay/vật cản chỉ để hoàn thành pilot.
Nếu mapping còn thiếu, dùng đúng slot commissioning đã dự trù và đúng
profile được chấp nhận, báo riêng, không tính thành repeat ID. Nếu slot
đó fail thì đóng các slot ID chưa chạy; không thêm smoke/retry hoặc chạy bù.
Không có tốc độ/ramp/duration mặc định nào trong tài liệu này được chấp nhận.

Trước khi ký protocol, chọn primary response summary, định nghĩa settling/
onset/T90, độ phân giải đủ dùng và điều kiện trial invalid/abort. Form giữ
thiết kế accepted=null; đề xuất sáu trial không phải ngân sách đã cấp.

## 5. Thu dữ liệu và phân tích

Giữ raw CDR/bag, metadata và hash. Bắt đầu ghi trước baseline, đánh dấu
trial, source command onset/ramp/hold/zero, switch RC/enable/stop và outcome.
Event có thể là file thủ công riêng với clock, đồng bộ và uncertainty đã
khai báo; không cần tạo ROS event publisher để hoàn tất form. Ghi cả lỗi,
abort, timeout, dữ liệu thiếu và mọi spike.

| Đại lượng | Clock/giới hạn diễn giải |
|---|---|
| Final Twist `/cmd_vel`: linear.x m/s, angular.z rad/s | Không có header; bag time là lúc recorder nhận, chưa phải lúc STM32 nhận/thực thi |
| `/motor_fb`: names, position rad, velocity rad/s, effort | Source header giữ nguyên; kiểm clock/validity, mapping/sign/freshness theo status; effort là reported chưa kiểm chứng |
| `/motor_status`: raw mask | Không có header; receipt không cho chính xác thời điểm đổi state bên MCU; rate thấp hơn feedback |
| Optional IMU | Acceleration m/s², gyro rad/s, sensor frame với TF; gravity/rotation/lever arm ảnh hưởng tín hiệu |
| Optional command trung gian | Mỗi topic phải tồn tại và được ghi nếu claim thời gian tầng đó; không đồng nhất requested với executed target |

Phân tích command→wheel là **đáp ứng tổng của đường từ final ROS request**,
bao gồm transport, firmware, motor mode/ramp và cơ học bánh. Chưa có target
telemetry thì không tách motor PI latency khỏi các phần khác. Header time
và bag receipt chỉ được trừ khi clock/offset và uncertainty phù hợp; nếu
chưa có thì báo khoảng thời gian quan sát được hoặc unknown.

Phân biệt ít nhất:

- **Onset:** lần đầu feedback thay đổi bền vững theo tiêu chí đã chốt từ
  baseline noise, kèm khoảng phân giải giữa các sample; không chọn ngưỡng
  sau khi thấy đường cong để làm latency nhỏ hơn.
- **T90 tổng tính từ đầu input ramp:** thời điểm feedback đạt 90% mức đổi
  theo reference endpoint đã định nghĩa; bao gồm thời gian ramp. Không gọi
  nó là transport latency hoặc motor time constant.
  Endpoint tốc độ bánh tính từ v/omega và geometry khai báo phải mang nhãn
  nominal; nêu giả thiết về clamp/mode trước khi dùng. Phép tính này không
  tạo telemetry executed target và không xác nhận geometry đã hiệu chuẩn.
- **Đạt endpoint/hold:** nếu feedback không đạt endpoint đã định nghĩa hoặc
  chưa có plateau phù hợp thì ghi “không đạt/không nhận dạng được”, không
  thay endpoint bằng mức thực đạt sau khi xem dữ liệu để tạo T90 đẹp.
- **Censoring:** nếu cửa sổ kết thúc trước onset/T90/settling, báo right-
  censored hoặc unknown theo nguyên nhân. Không thay bằng 0, không loại trial.
- **Stop:** đo từ zero/requested stop event tới feedback nằm trong tiêu chí
  yên đã chốt; chưa có body reference thì gọi wheel settling, không gọi
  thời gian/quãng đường dừng thân xe đã chứng nhận.

Counts/SQLite/hash/closure chỉ là software integrity. Cần kiểm sample
validity, freshness, gap/coverage trong từng cửa sổ baseline/ramp/hold/stop;
ngưỡng coverage và gap phục vụ câu hỏi phải được chốt cho protocol này,
không tự bê 98% của sim hoặc tùy ý nới sau kết quả.

## 6. Gate và điểm dừng

1. **Chuẩn bị:** JSON/QoS/`--check` hợp lệ, form có nguồn/path đúng. Chỉ đạt
   software preparation; không release motor.
2. **Release motion:** owner, RC/stop, limits/profile, data/clock và người
   vận hành được ghi rõ trong bản protocol mới có xác nhận. Form chưa ký
   giữ `draft_not_released`; collector không tự enforce việc ký này.
3. **Feasibility/data:** nếu mapping, freshness, mode, command conflict hoặc
   storage/coverage không phù hợp thì giữ outcome và dừng interpretation
   tương ứng; không chuyển sang obstacle/governor để bù một gate thiếu.
4. **Pilot:** báo từng trial và biến thiên, đạt/không đạt/unknown theo rule
   đã chốt. Cho tối đa một correction có nguyên nhân từ bằng chứng và một
   quyết định lại được định nghĩa trước; không âm thầm retry hoặc tăng N.
5. **Bước sau:** wheel-response đủ đo sẽ hỗ trợ chọn shaping/nhận dạng
   backend. Claim body/slip/H2 cần reference thân độc lập và thí nghiệm riêng.

Khi chưa nối Pi, có thể review source, hoàn thiện contract và chuẩn bị
analyzer từ raw đã có. Những việc đó không tạo bằng chứng mới về motor
response, stopping hay governor trên robot thật.
