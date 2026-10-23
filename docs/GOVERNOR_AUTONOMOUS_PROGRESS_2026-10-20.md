# Tiếp tục governor: observer diagnostics và điểm dừng — 20/10/2026

**Cập nhật 21/10:** [batch corrected logger](GOVERNOR_CORRECTED_LOGGER_CADENCE_2026-10-21.md)
đã xác nhận close/provenance/health dưới Gazebo ở attempt PI đầu. Batch mới
vẫn dừng 1/12 vì crossing joint/GT coverage 96,9% dưới gate 98%; không chạy
governor arm hoặc thay missing data. Nội dung 20/10 bên dưới là lịch sử.

## 1. Đã làm gì trong lượt tự tiếp tục

1. Tạo observer-only monotonic timing cho entry/exit callback và conversion,
   sanitize, JSON encode, write, flush, metadata write; buffer RAM có giới
   hạn và báo overflow/error rõ. Sidecar ghi sau collection.
2. Kiểm tra stalls giả lập, service gap, lỗi, overflow, truncate, source
   drift và byte-for-byte payload parity; 47 tests đạt trước live batch.
3. Freeze **một batch diagnostic mới 12 slots** theo yêu cầu tiếp tục của
   người dùng. Cùng PI/100 ms/20 ms và scenario như trước; không gọi là
   unseen test, không resume batch cũ. Only observer source changes.
4. Batch mới **hard-stop tại attempt 1**, PI full: physical arrival/2 s stop
   đạt, nhưng `metadata.complete=false`, thiếu health summary và provenance
   không đạt. Giữ failure instrumentation; 11 slot còn lại không chạy.
5. Tìm thấy bug shutdown của instrumentation mới: default ROS SIGINT làm
   context bắt đầu đóng khi executor còn đang take subscription; launcher
   gửi SIGINT nữa, cắt ngang sidecar serialization trong `close()`.
6. Sửa observer shutdown và kiểm tra lại **49 tests**, có test chính production
   main nhận SIGINT rồi SIGINT/SIGTERM ngay trong close; close hoàn tất trước
   destroy/shutdown. Có raw-payload parity, không sửa scoring.
7. Chạy hai fixture ROS cô lập dùng dữ liệu giả, **không Gazebo, không driver,
   không motor command và không kết nối robot thật**:
   - Hai SIGINT: return code 0, metadata complete, health valid, nhận được
     IMU/joint payload. Không claim hardware/sampling fidelity.
   - Inject writer stall 200 ms: đo được **200,151 ms**, nhận cả hai SIGINT
     và close hoàn tất. Đây là known-fault validation của telemetry, không
     chứng minh nguyên nhân gap attempt 9 lịch sử.

## 2. Bản sửa shutdown

Logger tạo ROS context với `SignalHandlerOptions.NO` và tự nhận SIGINT/
SIGTERM như yêu cầu dừng. Nó ngừng spin, close raw/event/health/metadata khi
context còn sống, sau đó destroy node/shutdown context. Signal lặp lại chỉ
cập nhật cờ, không ném KeyboardInterrupt vào giữa close. Handler cũ được
khôi phục khi thoát. Runtime exception thật vẫn được ghi và propagate;
sidecar lỗi không được coi là valid. Không tác động signal handler của PI,
driver, evaluator hoặc Gazebo; chỉ process logger.

Đây là correction lifecycle có bằng chứng từ traceback mới, **không phải
correction đã chứng minh cho gap 3,32 sim seconds của batch trước**. Phần
health telemetry trước gap lịch sử không tồn tại nên không thể khẳng định
writer hay scheduler gây gap đó.

## 3. Kết quả nào vẫn chưa đạt?

| Hạng mục | Trạng thái |
|---|---|
| Detector/governor/PI/physics/scoring | Giữ nguyên |
| Raw sampling và QoS/depth | Giữ nguyên |
| Coverage 98% | Giữ nguyên |
| Observer diagnostics | Có code và kiểm tra offline/synthetic ROS |
| Shutdown correction dưới Gazebo thật | **Chưa xác nhận** |
| Batch cadence 100 ms vs 20 ms hoàn chỉnh | **Chưa có** |
| Lợi ích physical speed/slip/rung của 20 ms | **Chưa chứng minh** |
| Ngưỡng 10% / +0,5 giây | Vẫn đề xuất |
| Predictor/PPO/Optuna | Giữ lại |
| Robot thật | Giữ lại |

