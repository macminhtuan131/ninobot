# Nino — chuẩn bị một lượt tiến–zero, 01/11/2026

> **Chuyển hướng mới nhất:** người dùng yêu cầu teleop không dùng RC.
> [Profile firmware ROS-only đã build, chưa nạp](NINO_ROS_ONLY_TELEOP_2026-11-01.md).
> Các lệnh trial bên dưới là luồng cũ cần arm bên ngoài Pi; chưa dùng lại
> để thay thế backend ROS-only.

> **Cập nhật sau lỗi/reboot, 01/11:** helper bị chặn ở điều kiện firmware
> enable trước lệnh tiến; chưa có `trial.claim`. Đã khôi phục sensor/EKF
> trong boot `b55bd806-d4f7-4fcb-b16d-3445d7fb2e4e`, runtime log
> `~/nino_runtime/reconnect_20261101_v2/`. IMU/motor 568 mẫu mỗi kênh trong
> cửa sổ 12 s; đủ các kênh sensor/TF đã kiểm, status 56/56 bằng 35. Bit 4
> chưa bật; chưa chạy lại command stack hoặc lượt tiến. Cần xác định đúng
> thao tác arm trên tay RC trước khi dùng lại các lệnh dưới đây.
>
> Source tham khảo `motor_task.c` chỉ xử lý arm RC khi trạng thái thay đổi;
> `rc_arm_prev=1` trong khi khởi động motor disabled có thể làm trạng thái
> ARM sẵn không tạo enable request. Đây là giả thuyết từ source, chưa chứng
> minh binary đang nạp hoặc vị trí công tắc thực. Source dùng A chọn mode,
> E arm và F stop; người dùng đang cần hướng dẫn thao tác, đã yêu cầu ảnh
> tay RC để đối chiếu. Không bỏ guard hoặc tự phát `/motor_enable`.
>
> Phiên `wheel_commissioning_20261101T134344657263Z` còn manifest `started`
> sau reboot. Kiểm SQLite read-only trả `database disk image is malformed`;
> giữ raw, chưa repair/reindex và không coi là dataset hợp lệ. Marker active
> của boot cũ được lưu riêng, không dùng để resume. Chưa xác định nguyên nhân
> hỏng file. Artifact: `artifacts/pi_reconnect_2026-11-01_v2/` trong workspace
> bên dưới. Helper đã bổ sung status số trong lỗi, lưu lỗi readiness và công
> cụ read-only `bash ~/nino_runtime/wheel_collection_20261101_v1/check_enable.sh`.

## Trạng thái và phạm vi

**[N, runtime]** Pi `d@192.168.0.109`, boot
`efa9e5ea-00fc-42f1-a5d0-006a8196be38`, ROS domain 0. Agent, bridge,
state publisher, RPLIDAR và EKF đang chạy trong boot này; chưa tạo autostart.
Snapshot cuối có publisher IMU, motor feedback/status, `/scan_raw`, `/odom`;
không có publisher trên bảy topic command/source/intermediate/enable được kiểm.
Đĩa còn khoảng 19 GB. Đây là kiểm trong cửa sổ quan sát, không bảo đảm runtime
tiếp tục sống sau reboot hoặc mất kết nối.

**[N, người vận hành]** Người dùng xác nhận đã kiểm ROS/RC, arm/disarm và
nút đỏ trên robot; đã chọn profile đề xuất. Assistant chưa đo lại các thao
tác dừng hoặc xác nhận binary STM32 khớp source.

| Thông số lượt commissioning duy nhất | Đã chọn |
|---|---:|
| Reference tiến tối đa | 0,05 m/s |
| Gia/giảm tốc reference | 0,10 m/s² |
| Thời gian phát source tiến mục tiêu | 2 s, sau đó zero |
| Quan sát thêm sau zero | 3 s |
| Ghi bag | 60 s |
| Số lượt | 1, không tự retry |

Đây là profile lệnh, chưa là vận tốc/quãng đường/quãng dừng thân xe được đo.
Không coi commissioning là pilot nhận dạng nhiều lặp hoặc phép thử governor.

## Những thay đổi đã thực hiện

- Chạy EKF có sẵn từ encoder odometry và IMU yaw rate, tạo `/odom` và TF
  `odom → base_footprint`. **Không phải body reference độc lập.**
- Tạo YAML riêng cho profile đã chọn; Collision Monitor đọc `/scan_raw`
  thực có trên Pi. Giữ polygon/stop và kiểm TF; chưa xác nhận deskew `/scan`.
- Kiểm gate → smoother → monitor trên toàn bộ command topic riêng
  `/nino_preflight/*`; cả hai lifecycle node active, có 41 output khác zero
  trong probe riêng. Không nối probe vào command của STM32.
