> **Cập nhật triển khai:** backend/context và parity gain=1 đã kiểm offline; xem [kết quả](NINO_SIM_GAIN_CONTEXT_OFFLINE_RESULT_2026-11-06.md). Chưa qualification Gazebo, runner physics/release hoặc learner mới. Các đoạn mô tả “chưa nối” dưới đây giữ lịch sử tại lúc chốt thiết kế.

# Quyết định benchmark Sim — baseline trước learner

06/11/2026 · Chốt thiết kế offline sau eval reset-ready 6/6.

## 1. Quyết định hiện tại

**Giữ cổ điển cho clear known-stop; không mở rộng checkpoint A theo mặc định.**
Primary vẫn là whole-14s native body velocity RMSE; GT20ms và dịch +10ms
báo riêng. Path RMSE ≤40 mm, marker và đứng yên liên tục 2 s trong horizon
14 s là constraints nghiên cứu kế thừa, không phải yêu cầu nhà máy được
chấp nhận. Rule hiệu ứng tương đối 5% vẫn là đề xuất nghiên cứu.

[Kết quả đã seal](NINO_SIM_READY_EVAL_ONLY_RESULT_2026-11-06.md): cổ điển
có velocity RMSE thấp hơn A/B0 ở stop 6/8 s trên cả ba grids; path RMSE
không đồng thời tốt hơn. Một seed/run mỗi condition chưa cho kết luận chung
về TD3. Không chọn lại primary để thay đổi kết quả đã công bố.

## 2. Quyền tác động thực sự trong contract đã chạy

Phân tích lại **840 hàng đã ghi**, không tạo transition hay simulation mới;
RMSE tính từ error từng hàng khớp primary gốc. Clock là thời điểm quyết định,
khác thời điểm body response cuối interval.

| Arm | Stop | Window mở | Tick mở / tổng | Error² khi mở / toàn lượt |
|---|---:|---|---:|---:|
| B0 | 6 s | 2,5–5,4 s | 30/140 | 43,27% |
| A seed11 | 6 s | 2,5–5,4 s | 30/140 | 67,74% |
| Cổ điển | 6 s | 2,5–5,4 s | 30/140 | 10,28% |
| Cổ điển | 8 s | 2,5–7,4 s | 50/140 | 11,36% |
| A seed11 | 8 s | 2,5–7,4 s | 50/140 | 70,38% |
| B0 | 8 s | 2,5–7,4 s | 50/140 | 42,85% |

**[N-sim]** Gate đóng khi nominal chưa steady và trước lịch dừng. Với cổ
điển, khoảng 89% error² quan sát nằm ở các tick window đóng.
**[S]** History dài hơn không tự tạo quyền tác động vào các phase bị gate
chặn. Đây là phân rã trajectory, **không là trần lợi ích/counterfactual**:
action trước đó vẫn có thể ảnh hưởng outcome sau khi window đóng.

## 3. Chọn đúng một câu hỏi tiếp theo

**[Đ] Gain common reference→drive cố định trong mỗi run nhưng controller
không biết trước:** baseline causal dùng encoder có thể bù được không?
Chưa đưa delay, contact, payload hay randomization nhiều yếu tố vào cùng bài.
Đây là stress test của mô phỏng, **không phải tham số motor thật đã nhận dạng**.

- Development đề xuất: gain **0,98 / 1 / 1,02**, stop **8 s**, clear-box,
  nominal **0,2 m/s**, common **±0,005 m/s**, 10 Hz, history5/103D→1D.
- ±2% được chọn bằng quyền tác động đại số, không từ SysID Nino. Với mô
  hình lý tưởng `y=g*(u+delta)`, bù cần thiết là +0,004082 / 0 / −0,003922
  m/s. Gain có thể bù zero error trong mô hình này nằm khoảng
  **[0,975610; 1,025641]**. Không chuyển kết quả này thành feasibility Gazebo.
- B0, fixed Classical_scheduled và **Causal_gain_candidate** dùng cùng
  observation, window, projection, geometry và giới hạn. Injected gain,
  GT/contact/caster và identity condition không vào controller.
- Candidate chỉ đọc 103D: median tỷ lệ vận tốc bánh quy đổi bằng geometry
  danh nghĩa / reference trước đó trong history; nghịch đảo gain ước lượng
  rồi chặn common. Reference thay đổi/nhỏ hoặc estimate ngoài dải thì request
  zero; gate/stop/ownership vẫn có quyền quyết định thực thi.

**Tự phản biện:** static gain có lời giải cổ điển đơn giản; không đủ tạo
lý do nghiên cứu TD3. Wheel proxy có thể sai do slip, geometry và độ trễ;
reference đều không chứng minh bánh/body đã steady. Timestamp trong history
chưa là phép đồng bộ target–encoder chính xác. Candidate có thể thất bại
khi lag/noise/caster tạo bias. Chưa nên thêm lag vào bài chỉ để RL có chỗ thắng.

## 4. Đã làm gì và chưa làm gì?

**Đã kiểm offline:** candidate dùng cùng 103D, mô hình static lý tưởng trả
đúng nominal cho ba gain; bounded/fallback/input-invalid và integrity có
17 software tests. Đã sinh shadow request trên sáu trace cũ; shadow không
phải rollout của candidate và **không có RMSE controller mới**. Không load
actor, optimizer hoặc chạy physics/hardware.

**Chưa triển khai vào Gazebo:** phép inject gain, telemetry effective-drive,
context identity và validator mới. Cùng kích thước 103D/1D không cho phép
resume checkpoint cũ. Không thay controller/sensor source đã tạo các artifact
frozen. [Draft qualification](NINO_SIM_GAIN_BASELINE_QUALIFICATION_DRAFT_2026-11-06.md)
đề xuất tối đa 9 launches/1.260 ticks, **chưa release/chạy**, không train TD3.

## 5. Điểm dừng và hướng đi

1. **Ngay sau bản chốt này:** xây backend/context riêng và gain=1 parity
   offline; không đổi frozen backend hoặc nới limits để qua gate.
2. Chỉ khi parity/measurement đạt mới xem xét baseline qualification theo
   draft riêng. Failure/STOP/missing giữ lại, không loại hoặc vá metric.
3. Nếu causal/fixed classical xử lý được nhu cầu: dùng cổ điển và dừng
   learning cho envelope này. Nếu không: chưa tự kết luận RL cần thiết;
   phải tách thiếu authority, observability, model và tuning trước.
4. Chỉ mở fresh learner khi có khoảng trống và cơ chế có thể bác bỏ; cần
   protocol/budget, independent train seeds và holdout mới. Các giá trị này
   hiện chưa được cấp. Không resume C partial hoặc tăng history theo mặc định.

**Artifact:** `~/nino_research/sim_benchmark_decision_v1/decision_2026_11_06_verified/`
chứa spec, decision, sáu shadow files và manifest. Bản dẫn xuất trước đó giữ
riêng; bản verified bổ sung kiểm config/summary/source khi GUI đọc. Raw eval
và checkpoint không bị sửa. Real cutoff giữ 02/11/2026.
