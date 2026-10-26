# Nino: phạm vi cần kiểm chứng và kế hoạch tiếp tục

> **Refinement hướng A/T3:** [motion contract và các khác biệt wrapper–inline](NINO_MOTION_CONTRACT_REVIEW_2026-10-23.md).
> Source review đã xong; proposal thu đứng yên/đo response chưa được thực thi.

> **Review tổng hợp mới:** [phản biện độc lập và 17 nguồn ngoài](NINO_INDEPENDENT_REVIEW_2026-10-23.md).
> Lộ trình và điểm dừng cập nhật ở §7; các lịch release bên dưới là lịch sử,
> không phải ngân sách được mở tự động.

> Trạng thái thực thi mới hơn:
> [cadence v6 và correction queue v7](GOVERNOR_ISOLATED_CADENCE_V6_RESULT_2026-10-23.md).
> V3/v4/v5/v6 đều đóng ở 1/12; v7 mới kiểm tra phần mềm, chưa có phép đo controller hợp lệ mới.
> Các tham chiếu screen v2 bên dưới là lịch sử thiết kế; không cấp lại slot đã đóng.

Ngày 23/10/2026. Phân loại dưới đây là **đề xuất nghiên cứu**, chưa phải
giới hạn phần cứng đã đo hoặc chính sách triển khai trên robot thật.

## 1. Phạm vi và cơ chế phải tách riêng

| Điều kiện | Bằng chứng Nino đang có | Hướng cần kiểm chứng | Điều kiện chưa cho phép kết luận |
|---|---|---|---|
| Sàn phẳng sạch | Matched-ramp sim đổi được wheel/body, hai lượt | Giữ PI/ramp baseline; dùng để kiểm tra command path | Không suy độ trễ hoặc gain motor thật từ sim |
| Gờ cứng capsule 6 mm, +8°, E1, 0,4 m/s | Survey 16/16 arrival/stop; lợi ích slip chưa rõ; early caster contact chiếm phần slip lớn | Screen v2: actual response trước contact sau và crossing quality | Không suy sang mọi gờ/góc/tải/tốc độ hoặc gọi đã giảm risk |
| Gờ 22 mm/bracket-first | Screen lịch sử có cơ chế khác 6 mm | Xét geometry/clearance trước speed adaptation | Không áp response hay tuning của 6 mm làm correction |
| Cáp mềm, lỏng, dễ kéo/quấn | Collision hiện là vật thể cứng; chưa có dữ liệu biến dạng/quấn | Xét tránh/thu dọn/bảo vệ cơ khí; traversal chỉ trong fixture phù hợp sau này | Sim capsule không xác nhận robot vượt dây mềm được |
| Groove/pothole âm | Có map/curriculum infrastructure; chưa có governor envelope hợp lệ | Kiểm tra kích thước so với bánh/caster và khả năng tránh; nghiên cứu riêng | Không dùng solid-box screen dương xác nhận mesh âm hoặc khả năng vượt |
| Tuyến đã đi nhiều lần | Có localization/navigation infrastructure, chưa có memory policy đánh giá | Dự phòng: gắn quality map cho lần sau để có preview theo tuyến | Cần localization uncertainty, tuổi dữ liệu và xử lý vật cản thay đổi |
| Vật cản thấp chưa biết ở lần đầu | Proprioception chỉ cung cấp bằng chứng sau tiếp xúc | Nếu bắt buộc xử lý trước contact: đánh giá nhu cầu cảm biến preview riêng | LiDAR ngang hiện có chưa chứng minh nhìn thấy mọi vật cản thấp |

Không lấy clearance danh nghĩa 9,03 mm, wheel radius 62,5 mm hoặc mass URDF
làm số đo có tải. Không suy một ngưỡng chiều cao vượt được từ một giá trị
clearance đơn lẻ: hướng tiếp cận, caster, bracket và tải đều chưa được xác nhận.

## 2. Ưu tiên và phương án dự phòng

**Nền ưu tiên:** xác định operating envelope, cơ khí và speed shaping cổ
điển có đối chứng. Governor frozen tiếp tục làm baseline cho screen đã
chuẩn bị. Không sửa nhiều biến để tìm một lượt đẹp.

