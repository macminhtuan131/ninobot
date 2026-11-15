# Velocity preflight và chuẩn bị offline — phần cứng để sau

Ngày 09/11/2026. Tiếp yêu cầu tự xử lý đến khi cần người vận hành.
**Cập nhật phạm vi cuối:** người dùng chưa cắm lại USB và yêu cầu kiểm các
phần khác trước. Phần cứng và mọi thu/thử robot được để sau; không cần thao
tác robot để hoàn tất các thay đổi offline bên dưới.
Không gửi enable, velocity/torque/MIT tới firmware; không đổi firmware,
gain/current/checkpoint hoặc TF mounting trong lần này.

## 1. Đã làm trước lần reboot tiếp theo

Pi .103 ban đầu ở boot `7f1f3519-70f0-4713-b81e-21bff8c8b867`.
Đã nối lại Agent domain0/serial921600 và khôi phục sensor-only theo cấu
hình đang cài. Không chạy teleop mặc định của repo Pi: launch đó không có
LiDAR/Collision Monitor, input limit0,50m/s khác profile diagnostic đã chọn.

Đã kiểm Collision Monitor thật đang cài bằng lifecycle configure/activate,
giữ cấu hình `FootprintApproach`, footprint từ local_costmap config
`[[0.26,0.21],[0.26,-0.21],[-0.26,-0.21],[-0.26,0.21]]`.
Chỉ thay namespace input/output/scan/footprint/state sang `/nino/preflight`.
Không nối output của monitor vào `/cmd_vel` firmware.

| Case | Input diagnostic | Kết quả |
|---|---|---|
| Live scan | Relay `/scan` thật, header giữ nguyên; reference diagnostic0,05m/s | Có output và scan thật; không tự gọi scene clear hoặc motion ready |
| Synthetic clear | Scan tổng hợp trống, frame base_footprint | Output0,05m/s trên các sample ổn định |
| Synthetic obstacle | Points tổng hợp trong configured footprint | Output zero trên các sample ổn định |
| Clear rearm | Scan tổng hợp trống trở lại | Output0,05m/s trở lại |
| Source stale | Ngừng relay scan test; vẫn gửi input diagnostic | Sau source-timeout1s và margin, output zero |

**5/5 integration cases đạt**, không phải năm thử robot/vượt gờ. Reference
0,05m/s chỉ ở topic diagnostic; không physical command. Snapshot trước/sau
không có publisher `/cmd_vel`, `/cmd_torque`, `/cmd_mit`, `/motor_enable`.
Monitor đã deactivate/cleanup/đóng exit0, không để guard test thành guard
đang bảo vệ robot. Đây không là physical stopping test hoặc chứng nhận safety.

`guard_preflight.py` và result/log/effective params lưu ở client
`artifacts/real_velocity_prepare_2026-11-09/guard_probe/` và Pi
`~/nino_runtime/real_prepare_20261109_v2/guard_probe/`.

## 2. Frame IMU: source giải quyết được gì?

Pi config hiện identity/xyz0; phép đo27/10 dùng yaw+90° và offsets gần đúng.
Source INS/ROS đã đọc ở checkout local chuyển accel/gyro theo physical sensor
axes; không có bằng chứng đủ để suy ra mounting mới bằng0 chỉ vì config ghi0.
Các hồ sơ firmware17/10 và07–08/11 thuộc nhiều build; chưa xác minh binary
hiện tại cùng INS mapping của checkout local. Không tự flash để trả lời.

Một gravity vector khi nằm ngang không phân biệt yaw0/+90°. Cần nhãn vật lý
khác hoặc bằng chứng mapping/mounting tương đương. Đã chuẩn bị bộ thu chỉ đọc:

- `collect_imu_frame.sh` / `.py`: LEVEL, NOSE_UP, LEFT_SIDE_UP, mỗi tư thế5s;
  ghi numeric IMU, CDR gốc, header/receipt, status, source/config hashes.
- Chỉ chạy khi operator xác nhận `DRIVE_DISABLED`; không tự disable motor,
  không publisher actuator và không sửa TF. Config được pin trước thu;
  thay config trong phiên làm phiên incomplete, không promote.
