# Nino — teleop bàn phím không RC, 01/11/2026

> **Cập nhật mới nhất 02/11:** người dùng yêu cầu chỉ nối agent như cũ;
> dừng hướng nạp firmware/backend mới. Đã mở agent trên Pi `.109`, giữ
> firmware STM32 hiện có. Trong cửa sổ 10 s nhận 473 IMU, 472 motor_fb,
> 47 status đều 32. Header IMU/motor không zero/lùi/trùng trong cửa sổ;
> status 32 chưa có freshness CAN hai bánh, phù hợp việc người dùng báo
> đã ngắt nguồn công suất motor, không coi motor_fb là feedback bánh hợp lệ
> cho ID lúc này. Không có publisher motor command trong snapshot. Không
> flash, enable hoặc phát chuyển động. Runtime agent:
> `/home/d/nino_runtime/agent_reconnect_20261102_v1`, launcher PGID 1646;
> boot `ceb30e10-5401-494a-99ed-2c8b51662909`. Bằng chứng laptop:
> `artifacts/agent_reconnect_2026-11-02/` trong workspace firmware bên dưới.
> Các phần ROS-only sau đây là thiết kế/build offline trước correction,
> chưa triển khai; bản nháp host mới trong `ros_only_commissioning_2026-11-02`
> cũng chưa kiểm/triển khai, không dùng để điều khiển.

## Yêu cầu và trạng thái

Người dùng yêu cầu “Teleop đi, ko cần RC”. Đã chuyển hướng khỏi thao tác
arm bằng tay RC. **Chưa điều khiển robot theo hướng mới, chưa nạp firmware.**
SSH tới `192.168.0.109` timeout trong lượt chuẩn bị này; đang chờ Pi/IP.

Source đã review bắt buộc SBUS: mất RC khiến `sbus_get_control_mode()` trả
emergency stop và motor task đặt effective enable bằng 0. Chỉ phát
`/cmd_vel` hoặc `/motor_enable` từ Pi không gỡ điều kiện này nếu binary đang
nạp khớp source đó. Danh tính binary trên board vẫn chưa được xác minh.

## Phần đã làm offline

Workspace firmware:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/`.

Đã thêm profile build **tường minh** `NINO_ROS_ONLY_TELEOP=1`; mặc định 0
giữ nhánh arbitration RC. Không dùng “mất RC” làm điều kiện tự chuyển mode.

- Khởi động disabled; `/motor_enable` là yêu cầu riêng, không auto-enable
  khi có `/cmd_vel`. Chỉ chấp nhận enable khi đã nhận reference zero hữu
  hạn và mới trong cửa sổ watchdog. Zero reference không chứng minh xe đứng yên.
- Profile chỉ nhận velocity; MIT/torque không đổi mode hoặc refresh watchdog.
- Clamp reference firmware ở ±0,05 m/s, ±0,10 rad/s. Đây là giới hạn build
  commissioning; không là xác nhận cho phép chạy lùi/quay hoặc giới hạn dừng
  vật lý. Profile thử tiến đã được người dùng chọn vẫn là 0,05 m/s, 2 s.
- Khi dòng lệnh cuối tới STM32 stale quá cấu hình 500 ms, xóa yêu cầu
  enable, yêu cầu disable; cần zero mới và enable mới để chạy lại. Khoảng
  500 ms là timeout cấu hình, chưa là stopping time đo được.
- Nếu Pi vẫn gửi zero đều sau khi keyboard mất, đó là zero command, không
  phải mất dòng lệnh cuối. Không hứa watchdog STM32 sẽ disable trong tình huống đó.
- Bit 7 `/motor_status` đánh dấu profile ROS-only; bit 4 giữ nghĩa firmware
  enable variable. Không bit nào là readback torque/power hoặc chứng nhận
  phần cứng. Status marker không thay hash/readback khi xác minh binary.
- RC A/E/F không còn là nguồn điều khiển/dừng trong profile này. Không thêm
  giả định về dây nút đỏ; software watchdog không thay emergency stop vật lý.

Đã build cả ROS-only và mặc định RC, chạy host fault checks trên các setter
C production với HAL tick/critical section được stub, kiểm boot/zero/enable,
stale/nonzero rearm, disable, clamp, MIT rejection, NaN và tick wrap. Không
test CAN/RTOS/physical stop bằng harness này. Build có warnings missing-braces
ở font LCD có sẵn; không có build error. Chưa đo trên board.

Build tái tạo trên laptop:

```bash
bash build_ros_only_firmware.sh
python3 Microros_H723_USB/tools/tests/test_ros_only_teleop.py
```

Binary:
`artifacts/ros_only_teleop_2026-11-01/build/microros_H7.bin`.
SHA256: `d9c88cc064f0d510f39f2e4d6db39243a73342c7b89eb902de514408ed64765b`.
Manifest, patch gồm file mới, hashes và build logs cùng directory. Target
vẫn STM32H723 của repo, không suy model MCU thật từ build thành công.

## Việc tiếp theo và giới hạn của helper hiện tại

1. Nối lại Pi, xác định kết nối nạp/target cho binary cụ thể. Người dùng
   trước đó yêu cầu giữ firmware đang có; cần chấp nhận việc thay firmware
   để áp profile mới. Chuẩn bị này không ghi flash hoặc bật motor.
2. Sau nạp logic-first, kiểm marker profile, boot disabled, raw sensors và
   enable/disable/watchdog với nguồn công suất được kiểm soát. Kiểm nút đỏ
   theo thao tác vận hành thực trước chuyển động đầu; không coi compile/test
   là thay thế phép kiểm này.
3. Chuẩn bị backend Pi riêng cho keyboard: gate disabled trước arm; trace
   zero → enable request → status ack, rồi gate cho teleop; zero → gate
   disabled → firmware disable khi kết thúc. Một owner `/motor_enable`,
   keyboard không phát trực tiếp final `/cmd_vel`.
4. Bảo đảm final zero còn được monitor publish trong cửa sổ arm. Config cũ
   `stop_pub_timeout=1.0` có thể im lặng khi zero kéo dài, nên không giả định
   cứ bật stack cũ là có fresh-zero để enable. Cần kiểm trace thật, không
   bypass monitor hoặc tự chế executed target.
5. Chỉ sau khi backend/profile mới được kiểm mới dùng keyboard và collector.
   Helper `run_trial.sh` cũ vẫn yêu cầu arm ngoài Pi và không phát motor
   enable; chưa tương thích tự động với luồng ROS-only mới. Chưa xóa guard
   để làm xe chạy. Một lượt tiến–zero vẫn là commissioning trước pilot ID.

Hướng nghiên cứu governor/RL không thay đổi bởi bản firmware chuẩn bị này;
chưa có dataset chuyển động mới hoặc evidence sim-to-real.
