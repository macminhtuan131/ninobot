# Nino — hiện trạng sau capture đứng yên v2

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

> **Bước hiện tại:** đợt đo độ lặp riêng tối đa3lượt mới đã chốt và kiểm readiness,hiện0/3. [Profile và lệnh lượt1](NINO_CLEAR_FLOOR_REPEATABILITY_2026-11-02.md). Phiên complete cũ giữ riêng; review trước mỗi lượt tiếp.


> **Kết quả mới nhất:** phiên dọn vùng thử đã thu1/1,data gate vàprimaryđạt;operator đã xác nhận và phiên complete1/1. Không chạy lại helper. [Kết quả](NINO_CLEAR_ZONE_MOTION_RESULT_2026-11-02.md).


> **Bước hiện tại:** một capture mới sau khi dọn vùng thử,0/1;guard kiểm scan/vùng trống5s trước cấp session. [Lệnh thu mới](NINO_CLEAR_ZONE_MOTION_READY_2026-11-02.md). Pilotv3 vẫn đóng1/3,không dùng lại helper cũ.


> **Kết quả mới nhất:** v3 đã đóng1/3;raw đạt nhưng primaryunknown do StopZone can thiệp. Người dùng xác nhận có người/đồ vật phía sau. Không chạy lại slot2/3. [Đánh giá và bước tiếp theo](NINO_WHEEL_REPEATABILITY_PILOT_V3_RESULT_2026-11-02.md). Nội dung cũ bên dưới là lịch sử.


> **Bước mới nhất:** pilot chuyển động v3 đã được yêu cầu, triển khai và kiểm readiness trên boot49371bb8; hiện0/3. [Lệnh thu lượt1](NINO_WHEEL_REPEATABILITY_PILOT_V3_2026-11-02.md). Các pilot cũ giữ đóng; chưa chạy motion v3.


**Capture recorder đã đạt:** stationary_closure_v2_20261102T085404983306Z,
22/22hash,SQLiteok,metadata20.749message,requiredchannels đủ55..60s.
Bag/audit/supervisor exit0,khôngforcedshutdown. Một capture đủ, chưa chứng
minh chống mất điện hoặc motion coverage. Có thể dừng lặp standing smoke.

Hardware sensor/TF đã tích hợp; có một motion feasibility RC AUTO trước đó,
nhưng pilot repeatability chưa hoàn thành. Old motionv1/v2 giữ stopped1/3,
không chạy lại các slot đóng. Body/slip reference và governor benefit còn thiếu.

**Bước đề xuất:** protocol mới1condition×tối đa3lượt, cùng0,05m/s,ramp0,10m/s²,
source2s,bag60s; firstslot là integration trong ngân sách, review từnglượt.
Chưa release hoặc thực thi. Sau pilot mới xét body reference; chưa tuning/PPO.

Báo cáo workspace: `artifacts/stationary_closure_v2_evaluation_2026-11-02/REPORT.md`;
metrics: `results.json`; proposal: `NEXT_MOTION_PILOT_DRAFT.json`.

Giữ nguyên thư mục bag WAL cùng.db3/.db3-wal/.db3-shm và metadata/hash.
Người dùng báo manualreboot trong stationaryv1, nên không coi đó là chứng
minh Pi/collector tự lỗi. Undervoltage lịch sử chưa được xác nhận đã xử lý.