Native outcome attempt PI mới vẫn success; observer GT coverage quan sát
được là 99,6386% và native replay khớp. Nhưng coverage tốt **không thay thế**
logger-close/provenance thất bại. Không dùng lượt này như quality-valid PI
reference, không tạo aggregate/CI từ một arm, không làm sạch partial sidecar
để hợp thức hóa. Partial health prefix chỉ có 862 record, không đại diện
cho cả run.

## 4. Vì sao dừng simulation ở đây?

Batch diagnostic chốt không tự mở rescue budget khi integrity fault. Giữ
nguyên điểm dừng: không reset/retry/bù attempt 1, không chạy slots 2–12,
không nối số liệu vào batch cadence cũ và không tạo chuỗi pilot không hạn.
Đã tiếp tục phần sửa và kiểm tra offline có thể làm mà không vi phạm điểm
dừng. Không triển khai predictor từ số liệu contact chưa có phép so sánh
đáng tin cậy.

**Chưa phải trạng thái chỉ còn thiếu dữ liệu thật.** Blocker trực tiếp vẫn
là xác nhận logger shutdown/coverage trong một protocol integration mới,
rồi thu được so sánh physical có thể tin cậy. Synthetic ROS checks giảm
rủi ro triển khai, không thay episode Gazebo hoặc H2 evidence. Không tuyên
bố cần robot thật để sửa một bug logging phần mềm.

Sau integration đáng tin cậy mới có cơ sở xem tiếp control-authority outcome.
Nếu intervention không có lợi ích hoặc kết quả chưa phân biệt được, dừng
cấu hình đó theo nghiên cứu; không ép phải train/tune chỉ vì pipeline chạy.

## 5. Khi nào dữ liệu thật sẽ cần thiết?

Để chuyển kết luận mô phỏng thành thiết kế governor triển khai, ít nhất cần:

- Đáp ứng command → wheel speed thực và giới hạn acceleration/braking/torque.
  Giá trị `effort`/lệnh torque không tự bằng mô-men đo trên motor.
- Hình học/caster/contact và kích thước, dạng vật cản thực để giới hạn miền
  mô phỏng vượt được; mô hình cylinder cứng chưa chứng minh dây mềm.
- Timestamp, mounting/orientation, noise và latency IMU/encoder trên phần cứng.

Chưa có những số đo đó thì vẫn có thể nghiên cứu cơ chế trong simulation,
nhưng không được nhận là đã sim-to-real, đã đảm bảo giới hạn an toàn phần
cứng, hoặc đã phù hợp mọi nền nhà máy. Phần robot thật vẫn on hold theo yêu
cầu; không thử chuyển động hoặc tự kết nối để lấy các số đo.

## 6. Artifacts

- [Follow-up protocol và trạng thái](GOVERNOR_OBSERVER_HEALTH_FOLLOWUP_2026-10-20.md).
- [Ledger diagnostic](/home/tuanmac/ninorobot/rl_runs/governor_observer_health_followup_2026-10-20/ledger.json).
- [Executor summary](/home/tuanmac/ninorobot/rl_runs/governor_observer_health_followup_2026-10-20/summary.json).
- [Synthetic shutdown](governor_observer_health_followup_2026-10-20/synthetic_ros_shutdown_check/result.json).
- [Injected stall](governor_observer_health_followup_2026-10-20/synthetic_ros_stall_check/result.json).
- [Observer source](/home/tuanmac/ninorobot/src/nino_rl/nino_rl/observer_health.py).
- [Logger source](/home/tuanmac/ninorobot/src/nino_rl/nino_rl/governor_logger.py).
- [Offline tests](/home/tuanmac/ninorobot/src/nino_rl/test/test_observer_health.py).

Source snapshot của batch thất bại không bị ghi đè bằng correction mới.
Correction và verification cuối được lưu riêng trong `offline_shutdown_fix/`.
