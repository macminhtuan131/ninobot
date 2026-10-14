# Governor v1 — implementation verification

Đây là bản ghi kiểm chứng phần mềm, không phải kết quả H2/H3 hoặc sim-to-real.

- `bounded_native_check.json`: 25 bước reactive PI; scale xuống 0.70 nhưng
  trigger ở x≈0.215 m, trước cáp x=2.9 m. Không gọi đó là phản ứng contact đúng.
- `native_logger_metadata.json`: instrumentation cuối có 7 component;
  bracket/chassis không có message trong đoạn kiểm tra. Logger đóng sạch.
- `full_speed_failed_episode.csv`: full-speed reference rollover ở 19.70 s;
  failure vẫn được giữ. Episode dùng instrumentation 4 bánh trước bản cuối.
- `full_speed_analysis.json`: phân tích offline timing/coverage từ episode
  thất bại; giữ missing data, không ngoại suy qua gap IMU dài.
- `pi_pipeline_launch.log`: optional Pi pipeline chạy trên máy phát triển;
  governor/gate disabled, Collision Monitor active, không có smoother thứ hai.

Bộ test cuối: **59 passed**. ROS wrapper với feedback giả kiểm tra slowdown,
recovery, stale-data stop, reset và command ownership. Native smoke kiểm tra
clock/ramp/feedback; chưa xác nhận crossing benefit. Gazebo có lỗi shutdown
segfault sau kiểm tra; process đã đóng và raw logs giữ trong `/tmp`.

Hướng dẫn và giới hạn tại [Governor v1](../NINO_REACTIVE_GOVERNOR_V1_2026-10-14.md).
