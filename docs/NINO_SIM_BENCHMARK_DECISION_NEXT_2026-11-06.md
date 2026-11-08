> **Đã hoàn thành phần chốt offline:** xem [quyết định](NINO_SIM_BENCHMARK_DECISION_2026-11-06.md) và [draft baseline qualification](NINO_SIM_GAIN_BASELINE_QUALIFICATION_DRAFT_2026-11-06.md). Không có training/physics mới. Nội dung dưới là đề xuất trước khi chốt.

# Bước Sim tiếp theo: chốt câu hỏi trước khi train thêm

06/11/2026 · Đề xuất thiết kế offline; **chưa release training/physics mới**.

## Vì sao đổi ưu tiên?

[Eval-only reset-ready](NINO_SIM_READY_EVAL_ONLY_RESULT_2026-11-06.md) hoàn tất
6/6: A seed11 bù âm gần giới hạn và velocity RMSE cao hơn B0/cổ điển trên
cả ba grids. Bài clear known-stop có giải pháp cổ điển đơn giản đang tốt
hơn. Không có cơ sở mặc định train dài hơn trên cùng bài chỉ vì pipeline chạy.

Điều này không bác bỏ TD3 nói chung. A mới có 1.024 training transitions,
coverage lệch; C chưa hoàn tất. Câu hỏi coverage A/C vẫn chưa được trả lời,
nhưng không tự mở lại C hoặc suy rằng probe chắc chắn sửa được policy.

## Outline có đầu ra và điểm dừng

| Bước | Việc cụ thể | Artifact | Qua / dừng / unknown |
|---|---|---|---|
| 1 · Offline | Chốt primary, tracking/time constraints và mức cải thiện nghiên cứu tối thiểu; giữ kết quả clear known-stop làm reference | Benchmark decision record: mục tiêu, envelope, baseline, claim và điều kiện bác bỏ | Nếu nhu cầu chỉ là tracking clear known-stop: dùng cổ điển, dừng nhánh learned correction cho envelope này |
| 2 · Offline | Chọn **một** câu hỏi có cơ chế: thích nghi với actuator delay/gain thay đổi là giả thuyết Sim; hoặc contact còn useful authority theo audit cũ. Không gộp hai câu hỏi thành mixed curriculum | Một protocol, train/tune/test split, baseline mạnh, thông tin actor được phép dùng, giới hạn tổng budget | Không xác định được phase/action có thể đổi outcome hoặc baseline chưa công bằng: dừng thiết kế, chưa train |
| 3 · Có điều kiện | Nếu chọn delay/gain: so cả baseline shaping/compensation thích hợp, pin tham số và giữ tổ hợp holdout riêng; stress ranges phải ghi là giả định Sim khi chưa có SysID thật | Protocol qualification baseline/authority trước learner; ngưỡng/conditions/repeats có lý do | Baseline đáp ứng mục tiêu: chọn tích hợp cổ điển. Authority/measurement chưa đạt: unknown, không dùng RL che lỗi |
| 4 · Sau protocol riêng | Chỉ khi còn khoảng trống đáng quan tâm mới chọn learner hoặc coverage study mới, với fresh learners cùng reset backend, budgets và evaluator | Ablation hợp lệ: TD3/B0/cổ điển, history chỉ khi delay cần; save replay/checkpoint/identity | Lợi ích không rõ hoặc sampling-sensitive: giữ unknown/no-go, không tự thêm sample, tăng history hoặc đổi objective |

## Điều giữ nguyên

- Không cần real dataset để thiết kế/kiểm một giả thuyết **trong sim**; thiếu
  dữ liệu thật giới hạn calibration, stress ranges và mọi claim sim-to-real.
- B0, cổ điển và actor phải dùng cùng preview/window/projection/reset,
  command ownership và constraints. Không nới common scale riêng cho TD3.
- Mọi correction/reset/physics/reward mới có version riêng, không sửa frozen
  modules hoặc tái dùng ngân sách các study đóng.
- Không thay bài đơn giản bằng bài phức tạp chỉ để tạo chỗ cho RL. Chọn bài
  theo nhu cầu robot và cơ chế, rồi mới chọn thuật toán.

**Artifact nên làm ngay:** benchmark decision record 1–2 trang từ kết quả đã
có, chọn clear known-stop dùng cổ điển hay một câu hỏi mới có thể bác bỏ.
Chỉ đổi khuyến nghị mở learner khi protocol chỉ ra khoảng trống baseline,
useful authority và cách kiểm bằng một budget có điểm dừng. Chưa có con số
train, dải delay/gain hoặc yêu cầu nhà máy nào được chấp nhận từ văn bản này.
