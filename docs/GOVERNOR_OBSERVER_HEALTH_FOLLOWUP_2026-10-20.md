# Observer health và cadence follow-up — 20/10/2026

**Kết quả thực thi:** dừng sau attempt 1/12 vì logger chưa close/provenance
không đạt. PI đã đến đích và dừng, nhưng sidecar bị SIGINT thứ hai cắt ngang.
Slots 2–12 không chạy; không resume hoặc cấp rescue budget. Đã sửa shutdown
offline sau đó và xác nhận bằng 49 tests cùng hai synthetic ROS checks không
Gazebo. Xem [tiến độ và giới hạn](GOVERNOR_AUTONOMOUS_PROGRESS_2026-10-20.md).

## Phạm vi được chốt trước chạy

Người dùng yêu cầu tiếp tục các bước được gợi ý. Thực hiện health telemetry
của observer trước; chỉ mở **một batch mô tả mới tối đa 12 attempts**, không
resume hoặc thay thế ba slot chưa chạy của batch cũ. Dừng trên integrity
fault; không mở rescue budget, tuning, predictor hoặc PPO tự động.

Thí nghiệm cadence/hình học giữ như trước: hai scenario seed 77600/77601,
ba controller PI/100 ms/20 ms, hai lần lặp mỗi block. Đây là **lượt mới trên
scenario đã xem**, không gọi là unseen validation. Schedule và phép phân
tích không đổi. Ngưỡng 10%/+0,5 giây tiếp tục chỉ là đề xuất.

## Thay đổi duy nhất: observer health

- `ObserverHealth` dùng monotonic clock, ghi entry/exit mỗi outer callback,
  duration conversion/sanitize/JSON encode/raw write/event write/flush/metadata.
- Contact callback gọi `record` bên trong vẫn chỉ tính một ROS callback;
  không tạo publisher, thread điều khiển hoặc thay command ownership.
- Record health nằm trong RAM khi thu thập; sidecar ghi **sau khi collection
  dừng**, không flush health file trong sensor callbacks. Có overhead CPU/RAM,
  không tuyên bố instrumentation miễn phí hoặc bảo đảm không lặp gap.
- Buffer tối đa 100.000 health records. Overflow, error, sidecar thiếu hoặc
  truncate làm integrity fault; không silently evict hoặc đổi sampling.
- Không đổi QoS/depth, tần số raw/contact, filter, PI, limits, physics,
  governor target/ramp/hold/detector, native scoring hoặc coverage 98%.
- Callback interarrival gap không tự phân biệt thiếu delivery với scheduling.
  Một duration stage dài định vị được nơi mất thời gian nhưng vẫn có thể
  bao gồm descheduling trong stage, không tự chứng minh disk là nguyên nhân.

## Kiểm tra offline

**47 tests đạt**: injected write/flush/conversion stalls, service gap không có
work chậm, nested callback, exception, explicit overflow, sidecar truncation
và source drift, byte-for-byte raw sensor/state/contact parity với executed
logger cũ. Kèm cadence/scoring/core tests đã có. Không ROS node/simulation
trong fault-injection tests. Source runtime diff trước batch chỉ có
`governor_logger.py` và module `observer_health.py` mới.

Protocol SHA256:
`c4eed1d079e7e4e57be8da2d3506016fbd3ec573af68f84db32e3ee8a66f3ebd`.
Release mới được ghi trước launch; domain 131, partition riêng. Dữ liệu,
release và failure batch cũ giữ nguyên.

## Artifacts

- [Protocol](governor_observer_health_followup_2026-10-20/protocol.json).
- [Release](governor_observer_health_followup_2026-10-20/execution_release.json).
- [Verification](governor_observer_health_followup_2026-10-20/verification.json).
- [Ledger](/home/tuanmac/ninorobot/rl_runs/governor_observer_health_followup_2026-10-20/ledger.json).
- [Health analysis tool](governor_observer_health_tools_2026-10-20/analyze_health.py).
- [Failed-batch analysis](governor_observer_health_followup_2026-10-20/failed_batch_analysis/report.json).
- [Synthetic ROS shutdown check](governor_observer_health_followup_2026-10-20/synthetic_ros_shutdown_check/result.json).
- [Synthetic ROS writer-stall check](governor_observer_health_followup_2026-10-20/synthetic_ros_stall_check/result.json).

Protocol/source snapshot ở trên là **phiên bản đã chạy và thất bại**. Shutdown
correction sau batch là revision mới, không đổi hash protocol/release cũ và
không làm attempt 1 trở thành hợp lệ hồi tố.
