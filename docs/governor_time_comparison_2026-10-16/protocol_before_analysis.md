# Governor so với PI tốc độ cố định — đối chứng thời gian

## Protocol ghi trước simulation

Tiếp tục từ [repeatability](CONTACT_REPEATABILITY_TIMING_2026-10-16.md).
Deep Research yêu cầu tách lợi ích thích nghi khỏi việc đơn thuần đi chậm;
giữ H2 trước predictor/H1. Không đổi governor hoặc tìm lại reward/threshold.

### Hai nhánh cố định, 10 episode

- Sensor governor: nguyên candidate Moderate 0.85, cruise 0.400 m/s, cùng
  detector/observations/hold/release/ramp 0.4/s; không oracle input.
- Constant PI: governor profile `full` (scale luôn 1), cruise **0.388 m/s**.
  Tên `full` trong raw là transparent governor, không có nghĩa cruise 0.400.
- Ước lượng tốc độ tham chiếu từ batch development trước:
  `0.4 × 16.72 / 17.24 = 0.387935 m/s`, làm tròn 0.388. Đây **chưa phải**
  time match đã đo. Profile 0.394 cũ được giữ nguyên, không dùng trong batch.
- 5 cold-start blocks seeds **76500–76504**, hai controller mỗi block;
  thứ tự lấy RNG seed **76550**, lưu plan trước khi launch. Đây là các lượt
  development mới, không gọi unseen terrain hoặc final test.
- World capsule/nền hộp, geometry, physics 1 ms, PI/robot/reset/damping,
  native physical scoring và dừng 2 s giữ nguyên. Khác biệt cố ý chỉ là
  governor profile và cruise của nhánh PI tham chiếu.

### Đọc kết quả và điểm dừng

1. Báo đủ native arrivals/failures/unavailable/stopping; không thay đổi gate.
2. Báo thời gian trung bình/range và từng block. Chỉ gọi **gần khớp thời gian**
   nếu chênh mean ≤2% (khoảng 0.34 s tại 17 s). Đây là dải so sánh exploratory
   được chọn trước chạy, không phải chuẩn ngành hoặc tolerance triển khai.
   Nếu vượt dải, ghi chưa khớp và **không tự quét tốc độ trên cùng bank**.
3. Cùng cửa sổ event first+0.05 → body qua x=3.40 m, thêm whole-route RMS,
   sampled peak, slip²/m, path RMSE, timing/actual wheel response/contact.
   Không gọi slip²/m là J; không gán missing contact/impact bằng 0.
4. Approach speed cố ý khác. First impact/prefix chỉ là mô tả, **không phải
   negative control của hai điều kiện tiếp cận tương đương**.
5. Không loại cold starts theo caster state/impact; không giả restore được
   engine/contact snapshot. Unit là episode/block, không phải sensor frame.
6. Nếu không có trade-off chất lượng tốt hơn PI gần cùng thời gian, **không
   mở predictor/PPO/Optuna**, không thêm correction phỏng đoán. Giữ PI/reactive
   reference và ra no-go cho việc phát triển predictive trong envelope này.
   Nếu có tín hiệu nhất quán, chỉ cân nhắc bước feasibility tiếp theo; một
   cáp/một speed không đủ chứng minh H1/generalization hay sim-to-real.
7. **Dừng sau 10 episode**, giữ mọi dữ liệu. Không lặp lại để tìm một winner.

## Trạng thái

Protocol đã ghi; kết quả sẽ được bổ sung sau batch. Chưa khẳng định time match.
