# Hướng đã chọn: gờ không biết trước, vượt được và bám quỹ đạo

Ngày 09/11/2026. **Cập nhật theo lựa chọn trực tiếp của người dùng.**

## 1. Sửa cách đặt bài toán

Người dùng xác định: **gờ phải được coi là không biết trước; robot cố gắng
vượt qua và bám quỹ đạo**. Vì vậy hướng preview gờ đã biết để giảm rung đã
được thay thế. Sáu lượt MQ trước chỉ là draft, đã cấp0 lượt; không thực hiện
hoặc chuyển chúng thành budget của task mới. Tài liệu/artifact đó giữ làm
lịch sử và công cụ metric phụ, không là roadmap hiện hành.

Mục tiêu theo thứ tự:

1. **Vượt gờ trong phạm vi cơ khí cho phép, thân xe tới đích và dừng.**
2. **Bám đường:** sai số ngang RMS/max và heading so cùng quỹ đạo.
3. Thời gian hoàn thành để tránh phương án gần như đứng yên hoặc quá chậm.

Rung, wheel/body discrepancy và saturation là chẩn đoán phụ. Không bắt buộc
giảm RMS rung10%, không ép giữ đúng0,20m/s xuyên suốt contact. Giảm/tăng tốc
cục bộ được xét theo tác dụng hoàn thành nhiệm vụ và bám đường. Các tolerance,
stall/timeout và bounds định lượng vẫn phải chọn trong protocol trước chạy;
lựa chọn mục tiêu này không tự chấp nhận một bộ ngưỡng nhà máy.

## 2. “Không biết gờ” nghĩa chính xác là gì?

**Đường đi và goal có thể được biết.** Controller không nhận vị trí, chiều
cao, góc, khoảng cách tới gờ, lịch phanh theo gờ hoặc thời điểm chạm định sẵn.
Pose estimator có thể phục vụ follower, nhưng không được ghép với map gờ
để ngầm tạo preview. Không mặc định LiDAR ngang thấy được gờ thấp.

```text
Reference path/goal → follower dùng estimator → nominal v, omega
IMU + encoder + causal command history → reactive hoặc residual đề xuất
Nominal + correction → projection/ownership/limits → motor backend → robot

GT + obstacle metadata + contact/caster labels → scoring/audit riêng
```

IMU/encoder chỉ có thể cho dấu hiệu nhiễu sau khi robot bắt đầu chịu tác
động; không gọi đó là nhìn thấy gờ trước va chạm. Sensor trigger cũng không
được gọi là ground-truth first contact. Nếu phần tiếp xúc còn lại quá ngắn
hoặc speed action không giúp thì giữ baseline/đổi action/cơ khí theo bằng
chứng, không hứa predictor hoặc thêm training sẽ sửa được mọi transient.

Các nguồn deployable dự kiến: raw IMU, encoder hai bánh, lịch sử command,
owner/freshness và reference follower. Giữ20 feature×5 frame làm điểm bắt
đầu; không tự thêm3 feature planned-stop/oracle từ common103. Checkpoint cũ
không tự tương thích với task/action/reward/termination mới.

## 3. Đánh giá vượt được và bám đường

- **Success vật lý:** thân xe tới goal, hình học toàn robot đã qua gờ và
  dừng liên tục theo contract. Encoder/estimator báo arrival đơn độc chưa
  đủ. Sim dùng GT/geometry để chấm; không đưa GT ngược vào controller.
- Chạm gờ dự định vượt không tự bị tính là collision terminal. Phải tách
  chạm gờ bình thường khỏi rollover, mắc kẹt, vi phạm đường đi hoặc fault.
- Failure/timeout/stall/override giữ trong mẫu và denominator; thiếu dữ
  liệu là UNKNOWN, không biến thành success hoặc âm thầm bỏ khỏi thống kê.
- Báo success/failure trước; sau đó path RMS/max/heading và thời gian,
  không dùng một reward tổng để che failure hoặc đánh đổi việc không tới đích.
- Giữ measurement validity/source clock/grid sensitivity. Velocity ISE
  nominal cũ không thay cho path tracking và physical task success mới.

