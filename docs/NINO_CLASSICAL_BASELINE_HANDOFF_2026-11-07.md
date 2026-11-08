# Nino — chốt Sim 30k và công việc tiếp theo

Ngày: 07/11/2026. Phạm vi thay đổi: trạng thái dự án, GUI và kế hoạch;
không thay controller, reward, history, tham số TD3 hoặc firmware.

> **Cập nhật tiếp 07/11:** đã đối chiếu bốn raw bag (95.459 messages,
> 100 file khớp hash). Mâu thuẫn feedback/thân ở V2 vẫn unknown; chưa có
> video trong artifact local đã tìm. [Kết quả và quyết định](NINO_WHEEL_BODY_GAP_REVIEW_2026-11-07.md),
> [draft một lượt có video](NINO_BODY_REFERENCE_DIAGNOSTIC_DRAFT_2026-11-07.md).
> Bước offline số 1 bên dưới đã hoàn tất; việc tiếp là chuẩn bị góc quay và
> kiểm live readiness trước khi review/release riêng. Chưa mở ba repeats.

## 1. Quyết định đã có bằng chứng

**Giữ Classical_scheduled cho clear-box, lịch dừng biết trước 6/8 s,
baseline Ki0,10 frozen.** Không suy rộng quyết định này tới vật cản, factory
mixed map hoặc robot thật; không kết luận TD3 không thể học tốt hơn.

- Cùng learner seed11 đã đạt **30.000 global steps**, gồm continuation
  10.000 bước từ 20.000; tổng **20.000 critic / 10.000 actor updates**.
- Phân tích offline dùng 1.680 packet evaluation chung cho checkpoint
  20k/25k/30k và kiểm 30.000 training rows. 25k chưa có rollout riêng.
- Trong phạm vi audit không thấy sai mapping, reference hoặc reward đã khai
  báo. Critic ranking chưa đáng tin; reward tăng có thể không đổi chuyển động.
- TD3 30k có native velocity RMSE toàn tuyến cao hơn classical khoảng
  8,62% / 5,08% cho stop6/8; hai GT grids cùng chiều. Đây là kết quả mô tả
  một seed trên scenario đã xem, không là chứng minh hội tụ hoặc tổng quát.

Chi tiết và giới hạn: [đánh giá 30k](NINO_COMMON_TD3_30K_ASSESSMENT_2026-11-07.md),
[phân tích phase/critic/action](NINO_TD3_OFFLINE_PHASE_REVIEW_2026-11-07.md).

## 2. Đã thực hiện trong lần bàn giao này

1. Cập nhật current evidence từ 20k sang **30k cumulative**, tách rõ số bước
   thêm trong job và số bước tổng của learner. Giữ record 20k làm lịch sử.
2. GUI Train hiển thị quyết định khoa học riêng với trạng thái process;
   mở phiên đã review để xem kết quả/map, không tự khởi động learner.
3. Trang benchmark hiển thị so sánh phase mở từ decision đã đóng dấu hash;
   trang outline nêu công việc tiếp theo thay cho đề xuất continuation cũ.
4. Bảo toàn checkpoint 20k/25k/30k; không đổi LR/history/reward/action scale.

Kiểm chứng phần mềm: **107 tests đạt**, `colcon build --packages-select
nino_pi` đạt. Bản đã cài được kiểm tra mở phiên hoàn tất, đọc đủ 10.000 rows
của continuation, hiển thị 30.000 global steps, hai dòng benchmark và tám
bước outline; đã xem ảnh GUI. Đây là kiểm chứng GUI/metadata, không phải
thêm thí nghiệm controller. Một lỗi khởi tạo observer trong panel test được
sửa bằng cách chỉ tự mở phiên hoàn tất khi external observation được bật.

Counters và kết luận chỉ hiện là đã xác minh khi sealed manifest, kết quả
job, hash diagnostic và liên kết learner khớp. Thiếu/sai artifact phải báo
chưa xác minh, không giữ nhãn thành công cũ.

## 3. Outline tiếp theo và điểm dừng

| Thứ tự | Việc cụ thể | Artifact cần có | Điều kiện chuyển bước |
|---|---|---|---|
| 1 | Đối chiếu các báo cáo/dataset thật hiện có: command → feedback từng bánh → quan sát thân xe | Bảng claim / evidence / unknown, theo đúng session | Phân biệt được wheel feedback với body motion; nếu thiếu raw chỉ ghi unknown và xác định đúng artifact cần đọc |
| 2 | Thiết kế reference thân độc lập tối thiểu, ví dụ video có thước chuẩn và mốc thời gian | Protocol camera/góc nhìn, frame, scale, đồng bộ và uncertainty; chưa thu mới | Có cách lượng hóa chuyển vị/timing đủ cho câu hỏi, không dùng encoder odom làm GT |
| 3 | Chỉ đề nghị một đợt đo mới khi đã review protocol và ngân sách riêng | Metadata, profile, thứ tự/lặp, QC, tiêu chí dừng | Không tự mở lại pilot cũ; tối đa một correction có căn cứ trước quyết định |
| 4 | So command→wheel và wheel→body, rồi mới sửa mô hình hoặc chọn câu hỏi Sim mới | Báo cáo SysID/model discrepancy và baseline | Có sai khác có thể đo được; không dùng randomization để che mismatch chưa nhận dạng |

Không lặp inventory, dấu gyro Z hoặc tư thế IMU đã đủ bằng chứng nếu không
có thay đổi phần cứng/firmware hay câu hỏi mới. Không cần full navigation
stack để kết luận đáp ứng bánh; muốn kết luận slip cần body reference độc lập.

**Các phiên thật cũ còn mâu thuẫn giữa feedback và quan sát xe phải giữ
mâu thuẫn đó.** Không nâng nhãn “bánh có feedback” thành “xe đã tiến”.
Những phiên cũ thiếu đối chứng thân xe không tự biến thành dataset slip.

## 4. Khi nào mở lại TD3 / Governor / History?

- Có nhu cầu ứng dụng cụ thể và phase mà actuator còn quyền tác động hữu ích.
- Có baseline cổ điển mạnh cùng information/action contract để đối chiếu.
- Chọn một yếu tố cần phân biệt, protocol và ngân sách riêng; giữ dữ liệu lỗi.
- Với real deployment: cần contract backend, reference/latency thực và gate
  triển khai độc lập. Kết quả Sim hiện tại không cho phép điều khiển robot.

GUI vẫn cho tạo Smoke/Train có yêu cầu rõ ràng và interlock hiện hữu.
Khuyến nghị giữ classical chỉ áp dụng benchmark nói trên; không là lệnh cấm
mọi nghiên cứu TD3. Laya chỉ hỗ trợ đọc tình hình, không quyết định promote.

## 5. Ràng buộc tài nguyên và thao tác

Đĩa chỉ còn khoảng 2 GiB tại lúc bàn giao; cần xác nhận dung lượng cho từng
job trước batch mới. Không xóa raw/checkpoint hoặc hạ QC để lấy chỗ.
Lần bàn giao này không chạy Gazebo, train, SSH, enable hoặc thu chuyển động.

**Việc nên làm tiếp:** bảng khoảng trống wheel/body từ dữ liệu thật đã có,
kèm protocol reference độc lập để review trước khi yêu cầu người vận hành thu.

Đổi khuyến nghị controller khi có outcome hợp lệ, cùng ràng buộc nhiệm vụ,
cho thấy lợi ích lặp lại của phương án khác; không đổi chỉ vì return/critic
loss đẹp hơn hoặc có thêm checkpoint.
