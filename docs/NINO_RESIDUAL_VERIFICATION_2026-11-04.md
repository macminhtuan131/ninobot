# Kết quả kiểm triển khai residual — 04/11/2026

Đây là **[N] bằng chứng phần mềm/fixture**, không phải kết quả mới của robot thật.
[Thiết kế, file map, cách dùng GUI và roadmap](NINO_RESIDUAL_IMPLEMENTATION_2026-11-04.md).
[Ledger máy đọc được](NINO_RESIDUAL_VERIFICATION_2026-11-04.json) chứa đường dẫn,
manifest SHA256, source fingerprint và môi trường.

## Kết quả hiện hành

| Kiểm tra | Kết quả | Claim được phép |
|---|---|---|
| Focused regression suite | **64 passed** | Core, history, fault/time-limit, actor integrity, SysID fixture, Qt/workflow/quality gates |
| Colcon | **4 package build đạt**: control, description, pi, rl | Packaging/dependency build; không xác nhận driver robot |
| Gym checker và intervention trace | Đạt; khác biệt target norm ≈0,696 rad/s, wheel feedback ≈0,690 rad/s giữa hai proposal | Proposal thực sự đi vào reduced-order transition; không là H2/contact benefit |
| TD3 optimizer | 128 transitions ở checkpoint hiện hành; actor parameter L1 change ≈32,565 | `.learn()` và cập nhật policy đã chạy thật |
| PPO optimizer | 128 transitions; policy parameter L1 change ≈7,896 | Đối chứng learner cùng ABI đã chạy |
| Portable actor | TD3 error tối đa 5,96×10⁻⁸; PPO 4,66×10⁻⁹ so deterministic SB3 | Export NumPy đúng trong phép thử; chưa đo Pi inference deadline |
| ROS DDS fixture | 72 callback/kênh ×5; 26 trace history-ready; domain 119; 0 motor-command publisher từ observer | ROS callbacks → shared history → actor → diagnostic trace |
| Gazebo fixture | 40 transition, khoảng 4 sim seconds; GT tiến ≈0,216 m giữa snapshot đầu/cuối | Native velocity → joint/body có phản ứng trong world thử phẳng |
| SysID pipeline | 3 session **tổng hợp**, fit hai/holdout một; recovered delay 0,08 s; holdout RMSE trái ≈0,00091, phải ≈0,00760 rad/s | Công cụ register/read/fit/holdout/output chạy; không là tham số đo Nino |
| GUI | Đã render/đọc lại artifact; sáu bước software hiện đạt, SysID real/hardware chờ | Sơ đồ cập nhật bằng manifest/source/hash; không lấy số test làm % tiến độ |

Thư mục GUI mặc định: `/home/tuanmac/nino_research/residual_build_v1`.
Checkpoint, portable actor, TD3 replay và JSONL mỗi transition nằm trong
artifact `train-td3`/`train-ppo` được ledger dẫn. Dùng GUI xem đường dẫn cụ thể.

Các lần optimizer kiểm khi sửa ABI/provenance được giữ riêng, seed 7 lặp lại;
không gộp thành nhiều training seeds độc lập hoặc một training run dài.
Ngân sách mỗi job là 128 transitions; đây không phải nghiên cứu hội tụ.

## So sánh hiện hành nói được gì?

Trên **plant giả định xác định**, B1 yaw feedback giảm heading error so B0;
Governor gần B0 trên sàn sạch của fixture. TD3 smoke có return cao hơn nhưng
heading/lateral error tệ hơn. Điều này trực tiếp nhắc rằng return cao không
đủ để promote policy. **Không kết luận TD3 tốt/xấu hơn PPO nói chung hoặc
tốt hơn controller Nino.** Chưa tuned classical baseline, chưa calibrated
Nino plant, chưa payload/layout/contact generalization.

Seed ID 101/102/103 cho kết quả trùng ở default fixture vì không có nhiễu/
randomization vật lý đang bật. Chúng không là ba điều kiện vật lý độc lập;
không có CI hoặc claim power từ 15 hàng evaluator này.

## Các lỗi được giữ và correction

- Các lần ROS/Gazebo integration lỗi import/transport/kiểm publisher được
  lưu ở artifact ban đầu. Gazebo cuối dùng requester native tách khỏi Python
  subscriber callbacks; không nới gate ACK hoặc giả dữ liệu khi request fail.
- Source và YAML thay đổi làm artifact cũ stale; các lần kiểm cuối có cùng
  fingerprint hiện hành. Worker kiểm runtime của mình trước khi dùng artifact.
  GUI hệ thống hiển thị kết quả đã ghi trong môi trường artifact, không suy
  system Python có đầy đủ learner packages.
- Full test từng bắt lỗi demo: timer final-state và closure gần nhau có thể
  đảo thứ tự khi Qt bận. Đã gộp chúng thành một callback có thứ tự, thêm
  regression mô phỏng delivery muộn. Lượt fail XML giữ lại; sau correction
  **64/64 đạt**. Không sửa gate đóng recorder thật hoặc fake closure event.
- Không lấy latest successful pass để che latest failed/cancelled attempt.
  Lần lỗi/hủy mới nhất chặn gate cho tới một lần kiểm mới được review/chạy rõ.

Gazebo joint publication counts gồm cả publication lặp khi pause; không dùng
counts đó làm unique source rate hoặc loss-free coverage. Fixture không có
CyberGear target readback, nên trường readback vẫn `null`; body GT chỉ có
trong nhánh nhãn/evaluation, không vào actor.

## Ranh giới hiện tại và việc cần người vận hành

- Không SSH, flash, enable hay thử chuyển động robot trong cập nhật này.
  Số phiên thật mới: **0**. Cutoff dữ liệu đã review vẫn 02/11/2026.
- ROS fixture là dữ liệu tổng hợp. Shadow robot thật, clock/latency trên Pi,
  quyền thực thi RC/motor và hard emergency stop readback còn chưa xác minh.
  Decoder status trong observer là diễn giải source, không chứng minh các trạng
  thái vật lý đó. Tuổi receipt không tự là tuổi phép đo ở sensor.
- Chưa có effective geometry, body/slip reference hoặc motor model hiệu chuẩn;
  chưa có ngưỡng nhà máy được chấp nhận. Chưa mở train benchmark nghiên cứu,
  predictor, real residual authority hoặc obstacle trial.

**Bước tiếp theo:** mở GUI v5 → **Xây project / sơ đồ** xem kết quả →
**Bước dữ liệu thật → phiên diagnostic**. Khi chuẩn bị thu, dùng video có mốc
bánh/thân/sàn và lưu outcome quan sát độc lập; không suy thân tiến chỉ từ
reported wheel speed. Review diagnostic trước khi mở protocol độ lặp/SysID.