**Câu hỏi tiếp theo duy nhất đã chuẩn bị:** 20 ms có tạo actual wheel/body
response sớm hơn có ích không? [Audit mới](GOVERNOR_H2_TIMING_ENVELOPE_2026-10-23.md)
cho thấy không có bế tắc timing toàn cục với drive contact muộn, nhưng đa
số slip xuất hiện trong 200 ms đầu. Đây là lý do phải kiểm tra cơ chế,
chưa phải bằng chứng nên triển khai fast governor.

**Dự phòng:** memory chất lượng mặt sàn theo tuyến. Dùng quan sát lần trước
để tạo cơ hội giảm tốc trước ở lần sau; so với PI thường và một speed zone
cố định. Chưa viết policy/huấn luyện/chạy batch mới. Trước đó cần một
protocol riêng có uncertainty định vị, map thay đổi, chi phí thời gian và
fallback khi thông tin cũ không còn đúng.

## 3. Quy tắc quyết định sau screen v2

| Kết quả | Hành động tiếp theo |
|---|---|
| Acquisition/lifecycle/coverage fail | Đóng batch; báo native outcome riêng; chỉ review lỗi cụ thể, không tự cấp batch khác |
| Command sớm, wheel/body chưa phân biệt được | Giữ H2 unknown; dừng thử cadence trên cùng setup; xem lại khả năng nhận dạng trước mọi tuning |
| Actual response sớm nhưng crossing không cải thiện rõ | Không promote; chuyển trọng tâm sang envelope/cơ khí hoặc chuẩn bị memory protocol |
| Response và crossing có tín hiệu lặp lại | Review trade-off và phạm vi; mới đề xuất classical tuning nhỏ với protocol riêng |

Các nhánh trên không tự cấp ngân sách hoặc chấp nhận ngưỡng. Với chỉ hai
seed block, không được đổi “có tín hiệu” thành chứng minh generalization
hoặc kết luận causal mạnh từ hai lượt cùng seed.

## 4. Khi mở lại robot thật: bốn nhóm đo tối thiểu

Hiện chưa thực hiện phép đo phần cứng. Dùng bộ collector hiện có trước khi
viết thêm driver hoặc hỏi toàn bộ thông số MCU.

1. **Đứng yên, chỉ đọc:** publisher đang phát và giá trị hợp lệ của IMU,
   encoder trái/phải, command path, motor telemetry. Lưu bag raw, header/
   receipt timestamps, rate/gaps, units/frame, metadata. Tên topic có trong
   graph không đủ. Kiểm tra nguồn và command ownership trước thử chuyển động.
2. **Backend đang chạy:** xác nhận speed mode/internal PI hay torque mode/
   external PI, wheel mapping/sign và giới hạn/flags thật từ driver/firmware.
   Ghi requested và executed target, actual speed; không suy torque từ cmd_vel.
   Model STM32 không phải điều kiện để ghi ROS topic đã được xuất.
3. **Đáp ứng trên sàn sạch có kiểm soát:** sau khi có protocol chuyển động
   riêng, đo command → limited wheel target → encoder → body reference độc
   lập. Ghi uncertainty đồng bộ. Video chỉ hữu ích khi hiệu chuẩn/góc nhìn
   đủ; encoder odom không làm body ground truth khi trượt. Không dùng speed
   step/gain sim như lệnh phần cứng mặc định.
4. **Cơ khí có tải:** đo drive radius hiệu dụng, caster diameter/bố trí,
   bracket clearance, mass/payload và hình học gờ thật. Sau đó mới thiết kế
   fixture cứng thấp; chưa dùng dây điện mềm đang hoạt động để thử.

Đầu ra tối thiểu là một session có provenance và kênh dữ liệu hợp lệ, một
response timeline với uncertainty, một bảng geometry có tải. Nếu chưa có
body reference độc lập, vẫn thu được encoder/IMU/telemetry nhưng không kết
luận slip thật hoặc motor-to-body latency chính xác.

## 5. Điểm dừng hiện tại

Đã hoàn tất audit có giới hạn và ma trận trên. Không mở PPO/predictor/
Optuna, không tiếp tục đào lại các trace hiện tại để tìm kết luận thuận lợi.
Phần simulation chỉ còn đề xuất review contract v7 tối đa 12 attempts;
chưa release, không dùng lại budget v2–v6. Correction queue là điểm dừng
của vòng sửa hiện tại; failure mới không tự cấp thêm batch hoặc correction.
Phần hardware vẫn giữ lại theo workflow hiện tại. Chưa cần thu mọi thông
số thật để review measurement readiness trong sim.
