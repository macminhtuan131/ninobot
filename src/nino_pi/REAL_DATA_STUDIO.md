# Nino Real Data Studio v7 — 04/11/2026

Mở launcher **Nino Real Data Studio**, hoặc `scripts/mode_gui.sh` như trước.
Giữ PyQt5 đang có; chưa chuyển toolkit sang PySide6. Trang mặc định mới
là **Studio · recorder chỉ đọc**. Trang commissioning cũ và authority nâng cao
được giữ riêng cùng ledger/cleanup, không phải chức năng của recorder Studio.

## Người vận hành bấm gì?

1. Điền Pi/SSH ở đầu cửa sổ. Bấm **Chuẩn bị observer trên Pi**: chỉ copy
   source/config vào namespace theo hash, không khởi chạy driver/Agent hoặc motor.
2. Chọn **kịch bản**, MCAP/SQLite, điền người vận hành và metadata. Chưa đo
   thì ghi `unknown`. Kịch bản chuyển động phải ghi ID protocol đã review;
   chọn kịch bản không cấp quyền chạy một trajectory mới.
3. Bấm **Kiểm sensor / storage / disk**. Bảng thể hiện message thực nhận,
   rate và tuổi receipt của observer, publisher; graph có tên không đủ đạt.
   Driver/Agent thật cần đang chạy. Studio không tự nối lại Agent/enable.
4. Xác nhận điều kiện và bấm **Bắt đầu ghi 60 giây**. Lệnh từ nguồn điều
   khiển đã được review được quan sát riêng; Studio không phát lệnh. Có thể
   đánh dấu sự kiện. Timestamp annotation là lúc observer nhận, không phải
   thời điểm contact chính xác.
5. Chờ process thực đóng và xem QC. **Dừng ghi không dừng robot**. Dừng sớm,
   mất heartbeat/SSH hoặc collector lỗi giữ phiên incomplete/FAIL; không retry.
6. Bấm **Tải phiên đã đóng**, xem QC tính lại tại laptop, **Mở kết quả** hoặc
   **Export Parquet**. **Các phiên đã tải** mở index SQLite local; index không
   thay raw hay tự xác nhận claim nghiên cứu.

Nút mới không đổi RC/AUTO, chiếm owner, ARM/DISARM, bật motor, gửi `cmd_vel`,
CAN/torque hay bypass Collision Monitor. Command safety/physical stop thuộc
nguồn điều khiển đang chạy và protocol của nó, độc lập với recorder.

## File thực tế

```text
~/nino_datasets/real/studio_<scenario>_<UTC>/
  session.json                 # identity, unknowns, protocol/controller metadata
  collection.json              # mapping required/optional theo claim
  preflight.json
  annotations.json             # receipt wall + monotonic anchors
  observer_lifecycle.json
  collector.log
  qc_report.json
  raw/
    bag/metadata.yaml
    bag/*.mcap | *.db3
    session.json, collection_config.json, qos.yaml
    manifest.json, sha256.json, audit/, *.log, power_timeline.json
```

Collector cũ được tái sử dụng, giữ cấu trúc `raw/bag` thay vì đổi layout của
các bag lịch sử. Raw đóng rồi không sửa; QC/import/export mới nằm ngoài raw.
Không đổi các pilot/bundle cũ, không mở lại slot. Studio dùng namespace
`studio_observer_v1_<content hash>`; upload cùng hash không reset phiên.

## QC: mức nào nghĩa gì?

| Kiểm tra | Kết quả / giới hạn |
|---|---|
| SHA256 + file ngoài index | mismatch/unhashed/missing → FAIL |
| Lifecycle + metadata + giải mã toàn bag | lỗi/thiếu/count mismatch → FAIL |
| Kênh required + giá trị động hữu hạn | thiếu/nonfinite IMU/wheel/Twist → FAIL; scan inf không tự là lỗi |
| Clock dynamic có header | timestamp lùi/zero → FAIL; duplicate được báo |
| Rate/gap/coverage | rate/gap thực được báo; expected Hz/loss/coverage chưa biết → WARN |
| Source clock/command semantics | Twist/status không header; thiếu execution/readback → WARN |
| Safety | giữ histogram status raw và CollisionMonitor action/polygon; không suy effective enable từ status bit |
| Feature/history/TD3 replay | chưa có mapping causal đầy đủ → chưa sẵn sàng |

Mỗi check có PASS/WARN/FAIL. Tổng phiên hiện tối đa **WARN/Q2** khi integrity
đạt nhưng claim còn unknown; lỗi → **FAIL/Q1**. Chưa tự gán PASS ứng dụng,
Q3/Q4, 95% coverage hoặc các ngưỡng độ lặp/thời gian dừng từ báo cáo đề xuất.
Observer counts/Hz không phải raw counts, source production hoặc packet loss.

## Export và phụ thuộc

MCAP dùng plugin `rosbag2_storage_mcap`; kiểm plugin trước ghi, không tự
đổi storage khi thiếu. Có thể chọn SQLite rõ ràng, bag lịch sử giữ nguyên.
Parquet cần `pyarrow` trong interpreter local; checkout này đã cài trong
`.venv`. GUI dùng interpreter đó cho export, không chạy learner trên Pi.
Nếu thiếu dependency, job báo lỗi giữ raw, không tạo dữ liệu giả.

Export `messages.parquet` là bảng dài: topic/type, bag receipt ns,
source header ns hoặc null, frame, JSON fields gốc. Invalid float được gắn
nhãn, không thay zero. Có export version/hash và checksum gốc. Chưa phải
`features.parquet`, observation History đã đồng bộ hay transition TD3.
Không random-split frame; SysID/evaluation giữ nguyên session/layout/condition.

## TD3 Parameter System

Tab **Xây project → TD3 · tham số có phiên bản** cho chọn/kiểm/sửa draft,
xem SHA256, lưu file mới và tạo effective config + actor ABI. Không tự chạy
training, thay job hiện hành hoặc mở authority. Catalog là
`src/nino_rl/config/td3_parameter_profiles.yaml`.

- Smoke h5: 32×32, replay 2048, warmup 16, batch 32; giữ job 128 bước riêng.
- Research h1/h5/h8: 256×256, replay 1M, warmup 10k, batch 256, ba seed đề
  xuất. Chưa có ngân sách train nghiên cứu hoặc kết quả so sánh h8.
- History 8 tại 10 Hz có span 0,7 s, không phải 0,8 s. Mỗi history có ABI
  riêng; checkpoint cũ không load được bằng cách đổi tên config.
- Action vẫn common/differential wheel-linear residual + projection đang
  được triển khai. Không âm thầm đổi sang direct v/omega hoặc mask/train-stat
  normalization. Hardware residual scale chưa đo giữ null, authority 0.
- SB3 hiện dùng một LR schedule; actor_lr khác critic_lr bị từ chối rõ.
- Profile sửa đổi thu hồi release/validation pointer; train cần validation
  đúng ABI/source/backend và budget riêng. Profile đúng schema không là
  evidence có ích hoặc release. Báo cáo runtime config được lưu cùng job.

Tiếp theo: review dữ liệu cũ/phiên phù hợp → wheel/body reference → SysID và
holdout → baseline/calibrated backend → nghiên cứu TD3/history → shadow.
