> **Mới nhất06/11 — Reset drive ACK qualification đạt2/2:** candidate gate giữcap5s,20zero ticks,0actor/optimizer;68hashes/72support checks/closure đạt. ACK muộn mới kiểm bằngfixture,không suy general reliability. Tiếp thiết kế eval-only A/B0/cổ điển,khôngtrain mới. [Kết quả](NINO_SIM_DRIVE_READINESS_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

# Drive readiness — qualification zero-only có giới hạn

06/11/2026 · Correction riêng sau [V2 đóng lỗi](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md).

## Phạm vi và release

Một attempt tại `~/nino_research/sim_drive_readiness_v1`, 2fresh launches ×
10zero native ticks =20ticks, actor loads0, optimizer updates0, hardware0,
retry0, deadline900s. Đây là ngân sách qualification mới sau yêu cầu tiếp tục,
không dùng lại49slots V2. Source/runtime/parent manifest/test report được pin
trong release riêng;82software tests đã đạt trước release.

## Correction duy nhất

`DriveReadinessBackend` kế thừa backend frozen, chỉ thay predicate settling:
physical quiet **và** diagnostics fresh≤40ms, drive `have_wheel_state=1`,
executed reference/actuator target zero. Điều kiện liên tục0,5s trong cùng
cap5sim seconds; dùng nguyên chunk50ms và các gate physical cũ. Không đổi
PI/gain/reward/physics/QoS. Missing ACK không được đổi thành permission=true.

Fixture ACK muộn/không đến đã kiểm; không ACK thì fail ở đúng50setup rounds,
không có loop/retry ngoài cap. Task epoch chỉ tạo sau gate. Trước mỗi zero tick,
input phải fresh/permission thật; không bypass gate hoặc bịa status.

## Qualification thực

- Hai source-stop plans6/8s được khai báo, nhưng qualification gọi backend trực
  tiếp bằng **zero**; không nạp actor/controller để phát motion reference.
- Source reference tính trong view có thể khác zero sau warmup; nó chỉ là
  instrumentation trong bài này. Command thực được phát phải luôn `[0,0]`.
- Ghi initial view, settling rows/drive ACK, control attempts, final target,
  raw sensors, boundary checks hai observer, physics ACK/iterations và closure.
- Pass: cả2reset códriveACKtrướcdecision,20ticks/final reference/target zero,
  support/closure đạt. Một failure đóng phần còn lại; giữ raw.
- Không được gọi pass này là motion/task benefit, general reliability,
  contact envelope, learned benefit hoặc deployment readiness.

## Sau qualification

Nếu đạt: thiết kế eval-only checkpoint A seed11 đã hoàn tất, B0/cổ điển cùng
reset contract tại stop6/8. Không resume partial C, không tự mở ma trận train.
Nếu fail: giữ qualification đóng, review reason/unknown; không sửa gate hoặc
retry để lấy pass. GUI có profile/nút/kết quả riêng.
