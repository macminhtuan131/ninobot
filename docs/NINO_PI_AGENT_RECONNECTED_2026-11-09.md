# Pi .103 — Agent đã nối lại, cần cập nhật bằng chứng real

Ngày 09/11/2026. Thao tác theo yêu cầu bật lại Agent của người dùng.

## Đã thực hiện và kiểm trực tiếp

- SSH vào `d@192.168.0.103`; STM32 USB `0483:5740`, serial `317136523233`,
  `/dev/ttyACM0`, alias `/dev/stm32_robot`. LiDAR adapter CP210x ở ttyUSB0.
- Không có Agent/owner serial trước launch. Chỉ khởi động micro-ROS Agent,
  serial 921600, domain 0, qua environment `~/nino-real-test/scripts/env.sh`.
  Agent native thực nằm trong `~/pi5-stm32-slam/.agent_ws/install/`.
- Wrapper lịch sử còn trỏ `pi5-stm32-slam-main` không tồn tại; không dùng lại
  wrapper đó và không ghi đè lịch sử. Tạo launcher/log mới riêng.
- Observer chỉ subscribe khoảng 10 s: IMU 409 mẫu, wheel 409, status 409;
  rate trên cửa sổ mẫu khoảng 46,8 Hz, receipt gap lớn nhất khoảng 26,9 ms.
  IMU debug 41 mẫu, khoảng 4,68 Hz. IMU/wheel values đã kiểm không nonfinite.
- Raw status trong cửa sổ đều 35; không dùng nó làm xác nhận nguồn/mode/RC
  hoặc quyền motor thực. Không thấy publisher `/cmd_vel`, `/cmd_torque`,
  `/cmd_mit`, `/motor_enable` trong snapshot cuối. `/scan_raw` chưa publisher.
- Disk Pi còn khoảng 11 GiB. Không enable, velocity/torque command, flash,
  bridge/EKF/Nav2/controller launch hoặc thu trial trong thao tác này.

Log/verification phía Pi:
`~/nino_runtime/agent_reconnect_20261109T122109963597Z/`.
Bản launcher/verification đã tải về client:
`artifacts/pi_agent_reconnect_2026-11-09_103/`.

## Phát hiện mới làm thay đổi kế hoạch real

Bảng real trên laptop trước đây chỉ tổng hợp dữ liệu đến 02/11. Pi hiện có
repo `~/nino-real-test` với source/config/results mới đến 08/11. Đã đọc
`AGENTS.md`, environment, hardware config, tài liệu INTEGRATION và hardware
contract, một số RESULT/MANIFEST JSON; chưa kiểm hash/raw toàn bộ hồ sơ này.
Vì vậy đây là **bằng chứng báo cáo/source vừa phát hiện**, chưa phải tái xác
minh toàn bộ experiment hoặc current actuator readback.

- Repo này dùng **PI/SAC residual torque, observation 23D**. Không đồng nhất
  với TD3 velocity-reference/history hoặc common103 đang train ở repo chính.
  Không copy gain/mode/checkpoint/config giữa các nhánh.
- Có test riêng từng bánh khoảng hai vòng và xác nhận operator về dấu tiến.
  Đây là bằng chứng mới hơn câu “chưa xác minh dấu/mapping” trong bảng cũ;
  cần nối hồ sơ với firmware/config, chưa suy body motion trên sàn.
- Watchdog test `watchdog400_verify_srt9tm5y/RESULT.json` báo passed:
  detect 401/402 ms và CAN TX 403/404 ms theo MCU clock; zero-torque-only,
  disabled observed. Đây không phải mechanical stopping time. Có cả lần
  failed được giữ; không chỉ chọn kết quả passed.
- `firmware_status50_20261108_i03_joab/MANIFEST.json` báo flash/verify,
  status period 20 ms. Bản kiểm `status50_imu_check_o4jc81sn` báo status,
  feedback/IMU khoảng 46,85 Hz, phù hợp quan sát live hôm nay. Chưa readback
  flash hiện tại để xác nhận binary identity.
- Có **8 thư mục phiên real_data/sac80k** ngày 08/11, có bag/config/controller/
  measurements. Cả 8 `outcome.json` đọc được hiện để null outcome và stop
  reason. Không gọi chúng là 8 lượt thành công hoặc 8 dataset hợp lệ.
- IMU mounting/geometry/clock của repo mới cần đối chiếu riêng; không áp
  yaw +90°/TF từ phiên cũ lên source hiện yêu cầu mounting identity.

## Việc tiếp theo theo thứ tự

1. **Đối chiếu dữ liệu mới trước khi thu thêm:** inventory 8 phiên, closure,
   bag metadata/hash, controller/config/firmware identity, error/abort và
   annotations/measurement. Kết quả nào chưa có thì giữ unknown. Tải bản
   cần thiết về laptop theo dung lượng, không xóa raw trên Pi.
2. **Chốt backend cho đợt real tiếp:** ghi rõ đang đánh giá PI/SAC torque
   của repo Pi hay velocity backend phục vụ TD3. Đây là hai contract khác;
   không dùng helper velocity cũ cho torque campaign chỉ vì Agent đã lên.
3. Sau review, khởi động **sensor-only** LiDAR/bridge/estimator đúng repo đã
   chọn, kiểm ownership/TF/frame/clock/STOP. Hiện Agent ready chưa là motion
   readiness hoặc localization readiness.
4. Nếu các session mới chưa trả lời được physical consistency/độ lặp,
   chuẩn bị protocol bổ sung tối thiểu. Không có camera thì mốc/thước cho
   displacement đầu-cuối; chưa có reference theo thời gian thì không claim
   slip/body latency/path error độc lập. Không tự mở lại slot cũ hoặc thêm
   controller comparison khi outcome/measurement còn thiếu.

**Bước ngay:** review/inventory các phiên 08/11 của `nino-real-test` để sửa
bảng “đã có/còn thiếu”, thay vì yêu cầu lặp lại thử bánh/watchdog đã có hồ sơ.
