# Sửa khởi tạo helper thử bánh — 02/11/2026

## Lỗi được xác nhận trong file

Trong V2 `clear_floor_repeatability_v2_20261102T102247471316Z`, status ngay
preallocation và trial_start bằng19: firmware enable variable đã bật từ
trước. Helper cũ gửi enable=true và chỉ cần một status mới có bit16 để đi
vào forward. Nó không buộc trạng thái disabled trước đó; ACK có thể chỉ là
một bản phát lại trạng thái đang bật, không phải sự áp dụng enable mới.

Source STM32 tham khảo trong `motor_task.c` chỉ gọi `motor_apply_enable`
khi `want_enable != g_system_enabled`; cấu hình mode nằm trong đường enable
này. Do đó bật lại true khi biến đã true không tái khởi tạo motor mode. Một
trường hợp có thể gặp là nguồn công suất motor đã đổi/reset nhưng STM32 vẫn
chạy. **Chưa có readback chứng minh trường hợp đó đã xảy ra trong lượt vừa
rồi hoặc binary đang chạy trùng source.** Test chỉ tái hiện thiếu edge trong
helper, không mô phỏng chứng minh nguyên nhân vật lý.

## Bản sửa

`run_trial.py` mới thực hiện:

1. Readiness/ownership/scene như cũ; claim một lượt theo release tương lai.
2. Pi gate disable có ACK, phát zero.
3. Request firmware disable; cần status nhận sau request và bit16 tắt.
4. Baseline zero2s; nếu firmware tự bật lại thì hủy, không tiến.
5. Kiểm scene trước enable, request enable, cần status mới với bit16 bật.
6. Kiểm scene trước forward; source0,05m/s target2s, ramp0,10m/s² và
   zero/disable giữ nguyên. STOP latch/scan guard/cleanup giữ nguyên.

`trial_result.json` thêm `physical_motion_verified:false` và trạng thái cần
đối chiếu người vận hành/reference độc lập. `source_sequence_completed`
chỉ giữ nghĩa chuỗi lệnh ROS hoàn tất. Không dựng actuator readback hoặc
body displacement từ cmd_vel/encoder. Cấu hình Collision Monitor, gain,
current, firmware, tốc độ, ramp và metric không đổi.

## Kiểm chứng

- 44 tests đạt, gồm regression chạy helper cũ trong endpoint mock với enable
  có sẵn: không tạo disabled→enabled edge, fixture bắt lỗi đó.
- 15 production mock handoff cases đạt cho bản sửa, gồm initial-enabled,
  disable-ACK-timeout, enable-timeout, owner conflict, feedback stale, STOP
  trước/trong forward và STOP rồi NONE. Disable timeout không phát forward.
- Các kiểm trên không tạo ROS node hoặc giao tiếp motor thật; không chứng
  minh mode motor đã được readback hoặc xe đã chạy.

## Giới hạn quyết định

Không xác nhận đây là nguyên nhân duy nhất hoặc đã sửa được hiện tượng
thân xe không tiến: latestV2 có final nonzero và reported wheel position đổi;
người vận hành báo thân không tiến. Giữ cả hai bằng chứng. Đây là sửa một
lỗ hổng khởi tạo có căn cứ, không loại bỏ yêu cầu kiểm thực tế sau sửa.

Candidate được copy riêng lên Pi ở
`~/nino_runtime/wheel_startup_fix_20261102_v1/`, **prepared_not_released**,
maximum_attempts0, không tạo ledger, không chạy motor command. Helper sẽ
refuse trước khi tạo ROS node nếu gọi trực tiếp. V1/V2 vẫn đóng1/3, không
sửa frozen inputs/ledger cũ, không tự cấp một đợt3lượt khác.

Bước kiểm tiếp được đề xuất là một lượt kiểm riêng của startup fix, profile
cũ, có mốc sàn và góc nhìn thấy bánh, sau khi chốt release/budget của lượt
đó. Chưa thực hiện hoặc coi user đã chấp nhận một motion budget mới.
