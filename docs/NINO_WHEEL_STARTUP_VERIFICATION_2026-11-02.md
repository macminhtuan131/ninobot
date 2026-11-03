# Thu một lượt kiểm bản sửa khởi tạo — 02/11/2026

> **Đã failed/closed1/1 trướcforward vì check tênendpoint. Không chạy lại lệnh bên dưới.**
> Xem [hiện trạng03/11](NINO_REAL_DATA_STATUS_2026-11-03.md).
> Phần chuẩn bị dưới đây là lịch sử; candidateendpointfix chưarelease motion.

**Sẵn sàng 0/1 lượt**, operator khởi chạy. Không dùng lại slot V1/V2 đã đóng.
Runtime duy nhất: `~/nino_runtime/wheel_startup_verification_20261102_v1/`.

## Mục tiêu và profile

Kiểm startup gate-off/zero/disable ACK mới → baseline zero2s → enable ACK
mới → source0,05m/s target2s → zero/disable/quan sát3s. Ramp tham chiếu
0,10m/s², raw bag60s. Giữ firmware, control/StopZone và primary như cũ.
Không chỉnh gain/current hoặc thử vật cản. Một lượt này không là đợt đo độ
lặp và không tự chứng minh nguyên nhân của kết quả trước.

## Chuẩn bị thao tác

Giữ RC AUTO, nguồn motor ở trạng thái đã kiểm, xe yên trên vùng sàn trống.
Chuẩn bị ba terminal trên Pi trước khi start stack. Giữ người/laptop/dây
ngoài vùng sát xe trong suốt phiên.

Đặt mốc dễ thấy trên sàn cạnh thân xe, không trong đường bánh. Quay video
nhìn được bánh chủ động và mốc thân/sàn; đặt camera ngoài vùng sát xe, bật
quay trước terminal3, để quay tới sau dừng. Ghi tên video trong metadata nếu
đã biết, nếu không ghi unknown. Mốc/video để phân biệt bánh quay, thân tiến
và quan sát thiếu chuyển vị ngắn; chưa có calibration/sync thì không suy
body-speed/slip/stopping time chính xác.

## Ba terminal — chỉ một lượt

Terminal1:

```bash
bash ~/nino_runtime/wheel_startup_verification_20261102_v1/start_stack.sh
```

ChờREADY, giữ mở. Trong khoảng30s sauREADY, terminal2:

```bash
bash ~/nino_runtime/wheel_startup_verification_20261102_v1/record_wheel.sh
```

NhậpAUTO khi đúng điều kiện; dòng pose/caster/video mô tả thực tế hoặcunknown.
Khi terminal2 báoOutput/bắt đầu ghi, terminal3 chạyngay:

```bash
bash ~/nino_runtime/wheel_startup_verification_20261102_v1/run_trial.sh
```

Dù trial báo lỗi, để recorder60s tự kết thúc, không reboot/cắt nguồn; sau
đóng/sync/FINISHED thìCtrl+C terminal1. Gửioutput terminal2/3, đường dẫn session,
video và mô tả bánh có quay/thân có tiến/tự dừng/lệchgiật/can thiệp. Không chạy
lại. Preallocationfail chưa tiêu slot nhưng cần đọc lỗi trước thao tác tiếp.
Khi đã cấp slot, failure/unknown giữ lại và đóng; không retry/replacement.

## Dữ liệu và review

Required source/selected/smoothed/final, enable, status, raw motorfb, rawIMU,
scanraw/TFstatic. Monitorstate là sparseevent. RawCDR/SQLite/hash/metadata/closure
kiểm trước báo response. Event thêm firmware_disabled_before_baseline_ack và
ACK enable mới; statusbit không là readback mode/power/effectiveRC.

Đối chiếu riêng reported wheel và quan sát thân. Primary số học giữ windows
baseline−2..0/primary+1,25..1,75s, support100ms bánh/200ms lệnh, plateau final
0,05±1e-6m/s; không chọn lại cửa sổ hoặc bỏspike. Không có forwardanchor thì
primaryunknown. `source_sequence_completed` không xác minh motion vật lý.

## Bằng chứng chuẩn bị

44 unit tests +15 production mock cases đạt; có test budget1 không cấp lượt2,
trạng thái enable có sẵn, disableACK timeout, STOP/scanstale và cleanup.
File-only trênPi đạt; zero-only check `20261102T104139057193Z` đạt: lifecycle
active, scene34scans/5,183s/maxgap0,460s/maxpoints0, finalzero mới; launchexit0,
khôngsource hoặc enable request. Maxgap đạt rule0,5s, không đồng nghĩa stream
không bao giờ gap; readiness/guard kiểm lại khi thu.

24frozenhashes kiểm trênPi; boot49371bb8-0556-4e1d-9479-224d0b909d24.
Contract `wheel_startup_single_verification_20261102_v1`, SHA256:
`e2fb14e3047b12b91cb00dda9ccb3041cd360805812e2122fd272eb6a470bbc2`.

Assistant chưa chạy enable/forward; zero stack đã đóng. Firmware và các
ledger cũ giữ nguyên, V1/V2 đều stopped1/3, hai slot còn lại đóng.
