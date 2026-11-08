# Sim V3 — estimator + follower trong Gazebo, residual zero

Review **05/11/2026**; batch chạy **04/11/2026**. Nguồn Nino mô phỏng,
không có dữ liệu thật mới. [Protocol trước chạy](NINO_SIM_GUIDED_BASELINE_V3_PROTOCOL_2026-11-04.md).

## Quyết định

**Giữ estimator + follower làm baseline ứng viên cho nhánh sim.** Cả tám
lượt đạt marker tiến độ và dừng; bốn lượt guided qua các gate engineering
đề xuất trước chạy. Chưa train thêm TD3, chưa promote checkpoint V2.

Bước tiếp có giá trị thông tin cao nhất là **screen baseline guided trên
sàn sạch/gờ cứng 6 mm**, giữ residual zero, kiểm drift khi tiếp xúc trước
khi mở learning dưới reference mới. Không cần chờ real dataset cho việc này.
[Thiết kế bước sau và contract TD3 V3](NINO_SIM_V3_NEXT_DESIGN_2026-11-05.md).

## Luồng đã chạy

```text
Joint drive speeds + gyro-Z, source stamps
  → estimator planar causal (wheel support stamp ≤ gyro stamp)
  → estimated pose có source/frame/clock/epoch
  → path follower → baseline (v, omega)
  → residual proposal [0, 0] + history/projection/ramp
  → velocity reference → wheel PI xuất torque → Nino/caster trong Gazebo

GT + caster/contact → reset settling / evaluator / audit riêng
```

Initial estimate `[0,0,0]` là metadata scenario tại task epoch, không đọc
pose thật sau settling hoặc căn chỉnh GT sau kết quả. Actor không nhận pose.
Nhận dạng thực, gyro bias/noise, slip robustness và deployment chưa được xác minh.

## Điều kiện và bảng kết quả

Clear solid-box factory hall, Nino URDF/caster và PI cũ. Robot yaw 0;
tuyến dài 3 m xoay ±5°. Policy/scoring 100 ms, physics 1 ms, cruise
0,2 m/s; source zero 0–0,5 s và từ 8 s; task kết thúc ở 14 s. Tất cả
action residual bằng zero, không actor/checkpoint/optimizer được nạp.

**RMSE tính trên toàn task 14 s, gồm pha dừng.** Thứ tự bảng là thứ tự chạy.

| Arm | Bearing | Lặp | RMSE cross-track (mm) | Max cross-track (mm) | Max error estimate position (mm) | Max error estimate yaw (rad) | Marker + stop |
|---|---:|---:|---:|---:|---:|---:|---|
| Constant | +5° | 1 | 93,182 | 127,869 | 4,358 | 0,000136 | Đạt |
| Guided | −5° | 1 | 13,327 | 28,745 | 2,758 | 0,002133 | Đạt |
| Guided | +5° | 1 | 13,841 | 30,328 | 2,738 | 0,001272 | Đạt |
| Constant | −5° | 1 | 93,652 | 128,611 | 2,803 | 0,000703 | Đạt |
| Constant | −5° | 2 | 93,326 | 128,100 | 2,910 | 0,000170 | Đạt |
| Guided | +5° | 2 | 13,696 | 30,209 | 5,419 | 0,000690 | Đạt |
| Guided | −5° | 2 | 13,088 | 28,792 | 2,799 | 0,001388 | Đạt |
| Constant | +5° | 2 | 93,058 | 127,650 | 3,283 | 0,000431 | Đạt |

- Guided max cross-track 28,74–30,33 mm, dưới bound đề xuất 40 mm.
- Guided max error position 2,74–5,42 mm, yaw 0,00069–0,00213 rad,
  dưới các bound đề xuất 50 mm / 0,05 rad. Đây là so sánh estimate mới nhất
  với GT tại boundary evaluator: estimate có thể cũ đến **14 ms**. Không
  gọi các số này là calibration accuracy hoặc sai số cùng source timestamp.
- Body v RMSE so với nominal shaped reference: constant 0,00478–0,00501 m/s,
  guided 0,00530–0,00541 m/s. Yaw-rate RMSE guided 0,01865–0,01925 rad/s;
  constant 0,000083–0,000332 rad/s do reference yaw của constant luôn zero.
  Hai arm yêu cầu chuyển động khác nhau; không lấy con số yaw này để kết
  luận follower có controller tracking tệ hơn trong cùng nhiệm vụ.
- Cả tám lượt progress dọc tuyến cuối 1,460–1,464 m; quiet liên tục cuối
  4,0–4,1 s. **Marker ≥0,95 m không là arrival tại goal 3 m.**
