# Frozen TD3 V3: ablation residual common / differential

05/11/2026 · **6/6 lượt đã đóng, 840 evaluation transitions, optimizer 0.**
Giữ guided B0 trên sàn sạch; chưa promote TD3 full hoặc common-only.
Không thêm dữ liệu thật, SSH, chạy motor hoặc chỉnh gain/current.

## 1. Đã thực hiện gì?

Theo [protocol khóa trước chạy](NINO_SIM_AXIS_ABLATION_PROTOCOL_2026-11-05.md):

- Guided B0; frozen TD3 V3 đầy đủ; cùng actor nhưng proposal vi sai = 0.
- Mỗi arm hai fresh launches trên **clear box**, tuyến thẳng yaw 0.
  Đây là controlled factory fixture, không phải full mixed factory map.
- Thứ tự B0/full/common/common/full/B0; đúng 140 tick × 6. Không retry.
- Cruise 0,2 m/s, source 0,5–8 s, task 14 s gồm dừng; giữ estimator,
  follower, h5/100D, projection/ramp và wheel PI V3.
- Actor từng học 512 transition/496 critic updates ở pilot V3 trước đó;
  **lượt ablation này không train, không cập nhật trọng số/optimizer**.
- Common-only vẫn có yaw từ follower. Mask thay đổi feedback/history và
  common output tương lai; không phải giữ nguyên trajectory common rồi
  tách một nguyên nhân độc lập từ exact-state branching.

Root: `/home/tuanmac/nino_research/sim_axis_ablation_v1/20261105T033454594138Z_sim-axis-ablation`.
Checkpoint: `sim_guided_td3_v3/20261105T022329071579Z_sim-v3-train`.
Manifest checkpoint SHA256:
`8cc9cbeafeea220074638185535d7a23d6a84156424b2e2a8f656414c6e71578`.

## 2. Kết quả primary: toàn task 14 giây

**[N — mô phỏng]** Không lấy cửa sổ có lợi hơn để thay metric toàn task.

| Arm / lượt theo arm | RMSE path, mm | RMSE v nominal, m/s | Max path, mm | Marker + stop | Gate kỹ thuật đề xuất |
|---|---:|---:|---:|---|---|
| B0 / 1 | 0,101 | 0,005294 | 0,144 | Đạt | Đạt |
| Full / 1 | 12,111 | 0,005806 | 18,445 | Đạt | Đạt |
| Common-only / 1 | 0,518 | 0,006010 | 0,807 | Đạt | Đạt |
| Common-only / 2 | 0,030 | 0,006364 | 0,043 | Đạt | Đạt |
| Full / 2 | 12,138 | 0,006026 | 18,515 | Đạt | Đạt |
| B0 / 2 | 0,110 | 0,004961 | 0,167 | Đạt | Đạt |

Gate kỹ thuật giữ max path 40 mm, max estimate position error 50 mm,
yaw 0,05 rad và marker/quiet stop; không là yêu cầu nhà máy được chấp nhận.
Marker 0,95 m không phải arrival goal 3 m hoặc navigation hoàn chỉnh.
6/6 đạt gate chỉ cho biết feasibility; không đồng nghĩa learning hữu ích.

**[S]** Mask differential loại phần lớn steering degradation trong batch này.
Full có accepted policy yaw contribution trung bình pha source khoảng
−0,01415..−0,01442 rad/s; common-only khoảng −0,00000168..+0,00000002.
Giá trị common-only không bắt buộc bằng zero sau projection vì state và
shaping của hai bánh có thể khác. Yaw follower vẫn hoạt động.

Common-only có một lượt path RMSE thấp hơn B0 và một lượt cao hơn; không
kết luận nó tốt hơn B0 về path. **Cả hai common-only có RMSE v toàn lượt
cao hơn cả hai B0.** Chưa có CI/power hoặc minimum effect được chấp nhận;
hai fresh launches không là hai seed huấn luyện hoặc exact-state pair.

## 3. Diagnostic sau kết quả: vì sao common-only vẫn tệ hơn về v?

**[N — mô phỏng]** Phân chia bằng source và nominal shaped reference đã ghi:
ramp 0,6–2,5 s; steady 2,6–8,0 s; deceleration 8,1–10,0 s; post-stop
10,1–14,0 s. Đây là timestamp cuối tick; không là phép đo latency mới.
Giữ whole-task primary; phase analysis chỉ tìm cơ chế cho protocol sau.

| Arm | Steady RMSE v, m/s | Bias body − nominal steady, m/s | Deceleration RMSE v, m/s |
|---|---:|---:|---:|
| B0 | 0,005282–0,005762 | −0,005097..−0,004727 | 0,006069–0,006748 |
| Full | 0,002654–0,002663 | +0,001201..+0,001386 | 0,012367–0,012968 |
| Common-only | 0,003099–0,003201 | +0,001977..+0,002032 | 0,013030–0,013851 |

