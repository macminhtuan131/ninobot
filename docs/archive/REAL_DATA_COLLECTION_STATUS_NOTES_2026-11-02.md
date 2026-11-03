# Thu thập dữ liệu robot thật Nino — Ubuntu 24.04 / ROS 2 Jazzy / Pi 5

> **Lượt kiểm startup fix mới sẵn sàng 0/1 (02/11/2026).**
> Chỉ dùng `~/nino_runtime/wheel_startup_verification_20261102_v1/`.
> Profile cũ 0,05m/s, ramp0,10m/s², source2s, bag60s; có disable→enable ACK
> mới. Hướng dẫn `docs/NINO_WHEEL_STARTUP_VERIFICATION_2026-11-02.md`.
> Cần đối chiếu bánh/thân bằng mốc/video. Chưa chạy motion; các đợt cũ vẫn đóng.

> **Bản sửa helper khởi tạo đã chuẩn bị, chưa thử chuyển động trên robot.**
> Đầu V2 enable bit đã bật sẵn; helper cũ chấp nhận trạng thái đó như ACK mới.
> Candidate mới buộc gate off → zero → disable có ACK mới → baseline → enable
> có ACK mới; xem `docs/NINO_WHEEL_STARTUP_FIX_2026-11-02.md`.
> 44 tests +15 mock cases đạt, copy lên Pi riêng; chưa release motion budget.
> Đây là lỗi khởi tạo được xác nhận, chưa chứng minh nguyên nhân xe không tiến.

> **Cập nhật sau v2 lượt 1: đợt đóng 1/3, review unknown; hai slot còn lại đóng.**
> Session `clear_floor_repeatability_v2_20261102T102247471316Z`: raw/hash/SQLite
> và primary số học đạt. Final có lệnh tiến; scan cửa sổ thử không có điểm
> trong vùng StopZone. Người vận hành xác nhận xe không tiến dù reported
> motor feedback thay đổi. Chưa giải thích được chuyển động bánh/thân.
> Không bypass LiDAR hoặc chạy các lệnh thu bên dưới. Báo cáo workspace:
> `artifacts/clear_floor_repeatability_v2_evaluation_2026-11-02/slot1/REPORT.md`.

> **Đợt mới v2 sẵn sàng 0/3, ngày 02/11/2026.** Giữ profile 0,05 m/s,
> ramp 0,10 m/s², source 2 s, raw 60 s; thêm trial scene/STOP abort supervision.
> Chỉ dùng runtime `~/nino_runtime/clear_floor_repeatability_20261102_v2/`.
> Hướng dẫn: `docs/NINO_CLEAR_FLOOR_REPEATABILITY_V2_2026-11-02.md`.
> Chưa chạy chuyển động. V1 đóng 1/3 và hai slot còn lại giữ đóng.

> **Cập nhật sau lượt 1 — đợt đã đóng 1/3, hai slot còn lại đóng.**
> Session `clear_floor_repeatability_20261102T100409043176Z`: raw/hash/SQLite đạt,
> nhưng Collision Monitor STOP suốt đoạn tiến, final `/cmd_vel` luôn zero.
> Người vận hành xác nhận xe không di chuyển và có người/đồ vật sát phải/sau phải.
> Primary unknown; không chạy lại các lệnh thu bên dưới. Bước tiếp theo là kiểm
> vùng quét read-only với người/laptop ở vị trí thao tác thực tế; chưa motor trial mới.
> Đã lưu báo cáo workspace `artifacts/clear_floor_repeatability_evaluation_2026-11-02/slot1/REPORT.md`.

> **Bước hiện tại:** đợt đo độ lặp riêng tối đa3lượt mới đã chốt và kiểm readiness,hiện0/3. [Profile và lệnh lượt1](../../../docs/NINO_CLEAR_FLOOR_REPEATABILITY_2026-11-02.md). Phiên complete cũ giữ riêng; review trước mỗi lượt tiếp.


> **Kết quả mới nhất:** phiên dọn vùng thử đã thu1/1,data gate vàprimaryđạt;operator đã xác nhận và phiên complete1/1. Không chạy lại helper. [Kết quả](../../../docs/NINO_CLEAR_ZONE_MOTION_RESULT_2026-11-02.md).


> **Bước hiện tại:** một capture mới sau khi dọn vùng thử,0/1;guard kiểm scan/vùng trống5s trước cấp session. [Lệnh thu mới](../../../docs/NINO_CLEAR_ZONE_MOTION_READY_2026-11-02.md). Pilotv3 vẫn đóng1/3,không dùng lại helper cũ.


> **Kết quả mới nhất:** v3 đã đóng1/3;raw đạt nhưng primaryunknown do StopZone can thiệp. Người dùng xác nhận có người/đồ vật phía sau. Không chạy lại slot2/3. [Đánh giá và bước tiếp theo](../../../docs/NINO_WHEEL_REPEATABILITY_PILOT_V3_RESULT_2026-11-02.md). Nội dung cũ bên dưới là lịch sử.


> **Bước mới nhất:** pilot chuyển động v3 đã được yêu cầu, triển khai và kiểm readiness trên boot49371bb8; hiện0/3. [Lệnh thu lượt1](../../../docs/NINO_WHEEL_REPEATABILITY_PILOT_V3_2026-11-02.md). Các pilot cũ giữ đóng; chưa chạy motion v3.


**Hiện trạng mới nhất 02/11/2026:** capture đứng yên v2 đã đóng sạch và
đạt metadata/hash/integrity, đủ telemetry cuối55..60s. Đã có một lượt
motion feasibility RC AUTO hợp lệ trước đó; repeatability chưa hoàn thành.
Các pilot cũ đã đóng, không dùng helper cũ để chạy lại.
[Xem hiện trạng và bước đề xuất](../../../docs/NINO_CURRENT_STATUS_2026-11-02.md).
Các cập nhật28/10 bên dưới là lịch sử. Giữ nguyên thư mục bag gồm WAL/SHM
nếu có; không chỉ copy riêng.db3.


**Cập nhật 28/10/2026:** đã có các phiên sensor/STM32/LiDAR thật ngày
27/10 được kiểm raw/hash và đối chiếu bridge; xem
[báo cáo hiện trạng](../../../docs/NINO_PROGRESS_AND_NEXT_STEPS_2026-10-28.md).
Bước kế tiếp là [wheel response trên sàn sạch](WHEEL_RESPONSE_PROTOCOL.md)
với profile và session form riêng. Dataset motion này chưa được thu;
profile full/navigation giữ required cũ. `--check` chỉ kiểm đầu vào/kế hoạch,
không chứng minh command ownership, coverage hoặc motion readiness.

**Điều khiển từ laptop khi thu:** xem
[LAPTOP_CONTROL_AND_COLLECTION.md](LAPTOP_CONTROL_AND_COLLECTION.md) cho helper
SSH keyboard, mapping/Nav2/RViz, build trên Pi và quy trình vừa lái vừa ghi.
Collector vẫn chỉ đọc; điều khiển được khởi động/bật riêng bởi người vận hành.