Tài liệu này chọn task, **chưa cài scorer/runner**. JSON mới để null các
tolerance và budget thay vì tự gán chúng từ ngưỡng của bài toán giảm rung.

## 4. Tránh “không biết” chỉ trên tên gọi

Mở đầu bằng họ gờ cứng thấp đã có trong lab; Ø6mm là development anchor,
không đại diện mọi gờ hoặc dây mềm. Vị trí phải thay đổi và ẩn khỏi packet
controller. Sau feasibility mới mở thêm height/angle có giới hạn.

Một vị trí cố định có thể bị học thuộc qua thời gian hoặc tiến độ ngay cả
khi không có trường `obstacle_x`. Vì vậy bank cần có vị trí khác, clear-floor
control, thay đổi start delay khi phù hợp và split theo toàn run/layout/seed.
Bank development/validation/test phải khóa trước chọn checkpoint; không
random-split các frame chồng lấp. Đổi vị trí không tự chứng minh tổng quát
theo height, caster, payload hoặc route rẽ.

Test adapter cần giữ nguyên sensor history nhưng đổi metadata gờ: packet
controller phải không đổi. Guard tên feature vừa thêm chỉ chặn trường thừa;
nó **chưa chứng minh provenance hoặc loại bỏ mọi shortcut**. Phải audit các
wrapper/runtime và normalization khi tích hợp.

## 5. Baseline, Governor, History và TD3 trong hướng này

| Thành phần | Vai trò tiếp theo |
|---|---|
| Classical B0 | Follower + velocity backend/limits, không biết gờ; baseline thực sự |
| Reactive B1 | Dùng IMU/encoder/history, không oracle; qualify riêng trước so sánh |
| Observation History | Bối cảnh nhiễu/đáp ứng nhân quả, không chứa map gờ hoặc dữ liệu tương lai |
| Residual TD3 | Ứng viên bù velocity reference có giới hạn sau khi task/env hợp lệ |
| PPO | Đối chứng học khi có câu hỏi cần so thuật toán, không bắt buộc mở ngay |
| Rung/slip metrics | Chẩn đoán phụ; slip thật vẫn cần body reference phù hợp |

Không yêu cầu TD3 chưa train phải thắng classical mới được train. Cần kiểm
task/reset/step, observation/action, reward/termination và budget trước
pilot có optimizer; **sau train** mới so với B0/B1 trên cùng task và test
bank độc lập. Không quay lại common± sau contact cũ rồi gọi nó là task mới.

Reward tương lai phải gắn với tiến độ tới goal, sai số đường và failures;
không chỉ phạt sai số vận tốc danh nghĩa. Trọng số, bounds và stall recovery
chưa chọn; không thay đổi đồng thời mọi tham số để tìm return đẹp.

## 6. Việc tiếp theo, theo thứ tự

1. **Implement task/scorer riêng:** physical goal, vượt qua geometry, path
   error, stall/timeout, continuous stop; test synthetic failure/missing.
2. **Tích hợp sensor-only adapter:** follower/estimator + History, bỏ oracle
   và scheduled obstacle features ở nhánh mới; test metadata leakage,
   freshness, projection và identity/ABI.
3. **Khóa hidden-layout bank và protocol integration B0:** tolerance, action
   bounds, budget, retention, clocks và review từng lượt cụ thể trước launch.
4. **Sau release:** smoke environment, pilot TD3 có optimizer rồi evaluation
   classical/reactive/TD3 cùng task. Báo steps và updates thật; smoke không
   chứng minh hội tụ hoặc vượt baseline.

**Trạng thái hiện tại:** mục tiêu đã được người dùng chọn; task spec và
feature-boundary fixture đã chuẩn bị; chưa runtime/task outcome mới, chưa
cấp lượt Sim/training/hardware. E2 vẫn đóng6/6, sampling-sensitive UNKNOWN
giữ nguyên. Hướng known-route vibration đã được gỡ khỏi bước hiện hành
trong Studio; các artifact lịch sử được giữ.

File: `src/nino_rl/config/unknown_step_traversal_tracking_task_v1.json`,
`nino_rl/unknown_step_task.py`; Studio SIM-R4 hiển thị đúng mục tiêu này.
