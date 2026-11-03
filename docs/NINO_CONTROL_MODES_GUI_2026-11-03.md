# GUI quyền điều khiển — 03/11/2026

**Bổ sung v2 cùng ngày:** đã có tab thu dữ liệu với 5 mode: đứng yên,
zero–ARM–DISARM, tiến–dừng, teleop giữ-nút và observer ROS ngoài/Nav2.
Các workflow dùng lại collector hiện có; ghi metadata/events và kiểm hash.
Nav2 ở đây là observer, chưa gửi goal hoặc commissioning navigation. Không
phát sinh data thật từ bổ sung này. Xem hướng dẫn bên dưới và báo cáo
`artifacts/control_modes_data_gui_2026-11-03/REPORT.md` của workspace triển khai.

Đã bổ sung [GUI chuyển nguồn, ARM/DISARM và STOP](../src/nino_pi/CONTROL_MODES_GUI.md).

| Phần | Trạng thái |
|---|---|
| GUI laptop / menu ứng dụng | Đã cài local; mở disconnected, không tự claim/ARM |
| Demo và kiểm UI | Đạt offline, không nối robot |
| Bridge ROS qua SSH | Đã có source và script copy; chưa copy Pi trong lần này |
| Firmware authority opt-in | Đã build H723xx; chưa xác nhận part board/chưa flash |
| Firmware RC mặc định / ROS-only cũ | Regression build đạt; không tự chọn profile mới |
| Triển khai thật | Chưa thực hiện; SSH Pi `.109` báo No route to host |
| Dữ liệu / motion mới | Không thu, không mở/retry slot pilot |

GUI cung cấp STOP / ROS không cần RC / tay RC, cùng các thao tác lấy/trả quyền,
ARM, DISARM, khóa/xóa khóa STOP. Đổi nguồn luôn DISARM; trạng thái dùng ACK
từ STM32. Firmware cũ không hỗ trợ contract này nên GUI sẽ khóa thao tác.

Đây là thay đổi command contract, **không phải một kết quả wheel response,
calibration, stop-time hoặc governor**. Các pilot/runtime cũ giữ nguyên;
helper `/motor_enable=true` cũ không được coi là tương thích profile mới.

Bước phụ thuộc tiếp theo là kết nối lại Pi, xác nhận board/firmware rollback
và triển khai đúng firmware hỗ trợ, rồi kiểm logic với công suất motor ngắt.
Chưa cần thu chuyển động mới ngay lúc này. Hướng dẫn chi tiết, wire contract
và giới hạn ở tài liệu GUI nêu trên.