- `evaluate_frame.py`: so bốn coarse yaw candidates0/+90/−90/180 với rule
  đã ghi trước; signal quá nhỏ hoặc clock lỗi giữ unknown. Không tự áp TF,
  không fine calibration hoặc kiểm gyro scale. Bốn fixture về identity,
  +90°, thiếu signal và bad header đã kiểm; collector import/static/summarize
  checks đạt. `--check` trên Pi đạt, **chưa có capture manual mới**.
- Bộ thu đã đặt trên Pi trong `~/nino_runtime/real_prepare_20261109_v2/`.
  Dữ liệu tương lai tạo folder mới `~/nino_real_data/imu_frame_reconcile_<UTC>`;
  không ghi đè session27/10 hoặc session08/11.

Đây là đối chiếu một thay đổi contract cụ thể, không lặp calibration vô hạn.
Wheel-response-only có thể giữ IMU raw như context và không cần giải quyết
toàn bộ mounting trước khi fit reported wheel; nhưng History/actor dùng
body XYZ cần frame đúng trước deployment.

## 3. Sau reboot được người vận hành xác nhận

Người dùng xác nhận vừa reboot/ngắt nguồn hoặc đổi mạng. SSH .103 quay lại
với boot `62f15335-a41a-4107-b071-1e40b15a1a56`.

Đã chạy lại Agent và sensor-only launcher, nhưng **kiểm tra cuối không có
dữ liệu**: USB STM32 và adapter LiDAR không còn xuất hiện trong `lsusb`;
`/dev/stm32_robot`, ttyACM/ttyUSB/by-id tương ứng không có. Agent báo
`Serial port not found`; LiDAR driver đã thoát do không bind được port.
RSP/bridge/EKF process có tồn tại không đồng nghĩa sensor ready; cửa sổ probe
không nhận sample, odom TF không có. Không gán zero thay dữ liệu thiếu.

Vì vậy trạng thái cuối:

| Hạng mục | Trạng thái |
|---|---|
| SSH .103 | Truy cập được lúc kiểm cuối |
| Agent process | Chạy, **chờ USB**, chưa nhận STM32 |
| Sensor telemetry | **Không sẵn sàng** sau reboot |
| Guard qualification | Đã đạt ở boot trước trên namespace diagnostic, result được giữ |
| Guard đang bảo vệ motor | Không |
| Manual frame dataset | Bộ thu đã chuẩn bị, chưa thu |
| Motion readiness / authority | false /0; không có lượt motion mới |

Không quy lỗi mất USB cho firmware/nguồn/SD khi chưa có bằng chứng. Agent
có thể chờ cổng; sensor-only cần restart có kiểm soát sau khi USB xuất hiện,
không khởi thêm bridge/EKF trùng process đang còn sống.

## 4. Các thay đổi offline đã thực hiện

| Vấn đề | Thay đổi | Giới hạn |
|---|---|---|
| Studio dùng đường dẫn môi trường Pi cũ | Observer chọn env đang có theo thứ tự `nino-real-test`, `pi5-stm32-slam`, rồi tên cũ `pi5-stm32-slam-main`; thiếu cả ba báo lỗi | Chưa deploy/kiểm kết nối lại sau khi người dùng để phần cứng sang sau |
| Bag có tổng count đúng nhưng sai từng topic vẫn có thể qua | Collector và QC đối chiếu per-topic metadata counts | Metadata cũ thiếu trường này được báo chưa xác minh; không suy ra packet loss từ count |
| Đọc SQLite có thể tạo sidecar hoặc bỏ qua pending writes | Reader immutable chỉ nhận storage hoàn tất; WAL/journal không rỗng bị từ chối | Không sửa/reindex bag hỏng, không giải thích nguyên nhân hỏng SD/DB |
| Thu velocity và torque không tách rõ | Thêm `real_collection_velocity_sysid.json`, mục **Velocity SysID** trong Studio | Khai báo controller phải là `firmware_velocity_reference`; vẫn cần đối chiếu backend thật |
| Torque/MIT request có thể đổi mode ngay cả khi giá trị zero | QC FAIL nếu hai topic này có message trong phiên velocity-only | Đây là xung đột contract; không tự suy mode actuator từ topic hoặc status |
| Session đứng yên bị gắn loại SysID | Metadata lấy dataset kind từ scenario; đứng yên là `sensor_inventory` | Không biến inventory thành motor-response dataset |
| Camera bị hiểu là điều kiện bắt buộc | GUI phân biệt wheel response, endpoint bằng thước/mốc và reference theo thời gian | Endpoint không cho slip/body onset/latency |
| Export Parquet bị bỏ qua do PyArrow26 không tương thích NumPy1.26 tại môi trường hiện tại | Tách `.venv-studio-export`, pins NumPy1.26.4/PyArrow19.0.1; GUI ưu tiên interpreter riêng | Không thay dependency của `.venv` train; chỉ kiểm export bằng bag tổng hợp |

