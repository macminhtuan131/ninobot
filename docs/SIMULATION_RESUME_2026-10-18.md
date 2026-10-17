# Tiếp tục nhánh mô phỏng — 18/10/2026

## Phạm vi người dùng vừa xác nhận

**Cập nhật:** người dùng đã chọn phương án A — khảo sát mô tả tối đa 16
attempts. Xem [contract triển khai](GOVERNOR_DESCRIPTIVE_SURVEY_2026-10-18.md).
Phần mô tả hai lựa chọn dưới đây giữ làm lịch sử chuẩn bị; không còn là câu
hỏi đang chờ trả lời. Ngưỡng vẫn chưa được chấp nhận hoặc áp dụng.

Giữ công việc robot thật ở trạng thái chờ; tiếp tục nhánh simulation.
Code/bundle thu thập Pi được giữ nguyên, chưa triển khai lên robot.
Lựa chọn trước đó giữ tiêu chí 10%/+0,5 giây ở mức đề xuất chưa được thay thế
bằng việc chấp nhận các ngưỡng này.

## Kiểm tra đã thực hiện, không chạy episode

- Validator protocol H2: structure valid; 30 frozen files và 23 workspace
  references khớp hash.
- Ledger offline: 0 attempts, 0 launch requests; đủ 16 slot chưa chạy.
- Application requirements vẫn pending, các ngưỡng chưa điền.
- Không sửa controller, PI, detector, ramp, scoring, protocol hoặc hash cũ.
- Không audit lại bốn trace cũ hoặc chạy thêm tests không có rủi ro mới.

## Hai phương án cụ thể để lựa chọn trước khi chạy

### A. Khảo sát mô tả, giữ tiêu chí là đề xuất

Chuẩn bị **contract riêng** và giới hạn tối đa 16 attempts: hai block seed
77500/77501, PI full và reactive delay 0, bốn cặp mỗi block. Dùng đúng
scenario, thứ tự cân bằng, cold start, zero/standstill gate và quy tắc
giữ failures/không retry của thiết kế đã chuẩn bị. Các lượt kiểm tra
integration nằm trong ngân sách này; lỗi integrity thì dừng, không bù lượt.

Khóa metric/window/sampling và phương pháp thống kê trước attempt đầu.
Báo arrival/stop, stall, tracking, thời gian, rung/slip sau contact và toàn
tuyến, tám cặp, hai block, khoảng bất định và bằng chứng can thiệp thực thi
trước contact kế tiếp. Dữ liệu thiếu và sampling sensitivity vẫn giữ nguyên.

Không chọn primary thắng cuộc hoặc ngưỡng lợi ích sau khi thấy dữ liệu.
Không áp dụng ngưỡng đề xuất 10%/+0,5 giây, không phát kết luận H2 formal
đạt/không đạt, không mở tuning/predictor/PPO từ khảo sát này. Nếu muốn xác
nhận theo yêu cầu ứng dụng sau này cần protocol và ngân sách riêng trước
dữ liệu xác nhận; không đổi nhãn khảo sát thành xác nhận hồi tố.

Phương án này **chưa được triển khai hoặc chạy**. Không dùng bypass hoặc
điền application confirmed giả để mở executor H2 hiện tại.

### B. Xác nhận H2 theo tiêu chí nghiên cứu được chấp nhận

Người dùng chấp nhận rõ: slip²/m sau contact giảm ít nhất 10%; rung sau
contact và rung/slip toàn tuyến không tăng; tăng thời gian tối đa 0,5 giây;
giữ các physical arrival/stop/tracking/time gates hiện có. Đây là giả định
nghiên cứu, không phải yêu cầu nhà máy đã được đo đạc hoặc tiêu chuẩn ngành.

Sau đó điền application, khóa hash cùng dependency hiện tại trước kết quả,
ghi release cho đúng batch tối đa 16 attempts và dùng executor/analyzer H2
đã chuẩn bị. Không có smoke episode riêng, retry, replacement hay tự tăng
ngân sách. Kết luận theo protocol: đạt / không đạt / chưa đủ bằng chứng.

## Trạng thái sau chuẩn bị này

Chưa chọn A/B, chưa chấp nhận tiêu chí số, chưa tạo release mới, chưa chạy
simulation. Việc hỏi lựa chọn xuất phát từ yêu cầu chốt tiêu chí trước chạy
trong protocol ngày 17/10 và lựa chọn trước đó của người dùng giữ tiêu chí
ở mức đề xuất; không phải điều kiện mới về an toàn hay hiệu quả RL.
