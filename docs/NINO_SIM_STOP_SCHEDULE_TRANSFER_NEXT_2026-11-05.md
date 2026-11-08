> **Cập nhật05/11:** dự thảo này đã được triển khai thành [protocol mới](NINO_SIM_STOP_TRANSFER_PROTOCOL_2026-11-05.md) và [đóng đủ6/6](NINO_SIM_STOP_TRANSFER_RESULT_2026-11-05.md). Phần dưới giữ nguyên nội dung trước chạy; không mở lại batch.

# Dự thảo Sim tiếp: chuyển lịch dừng đã biết sang6s

05/11/2026 · **Chưa triển khai/chạy hoặc mở budget.**
Sau [classical common comparison](NINO_SIM_CLASSICAL_COMMON_RESULT_2026-11-05.md),
câu hỏi duy nhất là candidate có còn tốt khi source stop thay từ8s sang6s?
Không tìm amplitude hoặc withdrawal đẹp hơn trên cùng dữ liệu.

- Giữ +0,005m/s, chỉ bật khi nominal steady0,2m/s. Viết rule
  `withdraw_at = planned_source_stop − 0,5s`, nên stop6s →withdraw5,5s.
  Đây là parameterization của kế hoạch dừng đã biết, không phát hiện gờ.
- **Hai arm**: B0 và classical; **ba fresh launches mỗi arm = tối đa6**,
  140 ticks/lượt, tổng840ticks. Thứ tự B0/classical/classical/B0/B0/classical.
  Ba lặp chỉ là pilot mô tả về một điều kiện mới, không statistical power
  hoặc ba learner seeds. Bỏ arm frozen TD3 đã có negative control ở hai batch.
- Giữ clear box, yaw0, source warmup0,5s, cruise0,2m/s, horizon14s, h5,
  estimator/follower/geometry/projection/ramp/PI. Đồng bộ stop6s ở backend,
  guidance, task scorer và candidate; không chỉ đổi một timestamp GUI.
- Root/task/module/protocol identity mới; giữ artifacts các batch cũ.
  Trước physics kiểm boundary5,4/5,5/6,0s, same nominal scorer, zero-source
  và stale/ownership/fault gates. Không nối hardware hoặc optimizer.
- Primary giữ whole-task14s nominal velocity RMSE. Giữ marker0,95m,
  quiet stop2s, maxpath40mm và estimate50mm/yaw0,05rad là engineering
  bounds đề xuất. Báo path RMSE và phase metrics riêng, không đổi primary.
  Chốt trước cả diagnostic GT-header grid20ms/dịch10ms như audit batch trước,
  không nội suy body; report riêng alignment/estimand. Đổi chiều theo cách
  đo hoặc chỉ effect nhỏ chưa có ý nghĩa ứng dụng →unknown, không promote
  chỉ từ native metric thuận lợi.
- Đọc từng lượt; chỉ xem là transfer signal mô tả khi cả ba classical RMSE
  thấp hơn cả ba B0 và không mất constraints. Minimum worthwhile effect
  vẫn null, không tự promote deployment hoặc claim generalization rộng.
- Effect chồng lấn/đổi chiều →unknown/giữ B0; failure vật lý/source/guidance
  đóng slot chưa dùng, giữ raw; không retry/thêm mẫu, hạ coverage hay tune.
  Tối đa một correction có nguyên nhân rõ và contract mới rồi quyết định;
  không tạo chuỗi calibration vô hạn. Candidate fail thì dừng nhánh này.

Không đợi dữ liệu thật cho phép kiểm Sim này. Hardware deployment, H2 khi
contact và yêu cầu ứng dụng vẫn gate riêng. Nếu candidate qua, ưu tiên dùng
baseline cổ điển có envelope hẹp làm đối chứng; chỉ mở learner mới khi có
remaining gap và cơ chế cần learning có thể kiểm chứng.
