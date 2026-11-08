# Đối chiếu wheel/body và quyết định bước tiếp — 07/11/2026

## 1. Hiện trạng

**[N — Sim]** TD3 cùng seed11 đã train tổng 30.000 bước, 20.000 critic /
10.000 actor updates; chưa tốt hơn Classical_scheduled cho clear-box, lịch
dừng biết trước 6/8 s, Ki0,10. Giữ kết luận trong envelope này, không suy
rộng sang robot thật. Xem [đánh giá 30k](NINO_COMMON_TD3_30K_ASSESSMENT_2026-11-07.md).

**[N — real, tái kiểm trực tiếp]** Đọc bốn bag lưu trên laptop, tổng
**95.459 messages**. 100/100 file raw được kê trong hash manifest khớp;
SQLite integrity và tổng/per-topic counts so metadata đạt. 118 đường dẫn
input gồm raw, review và operator records được kiểm hash trước/sau, không
đổi. Hai hash source identity mỗi phiên được giữ nhưng không tính như file
raw đã kiểm. Không SSH hoặc xác minh trạng thái Pi hiện tại.

Đây là kiểm integrity và đối chiếu claim có giới hạn; không lặp toàn bộ
clock/coverage/window-support. Primary dưới đây kế thừa review đã freeze,
không chọn lại cửa sổ. Không gọi counts/hash đạt là loss-free.

## 2. Claim → evidence → unknown, giữ riêng session

Các positive counts dưới đây lấy từ CDR nguyên bag, không phải suy từ log
helper. Chuỗi cột là source / selected / smoothed / final ROS.

| Session ngày 02/11 | Messages | Positive samples theo chuỗi | Reported wheel / operator | Kết luận hẹp |
|---|---:|---|---|---|
| `wheel_clear_zone_094226594883Z` | 23.995 | 39 / 40 / 50 / 50 | Primary delta L/R 0,834241 / 0,820122 rad/s; operator báo tiến và tự dừng | Một lần feasibility; chưa có displacement/reference độc lập |
| `clear_floor_repeatability_v2_102247471316Z` | 24.349 | 39 / 40 / 50 / 50 | Primary delta L/R 0,822438 / 0,743656 rad/s; operator báo **không tiến** | Outcome thân **unknown/mâu thuẫn**, không suy slip hoặc telemetry giả |
| `clear_floor_repeatability_100409043176Z` | 23.483 | 39 / 40 / 50 / **0** | Ghi 3 STOP events; operator báo không tiến | Input bị chặn; không dùng để fit đáp ứng motor với lệnh tiến đầy đủ |
| `wheel_startup_verification_104845142374Z` | 23.632 | 0 / 0 / 0 / 0 | 0 enable=true, 3 disable=false; discovery fail | Chưa thực hiện kích thích tiến; không là motor-response test |

Trong bốn bag không thấy nonfinite/shape error ở position/velocity raw
motor feedback; điều đó không xác minh scale, danh tính motor, binary hay
physical wheel rotation. Hai bag có final tiến đạt max 0,05 m/s, yaw zero.
Final Twist là yêu cầu ROS nhận tại recorder, chưa là target actuator đã
thực thi. Không có STOP event trong hai bag này không tự chứng minh monitor
luôn NONE; final nonzero hỗ trợ claim rằng lệnh tiến đã qua tầng đó.

**[N — báo cáo cũ]** Lượt `rc_auto_followup_050858953708Z` có operator báo
tiến/tự dừng và review riêng. Báo cáo này đã đọc, nhưng bag đó không nằm
trong bốn bag tái kiểm trực tiếp lần này; không cộng vào số liệu ở trên.

**[N — giới hạn file]** Không tìm thấy video .mp4/.mov/.mkv/.avi/.webm/.m4v
trong cây artifacts của workspace client, bỏ qua build/install/.venv/.git.
Không kết luận điện thoại hoặc Pi không có video. Không có body displacement,
body speed hoặc slip được điền thay cho phần còn thiếu.

## 3. Đánh giá độc lập

1. **Đã đủ để dừng audit lặp lại:** inventory, coarse IMU axes/dấu Z, closure
   mẫu đứng yên, và integrity của các phiên đã review. Chỉ mở lại khi có
   thay đổi hoặc câu hỏi cụ thể.
2. **Nút chặn claim vật lý:** thiếu quan sát độc lập bánh và thân đúng cùng
   session. Wheel feedback và encoder odom không thể tự giải quyết mâu thuẫn.
3. **Nút chặn vận hành trước motion:** startup/discovery candidate chưa có
   motion validation; boot/GID/endpoint hiện tại chưa được đọc. Kiểm live
   riêng, không dùng GID cũ hoặc phiên thất bại làm readiness hiện tại.
4. **Chưa có căn cứ tuning:** không fit gain/latency/current hoặc radius từ
   việc thân không tiến khi physical wheel motion còn chưa biết. L/R chênh
   ở hai phiên khác điều kiện không là estimate repeatability.

**[S]** Ba khả năng vẫn mở: bánh quay nhưng truyền động/tiếp xúc không tạo
chuyển vị; feedback không đại diện đúng bánh vật lý; chuyển vị ngắn không
được nhìn thấy. Dữ liệu hiện có chưa chọn được một khả năng. Một video có
mốc thân và bánh đúng phiên có thể phân biệt, không cần thêm PPO/predictor.

## 4. Quyết định và artifact tiếp theo

**[Đ] Chuẩn bị một phép chẩn đoán riêng, tối đa một lượt**, giữ profile đã
thảo luận 0,05 m/s, ramp 0,10 m/s², source 2 s, bag 60 s; bổ sung video thấy
bánh và thân/mốc cố định. Chưa mở campaign ba repeats, chưa cấp motion slot.
Xem [protocol draft](NINO_BODY_REFERENCE_DIAGNOSTIC_DRAFT_2026-11-07.md).

Mục tiêu đầu là xác nhận có chuyển động vật lý hay không, không phải slip
định lượng hoặc thời gian dừng. Sau khi biết bánh/thân có chuyển động và
clock/scale đủ, mới chọn phép đo SysID/độ lặp tiếp. Nếu video cũ đúng phiên
V2 được cung cấp và đủ góc nhìn, đọc nó trước; có thể không cần lượt mới.

Không sửa controller/firmware, không bỏ Collision Monitor, không tăng tốc
hoặc đổi đồng thời reward/history/LR/action scale. To-do đánh dấu phần
review offline đã hoàn tất, phần video/measurement vẫn chưa thu.

## 5. Nguồn và khả năng tái lập

Client artifact: `artifacts/wheel_body_gap_review_2026-11-07/` có `analyze.py`,
`analysis.json`, input hashes và manifest. Script chỉ dùng SQLite immutable
read-only; fail nếu có nonempty WAL cần chiến lược snapshot riêng. Không ghi
lại raw. Lần chạy đầu phát hiện metadata có topic zero-message mà SQL không
tạo count row; đã sửa đối chiếu missing count=0, không thay dữ liệu/ngưỡng.

Các nguồn đọc thêm: `NINO_REAL_DATA_STATUS_2026-11-03.md`,
`src/nino_pi/WHEEL_RESPONSE_PROTOCOL.md`, bốn `REPORT.md`/analysis/primary và
operator records ở các thư mục evaluation tương ứng; báo cáo rc_auto chỉ
đọc dạng review. Không tra cứu nguồn ngoài hoặc suy đang có kết nối hardware.