Common-only cộng accepted common khoảng **0,00726–0,00741 m/s** khi steady.
Khoảng **67,1–67,7%** tổng squared velocity error của nó nằm ở deceleration,
so B0 khoảng 21,4–23,2%. Không gọi tỷ lệ này là phần chắc chắn ngăn được.

**[N — source]** `VelocityReferenceController` trong
`src/nino_control/nino_control/residual_velocity.py` tính cả projected
baseline và total từ **cùng previous accepted reference**; sau đó previous
được cập nhật bằng total. Baseline zero chặn residual tạo locomotion mới,
nhưng reference vẫn hạ theo ramp. Vì vậy accepted policy delta có thể bằng
zero trong deceleration dù trạng thái ramp còn mang phần tốc độ cộng trước.
Không diễn giải delta=0 là can thiệp trước đó đã hết tác dụng.

**[S]** Dữ liệu phù hợp cơ chế boost steady → reference cao hơn khi bắt đầu
stop → tốn thêm thời gian giảm tốc dưới cùng acceleration bound. Chưa có
counterfactual state restore để quy toàn bộ chênh lệch body cho một nguyên
nhân. Không thể ép ngay xuống nominal nếu việc đó vi phạm giới hạn ramp.

## 4. Integrity và ngữ nghĩa action

**[N — artifact/software]** Audit đọc lại:

- **91 file** trong manifest ablation khớp SHA256; **53 file** của checkpoint
  frozen vẫn khớp manifest đã pin. Không có checkpoint mới.
- **1.740 world-control requests**: ACK/completion và iteration/clock delta
  đúng số physics steps 1 ms; retry 0. **12 parameter readbacks** hoàn tất.
- **840 trace rows**: actor raw / controller proposal / environment proposal
  / projection được phân biệt và kiểm khớp. B0 không gọi actor; bốn lượt
  full/common tổng **560 actor calls**.
- **4.200 estimator updates**: gyro stamp, wheel support stamp, dt/age và
  monotonic receipt causal; không dùng GT làm input guidance/actor.
- Không xuất replay để học từ masked action; `training_dataset_compatible=false`.
  Reward inherited nhận proposal sau mask; return không dùng chọn arm.
- Counts/hash/gap không chứng minh continuous coverage, loss-free hoặc
  timing hardware. GT 50 Hz không cho phép bịa timing body nhỏ hơn 20 ms.

**Giới hạn lifecycle:** outer exec trả 143 sau event `completed`; job.json
và manifest đã đóng `completed`, có đủ sáu trace/summary. Không tuyên bố
outer process đã exit 0. Giữ ghi chú này trong verification; không chạy lại
batch. Kiểm tra cuối không còn process sim thuộc workflow.

Regression liên quan: **74 sim/control tests + 14 GUI tests đạt**. Đây là
kiểm phần mềm; sáu launches mới là số lượt sim. GUI native Qt hiển thị bảng
sáu lượt, phase diagnostic, khóa batch đã dùng và giữ các profile lịch sử.
Build/cài đặt/source snapshot được ghi trong
[verification](NINO_SIM_AXIS_ABLATION_VERIFICATION_2026-11-05.json).

Raw audit và figure:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_axis_ablation_2026-11-05/`.
`analysis.json`, `analyze_ablation.py`, `axis_ablation_trace.png` và GUI screenshot
giữ độc lập với manifest raw đã khóa.

## 5. Quyết định và bước tiếp

1. **Giữ guided B0 clear.** Không promote full hoặc common-only; không tăng
   train/history/PPO để xử lý một lỗi đã có cơ chế cổ điển cần đối chứng.
2. **Tạm bỏ learned differential khỏi ứng viên tiếp**, giữ yaw follower.
   Đây là định hướng contract mới, không sửa checkpoint/ABI cũ.
3. **[Đ]** Chuẩn bị [đối chứng bù common có lịch rút trước dừng](NINO_SIM_CLASSICAL_COMMON_NEXT_PROTOCOL_2026-11-05.md) trên clear,
   tối đa sáu launches theo protocol mới; **chưa chạy**. So fixed compensation
   với B0 và frozen common-only trước khi quyết định có residual learning
   gap thật sự hay không. Preview lịch dừng không là preview vật cản.
4. Contact benefit vẫn **unknown**: B0 gờ outlier trong pilot V3 được giữ.
   Không lấy ablation clear để suy ra chất lượng qua gờ, slip, dây mềm,
   generalization hoặc sim-to-real. Hardware residual authority vẫn 0.

**Một việc tiếp theo:** hiện thực hóa đối chứng common cổ điển có planned-stop
withdrawal, kiểm contract offline rồi chạy đúng batch mới nếu được tiếp tục.
Đổi khuyến nghị nếu nó không cải thiện whole-task tracking hoặc lỗi path/stop
vẫn còn: giữ B0, khoanh model/actuator trước khi mở một learner khác.