- Ở từng bearing, RMSE guided lớn nhất thấp hơn RMSE constant nhỏ nhất.
  Đây là separation mô tả, không là CI/power test hoặc learned benefit.

Constant straight không có feedback tuyến nên lệch khỏi tuyến đã xoay là
kết quả dự kiến. So sánh này xác minh việc nối guidance; khi đánh giá TD3,
đối chứng chính phải là **guided baseline giống hệt, residual zero**.

## Kiểm dữ liệu và vòng đời

Artifact:
`/home/tuanmac/nino_research/sim_guided_baseline_v3/20261104T094119923673Z_sim-v3-baselines`.
Batch đã đóng, không tự chạy lại slot.

| Kiểm | Kết quả |
|---|---|
| Rollout / control transitions | 8/8 × 140 = 1.120 |
| Manifest | 115/115 file khớp SHA256 |
| Physics requests | 2.320/2.320 ACK/completed; đúng iteration + sim-clock delta; retry 0 |
| Read-only parameter calls | 16/16 completed |
| Estimator updates | 5.600, kiểm đủ support stamp, dt, age và receipt monotonic |
| Nạp actor / optimizer / hardware actions | 0 / 0 / 0 |
| Guidance faults / nonzero residual proposals | 0 / 0 |

Manifest SHA256:
`40b3e3bb0aa73680c1b1b0996afb51ae649704f8cbd4b1be886eef8d5a0909ed`.

Trong mỗi task: 700 IMU, 700 GT và 700 estimator updates; source gap lớn
nhất IMU/GT 20 ms, wheel 3–4 ms, drive 20–21 ms. Source age lớn nhất tại
boundary khoảng 19 ms. Các gap drive lớn hơn trong summary toàn episode
thuộc startup ngoài task; không loại mẫu hoặc vá bằng kênh khác. Counts,
gaps và closure không tự chứng minh continuous coverage theo một contract
98% cũ; batch này dùng các rule causal/freshness đã nêu trong protocol V3.

5.600 update đều chỉ dùng wheel stamp ≤ gyro stamp; gyro dt và wheel
support age không vượt 40 ms; callback receipt của input có trước lúc ghi
update. Kiểm trace zero residual và typed estimator API chỉ nhận hai nguồn
wheel/IMU bổ sung cho review source. Không lấy riêng cờ `truth_input=false`
làm bằng chứng duy nhất về không rò rỉ GT.

## Giới hạn và điểm dừng

1. Hai fresh launches mỗi điều kiện là mẫu mô tả nhỏ, không exact-state
   branching hoặc nhiều training seeds. Seed wrapper không chứng minh mọi
   nguồn ngẫu nhiên trong Gazebo đã được kiểm soát.
2. Chỉ clear floor và heading error ±5° tương đối tuyến. Chưa có kết quả
   guided qua gờ, drift khi trượt, dây mềm/rãnh/hõm hoặc full navigation.
3. Hệ thống dùng geometry danh nghĩa, bias gyro bằng zero và điều kiện sensor
   mô phỏng. Không suy ra wheel odometry là reference thân độc lập trên robot.
4. Observation 100D không đổi nhưng reference distribution/baseline identity
   đã đổi. Checkpoint V2 không được resume hoặc promote theo ABI đơn thuần.
5. Bound 40 mm/50 mm/0,05 rad là gate engineering của screen, chưa là mức
   chất lượng ứng dụng được người dùng chấp nhận hoặc đảm bảo an toàn.

Kiểm chứng phần mềm/install/GUI được ghi riêng ở
[verification](NINO_SIM_GUIDED_BASELINE_V3_VERIFICATION_2026-11-05.json).
Raw, analysis, plot và screenshot giữ tại
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_guided_baseline_v3_2026-11-04`.

## GUI và việc ngay sau

**Xây project → NHÁNH SIM → V3 · estimator + follower Gazebo** hiển thị
tám lượt, metric có đơn vị, marker/stop và gate ứng viên; stage đã đóng
không cho chạy lại. V1/V2/clear-bias vẫn xem được như lịch sử riêng.

**Một việc tiếp theo:** chốt và chạy screen guided clear/gờ 6 mm theo
[thiết kế kế tiếp](NINO_SIM_V3_NEXT_DESIGN_2026-11-05.md). Nếu estimate drift
hoặc baseline không hoàn thành stop/tracking dưới tiếp xúc, ưu tiên sửa
nguyên nhân đó hoặc thu hẹp envelope; không dùng thêm TD3/history để che lỗi.
