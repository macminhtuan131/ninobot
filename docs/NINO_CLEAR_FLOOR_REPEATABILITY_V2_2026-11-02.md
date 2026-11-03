# Đợt đo độ lặp v2 — sẵn sàng lượt 1/3

> **Cập nhật sau v2 lượt 1: đợt đóng 1/3, review unknown; hai slot còn lại đóng.**
> Session `clear_floor_repeatability_v2_20261102T102247471316Z`: raw/hash/SQLite
> và primary số học đạt. Final có lệnh tiến; scan cửa sổ thử không có điểm
> trong vùng StopZone. Người vận hành xác nhận xe không tiến dù reported
> motor feedback thay đổi. Chưa giải thích được chuyển động bánh/thân.
> Không bypass LiDAR hoặc chạy các lệnh thu bên dưới. Báo cáo workspace:
> `artifacts/clear_floor_repeatability_v2_evaluation_2026-11-02/slot1/REPORT.md`.

Đợt mới riêng, hiện **0/3**; review từng lượt. V1 đã đóng ở 1/3 và giữ nguyên
hai slot còn lại đóng. Các đợt cũ không được dùng để bổ sung số lần lặp.

## Profile đã chốt

- Source tiến **0,05 m/s**, ramp tham chiếu **0,10 m/s²**.
- Source tiến **2 giây**, rồi zero/gate disable/motor disable; quan sát 3 giây.
- Thu raw **60 giây/lượt**, để recorder tự đóng và sync.
- Cùng vùng mới, tải, firmware, geometry/mounting và boot. RC AUTO.
- Giữ người, chân, laptop, dây và đồ vật ra ngoài vùng sát xe cả trước, sau và hai bên; giữ vị trí thao tác từ trước READY đến hết phiên.

## Thay đổi đã kiểm

Trial cần 5 giây scan hỗ trợ vùng trống, kiểm suốt baseline, ngay trước
request enable, ngay trước source tiến và trong tiến/ramp/quan sát. Bất kỳ
STOP nhận được từ lúc node trial khởi động đều được giữ thành lỗi cả lượt;
monitor trở về NONE không tự cho tiếp tục. Scan bị cũ/gap hoặc có từ 3 điểm
trong vùng kiểm cũng hủy bằng zero/gate disable/motor disable. Cleanup vẫn
chạy khi lỗi. Không tự resume/retry.

Đây là giám sát ROS bằng receipt/callback, không có bảo đảm deadline dừng
vật lý. Phép chiếu scan XY dùng TF khai báo là kiểm bảo thủ; Collision Monitor
vẫn là tầng chặn lệnh thật, polygon và cấu hình điều khiển không đổi. State
monitor là sparse event; thiếu event không được coi là readback NONE.

Primary, windows, support và mọi spike giữ nguyên. Nếu final reference không
đạt 0,05 m/s trong cửa sổ primary thì unknown, không chọn cửa sổ khác.
Nếu hủy trước forward, analyzer báo thiếu anchor/primary unknown thay vì lỗi;
không chạy exporter fixed-window khi không có forward anchor.

## Ba terminal trên Pi — chỉ chạy lượt 1

Chuẩn bị sẵn cả ba terminal và câu ghi pose/caster. Terminal 1:

```bash
bash ~/nino_runtime/clear_floor_repeatability_20261102_v2/start_stack.sh
```

Chờ `READY`, giữ mở. **Trong khoảng 30 giây sau READY**, terminal 2:

```bash
bash ~/nino_runtime/clear_floor_repeatability_20261102_v2/record_wheel.sh
```

Nhập `AUTO` và mô tả pose/caster thực tế, hoặc `unknown`. Khi báo Output và
bắt đầu ghi, terminal 3 chạy ngay:

```bash
bash ~/nino_runtime/clear_floor_repeatability_20261102_v2/run_trial.sh
```

Kể cả trial báo lỗi, để recorder tự kết thúc; không reboot/cắt nguồn giữa
phiên. Sau `FINISHED`, Ctrl+C terminal 1. Gửi output và quan sát xe tiến/tự
dừng/lệch/giật/can thiệp của chính lượt này. **Chưa chạy lượt 2 trước review.**

Preallocation fail thì chưa dùng slot; đọc lỗi để xử lý, không lặp để ép qua.
Khi đã cấp slot, abort/failure/unknown hoặc đổi boot/condition đóng phần còn
lại; không chạy bù. Sau 3 reviewed pass, báo từng giá trị và median/range,
chưa claim hiệu chuẩn, equivalence, body/slip hoặc hiệu quả governor.

## Bằng chứng chuẩn bị

- 43 unit tests, gồm fixture CDR/SQLite cho abort không có forward anchor.
- 13 production mock handoff cases, gồm STOP baseline, trước tiến, đang tiến,
  STOP rồi NONE, vật vào baseline và scan stale; không tạo ROS node/motor command.
- Regression trên raw cũ giữ nguyên command/wheel summaries.
- File-only validation trên Pi đạt, không cấp slot hoặc ghi session.
- Live zero-only check `20261102T101848618396Z`: smoother/monitor active;
  monitor action 0, 35 scans/5,171 s, max gap 257 ms, max points 0, final zero
  mới; launch exit 0 và đóng sạch. Không source/enable request.
- 24/24 frozen input hashes đạt; boot `49371bb8-0556-4e1d-9479-224d0b909d24`.

Contract `clear_floor_repeatability_3x_20261102_v2`, SHA256:
`a7ec35292da43066014cf9c76c406847776344e5e5a8fc009e03cff2b14f77f0`.

Artifact workspace: `artifacts/clear_floor_repeatability_v2_2026-11-02/`.
Các kiểm phần mềm/zero trên không phải thử robot tiến hoặc chứng minh dừng.