- Dừng process group preflight riêng 3393; giữ EKF 3392 và sensing.
- Collector yêu cầu đủ bốn tầng command và ba kênh raw; helper trial kiểm
  owner, freshness/status và recorder trước khi bật **Pi gate**. Không phát
  `/motor_enable`, `/cmd_mit`, `/cmd_torque` hoặc trực tiếp `/cmd_vel`.
- Helper phát source tiến rồi zero, yêu cầu tắt Pi gate, lưu events và kết
  quả sequence. Watchdog/ramp không biến thành bảo đảm stopping vật lý.
- Config laptop được backup và trỏ sang YAML profile đã chọn, tránh dùng
  default teleop 0,2 m/s cho lượt này. Dùng helper chuyên biệt dưới đây.

**[N, kiểm phần mềm]** Syntax Python/shell đạt; năm tình huống sequencing
(bình thường, lỗi trước/giữa lượt, Ctrl+C, clock jump) đều yêu cầu zero và
không issue nonzero sau deadline quan sát. Collector `--check` đạt, không
tạo bag/active session. Mười file triển khai khớp SHA256 với bản laptop.
Không có lượt chuyển động motor được assistant thực thi trong chuẩn bị này.

Lần preflight đầu không có output riêng và observer ghi một header gap
256 ms; được giữ nguyên. Follow-up dùng probe hữu hạn trên topic riêng và
observer depth 200. Follow-up có max gap raw IMU/motor 24 ms trong cửa sổ;
không suy loss-free hoặc coi đó là coverage của dataset chuyển động tương lai.

## Lệnh người vận hành chạy

Mở ba terminal SSH: `ssh d@192.168.0.109`. Xe trên sàn trống. Chạy lần lượt:

**Terminal 1 — chuỗi command, bắt đầu với Pi gate disabled:**

```bash
bash ~/nino_runtime/wheel_collection_20261101_v1/start_stack.sh
```

Giữ terminal mở. Nếu launch báo lỗi lifecycle/TF/LiDAR thì dừng tại đây,
không bypass monitor.

**Terminal 2 — ghi dữ liệu 60 giây:**

```bash
bash ~/nino_runtime/wheel_collection_20261101_v1/record_wheel.sh
```

Đợi khoảng 5 giây. Dùng các công tắc đã kiểm để chọn ROS và arm. Helper
không thay thao tác RC. Chạy Terminal 3 ngay trong cửa sổ ghi này:

**Terminal 3 — thực hiện một lượt tiến–zero:**

```bash
bash ~/nino_runtime/wheel_collection_20261101_v1/run_trial.sh
```

Helper tự chờ recorder/telemetry/owner; từ chối nếu điều kiện thiếu hoặc
cửa sổ ghi gần hết. Kết thúc sequence không chứng minh xe đã dừng vật lý.
Quan sát xe; dùng nút dừng đã kiểm nếu chuyển động bất thường. Sau lượt,
disarm theo cách đã kiểm và để Terminal 2 ghi xong; sau đó Ctrl+C Terminal 1.
Nếu bị chặn hoặc có lỗi, giữ nguyên artifact, gửi log; không tự chạy bù.

## Dữ liệu và quyết định kế tiếp

Required: `/cmd_vel_teleop`, `/cmd_vel_selected`, `/cmd_vel_smoothed`,
`/cmd_vel`, `/motor_fb`, `/motor_status`, `/imu/data`.
Optional/context: joint states, IMU bridge, encoder odom, EKF odom, raw scan,
TF, monitor action changes và các command xung đột nếu xuất hiện. Không phát
thêm lệnh để lấp kênh optional. Twist không có header: bag time là thời điểm
nhận của recorder, chưa là thời điểm STM32/motor thực thi.

Output: `~/nino_real_data/wheel_commissioning_<UTC>/`, gồm raw bag, audit,
session/config/hash, `trial.claim.json`, `trial_events.jsonl`, `trial_result.json`.
Flag `source_sequence_completed` chỉ mô tả việc chạy helper. Kết luận phải
đọc raw: đủ command trace, wheel units/sign theo nhãn, freshness/fault,
command→wheel response và hồi về baseline sau zero. Giữ failures/missing.
Chưa có executed wheel target, body reference độc lập, slip hoặc stopping
certification. Nếu lượt đầu diễn giải được mới thiết kế pilot ID; nếu không,
chọn correction từ lỗi thực tế trước khi quyết định lượt mới.

Artifact laptop:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/wheel_collection_setup_2026-11-01/`.
Các file chính: `preflight_verification.initial.json`,
`preflight_verification.json`, `preflight_shutdown.json`,
`final_preparation_verification.json`, `collector_plan_check.txt`, accepted
profile/YAML và source helper. Runtime Pi cùng nội dung tại
`~/nino_runtime/wheel_collection_20261101_v1/`.