Profile mới yêu cầu raw IMU, wheel feedback, status, `/scan`, `/tf_static`
và final `/cmd_vel` trong bag. Source/selected/smoothed, enable và guard
state được giữ riêng nếu có. Các topic sự kiện không bị tạo message giả để
làm đủ schema. Muốn claim toàn command chain phải ghim các tầng thực sự
tồn tại thành required trong contract riêng. `/cmd_vel` là final ROS request,
không phải target readback hoặc thời điểm STM32 thực thi.

Preflight của profile này kiểm scan source `/scan` theo guard đã review,
plugin storage và dung lượng, không yêu cầu `/cmd_vel` phải có mẫu khi idle.
QC sau phiên vẫn yêu cầu `/cmd_vel`. Một preflight sensor đạt **không cấp
quyền chuyển động**. Profile giữ proposal0,05m/s, ramp0,10m/s²,source2s,
bag60s và `motion_released=false`; GUI không tự enable/phát trajectory.

## 5. Kết quả kiểm offline và dữ liệu đã có

- Suite cuối collector/Studio/quality/regression: **46 passed, không skip**
  trong interpreter export riêng, gồm roundtrip Parquet từ bag tổng hợp.
  Xem `offline_tests_final.log`. Suite đầu có44passed/1skip do xung đột
  PyArrow/NumPy; lỗi dependency này đã được xử lý riêng, không đổi môi trường
  train. GUI được render/kiểm ở chế độ offscreen, không mở SSH/ROS node.
- `offline_recheck.py` dùng reader mới trên bản sao tám phiên08/11:
  **6 hợp lệ /2 lỗi,313.555message ở sáu bag hợp lệ**, per-topic counts khớp.
- **431file** của gói review đã seal giữ nguyên hash trước/sau; gồm293file
  session. Không sửa raw, metadata hoặc outcome của phiên cũ.
- Hai bag lỗi vẫn bị giữ FAIL; SQL không đọc được không được thay count=0.
  Đây vẫn là các phiên PI/SAC torque lịch sử, không TD3 velocity replay.
- Không có capture/frame/motion dataset mới trong phần offline này.

Artifact ở client:
`artifacts/real_velocity_prepare_2026-11-09/` gồm scripts, guard result,
offline tests, đối chiếu bag, source/config snapshot và ảnh GUI.

## 6. Thứ tự tiếp theo khi người dùng mở lại phần cứng

Đây là kế hoạch để sau, **không yêu cầu thực hiện ngay**:

1. Xác nhận USB/sensor có sample thật sau reboot; chỉ restart process của
   stack được chọn, tránh bridge/EKF trùng owner. Snapshot graph không tự
   xác nhận command ownership cho cả phiên.
2. Đối chiếu frame hiện tại với hồ sơ cũ trước khi dùng IMU body XYZ cho
   History/actor. Bộ ba tư thế đã chuẩn bị chỉ là một lựa chọn; wheel-only
   response có thể giữ raw IMU như context, không buộc lặp toàn calibration.
3. Review và qualify chuỗi velocity/guard/owner trước một diagnostic với
   mốc/thước. Giữ profile hiện tại; recording contract chưa là motion helper
   đã release. Sau QC và quan sát mới quyết định có mở repeats hay không.

Các việc cần USB, phép đo body, gain/current, thử gờ, inference budget real
và deployment chưa được kết luận từ các kiểm offline này.
